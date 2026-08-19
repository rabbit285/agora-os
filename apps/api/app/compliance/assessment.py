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
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
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
from app.compliance.control_library import templates_for_framework
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


@dataclass
class ReadinessBreakdown:
    """A readiness percentage together with the arithmetic behind it.

    A bare "68%" is not usable by the person accountable for it — their
    next question is always "which ones, and what do I do". Every count
    here is a number the user can click through to a list, and
    `explanation` is assembled from those same counts so the sentence can
    never drift from the figure it explains.
    """

    percent: float
    satisfied: int
    partial: int
    needs_review: int
    evidence_missing: int
    not_assessed: int
    total: int
    explanation: str


# Weights for partial credit. A requirement with evidence that has not
# passed assessment is genuinely further along than one with no evidence
# at all, and scoring both zero tells the user their work achieved
# nothing. Deliberately conservative: only a `satisfied` requirement
# earns full credit, so the number can never overstate the position.
READINESS_WEIGHTS = {
    "satisfied": 1.0,
    "partial": 0.5,
    "needs_review": 0.25,
    "evidence_missing": 0.0,
    "not_assessed": 0.0,
}


def summarize_readiness(evaluations: list[RequirementEvaluation]) -> ReadinessBreakdown:
    """Turn per-requirement conclusions into an explainable score."""
    counts = {status: 0 for status in REQUIREMENT_STATUSES}
    for evaluation in evaluations:
        counts[evaluation.status] = counts.get(evaluation.status, 0) + 1

    total = len(evaluations)
    if total == 0:
        return ReadinessBreakdown(
            percent=0.0,
            satisfied=0,
            partial=0,
            needs_review=0,
            evidence_missing=0,
            not_assessed=0,
            total=0,
            explanation="This framework has no requirements loaded, so there is nothing to score.",
        )

    earned = sum(READINESS_WEIGHTS.get(e.status, 0.0) for e in evaluations)
    percent = round(100 * earned / total, 1)

    # Built from the counts rather than written prose, so the sentence and
    # the number are always the same calculation.
    parts: list[str] = []
    for status, label in (
        ("satisfied", "satisfied"),
        ("partial", "partially evidenced"),
        ("needs_review", "awaiting human review"),
        ("evidence_missing", "missing evidence"),
        ("not_assessed", "not yet assessed"),
    ):
        count = counts.get(status, 0)
        if count:
            parts.append(f"{count} {label}")

    detail = ", ".join(parts[:-1]) + f" and {parts[-1]}" if len(parts) > 1 else parts[0]
    explanation = (
        f"{percent}% ready because, of {total} requirement"
        f"{'' if total == 1 else 's'}, {detail}. "
        "Partially evidenced requirements count for half and those awaiting review for a "
        "quarter; only fully satisfied requirements count in full. This measures the "
        "evidence held in Veyntra, not a legal conclusion about compliance."
    )

    return ReadinessBreakdown(
        percent=percent,
        satisfied=counts.get("satisfied", 0),
        partial=counts.get("partial", 0),
        needs_review=counts.get("needs_review", 0),
        evidence_missing=counts.get("evidence_missing", 0),
        not_assessed=counts.get("not_assessed", 0),
        total=total,
        explanation=explanation,
    )


def _gap_kind_for(evaluation: RequirementEvaluation) -> str | None:
    return {
        "not_assessed": "no_control",
        "evidence_missing": "evidence_missing",
        "needs_review": "assessment_failed",
        "partial": "evidence_partial",
        "satisfied": None,
    }[evaluation.status]


