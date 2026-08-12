"""Tests for real entitlement enforcement and real payment gating (spec
§64, PLAT-19).

Two requirements are covered here. "Use entitlement service. Do not
hard-code plan checks across UI." — every org starts on Starter and
Starter's limits are really enforced. And the billing rules themselves:
Growth/Business are reachable only by completing a Stripe Checkout that a
signature-verified webhook confirms, Enterprise is never self-serve, and
a lapsed Starter trial locks premium functionality without destroying the
organization or its data.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

WEBHOOK_SECRET = "whsec_test_secret"


async def _expire_trial(
    db_session: AsyncSession, organization_id: uuid.UUID, *, days_ago: int
) -> None:
    """Backdate the trial rather than waiting 14 days. Uses the test's own
    session, since the client's get_db is overridden to the same one."""
    from app.billing.models import Subscription

    subscription = (
        await db_session.execute(
            select(Subscription).where(Subscription.organization_id == organization_id)
        )
    ).scalar_one()
    subscription.trial_ends_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    await db_session.flush()


@pytest.fixture(autouse=True)
def _webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the signing secret is set. STRIPE_SECRET_KEY stays unset on
    purpose, so nothing in this suite can make an outbound Stripe call —
    the tests that need a paid plan get there through the webhook, which
    is how production gets there too."""
    from app.config import settings

    monkeypatch.setattr(settings, "stripe_webhook_secret", WEBHOOK_SECRET)


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Billing Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


def _signed_headers(payload: bytes, *, secret: str = WEBHOOK_SECRET, timestamp: int | None = None):
    """Build a genuine Stripe-Signature header, so the webhook tests
    exercise the real verification path rather than stubbing past it."""
    ts = timestamp if timestamp is not None else int(time.time())
    digest = hmac.new(
        secret.encode(), msg=f"{ts}.".encode() + payload, digestmod=hashlib.sha256
    ).hexdigest()
    return {"Stripe-Signature": f"t={ts},v1={digest}"}


async def _activate_paid_plan(
    client: AsyncClient, organization_id: uuid.UUID, plan_key: str
) -> None:
    """Drive a real checkout.session.completed through the real endpoint —
    the only path in the system that grants a paid plan."""
    event = {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_{uuid.uuid4().hex}",
                "subscription": f"sub_{uuid.uuid4().hex}",
                "customer": f"cus_{uuid.uuid4().hex}",
                "metadata": {
                    "organization_id": str(organization_id),
                    "plan_key": plan_key,
                },
            }
        },
    }
    payload = json.dumps(event).encode()
    response = await client.post(
        "/api/v1/billing/webhook", content=payload, headers=_signed_headers(payload)
    )
    assert response.status_code == 200, response.text


async def test_list_plans_returns_all_four_seeded_plans(client: AsyncClient) -> None:
    await _signup(client, "billing1@example.com", "Billing Org 1")
    response = await client.get("/api/v1/billing/plans")
    assert response.status_code == 200
    keys = {p["key"] for p in response.json()}
    assert keys == {"starter", "growth", "business", "enterprise"}


async def test_new_organization_starts_on_starter(client: AsyncClient) -> None:
    await _signup(client, "billing2@example.com", "Billing Org 2")
    response = await client.get("/api/v1/billing/current")
    assert response.status_code == 200
    body = response.json()
    assert body["plan_key"] == "starter"
    assert body["entitlements"]["sso_enabled"] is False
    assert body["current_users"] == 1


async def test_new_organization_starts_a_14_day_trial(client: AsyncClient) -> None:
    await _signup(client, "billing-trial@example.com", "Billing Trial Org")
    body = (await client.get("/api/v1/billing/current")).json()
    subscription = body["subscription"]
    assert subscription["status"] == "trialing"
    assert subscription["access_state"] == "trialing"
    assert subscription["trial_days_remaining"] in (13, 14)
    # No card was taken, so there is no Stripe customer yet.
    assert subscription["has_payment_method"] is False


async def test_paid_plans_cannot_be_self_assigned_without_paying(client: AsyncClient) -> None:
    """The regression this whole feature exists to prevent: before billing,
    an org_admin could PUT any plan_key and receive it for free."""
    await _signup(client, "billing3@example.com", "Billing Org 3")

    for plan_key in ("growth", "business"):
        response = await client.put("/api/v1/billing/current", json={"plan_key": plan_key})
        assert response.status_code == 402, plan_key

    # And the org is still on Starter — the refusal is not cosmetic.
    body = (await client.get("/api/v1/billing/current")).json()
    assert body["plan_key"] == "starter"
    assert body["entitlements"]["sso_enabled"] is False


async def test_enterprise_cannot_be_self_assigned(client: AsyncClient) -> None:
    await _signup(client, "billing-ent@example.com", "Billing Enterprise Org")
    response = await client.put("/api/v1/billing/current", json={"plan_key": "enterprise"})
    assert response.status_code == 402
    assert "sales" in response.json()["error"]["message"].lower()


async def test_completed_checkout_webhook_activates_the_paid_plan(client: AsyncClient) -> None:
    organization_id = await _signup(client, "billing-paid@example.com", "Billing Paid Org")
    await _activate_paid_plan(client, organization_id, "growth")

    body = (await client.get("/api/v1/billing/current")).json()
    assert body["plan_key"] == "growth"
    assert body["entitlements"]["sso_enabled"] is True
    assert body["subscription"]["status"] == "active"
    # Paying ends the trial outright; a leftover trial_ends_at would later
    # lock a paying customer out.
    assert body["subscription"]["trial_ends_at"] is None


async def test_webhook_rejects_an_invalid_signature(client: AsyncClient) -> None:
    organization_id = await _signup(client, "billing-forge@example.com", "Billing Forge Org")
    event = {
        "id": "evt_forged",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "subscription": "sub_forged",
                "metadata": {
                    "organization_id": str(organization_id),
                    "plan_key": "business",
                },
            }
        },
    }
    payload = json.dumps(event).encode()

    # A correctly-shaped header signed with the wrong secret.
    forged = _signed_headers(payload, secret="whsec_wrong_secret")
    assert (
        await client.post("/api/v1/billing/webhook", content=payload, headers=forged)
    ).status_code == 400
    # And no header at all.
    assert (
        await client.post("/api/v1/billing/webhook", content=payload)
    ).status_code == 400

    body = (await client.get("/api/v1/billing/current")).json()
    assert body["plan_key"] == "starter"


async def test_webhook_rejects_a_stale_timestamp(client: AsyncClient) -> None:
    """A valid signature captured off the wire must not be replayable
    indefinitely."""
    organization_id = await _signup(client, "billing-replay@example.com", "Billing Replay Org")
    event = {
        "id": "evt_stale",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "subscription": "sub_stale",
                "metadata": {
                    "organization_id": str(organization_id),
                    "plan_key": "business",
                },
            }
        },
    }
    payload = json.dumps(event).encode()
    stale = _signed_headers(payload, timestamp=int(time.time()) - 3600)

    response = await client.post("/api/v1/billing/webhook", content=payload, headers=stale)
    assert response.status_code == 400
    assert (await client.get("/api/v1/billing/current")).json()["plan_key"] == "starter"


async def test_replayed_webhook_event_is_a_no_op(client: AsyncClient) -> None:
    """Stripe retries on any non-2xx and can deliver twice regardless."""
    organization_id = await _signup(client, "billing-dupe@example.com", "Billing Dupe Org")
    event = {
        "id": "evt_duplicate_delivery",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "subscription": "sub_dupe",
                "metadata": {
                    "organization_id": str(organization_id),
                    "plan_key": "growth",
                },
            }
        },
    }
    payload = json.dumps(event).encode()

    first = await client.post(
        "/api/v1/billing/webhook", content=payload, headers=_signed_headers(payload)
    )
    assert first.json()["status"] == "activated:growth"

    second = await client.post(
        "/api/v1/billing/webhook", content=payload, headers=_signed_headers(payload)
    )
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"


async def test_expired_trial_locks_premium_features_but_keeps_the_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The core of the lock behaviour the product promises: functionality
    stops, the organization and everything in it does not."""
    organization_id = await _signup(client, "billing-lapsed@example.com", "Billing Lapsed Org")
    await _expire_trial(db_session, organization_id, days_ago=1)

    body = (await client.get("/api/v1/billing/current")).json()
    assert body["subscription"]["access_state"] == "locked"
    # Every limit is zero and every feature flag is off.
    assert body["entitlements"]["max_documents"] == 0
    assert body["entitlements"]["sso_enabled"] is False

    # Creating new work is blocked...
    blocked = await client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "nope@example.com", "role_key": "employee"},
    )
    assert blocked.status_code == 402

    # ...and not only the two features that happen to check entitlements.
    # Writes are blocked centrally, so an unrelated module is locked too.
    unrelated_write = await client.post(
        "/api/v1/tasks",
        json={"title": "Should not be creatable while locked"},
    )
    assert unrelated_write.status_code == 402

    # ...but the organization still exists and its members can still read
    # it. Locking someone out of their own records over a lapsed trial
    # would be a data-hostage pattern.
    still_there = await client.get("/api/v1/organizations/current")
    assert still_there.status_code == 200
    assert still_there.json()["id"] == str(organization_id)

    # Export in particular must keep working — it is the thing a lapsed
    # customer is most entitled to.
    export = await client.get("/api/v1/organizations/current/data-export")
    assert export.status_code == 200

    # And billing itself stays reachable, or there would be no way back.
    assert (await client.get("/api/v1/billing/plans")).status_code == 200


