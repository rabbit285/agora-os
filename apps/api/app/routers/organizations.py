from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.invitations import create_invitation
from app.core.models import Invitation, Membership, MembershipRole, Organization, Role
from app.core.schemas import MembershipOut, OrganizationSettingsOut, OrganizationSettingsUpdate
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.identity.schemas import InvitationCreate, InvitationOut

router = APIRouter(prefix="/api/v1/organizations", tags=["organizations"])


@router.get("/current", response_model=OrganizationSettingsOut)
async def get_current_organization(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> Organization:
    org = await db.get(Organization, context.organization_id)
    assert org is not None  # tenant resolution already guarantees existence
    return org


@router.patch("/current", response_model=OrganizationSettingsOut)
async def update_current_organization(
    payload: OrganizationSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> Organization:
    org = await db.get(Organization, context.organization_id)
    assert org is not None
    before_name = org.name
    org.name = payload.name
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.settings.updated",
        object_type="organization",
        object_id=str(org.id),
        before_state={"name": before_name},
        after_state={"name": org.name},
    )
    await db.commit()
    await db.refresh(org)
    return org


@router.get("/current/members", response_model=list[MembershipOut])
async def list_members(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.users.manage")),
) -> list[MembershipOut]:
    result = await db.execute(
        select(Membership).where(Membership.organization_id == context.organization_id)
    )
    memberships = result.scalars().all()

    out: list[MembershipOut] = []
    for membership in memberships:
        role_result = await db.execute(
            select(Role.key)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(MembershipRole.membership_id == membership.id)
        )
        roles = [row[0] for row in role_result.all()]
        out.append(
            MembershipOut(
                id=membership.id, user_id=membership.user_id, status=membership.status, roles=roles
            )
        )
    return out


@router.get("/current/invitations", response_model=list[InvitationOut])
async def list_invitations(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.users.manage")),
) -> list[Invitation]:
    result = await db.execute(
        select(Invitation)
        .where(Invitation.organization_id == context.organization_id)
        .order_by(Invitation.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/current/invitations", response_model=InvitationOut, status_code=status.HTTP_201_CREATED
)
async def create_invitation_endpoint(
    payload: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.users.manage")),
) -> Invitation:
    org = await db.get(Organization, context.organization_id)
    assert org is not None
    try:
        invitation = await create_invitation(
            db,
            organization=org,
            email=payload.email,
            role_key=payload.role_key,
            invited_by=context.user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(invitation)
    return invitation


@router.post("/current/invitations/{invitation_id}/revoke", response_model=InvitationOut)
async def revoke_invitation_endpoint(
    invitation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.users.manage")),
) -> Invitation:
    invitation = await db.get(Invitation, invitation_id)
    if invitation is None or invitation.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    if invitation.accepted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Invitation has already been accepted"
        )
    invitation.revoked_at = datetime.now(UTC)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="org.invitation.revoked",
        object_type="invitation",
        object_id=str(invitation.id),
    )
    await db.commit()
    await db.refresh(invitation)
    return invitation
