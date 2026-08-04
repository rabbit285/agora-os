from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.billing.models import Plan
from app.billing.schemas import OrganizationPlanOut, PlanOut, SetPlanRequest
from app.billing.service import (
    count_active_members,
    get_entitlements,
    set_organization_plan,
)
from app.core.models import Organization
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(db: AsyncSession = Depends(get_db)) -> list[Plan]:
    """Public within an authenticated session (any active member can see
    what each tier includes, the same "show what upgrading gets you"
    transparency a real pricing page would have) — no special permission
    beyond being a member of some organization."""
    result = await db.execute(select(Plan).order_by(Plan.created_at))
    return list(result.scalars().all())


async def _plan_key(db: AsyncSession, organization_id: uuid.UUID) -> str:
    organization = await db.get(Organization, organization_id)
    assert organization is not None
    return organization.plan_key


@router.get("/current", response_model=OrganizationPlanOut)
async def get_current_plan(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> OrganizationPlanOut:
    entitlements = await get_entitlements(db, organization_id=context.organization_id)
    current_users = await count_active_members(db, organization_id=context.organization_id)
    return OrganizationPlanOut(
        plan_key=await _plan_key(db, context.organization_id),
        entitlements=entitlements,
        current_users=current_users,
    )


@router.put("/current", response_model=OrganizationPlanOut)
async def update_current_plan(
    payload: SetPlanRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OrganizationPlanOut:
    """Real plan assignment, no real payment collection behind it — spec
    §64's own "Plans architecture" qualifier (docs/KNOWN_LIMITATIONS.md).
    An org_admin picks their own plan directly rather than going through a
    checkout flow that doesn't exist in this build."""
    before_plan = await _plan_key(db, context.organization_id)
    organization = await set_organization_plan(
        db, organization_id=context.organization_id, plan_key=payload.plan_key
    )
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="billing.plan.changed",
        object_type="organization",
        object_id=str(organization.id),
        before_state={"plan_key": before_plan},
        after_state={"plan_key": organization.plan_key},
    )
    await db.commit()
    entitlements = await get_entitlements(db, organization_id=context.organization_id)
    current_users = await count_active_members(db, organization_id=context.organization_id)
    return OrganizationPlanOut(
        plan_key=organization.plan_key, entitlements=entitlements, current_users=current_users
    )
