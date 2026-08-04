"""Tests for real entitlement enforcement (spec §64, PLAT-19). The section
header itself carries spec's own "architecture" qualifier ("Plans
architecture:") — no real payment collection exists, disclosed in
docs/KNOWN_LIMITATIONS.md — but "Use entitlement service. Do not hard-code
plan checks across UI." is a real, tested requirement: every org starts on
Starter, and Starter's real limits/feature flags are really enforced.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


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


async def test_org_admin_can_upgrade_the_plan(client: AsyncClient) -> None:
    await _signup(client, "billing3@example.com", "Billing Org 3")
    response = await client.put("/api/v1/billing/current", json={"plan_key": "growth"})
    assert response.status_code == 200
    body = response.json()
    assert body["plan_key"] == "growth"
    assert body["entitlements"]["sso_enabled"] is True


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

    await _signup(client, "billing5@example.com", "Billing Org 5")
    upgraded = await client.put("/api/v1/billing/current", json={"plan_key": "growth"})
    assert upgraded.status_code == 200

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
    assert callback.headers["location"] == f"{settings.app_url}/"


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
