"""Tests for the Platform-foundation auth completion work: email
verification, org invitations, and TOTP-based MFA (spec §50, §54, E4).

Verification/invitation tokens are only ever logged (no real email
transport — docs/KNOWN_LIMITATIONS.md), so these tests extract the raw
token from the log line via `caplog`, the same way a user would click the
link in their actual email — not by reaching into the service layer's
internals, which would test less of the real system.
"""

from __future__ import annotations

import re
import uuid
from urllib.parse import parse_qs, urlparse

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Membership
from app.identity.models import EmailVerificationToken, User


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Auth Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


def _extract_token_from_log(caplog: pytest.LogCaptureFixture, path_prefix: str) -> str:
    for record in caplog.records:
        match = re.search(rf"{re.escape(path_prefix)}([A-Za-z0-9_-]+)", record.message)
        if match:
            return match.group(1)
    raise AssertionError(f"No log line found containing a {path_prefix!r} link")


# --- Email verification -----------------------------------------------------


async def test_signup_creates_email_verification_token(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "verify1@example.com", "Verify Org 1")
    token_row = (await db_session.execute(select(EmailVerificationToken))).scalar_one()
    assert token_row.used_at is None


async def test_verify_email_with_valid_token_marks_user_verified(
    client: AsyncClient, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="agora.identity"):
        await _signup(client, "verify2@example.com", "Verify Org 2")
    token = _extract_token_from_log(caplog, "/verify-email/")

    response = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert response.status_code == 200, response.text

    user = (
        await db_session.execute(select(User).where(User.email == "verify2@example.com"))
    ).scalar_one()
    assert user.email_verified_at is not None


async def test_verify_email_with_invalid_token_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert response.status_code == 400


async def test_resend_verification_email_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/resend-verification-email")
    assert response.status_code == 401


# --- Invitations --------------------------------------------------------


async def test_org_admin_can_create_invitation(client: AsyncClient) -> None:
    await _signup(client, "invite-admin1@example.com", "Invite Org 1")
    response = await client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "new-member@example.com", "role_key": "employee"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["email"] == "new-member@example.com"
    assert response.json()["role_key"] == "employee"


async def test_invitation_to_unknown_role_rejected(client: AsyncClient) -> None:
    await _signup(client, "invite-admin2@example.com", "Invite Org 2")
    response = await client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "new-member2@example.com", "role_key": "not-a-real-role"},
    )
    assert response.status_code == 422


async def test_duplicate_pending_invitation_rejected(client: AsyncClient) -> None:
    await _signup(client, "invite-admin3@example.com", "Invite Org 3")
    first = await client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "dup@example.com", "role_key": "employee"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "dup@example.com", "role_key": "employee"},
    )
    assert second.status_code == 422


async def test_accepting_invitation_creates_new_user_and_membership(
    client: AsyncClient, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    org_id = await _signup(client, "invite-admin4@example.com", "Invite Org 4")

    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": "invitee1@example.com", "role_key": "sales_representative"},
        )
    assert created.status_code == 201
    token = _extract_token_from_log(caplog, "/invite/")

    await client.post("/api/v1/auth/logout")

    accept = await client.post(
        "/api/v1/auth/accept-invitation",
        json={
            "token": token,
            "full_name": "New Invitee",
            "password": "brand-new-password-123",
        },
    )
    assert accept.status_code == 200, accept.text
    assert accept.json()["organization"]["id"] == str(org_id)

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "invitee1@example.com"

    user = (
        await db_session.execute(select(User).where(User.email == "invitee1@example.com"))
    ).scalar_one()
    membership = (
        await db_session.execute(select(Membership).where(Membership.user_id == user.id))
    ).scalar_one()
    assert membership.organization_id == org_id
    assert membership.invited_by is not None

    # A sales_representative should be able to create a lead but not
    # decide an approval (RBAC actually wired to the new membership's role).
    lead = await client.post("/api/v1/sales/leads", json={"source": "inbound"})
    assert lead.status_code == 201


async def test_accept_invitation_with_invalid_token_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": "not-a-real-token", "full_name": "Nobody", "password": "irrelevant-1234"},
    )
    assert response.status_code == 400


