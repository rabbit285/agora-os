"""The executive view: where we stand, what is wrong, what to do next.

Written for someone who is accountable for compliance but does not work
in it daily — a founder or a CTO who needs to answer an enterprise buyer
this week. That reader is badly served by a table of controls, and worse
served by a single percentage with nothing behind it.

So every figure here is either clickable through to the thing it counts,
or carries the arithmetic that produced it. Nothing is a hardcoded
target, and nothing is a model's opinion: readiness is computed from
approved evidence, gaps come from assessments, and recent activity is
read from the audit trail rather than narrated.

`recommended_next_actions` is the one piece of judgement, and it is rules
over the same state — ordered by what unblocks the most work, not by what
looks impressive.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance.ai_system_governance import assess_ai_system
from app.compliance.assessment import evaluate_framework, summarize_readiness
from app.compliance.models import (
    AISystem,
    ComplianceGap,
    EvidenceSuggestion,
    Framework,
    FrameworkActivation,
    Risk,
)
from app.core.models import Task

ACTIVITY_WINDOW = timedelta(days=7)

# Audit actions worth reporting back as "what the AI did", mapped to the
# phrasing a non-specialist reads without a glossary. Anything not listed
# is deliberately absent: a feed that reports every internal state change
# is noise, and noise here trains people to ignore the panel.
ACTIVITY_LABELS: dict[str, str] = {
    "compliance.evidence.suggestions_generated": "document{s} analysed for evidence",
    "compliance.evidence.suggestion_auto_approved": "evidence mapping{s} accepted automatically",
    "compliance.evidence.suggestion_approved": "evidence mapping{s} you approved",
    "compliance.evidence.suggestion_rejected": "evidence mapping{s} you rejected",
    "compliance.framework.assessed": "framework assessment{s} run",
    "compliance.gap.resolved": "gap{s} resolved",
    "compliance.gap.created": "new gap{s} identified",
    "compliance.gap.remediation_generated": "remediation{s} proposed",
    "compliance.framework.activated": "framework{s} adopted",
}


@dataclass
class ActivityLine:
    count: int
    label: str


@dataclass
class NextAction:
    title: str
    detail: str
    href: str
    priority: str


@dataclass
class FrameworkStatus:
    framework_id: uuid.UUID
    key: str
    name: str
    readiness_percent: float
    explanation: str
    open_gap_count: int


@dataclass
class SystemAtRisk:
    ai_system_id: uuid.UUID
    name: str
    risk_classification: str
    readiness_percent: float
    open_action_count: int


@dataclass
class ComplianceDashboard:
    readiness_percent: float
    readiness_explanation: str
    critical_gap_count: int
    open_risk_count: int
    ai_system_count: int
    high_risk_ai_system_count: int
    overdue_action_count: int

    frameworks: list[FrameworkStatus] = field(default_factory=list)
    critical_issues: list[NextAction] = field(default_factory=list)
    systems_at_risk: list[SystemAtRisk] = field(default_factory=list)
    recent_activity: list[ActivityLine] = field(default_factory=list)
    recommended_next_actions: list[NextAction] = field(default_factory=list)


def _plural(count: int) -> str:
    return "" if count == 1 else "s"


async def _recent_activity(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[ActivityLine]:
    """What actually happened, read from the audit trail.

    Counted from recorded events rather than narrated, so the panel can
    never claim work that did not happen — which is the failure mode that
    would make every other number here suspect.
    """
    since = datetime.now(UTC) - ACTIVITY_WINDOW
    rows = (
        await db.execute(
            select(AuditEvent.action, func.count(AuditEvent.id))
            .where(
                AuditEvent.organization_id == organization_id,
                AuditEvent.action.in_(list(ACTIVITY_LABELS)),
                AuditEvent.created_at >= since,
            )
            .group_by(AuditEvent.action)
        )
    ).all()

    lines = [
        ActivityLine(
            count=int(count),
            label=ACTIVITY_LABELS[action].format(s=_plural(int(count))),
        )
        for action, count in rows
        if count
    ]
    return sorted(lines, key=lambda line: line.count, reverse=True)


def _next_actions(
    *,
    frameworks: list[FrameworkStatus],
    proposals_awaiting: int,
    unscreened_systems: int,
    overdue_actions: int,
    critical_gaps: int,
    facts_declared: bool,
) -> list[NextAction]:
    """What to do next, ordered by what unblocks the most work.

    Rules over the same state the rest of the dashboard reports. The
    ordering is the opinion: adopting a framework comes before reviewing
    proposals because with no framework there is nothing to propose
    against, and reviewing proposals comes before chasing gaps because
    approving evidence can close gaps without any remediation at all.
    """
    actions: list[NextAction] = []

    if not facts_declared:
        actions.append(
            NextAction(
                title="Tell Veyntra about your company",
                detail=(
                    "Eight questions decide which frameworks you are held to. Until then we "
                    "cannot tell you what applies."
                ),
                href="/compliance",
                priority="high",
            )
        )
    elif not frameworks:
        actions.append(
            NextAction(
                title="Adopt your first framework",
                detail="Adopting one builds the control set your documents map to.",
                href="/compliance",
                priority="high",
            )
        )

    if proposals_awaiting:
        actions.append(
            NextAction(
                title=f"Review {proposals_awaiting} evidence mapping{_plural(proposals_awaiting)}",
                detail=(
                    "Approving evidence can close gaps without any remediation work, so this "
                    "is usually the cheapest way to move readiness."
                ),
                href="/review",
                priority="high",
            )
        )

    if unscreened_systems:
        actions.append(
            NextAction(
                title=f"Screen {unscreened_systems} AI system{_plural(unscreened_systems)}",
                detail=(
                    "Their risk tier decides which EU AI Act obligations apply, and it has "
                    "not been established from how they are actually used."
                ),
                href="/ai-systems",
                priority="high" if unscreened_systems > 1 else "medium",
            )
        )

    if overdue_actions:
        actions.append(
            NextAction(
                title=f"Chase {overdue_actions} overdue remediation task{_plural(overdue_actions)}",
                detail="Past their due date and still open.",
                href="/tasks",
                priority="high",
            )
        )

    if critical_gaps and not proposals_awaiting:
        actions.append(
            NextAction(
                title=f"Close {critical_gaps} high-severity gap{_plural(critical_gaps)}",
                detail=(
                    "Each names the evidence it needs. Upload it and the assessment re-runs "
                    "on its own."
                ),
                href="/compliance",
                priority="medium",
            )
        )

    return actions


async def build_dashboard(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    facts_declared: bool = False,
) -> ComplianceDashboard:
    active_frameworks = list(
        (
            await db.execute(
                select(Framework)
                .join(FrameworkActivation, FrameworkActivation.framework_id == Framework.id)
                .where(
                    FrameworkActivation.organization_id == organization_id,
                    FrameworkActivation.status == "active",
                )
                .order_by(Framework.name)
            )
        )
        .scalars()
        .all()
    )

    gaps = list(
        (
            await db.execute(
                select(ComplianceGap).where(
                    ComplianceGap.organization_id == organization_id,
                    ComplianceGap.status != "resolved",
                )
            )
        )
        .scalars()
        .all()
    )
    gaps_by_framework: dict[uuid.UUID, int] = {}
    for gap in gaps:
        gaps_by_framework[gap.framework_id] = gaps_by_framework.get(gap.framework_id, 0) + 1

    statuses: list[FrameworkStatus] = []
    weighted_total = 0.0
    requirement_total = 0
    for framework in active_frameworks:
        evaluations = await evaluate_framework(
            db, organization_id=organization_id, framework=framework
        )
        breakdown = summarize_readiness(evaluations)
        statuses.append(
            FrameworkStatus(
                framework_id=framework.id,
                key=framework.key,
                name=framework.name,
                readiness_percent=breakdown.percent,
                explanation=breakdown.explanation,
                open_gap_count=gaps_by_framework.get(framework.id, 0),
            )
        )
        # Weighted by requirement count, not a flat average across
        # frameworks: a 2-requirement framework at 100% should not drag an
        # overall figure to the same degree as a 25-requirement one.
        weighted_total += breakdown.percent * breakdown.total
        requirement_total += breakdown.total

    readiness = round(weighted_total / requirement_total, 1) if requirement_total else 0.0
    if statuses:
        readiness_explanation = (
            f"{readiness}% across {len(statuses)} adopted framework{_plural(len(statuses))}, "
            f"weighted by their {requirement_total} requirements. This measures the evidence "
            "held in Veyntra, not a legal conclusion about compliance."
        )
    else:
        readiness_explanation = (
            "No framework adopted yet, so there is nothing to measure against."
        )

    systems = list(
        (
            await db.execute(
                select(AISystem).where(AISystem.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    governance = [await assess_ai_system(db, system=system) for system in systems]
    at_risk = sorted(
        (
            SystemAtRisk(
                ai_system_id=row.ai_system_id,
                name=row.name,
                risk_classification=row.risk_classification,
                readiness_percent=row.readiness_percent,
                open_action_count=len(row.required_actions),
            )
            for row in governance
            if row.required_actions
        ),
        key=lambda row: (-row.open_action_count, row.readiness_percent),
    )[:5]

    open_risks = int(
        await db.scalar(
            select(func.count(Risk.id)).where(
                Risk.organization_id == organization_id, Risk.status == "open"
            )
        )
        or 0
    )
    overdue = int(
        await db.scalar(
            select(func.count(Task.id)).where(
                Task.organization_id == organization_id,
                Task.status.in_(("open", "in_progress")),
                Task.due_at.is_not(None),
                Task.due_at < datetime.now(UTC),
            )
        )
        or 0
    )
    proposals_awaiting = int(
        await db.scalar(
            select(func.count(EvidenceSuggestion.id)).where(
                EvidenceSuggestion.organization_id == organization_id,
                EvidenceSuggestion.status == "proposed",
            )
        )
        or 0
    )

    critical_gaps = [gap for gap in gaps if gap.severity == "high"]
    # Deduplicated by summary. One control mapped to six requirements
    # produces six gaps saying the same sentence, and showing that
    # sentence five times reads as five problems when it is one.
    critical_issues: list[NextAction] = []
    seen_summaries: set[str] = set()
    for gap in critical_gaps:
        summary = gap.summary[:140]
        if summary in seen_summaries:
            continue
        seen_summaries.add(summary)
        critical_issues.append(
            NextAction(
                title=summary,
                detail=gap.recommendation or "No remediation recorded yet.",
                href="/compliance",
                priority="high",
            )
        )
        if len(critical_issues) == 5:
            break

    return ComplianceDashboard(
        readiness_percent=readiness,
        readiness_explanation=readiness_explanation,
        critical_gap_count=len(critical_gaps),
        open_risk_count=open_risks,
        ai_system_count=len(systems),
        high_risk_ai_system_count=sum(
            1 for row in governance if row.risk_classification in ("high", "unacceptable")
        ),
        overdue_action_count=overdue,
        frameworks=statuses,
        critical_issues=critical_issues,
        systems_at_risk=at_risk,
        recent_activity=await _recent_activity(db, organization_id),
        recommended_next_actions=_next_actions(
            frameworks=statuses,
            proposals_awaiting=proposals_awaiting,
            unscreened_systems=sum(1 for row in governance if not row.has_current_screening),
            overdue_actions=overdue,
            critical_gaps=len(critical_gaps),
            facts_declared=facts_declared,
        ),
    )


__all__ = [
    "ACTIVITY_LABELS",
    "ACTIVITY_WINDOW",
    "ActivityLine",
    "ComplianceDashboard",
    "FrameworkStatus",
    "NextAction",
    "SystemAtRisk",
    "build_dashboard",
]
