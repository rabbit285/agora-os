from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.billing.service import ensure_plan_catalog, start_trial
from app.config import settings
from app.core.crypto import decrypt_token, encrypt_token
from app.core.models import LegalEntity, Membership, MembershipRole, Organization
from app.core.rbac import ensure_system_roles, get_system_role
from app.db.base import as_aware_utc
from app.identity.models import EmailVerificationToken, PasswordResetToken, User
from app.identity.models import Session as SessionModel
from app.identity.schemas import SignupRequest
from app.security import generate_token, hash_password, hash_token, verify_password

logger = logging.getLogger("agora.identity")

SESSION_TTL = timedelta(hours=settings.session_ttl_hours)
RESET_TOKEN_TTL = timedelta(hours=2)
EMAIL_VERIFICATION_TTL = timedelta(hours=48)
MFA_ISSUER_NAME = "Agora Origin"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "org"


async def _unique_slug(db: AsyncSession, name: str) -> str:
    base = _slugify(name)
    slug = base
    suffix = 1
    while (
        await db.execute(select(Organization).where(Organization.slug == slug))
    ).scalar_one_or_none() is not None:
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


async def signup(
    db: AsyncSession, payload: SignupRequest, *, ip_address: str | None, user_agent: str | None
) -> tuple[User, Organization, SessionModel]:
    email = payload.email.lower()
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        # Same response shape as any other validation error — do not reveal
        # that the email is already registered.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to create account"
        )

    await ensure_system_roles(db)
    await ensure_plan_catalog(db)

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        marketing_consent=payload.marketing_consent,
    )
    db.add(user)
    await db.flush()

    slug = await _unique_slug(db, payload.organization_name)
    organization = Organization(name=payload.organization_name, slug=slug)
    db.add(organization)
    await db.flush()

    db.add(
        LegalEntity(
            organization_id=organization.id, name=payload.organization_name, is_default=True
        )
    )

    # The 14-day Starter trial. No card, no Stripe call — signup stays a
    # single local transaction that cannot fail on a payment provider.
    await start_trial(db, organization_id=organization.id)

    membership = Membership(organization_id=organization.id, user_id=user.id, status="active")
    db.add(membership)
    await db.flush()

    org_admin_role = await get_system_role(db, "org_admin")
    db.add(MembershipRole(membership_id=membership.id, role_id=org_admin_role.id))

    await record_event(
        db,
        organization_id=organization.id,
        actor_user_id=user.id,
        action="auth.signup",
        object_type="organization",
        object_id=str(organization.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    session = await create_session(
        db, user=user, organization_id=organization.id, ip_address=ip_address, user_agent=user_agent
    )
    await request_email_verification(db, user=user)
    await db.commit()
    return user, organization, session


async def create_session(
    db: AsyncSession,
    *,
    user: User,
    organization_id: uuid.UUID | None,
    ip_address: str | None,
    user_agent: str | None,
    mfa_verified: bool = True,
) -> SessionModel:
    token = generate_token()
    session = SessionModel(
        user_id=user.id,
        organization_id=organization_id,
        session_token_hash=hash_token(token),
        user_agent=user_agent,
        ip_address=ip_address,
        expires_at=datetime.now(UTC) + SESSION_TTL,
        mfa_verified=mfa_verified,
    )
    db.add(session)
    await db.flush()
    session.raw_token = token  # type: ignore[attr-defined]  # transient, not persisted
    return session


async def _first_active_organization_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID | None:
    result = await db.execute(
        select(Membership.organization_id).where(
            Membership.user_id == user_id, Membership.status == "active"
        )
    )
    row = result.first()
    return row[0] if row else None


async def login(
    db: AsyncSession, email: str, password: str, *, ip_address: str | None, user_agent: str | None
) -> tuple[User, SessionModel, bool]:
    """Returns (user, session, mfa_required). When `user.mfa_enabled`, the
    session is created with `mfa_verified=False` — it authenticates the user
    but `app.dependencies.get_org_context` rejects it until a correct code is
    submitted to `/auth/mfa/verify` (spec E4's MFA challenge)."""
    normalized_email = email.lower()
    user = (
        await db.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()

    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
    )
    if user is None or not user.is_active:
        raise invalid_credentials
    if not verify_password(password, user.hashed_password):
        await record_event(
            db,
            organization_id=None,
            actor_user_id=user.id,
            action="auth.login.failed",
            object_type="user",
            object_id=str(user.id),
            ip_address=ip_address,
            user_agent=user_agent,
            policy_decision="denied",
        )
        await db.commit()
        raise invalid_credentials

    organization_id = await _first_active_organization_id(db, user.id)
    mfa_required = user.mfa_enabled
    session = await create_session(
        db,
        user=user,
        organization_id=organization_id,
        ip_address=ip_address,
        user_agent=user_agent,
        mfa_verified=not mfa_required,
    )
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=user.id,
        action="auth.login",
        object_type="user",
        object_id=str(user.id),
        ip_address=ip_address,
        user_agent=user_agent,
        after_state={"mfa_required": mfa_required},
    )
    await db.commit()
    return user, session, mfa_required


async def logout(db: AsyncSession, session: SessionModel) -> None:
    session.revoked_at = datetime.now(UTC)
    await record_event(
        db,
        organization_id=session.organization_id,
        actor_user_id=session.user_id,
        action="auth.logout",
        object_type="session",
        object_id=str(session.id),
    )
    await db.commit()


def _dispatch_password_reset_email(email: str, token: str) -> None:
    """Dev/local adapter: logs the reset link instead of sending real email.

    No transactional email provider (SES/SMTP) is wired yet — see
    docs/KNOWN_LIMITATIONS.md. This keeps the flow fully functional for
    local development and tests without requiring credentials.
    """
    reset_url = f"{settings.app_url}/reset-password/{token}"
    logger.info("Password reset requested for %s: %s", email, reset_url)


async def request_password_reset(db: AsyncSession, email: str) -> None:
    normalized_email = email.lower()
    user = (
        await db.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if user is None:
        # Do not reveal whether the email exists.
        return
    token = generate_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + RESET_TOKEN_TTL,
        )
    )
    await db.commit()
    _dispatch_password_reset_email(user.email, token)


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    token_hash = hash_token(token)
    reset_token = (
        await db.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
        )
    ).scalar_one_or_none()

    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token"
    )
    if reset_token is None or reset_token.used_at is not None:
        raise invalid
    if as_aware_utc(reset_token.expires_at) < datetime.now(UTC):
        raise invalid

    user = await db.get(User, reset_token.user_id)
    if user is None:
        raise invalid

    user.hashed_password = hash_password(new_password)
    reset_token.used_at = datetime.now(UTC)

    # Revoke all existing sessions on password reset.
    existing_sessions = (
        await db.execute(select(SessionModel).where(SessionModel.user_id == user.id))
    ).scalars()
    for existing_session in existing_sessions:
        existing_session.revoked_at = datetime.now(UTC)

    await record_event(
        db,
        organization_id=None,
        actor_user_id=user.id,
        action="auth.password_reset",
        object_type="user",
        object_id=str(user.id),
    )
    await db.commit()