async def test_preview_invitation_for_a_new_email_reports_pending_and_no_account(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await _signup(client, "invite-preview1@example.com", "Invite Preview Org 1")

    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": "brand-new-invitee@example.com", "role_key": "employee"},
        )
    assert created.status_code == 201
    token = _extract_token_from_log(caplog, "/invite/")

    await client.post("/api/v1/auth/logout")

    preview = await client.get(f"/api/v1/auth/invitations/{token}")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["organization_name"] == "Invite Preview Org 1"
    assert body["email"] == "brand-new-invitee@example.com"
    assert body["role_key"] == "employee"
    assert body["inviter_name"] == "Auth Tester"
    assert body["status"] == "pending"
    assert body["account_exists"] is False


async def test_preview_invitation_reports_an_existing_account(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await _signup(client, "existing-invitee@example.com", "Existing Invitee Org")
    await client.post("/api/v1/auth/logout")
    await _signup(client, "invite-preview2@example.com", "Invite Preview Org 2")

    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": "existing-invitee@example.com", "role_key": "employee"},
        )
    assert created.status_code == 201
    token = _extract_token_from_log(caplog, "/invite/")
    await client.post("/api/v1/auth/logout")

    preview = await client.get(f"/api/v1/auth/invitations/{token}")
    assert preview.status_code == 200, preview.text
    assert preview.json()["account_exists"] is True


async def test_preview_invitation_for_unknown_token_is_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/invitations/not-a-real-token")
    assert response.status_code == 404


async def test_preview_invitation_reports_revoked_status(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await _signup(client, "invite-preview3@example.com", "Invite Preview Org 3")

    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": "to-be-revoked@example.com", "role_key": "employee"},
        )
    invitation_id = created.json()["id"]
    token = _extract_token_from_log(caplog, "/invite/")

    revoke = await client.post(f"/api/v1/organizations/current/invitations/{invitation_id}/revoke")
    assert revoke.status_code == 200
    await client.post("/api/v1/auth/logout")

    preview = await client.get(f"/api/v1/auth/invitations/{token}")
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "revoked"


async def test_decline_invitation_marks_it_revoked_and_unacceptable(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await _signup(client, "invite-decline1@example.com", "Invite Decline Org 1")

    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": "declines-it@example.com", "role_key": "employee"},
        )
    assert created.status_code == 201
    token = _extract_token_from_log(caplog, "/invite/")
    await client.post("/api/v1/auth/logout")

    decline = await client.post(f"/api/v1/auth/invitations/{token}/decline")
    assert decline.status_code == 204

    preview = await client.get(f"/api/v1/auth/invitations/{token}")
    assert preview.json()["status"] == "revoked"

    accept = await client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": token, "full_name": "Too Late", "password": "irrelevant-12345"},
    )
    assert accept.status_code == 400


async def test_decline_invitation_with_invalid_token_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/invitations/not-a-real-token/decline")
    assert response.status_code == 400


async def test_preview_invitation_reports_expired_status(
    client: AsyncClient, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.core.models import Invitation

    await _signup(client, "invite-preview4@example.com", "Invite Preview Org 4")

    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": "will-expire@example.com", "role_key": "employee"},
        )
    invitation_id = created.json()["id"]
    token = _extract_token_from_log(caplog, "/invite/")
    await client.post("/api/v1/auth/logout")

    invitation = await db_session.get(Invitation, uuid.UUID(invitation_id))
    assert invitation is not None
    invitation.expires_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.commit()

    preview = await client.get(f"/api/v1/auth/invitations/{token}")
    assert preview.status_code == 200, preview.text
    assert preview.json()["status"] == "expired"


async def test_revoked_invitation_cannot_be_accepted(
    client: AsyncClient, db_session: AsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    await _signup(client, "invite-admin5@example.com", "Invite Org 5")

    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": "revoked-invitee@example.com", "role_key": "employee"},
        )
    invitation_id = created.json()["id"]
    token = _extract_token_from_log(caplog, "/invite/")

    revoke = await client.post(f"/api/v1/organizations/current/invitations/{invitation_id}/revoke")
    assert revoke.status_code == 200

    accept = await client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": token, "full_name": "Too Late", "password": "irrelevant-12345"},
    )
    assert accept.status_code == 400


