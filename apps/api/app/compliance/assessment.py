"""Framework assessment: turning evidence into an explainable position.

This is the middle of the spec's chain — Control/Evidence go in, a
per-requirement status and a named `ComplianceGap` come out, and a
remediation Task can be raised from the gap and traced back to it.

**The evaluation is deterministic, not generative, and that is the
point.** A language model asked "are we GDPR compliant?" will produce a
confident answer whether or not the evidence supports one, and a
compliance tool that does this is worse than no tool: it manufactures
assurance. Everything here is computed from rows that exist — how many
controls are mapped to a requirement, how much evidence is attached to
them, what the most recent assessment of each concluded. Every status
can be traced to those rows, which is what makes the result defensible
in front of an auditor.

The wording is held to the same standard. A requirement with no evidence
produces "sufficient evidence has not been found", never "you are in
breach". Absence of evidence in this system is evidence of absence *in
this system* — the organization may well hold the document in a filing
cabinet — and the copy keeps that distinction visible to whoever reads
it. Concluding a legal violation is a lawyer's call, not a query's.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import (
    ComplianceGap,
    Control,
    ControlAssessment,
    ControlMapping,
    Evidence,
    Framework,
    FrameworkActivation,
    Requirement,
)
from app.core.models import Task

# Per-requirement conclusions, ordered worst to best. These are states of
# *our knowledge*, not verdicts: "satisfied" means the evidence on file
# supports the requirement, not that a regulator would agree.
REQUIREMENT_STATUSES = ("not_assessed", "evidence_missing", "needs_review", "partial", "satisfied")

GAP_SEVERITY_BY_KIND = {
    "no_control": "high",
    "evidence_missing": "high",
    "assessment_failed": "high",
    "evidence_partial": "medium",
}

# What a complete answer to a specific requirement actually contains.
# Regulatory text, not model output — Article 30(1) really does enumerate
# these fields, so listing them is quoting the law rather than guessing.
# Keyed by "<framework key>:<reference code>"; anything absent falls back
# to the generic recommendation.
REMEDIATION_HINTS: dict[str, str] = {
    "gdpr:Art. 30": (
        "Prepare and approve a Record of Processing Activities covering, for each activity: "
        "the processing purposes; the categories of data subjects and of personal data; the "
        "categories of recipients; any transfers to third countries and the safeguards applied; "
        "the envisaged retention periods; and a general description of the technical and "
        "organisational security measures. Attach the approved record as evidence."
    ),
    "gdpr:Art. 33": (
        "Document a personal data breach procedure covering detection, assessment against the "
        "72-hour notification threshold, the internal escalation path, the content of a "
        "supervisory-authority notification, when data subjects must be informed, and the "
        "internal breach register. Attach the approved procedure as evidence."
    ),
    "gdpr:Art. 35": (
        "Document how processing operations are screened for high risk and how a DPIA is carried "
        "out when the screening indicates one is required, including the description of the "
        "processing, the necessity and proportionality assessment, the risks to data subjects, "
        "the mitigating measures, and the DPO consultation. Attach the screening procedure and a "
        "completed DPIA as evidence."
    ),
    "gdpr:Art. 5": (
        "Document how lawfulness, fairness and transparency, purpose limitation, data "
        "minimisation, accuracy, storage limitation, integrity and confidentiality, and "
        "accountability are applied in practice. A privacy notice and data processing agreement "
        "usually evidence the first three; retention schedules and security policy cover the "
        "rest. Attach the approved documents as evidence."
    ),
}


@dataclass(frozen=True)
class RequirementEvaluation:
    """One requirement's computed position, plus the counts behind it.

    The counts travel with the status on purpose: a reader who disagrees
    with the conclusion can see exactly what it was drawn from.
    """

    requirement: Requirement
    status: str
    control_ids: list[uuid.UUID]
    evidence_count: int
    latest_assessment_status: str | None
    summary: str


def _requirement_hint(framework_key: str, reference_code: str) -> str | None:
    return REMEDIATION_HINTS.get(f"{framework_key}:{reference_code}")


async def evaluate_requirement(
    db: AsyncSession, *, organization_id: uuid.UUID, requirement: Requirement
) -> RequirementEvaluation:
    """Compute one requirement's status from the rows that exist."""
    controls = list(
        (
            await db.execute(
                select(Control)
                .join(ControlMapping, ControlMapping.control_id == Control.id)
                .where(
                    ControlMapping.requirement_id == requirement.id,
                    Control.organization_id == organization_id,
                )
            )
        )
        .scalars()
        .all()
    )

    if not controls:
        return RequirementEvaluation(
            requirement=requirement,
            status="not_assessed",
            control_ids=[],
            evidence_count=0,
            latest_assessment_status=None,
            summary=(
                "No control is mapped to this requirement, so there is nothing recorded here to "
                "evaluate. This is a gap in the record, not a finding about the organization."
            ),
        )

    control_ids = [c.id for c in controls]
    evidence_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Evidence)
                .where(
                    Evidence.control_id.in_(control_ids),
                    Evidence.organization_id == organization_id,
                )
            )
        ).scalar_one()
    )

    # Most recent assessment per control; the worst of them decides, since
    # one failing control is enough to make the requirement unproven.
    latest_statuses: list[str] = []
    for control_id in control_ids:
        row = (
            await db.execute(
                select(ControlAssessment.status)
                .where(ControlAssessment.control_id == control_id)
                .order_by(ControlAssessment.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is not None:
            latest_statuses.append(row)

    worst = None
    for candidate in ("fail", "partial", "not_assessed", "pass"):
        if candidate in latest_statuses:
            worst = candidate
            break

    titles = ", ".join(f"'{c.title}'" for c in controls)

    if evidence_count == 0:
        return RequirementEvaluation(
            requirement=requirement,
            status="evidence_missing",
            control_ids=control_ids,
            evidence_count=0,
            latest_assessment_status=worst,
            summary=(
                f"{titles} is mapped to this requirement, but no evidence is attached to it. "
                "Sufficient evidence demonstrating this requirement has not been found in "
                "Veyntra — which is not the same as the requirement being unmet."
            ),
        )

    if worst == "fail":
        return RequirementEvaluation(
            requirement=requirement,
            status="needs_review",
            control_ids=control_ids,
            evidence_count=evidence_count,
            latest_assessment_status=worst,
            summary=(
                f"{titles} has {evidence_count} piece(s) of evidence attached, but its most "
                "recent assessment concluded 'fail'. The evidence on file does not currently "
                "support this requirement."
            ),
        )

    if worst == "pass" and all(c.status == "implemented" for c in controls):
        return RequirementEvaluation(
            requirement=requirement,
            status="satisfied",
            control_ids=control_ids,
            evidence_count=evidence_count,
            latest_assessment_status=worst,
            summary=(
                f"{titles} is implemented, has {evidence_count} piece(s) of evidence attached, "
                "and passed its most recent assessment."
            ),
        )

    return RequirementEvaluation(
        requirement=requirement,
        status="partial",
        control_ids=control_ids,
        evidence_count=evidence_count,
        latest_assessment_status=worst,
        summary=(
            f"{titles} has {evidence_count} piece(s) of evidence attached, but has not been "
            "assessed as passing — the most recent assessment concluded "
            f"'{worst or 'nothing yet'}'. This requirement needs human review."
        ),
    )


def _gap_kind_for(evaluation: RequirementEvaluation) -> str | None:
    return {
        "not_assessed": "no_control",
        "evidence_missing": "evidence_missing",
        "needs_review": "assessment_failed",
        "partial": "evidence_partial",
        "satisfied": None,
    }[evaluation.status]


async def run_framework_assessment(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    framework: Framework,
    actor_user_id: uuid.UUID | None,
) -> list[RequirementEvaluation]:
    """Evaluate every requirement in a framework and reconcile its gaps.

    Re-runnable by design: a requirement that is now satisfied has its gap
    resolved rather than left behind, and one that is still deficient has
    its existing gap updated instead of gaining a duplicate. That is what
    makes "fix it, then reassess" a real loop rather than an append-only
    pile of findings.
    """
    requirements = list(
        (
            await db.execute(
                select(Requirement)
                .where(Requirement.framework_id == framework.id)
                .order_by(Requirement.reference_code)
            )
        )
        .scalars()
        .all()
    )

    evaluations: list[RequirementEvaluation] = []
    for requirement in requirements:
        evaluation = await evaluate_requirement(
            db, organization_id=organization_id, requirement=requirement
        )
        evaluations.append(evaluation)

        existing = (
            await db.execute(
                select(ComplianceGap).where(
                    ComplianceGap.organization_id == organization_id,
                    ComplianceGap.requirement_id == requirement.id,
                )
            )
        ).scalar_one_or_none()

        kind = _gap_kind_for(evaluation)

        if kind is None:
            # Requirement is satisfied. Close any gap still open against
            # it, so reassessment after remediation actually clears.
            if existing is not None and existing.status != "resolved":
                existing.status = "resolved"
                existing.resolved_at = datetime.now(UTC)
                await record_event(
                    db,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    action="compliance.gap.resolved",
                    object_type="compliance_gap",
                    object_id=str(existing.id),
                    after_state={"status": "resolved"},
                )
            continue

        if existing is None:
            gap = ComplianceGap(
                organization_id=organization_id,
                framework_id=framework.id,
                requirement_id=requirement.id,
                control_id=evaluation.control_ids[0] if evaluation.control_ids else None,
                kind=kind,
                severity=GAP_SEVERITY_BY_KIND[kind],
                summary=evaluation.summary,
                status="open",
            )
            db.add(gap)
            await db.flush()
            await record_event(
                db,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="compliance.gap.created",
                object_type="compliance_gap",
                object_id=str(gap.id),
                after_state={"kind": kind, "requirement": requirement.reference_code},
            )
        else:
            existing.kind = kind
            existing.severity = GAP_SEVERITY_BY_KIND[kind]
            existing.summary = evaluation.summary
            existing.control_id = evaluation.control_ids[0] if evaluation.control_ids else None
            # A gap that had been resolved and has regressed is open again;
            # one already being worked keeps its `remediating` status so a
            # reassessment does not discard that context.
            if existing.status == "resolved":
                existing.status = "open"
                existing.resolved_at = None

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.framework.assessed",
        object_type="framework",
        object_id=str(framework.id),
        after_state={
            "requirements_evaluated": len(evaluations),
            "satisfied": sum(1 for e in evaluations if e.status == "satisfied"),
        },
    )
    return evaluations


async def generate_remediation(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    gap: ComplianceGap,
    actor_user_id: uuid.UUID | None,
) -> ComplianceGap:
    """Write a concrete recommendation onto a gap.

    Assembled from the requirement's own text plus, where we have one, a
    hint enumerating what a complete answer contains. Both are drawn from
    the regulation rather than generated, so the advice cannot drift into
    invention on a subject where invention is harmful.
    """
    requirement = await db.get(Requirement, gap.requirement_id)
    framework = await db.get(Framework, gap.framework_id)
    assert requirement is not None and framework is not None

    hint = _requirement_hint(framework.key, requirement.reference_code)

    if gap.kind == "no_control":
        opening = (
            f"Define a control describing how the organization meets {requirement.reference_code} "
            f"({requirement.title}), map it to this requirement, and attach the documents that "
            "demonstrate it."
        )
    elif gap.kind == "evidence_missing":
        opening = (
            "Attach the documents that demonstrate this control to it as evidence. Until "
            "something is attached, this requirement cannot be shown as met from within Veyntra."
        )
    elif gap.kind == "assessment_failed":
        opening = (
            "The most recent assessment of the mapped control concluded 'fail'. Address the "
            "finding recorded on that assessment, attach the corrected evidence, and reassess."
        )
    else:
        opening = (
            "Review the evidence attached to the mapped control, confirm it covers this "
            "requirement in full, and record a passing assessment against it."
        )

    gap.recommendation = f"{opening}\n\n{hint}" if hint else opening

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.gap.remediation_generated",
        object_type="compliance_gap",
        object_id=str(gap.id),
    )
    return gap


async def create_task_from_gap(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    gap: ComplianceGap,
    actor_user_id: uuid.UUID | None,
    title: str | None = None,
    assignee_id: uuid.UUID | None = None,
    priority: str = "high",
    due_in_days: int = 7,
) -> Task:
    """Raise a remediation Task that points back at the gap.

    `entity_type`/`entity_id` are set to the gap rather than left null,
    which is what lets the Tasks module answer "why does this task exist?"
    without the answer having to be re-read out of the title.
    """
    requirement = await db.get(Requirement, gap.requirement_id)
    assert requirement is not None

    task = Task(
        organization_id=organization_id,
        title=title or f"Remediate {requirement.reference_code}: {requirement.title}",
        description=gap.recommendation or gap.summary,
        module="compliance",
        entity_type="compliance_gap",
        # Task.entity_id is a String column, not a Uuid — it is a generic
        # pointer shared by every module, so it stores the id as text.
        entity_id=str(gap.id),
        priority=priority,
        status="open",
        assignee_id=assignee_id,
        created_by=actor_user_id,
        due_at=datetime.now(UTC) + timedelta(days=due_in_days),
    )
    db.add(task)
    await db.flush()

    gap.task_id = task.id
    gap.status = "remediating"

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.gap.task_created",
        object_type="compliance_gap",
        object_id=str(gap.id),
        after_state={"task_id": str(task.id)},
    )
    return task