async def test_paying_after_a_lapsed_trial_restores_access(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "billing-rescue@example.com", "Billing Rescue Org")
    await _expire_trial(db_session, organization_id, days_ago=3)

    assert (await client.get("/api/v1/billing/current")).json()["subscription"][
        "access_state"
    ] == "locked"

    await _activate_paid_plan(client, organization_id, "business")

    body = (await client.get("/api/v1/billing/current")).json()
    assert body["subscription"]["access_state"] == "active"
    assert body["plan_key"] == "business"
    assert body["entitlements"]["scim_enabled"] is True


async def test_cancelled_subscription_locks_and_returns_the_org_to_starter(
    client: AsyncClient,
) -> None:
    organization_id = await _signup(client, "billing-cancel@example.com", "Billing Cancel Org")
    await _activate_paid_plan(client, organization_id, "growth")

    event = {
        "id": "evt_subscription_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "object": "subscription",
                "status": "canceled",
                "metadata": {"organization_id": str(organization_id)},
            }
        },
    }
    payload = json.dumps(event).encode()
    response = await client.post(
        "/api/v1/billing/webhook", content=payload, headers=_signed_headers(payload)
    )
    assert response.json()["status"] == "canceled"

    body = (await client.get("/api/v1/billing/current")).json()
    assert body["plan_key"] == "starter"
    assert body["subscription"]["access_state"] == "locked"


