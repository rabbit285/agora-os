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

from app.compliance.models import Control, Evidence, Framework, FrameworkActivation
from app.identity.models import User
from app.onboarding.models import OnboardingProfile
from app.onboarding.schemas import ReadinessDimensionOut, ReadinessOpportunityOut, ReadinessOut
from app.secops.service import compute_security_score


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


async def _evidence_coverage_percent(db: AsyncSession, organization_id: uuid.UUID) -> float:
    """Share of this organization's controls with at least one piece of
    evidence attached.

    Distinct from the compliance percentage above, which counts controls
    marked implemented. A control someone ticked as implemented but never
    evidenced is exactly the gap an auditor finds first, so the two are
    reported separately rather than averaged into one reassuring number.
    """
    total = await _count(db, select(Control.id).where(Control.organization_id == organization_id))
    if total == 0:
        return 0.0
    with_evidence = await _count(
        db,
        select(Control.id)
        .join(Evidence, Evidence.control_id == Control.id)
        .where(Control.organization_id == organization_id)
        .distinct(),
    )
    return round(100 * with_evidence / total, 1)


async def _framework_adoption_percent(
    db: AsyncSession, organization_id: uuid.UUID
) -> tuple[float, int]:
    """How much of the framework catalog this organization has adopted.

    Returns the percentage and the number still inactive, so the caller can
    turn "none adopted" into an actionable next step rather than a bare
    zero."""
    total = await _count(db, select(Framework.id).where(Framework.organization_id.is_(None)))
    if total == 0:
        return 0.0, 0
    active = await _count(
        db,
        select(FrameworkActivation.id).where(
            FrameworkActivation.organization_id == organization_id,
            FrameworkActivation.status == "active",
        ),
    )
    return round(100 * active / total, 1), total - active

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
    evidence_percent = await _evidence_coverage_percent(db, organization_id)
    framework_percent, inactive_frameworks = await _framework_adoption_percent(
        db, organization_id
    )
    security_percent = float(await compute_security_score(db, organization_id=organization_id))

    opportunities: list[ReadinessOpportunityOut] = []
    if framework_percent == 0.0:
        # Listed first when it applies: with no framework adopted there are
        # no controls, so every other number below is zero for the same
        # single reason and fixing this is what unblocks them.
        opportunities.append(
            ReadinessOpportunityOut(
                title="Adopt your first framework",
                detail=(
                    "Activating GDPR, the EU AI Act or ISO 27001 builds the control set "
                    "your evidence attaches to."
                ),
            )
        )
    elif inactive_frameworks > 0:
        opportunities.append(
            ReadinessOpportunityOut(
                title=f"{inactive_frameworks} framework"
                f"{'s are' if inactive_frameworks != 1 else ' is'} still inactive",
                detail="Adopt the ones you are held to so their requirements are assessed.",
            )
        )
    if evidence_percent < 100:
        opportunities.append(
            ReadinessOpportunityOut(
                title="Upload a policy and let Veyntra map it",
                detail=(
                    f"{round(100 - evidence_percent)}% of your controls have no evidence "
                    "attached. Document intelligence proposes the mappings for you."
                ),
            )
        )
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

    return ReadinessOut(
        compliance=ReadinessDimensionOut(label="Controls implemented", percent=compliance_percent),
        evidence_coverage=ReadinessDimensionOut(
            label="Evidence coverage", percent=evidence_percent
        ),
        framework_adoption=ReadinessDimensionOut(
            label="Frameworks adopted", percent=framework_percent
        ),
        security=ReadinessDimensionOut(label="Security", percent=security_percent),
        opportunities=opportunities,
    )
