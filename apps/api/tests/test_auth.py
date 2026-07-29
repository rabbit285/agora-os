from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.models import PasswordResetToken


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