async def test_failed_payment_marks_past_due_without_locking(client: AsyncClient) -> None:
    """Stripe retries a declined card for days. Killing access on the
    first decline punishes a customer for an expiring card."""
    organization_id = await _signup(client, "billing-pastdue@example.com", "Billing PastDue Org")
    await _activate_paid_plan(client, organization_id, "growth")

    event = {
        "id": "evt_payment_failed",
        "type": "invoice.payment_failed",
        "data": {"object": {"metadata": {"organization_id": str(organization_id)}}},
    }
    payload = json.dumps(event).encode()
    await client.post("/api/v1/billing/webhook", content=payload, headers=_signed_headers(payload))

    body = (await client.get("/api/v1/billing/current")).json()
    assert body["subscription"]["status"] == "past_due"
    assert body["subscription"]["access_state"] == "past_due"
    # Still entitled — not locked.
    assert body["entitlements"]["sso_enabled"] is True


async def test_checkout_refuses_honestly_when_stripe_is_not_configured(
    client: AsyncClient,
) -> None:
    """No STRIPE_SECRET_KEY in this suite, so checkout must say so rather
    than pretend the purchase worked (spec §82: never a fake success)."""
    await _signup(client, "billing-noconf@example.com", "Billing NoConf Org")
    response = await client.post("/api/v1/billing/checkout", json={"plan_key": "growth"})
    assert response.status_code == 409
    assert (await client.get("/api/v1/billing/current")).json()["plan_key"] == "starter"


