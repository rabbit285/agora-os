"""Tests for real Sign-in-with-Google/Microsoft SSO (spec §59, PLAT-18).
No real Google/Microsoft developer app exists in this environment (same
constraint as every OAuth-based feature this session), so these tests
monkeypatch the two real external-network boundaries
(`get_oauth_adapter`'s token exchange, `_fetch_identity`'s userinfo call)
while exercising every other real line: state-token issuance/consumption,
session/cookie creation, and — the case most worth testing — genuine
first-time-SSO organization auto-provisioning.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Membership
from app.identity.models import User


async def test_providers_endpoint_is_public_and_honestly_unconfigured(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/auth/sso/providers")
    assert response.status_code == 200
    by_provider = {p["provider"]: p["configured"] for p in response.json()}
    assert by_provider == {"google": False, "microsoft": False}


async def test_start_is_refused_when_the_provider_is_not_configured(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/sso/google/start")
    assert response.status_code == 400


async def test_start_returns_a_real_minimal_scope_authorization_url(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-secret")

    response = await client.get("/api/v1/auth/sso/google/start")
    assert response.status_code == 200
    url = response.json()["authorization_url"]
    assert "accounts.google.com" in url
    assert "scope=openid" in url
    assert "calendar" not in url  # never the broader Integrations scope set
    assert "state=" in url


async def test_unknown_provider_is_rejected(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/sso/not-a-real-provider/start")
    assert response.status_code == 404


async def test_first_time_sso_login_provisions_a_new_org_and_admin(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.identity.sso as sso_module
    from app.config import settings

    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-secret")

    start = await client.get("/api/v1/auth/sso/google/start")
    assert start.status_code == 200
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
        return "new-sso-user@example.com", "New SSO User"

    monkeypatch.setattr(sso_module, "get_oauth_adapter", lambda provider: _FakeAdapter())
    monkeypatch.setattr(sso_module, "_fetch_identity", _fake_fetch_identity)

    callback = await client.get(
        "/api/v1/auth/sso/google/callback",
        params={"code": "fake-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code in (302, 307)
    assert callback.headers["location"].endswith("/onboarding")
    assert "session" in callback.cookies or any(
        "session" in c for c in callback.headers.get_list("set-cookie")
    )

    user = (
        await db_session.execute(select(User).where(User.email == "new-sso-user@example.com"))
    ).scalar_one()
    assert user.email_verified_at is not None
    membership = (
        await db_session.execute(select(Membership).where(Membership.user_id == user.id))
    ).scalar_one()
    assert membership.status == "active"


async def test_reusing_a_consumed_state_is_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.identity.sso as sso_module
    from app.config import settings

    monkeypatch.setattr(settings, "google_client_id", "fake-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-secret")

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
        return "reuse-state@example.com", "Reuse State"

    monkeypatch.setattr(sso_module, "get_oauth_adapter", lambda provider: _FakeAdapter())
    monkeypatch.setattr(sso_module, "_fetch_identity", _fake_fetch_identity)

    first = await client.get(
        "/api/v1/auth/sso/google/callback",
        params={"code": "fake-code", "state": state},
        follow_redirects=False,
    )
    assert first.headers["location"].endswith("/onboarding")

    second = await client.get(
        "/api/v1/auth/sso/google/callback",
        params={"code": "fake-code-again", "state": state},
        follow_redirects=False,
    )
    assert "error=" in second.headers["location"]
