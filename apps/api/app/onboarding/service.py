"""Onboarding service (spec §68). `compute_readiness` computes the
"Business AI Readiness" output live from real organization data —
Compliance/Security/Sales/Support/Process percentages and named
opportunities — never a hardcoded or randomized number. Each dimension
reuses (or, where no service function existed yet, mirrors) the exact
formula the corresponding module's own dashboard already uses, so the
Onboarding number and, say, the Security Overview page's number never
silently disagree.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Control
from app.identity.models import User
from app.onboarding.models import OnboardingProfile
from app.onboarding.schemas import ReadinessDimensionOut, ReadinessOpportunityOut, ReadinessOut
from app.sales.icp import get_icp_profile
from app.sales.lead_finder import MIN_ICP_SCORE_FOR_MATCH, OPEN_LEAD_STATUSES
from app.sales.models import Account, Lead
from app.secops.service import compute_security_score
from app.support.models import TicketMessage


async def get_or_create_profile(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> OnboardingProfile:
    profile = (
        await db.execute(
            select(OnboardingProfile).where(OnboardingProfile.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = OnboardingProfile(organization_id=organization_id)
        db.add(profile)
        await db.flush()
    return profile


async def _count(db: AsyncSession, stmt) -> int:  # type: ignore[no-untyped-def]
    result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    return int(result.scalar_one())


async def _compliance_percent(db: AsyncSession, organization_id: uuid.UUID) -> tuple[float, int]:
    total = await _count(db, select(Control.id).where(Control.organization_id == organization_id))
    if total == 0:
        return 0.0, 0
    implemented = await _count(
        db,
        select(Control.id).where(
            Control.organization_id == organization_id, Control.status == "implemented"
        ),
    )
    gaps = total - implemented
    return round(100 * implemented / total, 1), gaps


async def _support_automation_percent(db: AsyncSession, organization_id: uuid.UUID) -> float:
    """% of agent-facing reply volume (agent + ai sender types) that was
    an AI-authored, auto-sent message — a real, honest proxy for "how much
    of support is automated" (spec §68's "37% of support questions could
    be automated" example, computed rather than invented)."""
    total_replies = await _count(
        db,
        select(TicketMessage.id).where(
            TicketMessage.organization_id == organization_id,
            TicketMessage.sender_type.in_(["agent", "ai"]),
        ),
    )
    if total_replies == 0:
        return 0.0
    ai_sent = await _count(
        db,
        select(TicketMessage.id).where(
            TicketMessage.organization_id == organization_id,
            TicketMessage.sender_type == "ai",
            TicketMessage.status == "sent",
        ),
    )
    return round(100 * ai_sent / total_replies, 1)


async def _process_automation_percent(db: AsyncSession, organization_id: uuid.UUID) -> float:
    """Reuses Automation Analytics' own success-rate formula rather than
    a separately-computed number — see app.automation.analytics."""
    from app.automation.analytics import compute_workflow_analytics

    analytics = await compute_workflow_analytics(db, organization_id=organization_id)
    return float(analytics["success_rate_percent"])


async def _sales_automation_percent(db: AsyncSession, organization_id: uuid.UUID) -> float:
    from app.sales.intelligence import compute_sales_intelligence

    intelligence = await compute_sales_intelligence(db, organization_id=organization_id)
    return float(intelligence["sequence_completion_rate_percent"])


async def _icp_fit_accounts_without_a_lead(db: AsyncSession, organization_id: uuid.UUID) -> int:
    profile = await get_icp_profile(db, organization_id=organization_id)
    if profile is None:
        return 0
    accounts = list(
        (
            await db.execute(
                select(Account.id).where(
                    Account.organization_id == organization_id,
                    Account.icp_score >= MIN_ICP_SCORE_FOR_MATCH,
                )
            )
        )
        .scalars()
        .all()
    )
    if not accounts:
        return 0
    accounts_with_open_leads = {
        row[0]
        for row in (
            await db.execute(
                select(Lead.account_id).where(
                    Lead.organization_id == organization_id,
                    Lead.status.in_(OPEN_LEAD_STATUSES),
                    Lead.account_id.isnot(None),
                )
            )
        ).all()
    }
    return len([a for a in accounts if a not in accounts_with_open_leads])


async def _admins_without_mfa(db: AsyncSession, organization_id: uuid.UUID) -> int:
    from app.core.models import Membership, MembershipRole, Role

    admins = (
        await db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .join(MembershipRole, MembershipRole.membership_id == Membership.id)
            .join(Role, Role.id == MembershipRole.role_id)
            .where(Membership.organization_id == organization_id, Role.key == "org_admin")
        )
    ).scalars().all()
    return sum(1 for admin in admins if not admin.mfa_enabled)


async def compute_readiness(db: AsyncSession, *, organization_id: uuid.UUID) -> ReadinessOut:
    compliance_percent, compliance_gaps = await _compliance_percent(db, organization_id)
    security_percent = float(await compute_security_score(db, organization_id=organization_id))
    sales_percent = await _sales_automation_percent(db, organization_id)
    support_percent = await _support_automation_percent(db, organization_id)
    process_percent = await _process_automation_percent(db, organization_id)

    opportunities: list[ReadinessOpportunityOut] = []
    if compliance_gaps > 0:
        opportunities.append(
            ReadinessOpportunityOut(
                title=f"Fix {compliance_gaps} compliance control gap"
                f"{'s' if compliance_gaps != 1 else ''}",
                detail="Controls not yet marked implemented across your framework catalog.",
            )
        )
    admins_without_mfa = await _admins_without_mfa(db, organization_id)
    if admins_without_mfa > 0:
        opportunities.append(
            ReadinessOpportunityOut(
                title=f"Enable MFA for {admins_without_mfa} administrator"
                f"{'s' if admins_without_mfa != 1 else ''}",
                detail="Organization Admins without TOTP MFA enrolled.",
            )
        )
    icp_fit_count = await _icp_fit_accounts_without_a_lead(db, organization_id)
    if icp_fit_count > 0:
        opportunities.append(
            ReadinessOpportunityOut(
                title=f"{icp_fit_count} potential high-fit sales account"
                f"{'s' if icp_fit_count != 1 else ''} identified",
                detail="Accounts matching your ICP with no open Lead tracking them.",
            )
        )
    if support_percent < 50:
        opportunities.append(
            ReadinessOpportunityOut(
                title=f"{round(100 - support_percent)}% of support replies are still manual",
                detail="Configure the Support AI Agent to auto-send grounded replies.",
            )
        )
    if process_percent < 80:
        opportunities.append(
            ReadinessOpportunityOut(
                title="Review failing or stalled automation workflow runs",
                detail=f"Current workflow run success rate is {process_percent}%.",
            )
        )

    return ReadinessOut(
        compliance=ReadinessDimensionOut(label="Compliance", percent=compliance_percent),
        security=ReadinessDimensionOut(label="Security", percent=security_percent),
        sales_automation=ReadinessDimensionOut(label="Sales Automation", percent=sales_percent),
        support_automation=ReadinessDimensionOut(
            label="Support Automation", percent=support_percent
        ),
        process_automation=ReadinessDimensionOut(
            label="Process Automation", percent=process_percent
        ),
        opportunities=opportunities,
    )