async def evaluate_framework(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    framework: Framework,
) -> list[RequirementEvaluation]:
    """Evaluate a framework's requirements without touching anything.

    The read-only half of `run_framework_assessment`, which also reconciles
    gaps. Split out because the overview endpoint is a GET read on every
    page load: reconciling gaps there would mean the act of looking at the
    dashboard silently opened and closed findings, and the audit trail
    would fill with events nobody performed.
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
    return [
        await evaluate_requirement(
            db, organization_id=organization_id, requirement=requirement
        )
        for requirement in requirements
    ]

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

    scaffolded = 0
    if active:
        scaffolded = await scaffold_controls_for_framework(
            db,
            organization_id=organization_id,
            framework=framework,
            actor_user_id=actor_user_id,
        )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.framework.activated" if active else "compliance.framework.deactivated",
        object_type="framework",
        object_id=str(framework.id),
        after_state={"status": activation.status, "controls_scaffolded": scaffolded},
    )
    return activation


async def reassess_frameworks_for_control(
    control_id: uuid.UUID,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
) -> list[uuid.UUID]:
    """Re-run the assessment for every active framework this control serves.

    Called after a person approves evidence, so the readiness figure and
    the gap list reflect the decision they just made without them having
    to find the framework screen and press a button. Opens its own session
    because it runs as a background task after the response is sent.

    This does not weaken the rule that a human decides what counts as
    evidence — approval is still the gate, and it still happens by hand.
    What is automated is the arithmetic that follows it, which is
    deterministic: the same approved evidence always yields the same
    conclusion, whether a person triggers the recomputation or an approval
    does. Only active frameworks are touched, so approving evidence never
    revives a framework the organization stood down."""
    from app.db.session import AsyncSessionLocal

    factory = session_factory or AsyncSessionLocal
    assessed: list[uuid.UUID] = []

    async with factory() as db:
        frameworks = list(
            (
                await db.execute(
                    select(Framework)
                    .join(Requirement, Requirement.framework_id == Framework.id)
                    .join(ControlMapping, ControlMapping.requirement_id == Requirement.id)
                    .join(FrameworkActivation, FrameworkActivation.framework_id == Framework.id)
                    .where(
                        ControlMapping.control_id == control_id,
                        FrameworkActivation.organization_id == organization_id,
                        FrameworkActivation.status == "active",
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )

        for framework in frameworks:
            evaluations = await run_framework_assessment(
                db,
                organization_id=organization_id,
                framework=framework,
                actor_user_id=actor_user_id,
            )
            control_ids = {cid for e in evaluations for cid in e.control_ids}
            if control_ids:
                await db.execute(
                    update(Control)
                    .where(
                        Control.id.in_(control_ids),
                        Control.organization_id == organization_id,
                    )
                    .values(needs_reassessment=False)
                )
            assessed.append(framework.id)

        await db.commit()

    return assessed

async def scaffold_controls_for_framework(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    framework: Framework,
    actor_user_id: uuid.UUID | None,
) -> int:
    """Give a newly adopted framework a control set, reusing what exists.

    Without this, adopting GDPR produces requirements with nothing
    attached and the document intelligence has no target to propose
    against — a privacy notice cannot be mapped to Article 13 if no
    control for it exists.

    Controls come from app.compliance.control_library, where one measure
    lists every requirement it supports across frameworks. That matters
    on the second adoption: an organization that already holds "Restrict
    access to personal data" for GDPR gets that same control mapped to
    the ISO 42001 clause too, rather than a duplicate with a different
    name and its own empty evidence list. Their existing evidence starts
    counting immediately, which is the whole argument for adopting a
    second framework here rather than starting again elsewhere.

    Scaffolded controls are created `not_started` with no evidence.
    Adopting a framework must never move the compliance position: this
    builds the shelf, not the contents.

    Returns the number of controls created. Idempotent — re-activating a
    framework adds only missing mappings, and never edits a control the
    organization wrote themselves.
    """
    requirements = list(
        (
            await db.execute(
                select(Requirement).where(Requirement.framework_id == framework.id)
            )
        )
        .scalars()
        .all()
    )
    if not requirements:
        return 0

    by_code = {requirement.reference_code: requirement for requirement in requirements}

    # Controls this organization already has from the library, so a
    # second framework extends them instead of duplicating.
    existing = {
        control.template_key: control
        for control in (
            await db.execute(
                select(Control).where(
                    Control.organization_id == organization_id,
                    Control.template_key.is_not(None),
                )
            )
        )
        .scalars()
        .all()
        if control.template_key
    }

    created = 0
    for template in templates_for_framework(framework.key):
        codes = [code for fk, code in template.satisfies if fk == framework.key]
        targets = [by_code[code] for code in codes if code in by_code]
        if not targets:
            # The template names a requirement this framework revision
            # does not carry. Skipped rather than invented.
            continue

        control = existing.get(template.key)
        if control is None:
            control = Control(
                organization_id=organization_id,
                title=template.title,
                description=template.description,
                status="not_started",
                category=template.category,
                priority=template.priority,
                template_key=template.key,
            )
            db.add(control)
            await db.flush()
            existing[template.key] = control
            created += 1

        for requirement in targets:
            already = (
                await db.execute(
                    select(ControlMapping).where(
                        ControlMapping.control_id == control.id,
                        ControlMapping.requirement_id == requirement.id,
                    )
                )
            ).scalar_one_or_none()
            if already is None:
                db.add(
                    ControlMapping(control_id=control.id, requirement_id=requirement.id)
                )

    await db.flush()
    return created

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
