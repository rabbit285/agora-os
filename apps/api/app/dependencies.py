"""Tenant resolution and RBAC enforcement dependencies.

Per docs/SECURITY_ARCHITECTURE.md: the organization_id used for every query
in a request is resolved server-side from the session + membership table,
never taken at face value from client input.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.models import Membership, MembershipRole, Permission, Role, RolePermission
from app.db.base import as_aware_utc
from app.db.session import get_db
from app.identity.models import Session as SessionModel
from app.identity.models import User
from app.security import hash_token


@dataclass
class OrgContext:
    user: User
    organization_id: uuid.UUID
    membership: Membership
    permissions: frozenset[str] = field(default_factory=frozenset)


async def _load_session(db: AsyncSession, token: str) -> SessionModel | None:
    token_hash = hash_token(token)
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_token_hash == token_hash)
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if as_aware_utc(session.expires_at) < datetime.now(UTC):
        return None
    return session


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> tuple[User, SessionModel]:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    session = await _load_session(db, token)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user, session


async def get_org_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_session: tuple[User, SessionModel] = Depends(get_current_user),
) -> OrgContext:
    user, session = user_session

    if not session.mfa_verified:
        # Authenticated (get_current_user succeeded) but the login-time MFA
        # challenge hasn't been completed yet — /auth/me and /auth/mfa/verify
        # only depend on get_current_user, so they still work mid-challenge.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA verification required"
        )

    requested_org_id_raw = request.headers.get("X-Organization-Id")
    organization_id = (
        uuid.UUID(requested_org_id_raw) if requested_org_id_raw else session.organization_id
    )
    if organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No organization selected",
        )

    result = await db.execute(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.organization_id == organization_id,
            Membership.status == "active",
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        # Deliberately identical to "org does not exist" — do not leak
        # whether the organization exists if the user isn't a member of it.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    await _enforce_subscription_lock(db, request, organization_id)

    permissions = await _resolve_permissions(db, membership.id)
    return OrgContext(
        user=user,
        organization_id=organization_id,
        membership=membership,
        permissions=permissions,
    )


# Paths that must keep working for a locked organization. Billing is how
# they unlock; the deletion request is a data right that cannot be held
# hostage behind a payment.
_LOCK_EXEMPT_PATH_PREFIXES = (
    "/api/v1/billing",
    "/api/v1/organizations/current/deletion-request",
)
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def _enforce_subscription_lock(
    db: AsyncSession, request: Request, organization_id: uuid.UUID
) -> None:
    """Block writes for an organization whose trial lapsed or whose
    subscription ended.

    This lives here rather than as an entitlement check per feature for a
    blunt reason: only two call sites in the codebase consult entitlements
    at all (invitations and SSO login), so zeroing the entitlement values
    alone would "lock" an account that could still create documents,
    workflows, and everything else. `get_org_context` is the one place
    every org-scoped request already passes through.

    Reads are deliberately untouched — GET stays open, which is what keeps
    "your organization and its data are preserved, and you can still
    export them" true rather than a slogan.
    """
    if request.method not in _MUTATING_METHODS:
        return
    path = request.url.path
    if any(path.startswith(prefix) for prefix in _LOCK_EXEMPT_PATH_PREFIXES):
        return

    # Imported here, not at module scope: app.billing.service imports the
    # models this module's callers also import, and a top-level import
    # would make the cycle load-order dependent.
    from app.billing.service import get_subscription, resolve_access_state

    subscription = await get_subscription(db, organization_id=organization_id)
    if resolve_access_state(subscription) != "locked":
        return

    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=(
            "This organization's plan has lapsed. Your data is safe and still readable — "
            "choose a plan in Settings → Billing to resume making changes."
        ),
    )


async def _resolve_permissions(db: AsyncSession, membership_id: uuid.UUID) -> frozenset[str]:
    result = await db.execute(
        select(Permission.key)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(MembershipRole, MembershipRole.role_id == Role.id)
        .where(MembershipRole.membership_id == membership_id)
    )
    return frozenset(row[0] for row in result.all())


def require_permission(permission_key: str) -> Callable[[OrgContext], Awaitable[OrgContext]]:
    async def _dependency(context: OrgContext = Depends(get_org_context)) -> OrgContext:
        if permission_key not in context.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {permission_key}",
            )
        return context

    return _dependency