def _dispatch_email_verification_email(email: str, token: str) -> None:
    """Same dev/local logging adapter as `_dispatch_password_reset_email` —
    no transactional email provider is wired yet (docs/KNOWN_LIMITATIONS.md)."""
    verify_url = f"{settings.app_url}/verify-email/{token}"
    logger.info("Email verification requested for %s: %s", email, verify_url)


async def request_email_verification(db: AsyncSession, *, user: User) -> None:
    """Called once at signup and available to call again (resend) for a
    user whose email isn't verified yet. A no-op, not an error, if the email
    is already verified — resending a verification link for a verified
    address should never be possible to distinguish from one that doesn't
    exist (same non-enumeration principle as password reset)."""
    if user.email_verified_at is not None:
        return
    token = generate_token()
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + EMAIL_VERIFICATION_TTL,
        )
    )
    await db.flush()
    _dispatch_email_verification_email(user.email, token)


async def verify_email(db: AsyncSession, token: str) -> User:
    token_hash = hash_token(token)
    verification_token = (
        await db.execute(
            select(EmailVerificationToken).where(EmailVerificationToken.token_hash == token_hash)
        )
    ).scalar_one_or_none()

    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification link"
    )
    if verification_token is None or verification_token.used_at is not None:
        raise invalid
    if as_aware_utc(verification_token.expires_at) < datetime.now(UTC):
        raise invalid

    user = await db.get(User, verification_token.user_id)
    if user is None:
        raise invalid

    verification_token.used_at = datetime.now(UTC)
    user.email_verified_at = datetime.now(UTC)

    await record_event(
        db,
        organization_id=None,
        actor_user_id=user.id,
        action="auth.email_verified",
        object_type="user",
        object_id=str(user.id),
    )
    await db.commit()
    return user