async def set_framework_activation(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    framework: Framework,
    active: bool,
    actor_user_id: uuid.UUID | None,
) -> FrameworkActivation:
    """Adopt or stand down a framework for one organization."""
    activation = (
        await db.execute(
            select(FrameworkActivation).where(
                FrameworkActivation.organization_id == organization_id,
                FrameworkActivation.framework_id == framework.id,
            )
        )
    ).scalar_one_or_none()

    if activation is None:
        activation = FrameworkActivation(
            organization_id=organization_id,
            framework_id=framework.id,
            status="active" if active else "inactive",
            activated_at=datetime.now(UTC) if active else None,
            activated_by=actor_user_id if active else None,
        )
        db.add(activation)
        await db.flush()
    else:
        activation.status = "active" if active else "inactive"
        if active:
            activation.activated_at = datetime.now(UTC)
            activation.activated_by = actor_user_id

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.framework.activated" if active else "compliance.framework.deactivated",
        object_type="framework",
        object_id=str(framework.id),
        after_state={"status": activation.status},
    )
    return activation


async def active_framework_ids(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> set[uuid.UUID]:
    rows = (
        await db.execute(
            select(FrameworkActivation.framework_id).where(
                FrameworkActivation.organization_id == organization_id,
                FrameworkActivation.status == "active",
            )
        )
    ).scalars()
    return set(rows.all())
