from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import OrgContext, require_permission
from app.onboarding.models import OnboardingProfile
from app.onboarding.schemas import (
    CompanyStepUpdate,
    ComplianceProfileStepUpdate,
    GoalsStepUpdate,
    OnboardingProfileOut,
    ReadinessOut,
    SalesProfileStepUpdate,
    SecurityProfileStepUpdate,
    SupportProfileStepUpdate,
)
from app.onboarding.service import compute_readiness, get_or_create_profile

router = APIRouter(prefix="/api/v1/onboarding", tags=["onboarding"])


@router.get("/status", response_model=OnboardingProfileOut)
async def get_status(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OnboardingProfile:
    return await get_or_create_profile(db, organization_id=context.organization_id)


async def _advance(profile: OnboardingProfile, step: int) -> None:
    if profile.current_step <= step:
        profile.current_step = step + 1


@router.put("/company", response_model=OnboardingProfileOut)
async def update_company_step(
    payload: CompanyStepUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OnboardingProfile:
    profile = await get_or_create_profile(db, organization_id=context.organization_id)
    profile.industry = payload.industry
    profile.employee_count_range = payload.employee_count_range
    await _advance(profile, 1)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.put("/goals", response_model=OnboardingProfileOut)
async def update_goals_step(
    payload: GoalsStepUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OnboardingProfile:
    profile = await get_or_create_profile(db, organization_id=context.organization_id)
    profile.selected_goals = payload.selected_goals
    await _advance(profile, 2)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.put("/compliance-profile", response_model=OnboardingProfileOut)
async def update_compliance_profile_step(
    payload: ComplianceProfileStepUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OnboardingProfile:
    profile = await get_or_create_profile(db, organization_id=context.organization_id)
    profile.selected_framework_keys = payload.selected_framework_keys
    await _advance(profile, 3)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.put("/security-profile", response_model=OnboardingProfileOut)
async def update_security_profile_step(
    payload: SecurityProfileStepUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OnboardingProfile:
    profile = await get_or_create_profile(db, organization_id=context.organization_id)
    profile.primary_cloud_provider = payload.primary_cloud_provider
    await _advance(profile, 4)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.put("/sales-profile", response_model=OnboardingProfileOut)
async def update_sales_profile_step(
    payload: SalesProfileStepUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OnboardingProfile:
    profile = await get_or_create_profile(db, organization_id=context.organization_id)
    profile.sales_focus = payload.sales_focus
    await _advance(profile, 5)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.put("/support-profile", response_model=OnboardingProfileOut)
async def update_support_profile_step(
    payload: SupportProfileStepUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OnboardingProfile:
    profile = await get_or_create_profile(db, organization_id=context.organization_id)
    profile.support_channels = payload.support_channels
    await _advance(profile, 6)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.post("/advance", response_model=OnboardingProfileOut)
async def advance_step(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OnboardingProfile:
    """Steps 8 ("Connect tools") and 9 ("Upload knowledge") have no fields
    of their own — they link to the real Integrations/Knowledge pages —
    so the frontend just calls this to move past them."""
    profile = await get_or_create_profile(db, organization_id=context.organization_id)
    await _advance(profile, profile.current_step)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/readiness", response_model=ReadinessOut)
async def get_readiness(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> ReadinessOut:
    """Step 10's "Business AI Readiness" — computed live from real
    organization data every time, never stored (spec §68)."""
    return await compute_readiness(db, organization_id=context.organization_id)


@router.post("/complete", response_model=OnboardingProfileOut)
async def complete_onboarding(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OnboardingProfile:
    profile = await get_or_create_profile(db, organization_id=context.organization_id)
    profile.completed_at = datetime.now(UTC)
    profile.current_step = 10
    await db.commit()
    await db.refresh(profile)
    return profile
