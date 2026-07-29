from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.models import Membership, MembershipRole, Organization, Role
from app.core.schemas import MembershipOut, OrganizationSettingsOut, OrganizationSettingsUpdate
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission

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
