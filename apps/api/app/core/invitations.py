"""Organization invitation flow (spec §50, §54): a holder of
`org.users.manage` invites an email address to a specific system role;
accepting the invitation creates a new `User` (or attaches an existing one)
plus an active `Membership` in that role, with `Membership.invited_by` set.

No real email provider is wired up yet (same dev/local logging adapter
pattern as password-reset and email-verification — see
docs/KNOWN_LIMITATIONS.md); the invitation link is logged, not emailed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.billing.service import count_active_members, require_numeric_capacity
from app.config import settings
from app.core.models import Invitation, Membership, MembershipRole, Organization
from app.core.rbac import SYSTEM_ROLE_KEYS, get_system_role
from app.db.base import as_aware_utc
from app.identity.models import Session as SessionModel
from app.identity.models import User
from app.identity.schemas import InvitationPreviewOut
from app.identity.service import create_session
from app.security import generate_token, hash_password, hash_token

logger = logging.getLogger("agora.invitations")

INVITATION_TTL = timedelta(days=7)


def _dispatch_invitation_email(email: str, org_name: str, token: str) -> None:
    invite_url = f"{settings.app_url}/invite/{token}"
    logger.info("Invitation to join %s sent to %s: %s", org_name, email, invite_url)


async def create_invitation(
    db: AsyncSession,
    *,
    organization: Organization,
    email: str,
    role_key: str,
    invited_by: uuid.UUID,
) -> Invitation:
    normalized_email = email.lower()
    if role_key not in SYSTEM_ROLE_KEYS:
        raise ValueError(f"Unknown role: {role_key}")

    # spec §64 entitlement enforcement (max_users) — counts active
    # memberships only; a pending invitation doesn't consume a seat until
    # accepted, matching how `count_active_members` is defined.
    current_users = await count_active_members(db, organization_id=organization.id)
    await require_numeric_capacity(
        db,
        organization_id=organization.id,
        key="max_users",
        current_usage=current_users,
        feature_name="Users",
    )

    existing_user = (
        await db.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if existing_user is not None:
        existing_membership = (
            await db.execute(
                select(Membership).where(
                    Membership.organization_id == organization.id,
                    Membership.user_id == existing_user.id,
                    Membership.status == "active",
                )
            )
        ).scalar_one_or_none()
        if existing_membership is not None:
            raise ValueError("This person is already a member of the organization")

    existing_pending = (
        await db.execute(
            select(Invitation).where(
                Invitation.organization_id == organization.id,
                Invitation.email == normalized_email,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing_pending is not None and as_aware_utc(existing_pending.expires_at) >= datetime.now(
        UTC
    ):
        raise ValueError("An invitation to this email is already pending")

    token = generate_token()
    invitation = Invitation(
        organization_id=organization.id,
        email=normalized_email,
        role_key=role_key,
        token_hash=hash_token(token),
        invited_by=invited_by,
        expires_at=datetime.now(UTC) + INVITATION_TTL,
    )
    db.add(invitation)
    await db.flush()

    await record_event(
        db,
        organization_id=organization.id,
        actor_user_id=invited_by,
        action="org.invitation.created",
        object_type="invitation",
        object_id=str(invitation.id),
        after_state={"email": normalized_email, "role_key": role_key},
    )

    _dispatch_invitation_email(normalized_email, organization.name, token)
    return invitation


async def get_invitation_preview(db: AsyncSession, *, token: str) -> InvitationPreviewOut | None:
    """Lets the /invite/[token] page show who's inviting whom, into what
    role, before the visitor commits to filling out a form — and lets it
    branch to a real "sign in instead" state when the invited email
    already has an account, which the frontend previously had no way to
    detect (docs/AUTH_UX_AUDIT.md §8 item 5)."""
    token_hash = hash_token(token)
    invitation = (
        await db.execute(select(Invitation).where(Invitation.token_hash == token_hash))
    ).scalar_one_or_none()
    if invitation is None:
        return None

    if invitation.revoked_at is not None:
        preview_status = "revoked"
    elif invitation.accepted_at is not None:
        preview_status = "accepted"
    elif as_aware_utc(invitation.expires_at) < datetime.now(UTC):
        preview_status = "expired"
    else:
        preview_status = "pending"

    organization = await db.get(Organization, invitation.organization_id)
    assert organization is not None  # FK guarantees existence
    inviter = await db.get(User, invitation.invited_by)
    account_exists = (
        await db.execute(select(User.id).where(User.email == invitation.email))
    ).scalar_one_or_none() is not None

    return InvitationPreviewOut(
        organization_name=organization.name,
        email=invitation.email,
        role_key=invitation.role_key,
        inviter_name=inviter.full_name if inviter is not None else None,
        expires_at=invitation.expires_at,
        status=preview_status,
        account_exists=account_exists,
    )


async def decline_invitation(db: AsyncSession, *, token: str) -> None:
    """The invited person's own choice not to join — uses the same
    `revoked_at` field an admin's revoke already sets, since both mean the
    identical thing to the rest of the system: this invitation is no
    longer valid, and re-inviting the same email requires a fresh one.
    Public/unauthenticated, matching accept_invitation's own access model
    — the token itself is the only credential needed."""
    token_hash = hash_token(token)
    invitation = (
        await db.execute(select(Invitation).where(Invitation.token_hash == token_hash))
    ).scalar_one_or_none()

    invalid = ValueError("Invalid or expired invitation")
    if (
        invitation is None
        or invitation.revoked_at is not None
        or invitation.accepted_at is not None
    ):
        raise invalid

    invitation.revoked_at = datetime.now(UTC)
    await record_event(
        db,
        organization_id=invitation.organization_id,
        actor_user_id=None,
        action="org.invitation.declined",
        object_type="invitation",
        object_id=str(invitation.id),
    )
    await db.commit()


async def accept_invitation(
    db: AsyncSession,
    *,
    token: str,
    full_name: str | None,
    password: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[User, Organization, SessionModel]:
    token_hash = hash_token(token)
    invitation = (
        await db.execute(select(Invitation).where(Invitation.token_hash == token_hash))
    ).scalar_one_or_none()

    invalid = ValueError("Invalid or expired invitation")
    if (
        invitation is None
        or invitation.revoked_at is not None
        or invitation.accepted_at is not None
    ):
        raise invalid
    if as_aware_utc(invitation.expires_at) < datetime.now(UTC):
        raise invalid

    user = (
        await db.execute(select(User).where(User.email == invitation.email))
    ).scalar_one_or_none()
    if user is None:
        if not password:
            raise ValueError("A password is required to create your account")
        user = User(
            email=invitation.email,
            hashed_password=hash_password(password),
            full_name=full_name,
        )
        db.add(user)
        await db.flush()

    membership = Membership(
        organization_id=invitation.organization_id,
        user_id=user.id,
        status="active",
        invited_by=invitation.invited_by,
    )
    db.add(membership)
    await db.flush()

    role = await get_system_role(db, invitation.role_key)
    db.add(MembershipRole(membership_id=membership.id, role_id=role.id))

    invitation.accepted_at = datetime.now(UTC)

    await record_event(
        db,
        organization_id=invitation.organization_id,
        actor_user_id=user.id,
        action="org.invitation.accepted",
        object_type="invitation",
        object_id=str(invitation.id),
        after_state={"role_key": invitation.role_key},
    )

    session = await create_session(
        db,
        user=user,
        organization_id=invitation.organization_id,
        ip_address=ip_address,
        user_agent=user_agent,
        mfa_verified=not user.mfa_enabled,
    )
    organization = await db.get(Organization, invitation.organization_id)
    assert organization is not None  # FK guarantees existence

    from app.automation.triggers import dispatch_event

    await dispatch_event(
        db,
        organization_id=invitation.organization_id,
        trigger_type="new_employee",
        payload={"user_id": str(user.id), "email": user.email},
        actor_user_id=user.id,
    )

    await db.commit()
    return user, organization, session
