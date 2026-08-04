"""AI Recommendation Engine (spec §87). Each generator below scans this
org's own real rows and, if a genuine condition holds, produces one
`RecommendationDraft` naming the exact sources it came from — never an
invented suggestion. `estimated_value` is populated only when it can be
derived from a real historical average already computed elsewhere
(Sales Intelligence's `average_deal_size`); every other recommendation
honestly leaves it unset rather than fabricating a figure, the same
discipline `app.reporting.content`'s Automation ROI report follows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.analytics import compute_workflow_analytics
from app.compliance.models import Control
from app.recommendations.models import Recommendation
from app.sales.intelligence import compute_sales_intelligence
from app.sales.lead_finder import MIN_ICP_SCORE_FOR_MATCH, OPEN_LEAD_STATUSES
from app.sales.models import Account, Lead
from app.secops.models import SecurityFinding
from app.support.analytics import compute_support_analytics


@dataclass
class RecommendationDraft:
    source_key: str
    category: str
    title: str
    business_impact: str
    reason: str
    sources: list[str]
    confidence: str
    estimated_value: str | None
    suggested_action: str
    risk: str
    required_approval: bool


async def _count(db: AsyncSession, stmt: Any) -> int:
    result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    return int(result.scalar_one())


async def _compliance_gaps(db: AsyncSession, organization_id: uuid.UUID) -> RecommendationDraft | None:
    gaps_result = await db.execute(
        select(Control)
        .where(Control.organization_id == organization_id, Control.status == "not_started")
        .order_by(Control.created_at.desc())
        .limit(5)
    )
    gaps = list(gaps_result.scalars().all())
    if not gaps:
        return None
    total = await _count(
        db, select(Control.id).where(Control.organization_id == organization_id, Control.status == "not_started")
    )
    return RecommendationDraft(
        source_key="compliance_gaps",
        category="compliance",
        title=f"Address {total} compliance control gap{'s' if total != 1 else ''}",
        business_impact="Unimplemented controls reduce your compliance posture and framework coverage.",
        reason=f"{total} control{'s' if total != 1 else ''} in your framework catalog have not been started.",
        sources=[f"control:{c.id}" for c in gaps],
        confidence="high",
        estimated_value=None,
        suggested_action="Review and assign owners to the unimplemented controls.",
        risk="medium",
        required_approval=False,
    )


async def _security_critical_findings(
    db: AsyncSession, organization_id: uuid.UUID
) -> RecommendationDraft | None:
    findings_result = await db.execute(
        select(SecurityFinding)
        .where(
            SecurityFinding.organization_id == organization_id,
            SecurityFinding.severity.in_(["critical", "high"]),
            SecurityFinding.status == "open",
        )
        .order_by(SecurityFinding.created_at.desc())
        .limit(5)
    )
    findings = list(findings_result.scalars().all())
    if not findings:
        return None
    total = await _count(
        db,
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == organization_id,
            SecurityFinding.severity.in_(["critical", "high"]),
            SecurityFinding.status == "open",
        ),
    )
    return RecommendationDraft(
        source_key="security_critical_findings",
        category="security",
        title=f"Remediate {total} critical/high security finding{'s' if total != 1 else ''}",
        business_impact="Open critical/high findings are the biggest deductions in your Security Score.",
        reason=f"{total} finding{'s' if total != 1 else ''} at critical or high severity remain open.",
        sources=[f"security_finding:{f.id}" for f in findings],
        confidence="high",
        estimated_value=None,
        suggested_action="Triage and remediate the open critical/high findings.",
        risk="high",
        required_approval=False,
    )


async def _sales_icp_no_lead(db: AsyncSession, organization_id: uuid.UUID) -> RecommendationDraft | None:
    accounts_result = await db.execute(
        select(Account)
        .where(
            Account.organization_id == organization_id,
            Account.icp_score >= MIN_ICP_SCORE_FOR_MATCH,
        )
        .order_by(Account.icp_score.desc())
    )
    accounts = list(accounts_result.scalars().all())
    if not accounts:
        return None
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
    untouched = [a for a in accounts if a.id not in accounts_with_open_leads]
    if not untouched:
        return None

    intelligence = await compute_sales_intelligence(db, organization_id=organization_id)
    average_deal_size = float(intelligence["average_deal_size"])
    estimated_value = (
        f"~€{average_deal_size * len(untouched):,.0f} potential (based on your average deal size)"
        if average_deal_size > 0
        else None
    )
    return RecommendationDraft(
        source_key="sales_icp_no_lead",
        category="sales",
        title=f"{len(untouched)} high-fit account{'s' if len(untouched) != 1 else ''} "
        f"{'have' if len(untouched) != 1 else 'has'} no active lead",
        business_impact="Accounts matching your Ideal Customer Profile are not being pursued.",
        reason="These accounts score at or above your ICP match threshold with no open Lead tracking them.",
        sources=[f"account:{a.id}" for a in untouched[:5]],
        confidence="medium",
        estimated_value=estimated_value,
        suggested_action="Create leads for these accounts and enroll them in an outreach sequence.",
        risk="low",
        required_approval=False,
    )


async def _automation_failures(db: AsyncSession, organization_id: uuid.UUID) -> RecommendationDraft | None:
    analytics = await compute_workflow_analytics(db, organization_id=organization_id)
    total_runs = int(analytics["total_runs"])
    success_rate = float(analytics["success_rate_percent"])
    if total_runs < 5 or success_rate >= 80.0:
        return None
    failure_rate = round(100 - success_rate, 1)
    return RecommendationDraft(
        source_key="automation_failures",
        category="automation",
        title=f"Automation workflows are failing {failure_rate}% of the time",
        business_impact="Failing workflow runs mean manual staff time is still being spent on work meant to be automated.",
        reason=f"{success_rate}% success rate across {total_runs} runs, below the 80% healthy threshold.",
        sources=["automation_analytics"],
        confidence="high",
        estimated_value=None,
        suggested_action="Review failing runs and fix the underlying step configuration.",
        risk="medium",
        required_approval=False,
    )


async def _support_satisfaction(db: AsyncSession, organization_id: uuid.UUID) -> RecommendationDraft | None:
    analytics = await compute_support_analytics(db, organization_id=organization_id)
    csat_count = int(analytics["csat_response_count"])
    average_csat = float(analytics["average_csat"])
    if csat_count < 3 or average_csat >= 3.5:
        return None
    return RecommendationDraft(
        source_key="support_satisfaction",
        category="support",
        title=f"Customer satisfaction is trending low ({average_csat}/5)",
        business_impact="Low CSAT is an early indicator of churn risk.",
        reason=f"Average CSAT across {csat_count} response{'s' if csat_count != 1 else ''} is {average_csat}/5,"
        " below the 3.5 healthy threshold.",
        sources=["support_analytics"],
        confidence="medium",
        estimated_value=None,
        suggested_action="Review recent low-scoring tickets for a common root cause.",
        risk="medium",
        required_approval=False,
    )


_GENERATORS = [
    _compliance_gaps,
    _security_critical_findings,
    _sales_icp_no_lead,
    _automation_failures,
    _support_satisfaction,
]


async def refresh_recommendations(db: AsyncSession, *, organization_id: uuid.UUID) -> None:
    """Recomputes every generator and upserts real, active recommendations.
    A recommendation the user already `dismissed` or `actioned` is never
    overwritten or resurrected — refreshing only ever touches `new` rows
    (to keep their content current) or inserts a genuinely new one."""
    existing_result = await db.execute(
        select(Recommendation).where(Recommendation.organization_id == organization_id)
    )
    existing_by_key = {r.source_key: r for r in existing_result.scalars().all()}

    for generator in _GENERATORS:
        draft = await generator(db, organization_id)
        existing = existing_by_key.get(draft.source_key if draft else "")
        if draft is None:
            continue
        if existing is None:
            db.add(
                Recommendation(
                    organization_id=organization_id,
                    source_key=draft.source_key,
                    category=draft.category,
                    title=draft.title,
                    business_impact=draft.business_impact,
                    reason=draft.reason,
                    sources=draft.sources,
                    confidence=draft.confidence,
                    estimated_value=draft.estimated_value,
                    suggested_action=draft.suggested_action,
                    risk=draft.risk,
                    required_approval=draft.required_approval,
                )
            )
        elif existing.status == "new":
            existing.title = draft.title
            existing.business_impact = draft.business_impact
            existing.reason = draft.reason
            existing.sources = draft.sources
            existing.confidence = draft.confidence
            existing.estimated_value = draft.estimated_value
            existing.suggested_action = draft.suggested_action
            existing.risk = draft.risk
            existing.required_approval = draft.required_approval
    await db.commit()


async def list_recommendations(db: AsyncSession, *, organization_id: uuid.UUID) -> list[Recommendation]:
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.organization_id == organization_id, Recommendation.status == "new")
        .order_by(Recommendation.created_at.desc())
    )
    return list(result.scalars().all())


async def set_recommendation_status(
    db: AsyncSession, *, organization_id: uuid.UUID, recommendation_id: uuid.UUID, status: str
) -> Recommendation | None:
    """Sets the status and flushes (does not commit) — the caller commits
    once, together with its own audit_event write, so both land in one
    transaction."""
    recommendation = await db.get(Recommendation, recommendation_id)
    if recommendation is None or recommendation.organization_id != organization_id:
        return None
    recommendation.status = status
    await db.flush()
    return recommendation
