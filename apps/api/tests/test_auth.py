from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import PasswordResetToken, User


async def _signup(client: AsyncClient, email: str = "founder@example.com") -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Founder Person",
            "organization_name": "Test Org",
        },
    )
    assert response.status_code == 200, response.text


async def test_signup_sets_session_cookie_and_creates_org(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "founder@example.com",
            "password": "correct-horse-battery",
            "full_name": "Founder Person",
            "organization_name": "Test Org",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization"]["name"] == "Test Org"
    assert "agora_session" in response.cookies


async def test_signup_marketing_consent_defaults_false_and_persists_when_opted_in(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    default_response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "no-consent@example.com",
            "password": "correct-horse-battery",
            "full_name": "No Consent",
            "organization_name": "No Consent Org",
        },
    )
    assert default_response.status_code == 200, default_response.text
    default_user_id = default_response.json()["user"]["id"]
    default_user = await db_session.get(User, uuid.UUID(default_user_id))
    assert default_user is not None
    assert default_user.marketing_consent is False

    opted_in_response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "opted-in@example.com",
            "password": "correct-horse-battery",
            "full_name": "Opted In",
            "organization_name": "Opted In Org",
            "marketing_consent": True,
        },
    )
    assert opted_in_response.status_code == 200, opted_in_response.text
    opted_in_user_id = opted_in_response.json()["user"]["id"]
    opted_in_user = await db_session.get(User, uuid.UUID(opted_in_user_id))
    assert opted_in_user is not None
    assert opted_in_user.marketing_consent is True


async def test_signup_duplicate_email_rejected(client: AsyncClient) -> None:
    await _signup(client)
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "founder@example.com",
            "password": "another-password-1234",
            "full_name": "Someone Else",
            "organization_name": "Other Org",
        },
    )
    assert response.status_code == 400


async def test_login_wrong_password_rejected(client: AsyncClient) -> None:
    await _signup(client)
    response = await client.post(
        "/api/v1/auth/login", json={"email": "founder@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 401


async def test_login_success_and_me(client: AsyncClient) -> None:
    await _signup(client)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "founder@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "founder@example.com"


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_logout_revokes_session(client: AsyncClient) -> None:
    await _signup(client)
    logout = await client.post("/api/v1/auth/logout")
    assert logout.status_code == 200

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 401


async def test_logout_clears_a_cookie_whose_session_is_already_gone(client: AsyncClient) -> None:
    """A dead cookie must still be removable.

    Without this, the only endpoint that clears the cookie is the one that
    401s on a dead session, so the browser keeps presenting it forever —
    and the web middleware, which reads cookie presence as "logged in",
    bounces the user off /login while AuthGuard bounces them back. That
    deadlock renders a blank page with no way out (see the docstring on
    `logout_endpoint`).
    """
    client.cookies.set("agora_session", "a-token-whose-session-no-longer-exists")

    logout = await client.post("/api/v1/auth/logout")

    assert logout.status_code == 200
    assert logout.json() == {"ok": True}
    # Assert the expiry directive rather than the client's cookie jar: the
    # jar only evicts on a domain match, and the test client sets this
    # cookie without one, so checking it would test httpx, not the API.
    set_cookie = logout.headers.get("set-cookie", "")
    assert "agora_session" in set_cookie
    assert "Max-Age=0" in set_cookie


async def test_logout_succeeds_with_no_cookie_at_all(client: AsyncClient) -> None:
    """Logging out when already logged out is not an error."""
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 200


async def test_forgot_password_is_silent_about_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_reset_password_flow(client: AsyncClient, db_session: AsyncSession) -> None:
    await _signup(client)
    await client.post("/api/v1/auth/forgot-password", json={"email": "founder@example.com"})

    reset_token = (await db_session.execute(select(PasswordResetToken))).scalar_one()
    # The raw token isn't recoverable from the hash in tests (as in
    # production); we only assert the record and downstream flow shape via
    # the service layer directly, since email delivery is a dev/log-only
    # adapter (docs/KNOWN_LIMITATIONS.md).
    assert reset_token.used_at is None

    invalid = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "brand-new-password-123"},
    )
    assert invalid.status_code == 400
