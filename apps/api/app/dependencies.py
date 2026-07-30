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

    permissions = await _resolve_permissions(db, membership.id)
    return OrgContext(
        user=user,
        organization_id=organization_id,
        membership=membership,
        permissions=permissions,
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