async def test_downgrade_to_starter_is_allowed(client: AsyncClient) -> None:
    organization_id = await _signup(client, "billing-down@example.com", "Billing Down Org")
    await _activate_paid_plan(client, organization_id, "growth")

    response = await client.put("/api/v1/billing/current", json={"plan_key": "starter"})
    assert response.status_code == 200
    assert response.json()["plan_key"] == "starter"


async def test_invitation_creation_is_blocked_once_the_starter_user_limit_is_reached(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Starter's real limit is 5 — lower it to 1 for a fast, deterministic
    # test rather than creating and accepting 5 real invitations. Patched
    # before signup so the Plan row this org resolves against is seeded
    # with the lowered limit from the start.
    from app.billing.service import PLAN_CATALOG

    monkeypatch.setitem(PLAN_CATALOG["starter"]["entitlements"], "max_users", 1)

    await _signup(client, "billing4@example.com", "Billing Org 4")

    response = await client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "someone-else@example.com", "role_key": "employee"},
    )
    # The signing-up admin is already the 1 active user Starter allows in
    # this test's patched catalog, so a second invitation is blocked.
    assert response.status_code == 402


async def test_growth_plan_permits_sso_login_for_an_existing_org(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import app.identity.sso as sso_module
    from app.config import settings

    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-secret")

    organization_id = await _signup(client, "billing5@example.com", "Billing Org 5")
    # Reached by paying, which is now the only way to reach it.
    await _activate_paid_plan(client, organization_id, "growth")

    start = await client.get("/api/v1/auth/sso/google/start")
    state = start.json()["authorization_url"].split("state=")[1].split("&")[0]

    class _FakeAdapter:
        async def exchange_code_for_tokens(self, *, code: str, redirect_uri: str):  # type: ignore[no-untyped-def]
            from app.integrations.adapters.base import TokenResult

            return TokenResult(
                access_token="fake-access-token",
                refresh_token=None,
                expires_in_seconds=3600,
                scopes=["openid", "email"],
            )

    async def _fake_fetch_identity(provider: str, access_token: str):  # type: ignore[no-untyped-def]
        return "billing5@example.com", "Billing Tester"

    monkeypatch.setattr(sso_module, "get_oauth_adapter", lambda provider: _FakeAdapter())
    monkeypatch.setattr(sso_module, "_fetch_identity", _fake_fetch_identity)

    callback = await client.get(
        "/api/v1/auth/sso/google/callback",
        params={"code": "fake-code", "state": state},
        follow_redirects=False,
    )
    assert callback.headers["location"] == f"{settings.app_url}/dashboard"


async def test_starter_plan_blocks_sso_login_for_an_existing_org(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.identity.sso as sso_module
    from app.config import settings

    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-secret")

    await _signup(client, "billing6@example.com", "Billing Org 6")

    start = await client.get("/api/v1/auth/sso/google/start")
    state = start.json()["authorization_url"].split("state=")[1].split("&")[0]

    class _FakeAdapter:
        async def exchange_code_for_tokens(self, *, code: str, redirect_uri: str):  # type: ignore[no-untyped-def]
            from app.integrations.adapters.base import TokenResult

            return TokenResult(
                access_token="fake-access-token",
                refresh_token=None,
                expires_in_seconds=3600,
                scopes=["openid", "email"],
            )

    async def _fake_fetch_identity(provider: str, access_token: str):  # type: ignore[no-untyped-def]
        return "billing6@example.com", "Billing Tester"

    monkeypatch.setattr(sso_module, "get_oauth_adapter", lambda provider: _FakeAdapter())
    monkeypatch.setattr(sso_module, "_fetch_identity", _fake_fetch_identity)

    callback = await client.get(
        "/api/v1/auth/sso/google/callback",
        params={"code": "fake-code", "state": state},
        follow_redirects=False,
    )
    assert "error=" in callback.headers["location"]