async def start_mfa_enrollment(db: AsyncSession, *, user: User) -> str:
    """Generates a new TOTP secret and stores it encrypted, but leaves
    `mfa_enabled` False until confirmed via `confirm_mfa_enrollment` with a
    valid code — enrollment isn't active just because a secret exists (spec
    F2 "no direct autonomous writes" applied to security-sensitive state)."""
    secret = pyotp.random_base32()
    user.mfa_secret_encrypted = encrypt_token(secret)
    await db.commit()
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=MFA_ISSUER_NAME)


async def confirm_mfa_enrollment(db: AsyncSession, *, user: User, code: str) -> None:
    if user.mfa_secret_encrypted is None:
        raise ValueError("No MFA enrollment is in progress — call start_mfa_enrollment first")
    secret = decrypt_token(user.mfa_secret_encrypted)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise ValueError("Invalid verification code")
    user.mfa_enabled = True
    await record_event(
        db,
        organization_id=None,
        actor_user_id=user.id,
        action="auth.mfa_enabled",
        object_type="user",
        object_id=str(user.id),
    )
    await db.commit()


async def disable_mfa(db: AsyncSession, *, user: User, code: str) -> None:
    if not user.mfa_enabled or user.mfa_secret_encrypted is None:
        raise ValueError("MFA is not enabled for this account")
    secret = decrypt_token(user.mfa_secret_encrypted)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise ValueError("Invalid verification code")
    user.mfa_enabled = False
    user.mfa_secret_encrypted = None
    await record_event(
        db,
        organization_id=None,
        actor_user_id=user.id,
        action="auth.mfa_disabled",
        object_type="user",
        object_id=str(user.id),
    )
    await db.commit()


async def verify_mfa_challenge(
    db: AsyncSession, *, user: User, session: SessionModel, code: str
) -> None:
    """Completes the login-time MFA challenge for a session already created
    with `mfa_verified=False` by `login()`. Wrong-code attempts are audited
    with `policy_decision="denied"` but do not revoke the pending session —
    the caller can retry until it expires like any other session."""
    if user.mfa_secret_encrypted is None:
        raise ValueError("MFA is not enabled for this account")
    secret = decrypt_token(user.mfa_secret_encrypted)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        await record_event(
            db,
            organization_id=session.organization_id,
            actor_user_id=user.id,
            action="auth.mfa_challenge.failed",
            object_type="session",
            object_id=str(session.id),
            policy_decision="denied",
        )
        await db.commit()
        raise ValueError("Invalid verification code")

    session.mfa_verified = True
    await record_event(
        db,
        organization_id=session.organization_id,
        actor_user_id=user.id,
        action="auth.mfa_challenge.succeeded",
        object_type="session",
        object_id=str(session.id),
    )
    await db.commit()