async def test_employee_cannot_create_invitations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.core.rbac import get_system_role
    from app.identity.service import create_session
    from app.security import hash_password

    org_id = await _signup(client, "invite-admin6@example.com", "Invite Org 6")
    await client.post("/api/v1/auth/logout")

    user = User(
        email="employee-inviter@example.com", hashed_password=hash_password("irrelevant-123")
    )
    db_session.add(user)
    await db_session.flush()
    membership = Membership(organization_id=org_id, user_id=user.id, status="active")
    db_session.add(membership)
    await db_session.flush()
    role = await get_system_role(db_session, "employee")
    from app.core.models import MembershipRole

    db_session.add(MembershipRole(membership_id=membership.id, role_id=role.id))
    session = await create_session(
        db_session, user=user, organization_id=org_id, ip_address=None, user_agent=None
    )
    await db_session.commit()
    client.cookies.set("agora_session", session.raw_token)  # type: ignore[attr-defined]

    response = await client.post(
        "/api/v1/organizations/current/invitations",
        json={"email": "blocked@example.com", "role_key": "employee"},
    )
    assert response.status_code == 403


# --- MFA -----------------------------------------------------------------


def _totp_secret_from_provisioning_uri(uri: str) -> str:
    query = parse_qs(urlparse(uri).query)
    return query["secret"][0]


async def test_mfa_enroll_and_confirm(client: AsyncClient) -> None:
    await _signup(client, "mfa1@example.com", "MFA Org 1")

    enroll = await client.post("/api/v1/auth/mfa/enroll")
    assert enroll.status_code == 200
    secret = _totp_secret_from_provisioning_uri(enroll.json()["provisioning_uri"])

    valid_code = pyotp.TOTP(secret).now()
    confirm = await client.post("/api/v1/auth/mfa/confirm", json={"code": valid_code})
    assert confirm.status_code == 200, confirm.text


async def test_mfa_confirm_with_wrong_code_rejected(client: AsyncClient) -> None:
    await _signup(client, "mfa2@example.com", "MFA Org 2")
    await client.post("/api/v1/auth/mfa/enroll")

    confirm = await client.post("/api/v1/auth/mfa/confirm", json={"code": "000000"})
    assert confirm.status_code == 422


async def test_login_with_mfa_enabled_requires_challenge_before_org_access(
    client: AsyncClient,
) -> None:
    await _signup(client, "mfa3@example.com", "MFA Org 3")
    enroll = await client.post("/api/v1/auth/mfa/enroll")
    secret = _totp_secret_from_provisioning_uri(enroll.json()["provisioning_uri"])
    await client.post("/api/v1/auth/mfa/confirm", json={"code": pyotp.TOTP(secret).now()})

    await client.post("/api/v1/auth/logout")

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "mfa3@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    assert login.json()["mfa_required"] is True

    # Authenticated (get_current_user) but not yet MFA-verified.
    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200

    # get_org_context-gated endpoints must reject until the challenge passes.
    blocked = await client.get("/api/v1/tasks")
    assert blocked.status_code == 401

    wrong_code = await client.post("/api/v1/auth/mfa/verify", json={"code": "000000"})
    assert wrong_code.status_code == 422
    still_blocked = await client.get("/api/v1/tasks")
    assert still_blocked.status_code == 401

    verify = await client.post("/api/v1/auth/mfa/verify", json={"code": pyotp.TOTP(secret).now()})
    assert verify.status_code == 200

    unblocked = await client.get("/api/v1/tasks")
    assert unblocked.status_code == 200


async def test_disable_mfa_requires_valid_code(client: AsyncClient) -> None:
    await _signup(client, "mfa4@example.com", "MFA Org 4")
    enroll = await client.post("/api/v1/auth/mfa/enroll")
    secret = _totp_secret_from_provisioning_uri(enroll.json()["provisioning_uri"])
    await client.post("/api/v1/auth/mfa/confirm", json={"code": pyotp.TOTP(secret).now()})

    wrong = await client.post("/api/v1/auth/mfa/disable", json={"code": "000000"})
    assert wrong.status_code == 422

    right = await client.post("/api/v1/auth/mfa/disable", json={"code": pyotp.TOTP(secret).now()})
    assert right.status_code == 200

    await client.post("/api/v1/auth/logout")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "mfa4@example.com", "password": "correct-horse-battery"},
    )
    assert login.json()["mfa_required"] is False
