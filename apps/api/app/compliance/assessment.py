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
from app.compliance.control_library import templates_for_framework
from app.compliance.evidence_coverage import RequirementCoverage, analyse_coverage
from app.compliance.framework_applicability import CompanyFacts
from app.compliance.models import (
    AISystem,
    ComplianceGap,
    Control,
    ControlAssessment,
    ControlMapping,
    Evidence,
    Framework,
    FrameworkActivation,
    Requirement,
)
from app.compliance.remediation import (
    RemediationPlan,
    build_plan,
    render_description,
    sentence_list,
)
from app.compliance.requirement_applicability import (
    OrganizationProfile,
    evaluate_applicability,
    load_profile,
)
from app.core.models import File, Task
from app.onboarding.models import OnboardingProfile

# Per-requirement conclusions, ordered worst to best. These are states of
# *our knowledge*, not verdicts: "satisfied" means the evidence on file
# supports the requirement, not that a regulator would agree.
# "not_applicable" is deliberately first: it is not a degree of
# compliance at all, it means the requirement does not bind this
# organization. It never produces a gap and never enters the readiness
# denominator — a company in scope of fewer articles must not score
# higher than one that actually evidenced them.
REQUIREMENT_STATUSES = (
    "not_applicable",
    "not_assessed",
    "evidence_missing",
    "assessment_failed",
    "deficient",
    "needs_review",
    "satisfied",
)

# The words for those states. Here rather than in each screen, so an
# auditor and a compliance manager reading the same requirement are shown
# the same description of it.
REQUIREMENT_STATUS_LABELS = {
    "not_applicable": "Not applicable",
    "not_assessed": "No control mapped",
    "evidence_missing": "No evidence",
    "assessment_failed": "Assessment failed",
    "deficient": "Partially evidenced",
    "needs_review": "Needs review",
    "satisfied": "Satisfied",
}

# The states that mean a real deficiency has been established, and are
# therefore allowed to raise a gap. `needs_review` is deliberately not
# among them: evidence exists and nothing has been shown to be wrong
# with it, so a confirmed finding would be asserting a problem nobody
# has identified. That was the bug — a requirement with one document and
# no assessment yet reported a medium-severity gap and went straight to
# `remediating`, which is a state machine skipping its own middle.
GAP_BEARING_STATUSES = frozenset(
    {"not_assessed", "evidence_missing", "assessment_failed", "deficient"}
)

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
    # What the evidence was read to show. Carried so the gap can name
    # the unmet condition instead of telling the customer to go and work
    # out which part of the requirement is uncovered.
    coverage: RequirementCoverage | None = None


def _requirement_hint(framework_key: str, reference_code: str) -> str | None:
    return REMEDIATION_HINTS.get(f"{framework_key}:{reference_code}")


async def load_scoping_profile(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> OrganizationProfile:
    """Facts plus AI inventory, gathered once per assessment run.

    Loaded here rather than per requirement: a framework has dozens of
    them and the profile is identical for all of them.
    """
    profile_row = (
        await db.execute(
            select(OnboardingProfile).where(
                OnboardingProfile.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()

    facts = (
        CompanyFacts(
            operates_in_eu=profile_row.operates_in_eu,
            sells_to_eu_customers=profile_row.sells_to_eu_customers,
            processes_personal_data=profile_row.processes_personal_data,
            processes_special_category_data=profile_row.processes_special_category_data,
            uses_third_party_ai=profile_row.uses_third_party_ai,
            builds_ai_features=profile_row.builds_ai_features,
            is_data_processor=profile_row.is_data_processor,
            sells_to_enterprise=profile_row.sells_to_enterprise,
            sector=profile_row.sector,
            employee_count_range=profile_row.employee_count_range,
        )
        if profile_row is not None
        else CompanyFacts()
    )
    return await load_profile(
        db,
        organization_id=organization_id,
        facts=facts,
        facts_declared=profile_row is not None,
    )


async def evaluate_requirement(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    requirement: Requirement,
    framework_key: str | None = None,
    profile: OrganizationProfile | None = None,
) -> RequirementEvaluation:
    """Compute one requirement's status from the rows that exist.

    Scoping runs first. A requirement that does not bind this
    organization is reported as `not_applicable` and never evaluated
    further — it produces no gap and is excluded from readiness.
    """
    if framework_key is not None and profile is not None:
        applicability = evaluate_applicability(
            profile,
            framework_key=framework_key,
            reference_code=requirement.reference_code,
        )
        # Only a settled "does not bind you" leaves the denominator.
        # `needs_review` and `likely_applicable` still count — we cannot
        # tell yet, and shrinking the score on a guess flatters it.
        if not applicability.counts_toward_coverage:
            return RequirementEvaluation(
                requirement=requirement,
                status="not_applicable",
                control_ids=[],
                evidence_count=0,
                latest_assessment_status=None,
                summary=applicability.reason,
            )

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
            status="assessment_failed",
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

    # Evidence exists and no person has failed it. What it actually
    # shows is a question about the evidence, not about how many rows
    # there are — so it is answered by reading the citations behind it
    # against what a complete answer to this requirement contains.
    document_names = [
        str(name)
        for name in (
            await db.execute(
                select(File.original_filename)
                .join(Evidence, Evidence.file_id == File.id)
                .where(Evidence.control_id.in_(control_ids))
                .distinct()
            )
        )
        .scalars()
        .all()
    ]
    coverage = await analyse_coverage(
        db,
        organization_id=organization_id,
        requirement=requirement,
        framework_key=framework_key or "",
        control_ids=control_ids,
        document_names=document_names,
    )

    if coverage.verdict == "satisfied":
        return RequirementEvaluation(
            requirement=requirement,
            status="satisfied",
            control_ids=control_ids,
            evidence_count=evidence_count,
            latest_assessment_status=worst,
            coverage=coverage,
            summary=(
                f"{titles} has {evidence_count} piece(s) of evidence on file covering "
                f"{sentence_list(coverage.met)}. That is everything Veyntra expects to see "
                "for this requirement."
            ),
        )

    if coverage.verdict == "deficient":
        return RequirementEvaluation(
            requirement=requirement,
            status="deficient",
            control_ids=control_ids,
            evidence_count=evidence_count,
            latest_assessment_status=worst,
            coverage=coverage,
            summary=(
                (
                    f"{titles} has evidence covering {sentence_list(coverage.met)}, but "
                    if coverage.met
                    else f"{titles} has evidence attached, but "
                )
                + f"nothing on file provides {sentence_list(coverage.unmet)}."
            ),
        )

    return RequirementEvaluation(
        requirement=requirement,
        status="needs_review",
        control_ids=control_ids,
        evidence_count=evidence_count,
        latest_assessment_status=worst,
        coverage=coverage,
        summary=(
            f"{titles} has {evidence_count} piece(s) of evidence attached and nothing has "
            "been found wrong with it. "
            + (coverage.uncertainty or "")
            + " No deficiency has been identified, so no gap has been raised."
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
    # Evidence on file, nothing shown to be wrong, nobody has confirmed
    # it. Not a finding — see GAP_BEARING_STATUSES.
    needs_review: int
    # A named condition is unmet. These are the real findings.
    deficient: int
    assessment_failed: int
    evidence_missing: int
    not_assessed: int
    # Applicable requirements only. Never the raw count — see
    # summarize_readiness.
    total: int
    not_applicable: int
    explanation: str


# Weights for partial credit. A requirement with evidence that has not
# passed assessment is genuinely further along than one with no evidence
# at all, and scoring both zero tells the user their work achieved
# nothing. Deliberately conservative: only a `satisfied` requirement
# earns full credit, so the number can never overstate the position.
READINESS_WEIGHTS = {
    "satisfied": 1.0,
    # Evidence is on file and nothing has been shown to be wrong with
    # it — a better position than one where a condition is known to be
    # unmet, and scored accordingly. Still not full credit: nobody has
    # confirmed it.
    "needs_review": 0.5,
    "deficient": 0.25,
    "assessment_failed": 0.0,
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
            needs_review=0,
            deficient=0,
            assessment_failed=0,
            evidence_missing=0,
            not_assessed=0,
            total=0,
            not_applicable=0,
            explanation="This framework has no requirements loaded, so there is nothing to score.",
        )

    # Scored against what actually binds this organization. Counting a
    # non-applicable requirement as either passed or failed would both
    # be wrong: it is not a measure of anything.
    in_scope = [e for e in evaluations if e.status != "not_applicable"]
    scored_total = len(in_scope)
    if scored_total == 0:
        return ReadinessBreakdown(
            percent=0.0,
            satisfied=0,
            needs_review=0,
            deficient=0,
            assessment_failed=0,
            evidence_missing=0,
            not_assessed=0,
            total=0,
            not_applicable=counts.get("not_applicable", 0),
            explanation=(
                "None of this framework's requirements currently apply to your "
                "organization, so there is nothing to score."
            ),
        )

    earned = sum(READINESS_WEIGHTS.get(e.status, 0.0) for e in in_scope)
    percent = round(100 * earned / scored_total, 1)

    # Built from the counts rather than written prose, so the sentence and
    # the number are always the same calculation.
    parts: list[str] = []
    for status, label in (
        ("satisfied", "satisfied"),
        ("needs_review", "awaiting review"),
        ("deficient", "with an identified deficiency"),
        ("assessment_failed", "failed at assessment"),
        ("evidence_missing", "missing evidence"),
        ("not_assessed", "with no control mapped"),
    ):
        count = counts.get(status, 0)
        if count:
            parts.append(f"{count} {label}")

    detail = ", ".join(parts[:-1]) + f" and {parts[-1]}" if len(parts) > 1 else parts[0]
    # Named explicitly. A denominator that silently shrank would look
    # like a bug, and the reader deserves to know some requirements were
    # considered and found not to bind them.
    excluded = len(evaluations) - scored_total
    scope_note = (
        f" {excluded} further requirement{'' if excluded == 1 else 's'} "
        f"do{'es' if excluded == 1 else ''} not apply to your organization and "
        "are excluded from this score."
        if excluded
        else ""
    )
    explanation = (
        f"{percent}% ready because, of {scored_total} applicable requirement"
        f"{'' if scored_total == 1 else 's'}, {detail}. "
        "Requirements awaiting review count for half and those with an identified "
        "deficiency for a quarter; only fully satisfied requirements count in full."
        + scope_note
        + " This measures the evidence held in Veyntra, not a legal conclusion about "
        "compliance."
    )

    return ReadinessBreakdown(
        percent=percent,
        satisfied=counts.get("satisfied", 0),
        needs_review=counts.get("needs_review", 0),
        deficient=counts.get("deficient", 0),
        assessment_failed=counts.get("assessment_failed", 0),
        evidence_missing=counts.get("evidence_missing", 0),
        not_assessed=counts.get("not_assessed", 0),
        not_applicable=counts.get("not_applicable", 0),
        # The in-scope count, not the raw one. This is the denominator the
        # percentage was computed against, and reporting a different
        # number beside it would make the arithmetic unfollowable.
        total=scored_total,
        explanation=explanation,
    )


def _gap_kind_for(evaluation: RequirementEvaluation) -> str | None:
    # A requirement that does not bind this organization cannot be a
    # finding against them. Article 26 raising a high-severity gap at a
    # company that deploys no high-risk AI is the false positive that
    # teaches people to stop reading the gap list.
    if evaluation.status not in GAP_BEARING_STATUSES:
        return None
    return {
        "not_assessed": "no_control",
        "evidence_missing": "evidence_missing",
        "assessment_failed": "assessment_failed",
        "deficient": "evidence_partial",
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
    profile = await load_scoping_profile(db, organization_id=organization_id)
    return [
        await evaluate_requirement(
            db,
            organization_id=organization_id,
            requirement=requirement,
            framework_key=framework.key,
            profile=profile,
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

    profile = await load_scoping_profile(db, organization_id=organization_id)

    evaluations: list[RequirementEvaluation] = []
    for requirement in requirements:
        evaluation = await evaluate_requirement(
            db,
            organization_id=organization_id,
            requirement=requirement,
            framework_key=framework.key,
            profile=profile,
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
                    after_state={
                        "status": "resolved",
                        "requirement": requirement.reference_code,
                    },
                )
                await _close_task_for_gap(
                    db,
                    organization_id=organization_id,
                    gap=existing,
                    actor_user_id=actor_user_id,
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
                missing_conditions=(
                    list(evaluation.coverage.unmet) if evaluation.coverage else []
                ),
            )
            db.add(gap)
            await db.flush()
            # Recorded before the plan, because that is the order it
            # happened in: the finding exists, then the fix is written
            # for it. Reversed, the activity feed opened with a plan for
            # a gap that had not been identified yet.
            await record_event(
                db,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="compliance.gap.created",
                object_type="compliance_gap",
                object_id=str(gap.id),
                after_state={"kind": kind, "requirement": requirement.reference_code},
            )
            # Remediation is written as the gap is raised, not on a later
            # button press. A finding whose fix the product already knows
            # should not wait for someone to ask for it — and the
            # recommendation is assembled from the regulation's own text,
            # so generating it eagerly costs nothing and invents nothing.
            await generate_remediation(
                db,
                organization_id=organization_id,
                gap=gap,
                actor_user_id=actor_user_id,
            )
        else:
            existing.kind = kind
            existing.severity = GAP_SEVERITY_BY_KIND[kind]
            existing.summary = evaluation.summary
            existing.control_id = evaluation.control_ids[0] if evaluation.control_ids else None
            existing.missing_conditions = (
                list(evaluation.coverage.unmet) if evaluation.coverage else []
            )
            # A gap that had been resolved and has regressed is open again;
            # one already being worked keeps its `remediating` status so a
            # reassessment does not discard that context.
            if existing.status == "resolved":
                existing.status = "open"
                existing.resolved_at = None
            # Evidence has arrived for something that had none. The work
            # the task asked for is done; what is left is a human saying
            # so. Surfaced as a status change rather than left `open`,
            # because "waiting on you to find a document" and "waiting on
            # you to sign it off" are different asks.
            if kind == "evidence_partial":
                await _mark_task_ready_for_review(
                    db,
                    organization_id=organization_id,
                    gap=existing,
                    actor_user_id=actor_user_id,
                )
            # The plan describes evidence that was already looked at, so
            # it goes stale the moment a new document lands. Regenerated
            # rather than left as first written — a task still asking for
            # a document the customer uploaded last week reads as broken.
            await generate_remediation(
                db,
                organization_id=organization_id,
                gap=existing,
                actor_user_id=actor_user_id,
            )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.framework.assessed",
        object_type="framework",
        object_id=str(framework.id),
        # The whole breakdown, not just the total and the good news: a
        # reader asking what a reassessment concluded needs the counts
        # that did not go their way too.
        after_state={
            "requirements_evaluated": len(evaluations),
            "satisfied": sum(1 for e in evaluations if e.status == "satisfied"),
            "needs_review": sum(1 for e in evaluations if e.status == "needs_review"),
            "gaps": sum(1 for e in evaluations if e.status in GAP_BEARING_STATUSES),
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
    """Write a structured remediation plan onto a gap.

    Not a sentence restating the finding — the deficiency, why it is
    open, what evidence was already looked at, who usually owns this
    work, what would close it, and an ordered checklist. See
    app.compliance.remediation for why the plans are assembled from
    playbooks rather than generated.
    """
    requirement = await db.get(Requirement, gap.requirement_id)
    framework = await db.get(Framework, gap.framework_id)
    assert requirement is not None and framework is not None

    control = await db.get(Control, gap.control_id) if gap.control_id else None

    # What was already looked at. Naming it matters: a plan that asks
    # for evidence without saying what it already read reads as though
    # nobody checked.
    evidence_reviewed: list[str] = []
    if gap.control_id:
        rows = list(
            (
                await db.execute(
                    select(File.original_filename)
                    .join(Evidence, Evidence.file_id == File.id)
                    .where(Evidence.control_id == gap.control_id)
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        evidence_reviewed = [str(name) for name in rows]

    # AI systems only where the requirement is actually about them —
    # listing every system under a GDPR retention gap is noise.
    affected_ai_systems: list[str] = []
    if framework.key == "eu_ai_act":
        affected_ai_systems = [
            str(name)
            for name in (
                await db.execute(
                    select(AISystem.name).where(
                        AISystem.organization_id == organization_id
                    )
                )
            )
            .scalars()
            .all()
        ]

    plan = build_plan(
        framework_key=framework.key,
        framework_name=framework.name,
        requirement_code=requirement.reference_code,
        requirement_title=requirement.title,
        requirement_description=requirement.description,
        gap_kind=gap.kind,
        severity=gap.severity,
        control_title=control.title if control else None,
        evidence_reviewed=evidence_reviewed,
        affected_ai_systems=affected_ai_systems,
        missing_conditions=list(gap.missing_conditions or []),
    )

    previous = gap.remediation_plan
    payload = plan.as_dict()
    gap.remediation_plan = payload
    gap.recommendation = plan.action[:4000]

    # Reassessment runs this on every open gap. Announcing an unchanged
    # plan each time would bury the reads that matter under a repeating
    # line the activity feed cannot distinguish from real work.
    if previous != payload:
        await record_event(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            # A rewrite after new evidence is not a second first draft.
            # Two identical "plan generated" lines read as a repeated
            # event rather than as the plan having moved.
            action=(
                "compliance.gap.remediation_updated"
                if previous
                else "compliance.gap.remediation_generated"
            ),
            object_type="compliance_gap",
            object_id=str(gap.id),
            after_state={
                "requirement": requirement.reference_code,
                "owner": plan.owner,
                "checklist_items": len(plan.checklist),
                "required_evidence": len(plan.required_evidence),
                "evidence_reviewed": len(plan.evidence_reviewed),
            },
        )
    return gap


async def _close_task_for_gap(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    gap: ComplianceGap,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Close the remediation task when its gap closes.

    The evidence that satisfied the requirement is the same evidence the
    task was asking for, so leaving the task open would ask somebody to
    do work the system has already accepted as done. The checklist is
    not ticked on their behalf — what they did is their record, not
    ours.
    """
    if gap.task_id is None:
        return
    task = await db.get(Task, gap.task_id)
    if task is None or task.status in {"done", "cancelled"}:
        return

    before = task.status
    task.status = "done"
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="core.task.status_changed",
        object_type="task",
        object_id=str(task.id),
        before_state={"status": before},
        after_state={"status": "done", "closed_by": "gap_resolved"},
    )


async def _mark_task_ready_for_review(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    gap: ComplianceGap,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Move a remediation task to `in_progress` once evidence exists.

    Not `done`: evidence being on file is not the same as a person having
    concluded the control passes, and closing the task here would make
    the product assert a compliance position nobody signed.
    """
    if gap.task_id is None:
        return
    task = await db.get(Task, gap.task_id)
    if task is None or task.status != "open":
        return

    task.status = "in_progress"
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="core.task.status_changed",
        object_type="task",
        object_id=str(task.id),
        before_state={"status": "open"},
        after_state={"status": "in_progress", "reason": "evidence_found"},
    )


async def note_evidence_on_control(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    control_id: uuid.UUID,
    filename: str,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Record, against any open gap on this control, that a document
    arrived which might close it.

    Written against the gap rather than the evidence so it reaches the
    remediation task's activity feed. Somebody working a gap needs to
    see "a document that may answer this landed" without going to look
    for it.
    """
    gaps = list(
        (
            await db.execute(
                select(ComplianceGap).where(
                    ComplianceGap.organization_id == organization_id,
                    ComplianceGap.control_id == control_id,
                    ComplianceGap.status != "resolved",
                )
            )
        )
        .scalars()
        .all()
    )
    for gap in gaps:
        await record_event(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="compliance.gap.evidence_detected",
            object_type="compliance_gap",
            object_id=str(gap.id),
            after_state={"filename": filename, "control_id": str(control_id)},
        )


def _plan_kwargs(data: dict[str, object]) -> dict[str, object]:
    """Only the fields RemediationPlan declares.

    A plan stored by an older version of the code may carry keys this
    one does not know; filtering rather than exploding means an old gap
    still renders.
    """
    allowed = {
        "problem",
        "why",
        "action",
        "owner",
        "priority",
        "due_in_days",
        "required_evidence",
        "checklist",
        "evidence_reviewed",
        "missing_conditions",
        "missing_evidence",
        "requirement_code",
        "requirement_title",
        "framework_name",
        "control_title",
        "affected_ai_systems",
    }
    return {key: value for key, value in data.items() if key in allowed}


async def create_task_from_gap(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    gap: ComplianceGap,
    actor_user_id: uuid.UUID | None,
    title: str | None = None,
    assignee_id: uuid.UUID | None = None,
    priority: str | None = None,
    due_in_days: int | None = None,
) -> Task:
    """Raise a remediation Task that points back at the gap.

    `entity_type`/`entity_id` are set to the gap rather than left null,
    which is what lets the Tasks module answer "why does this task exist?"
    without the answer having to be re-read out of the title.
    """
    requirement = await db.get(Requirement, gap.requirement_id)
    assert requirement is not None

    # The plan is the task. Without this the task was a title and a
    # one-line restatement of the gap with an empty checklist — a shell
    # that told whoever picked it up nothing they did not already know.
    plan_data = gap.remediation_plan or {}
    checklist = [
        {"text": str(step), "done": False}
        for step in plan_data.get("checklist", [])
    ]
    description = (
        render_description(RemediationPlan(**_plan_kwargs(plan_data)))
        if plan_data
        else (gap.recommendation or gap.summary)
    )[:4000]
    # An explicit override wins; otherwise the plan decides, because it
    # knows whether this is a policy edit or a training programme.
    suggested_priority = str(priority or plan_data.get("priority") or "high")
    suggested_due = int(due_in_days or plan_data.get("due_in_days") or 30)

    task = Task(
        organization_id=organization_id,
        # Short enough to scan on a board. The plan is the body, not
        # the title — an action sentence here would be 200 characters.
        title=title
        or f"Remediate {requirement.reference_code}: {requirement.title}"[:300],
        description=description,
        checklist=checklist,
        module="compliance",
        entity_type="compliance_gap",
        # Task.entity_id is a String column, not a Uuid — it is a generic
        # pointer shared by every module, so it stores the id as text.
        entity_id=str(gap.id),
        priority=suggested_priority,
        status="open",
        assignee_id=assignee_id,
        created_by=actor_user_id,
        due_at=datetime.now(UTC) + timedelta(days=suggested_due),
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

        # Recorded before the run, so the gap's feed reads in the order
        # it happened: the control was looked at again, and then the gap
        # either closed or did not.
        open_gaps = list(
            (
                await db.execute(
                    select(ComplianceGap).where(
                        ComplianceGap.organization_id == organization_id,
                        ComplianceGap.control_id == control_id,
                        ComplianceGap.status != "resolved",
                    )
                )
            )
            .scalars()
            .all()
        )
        for open_gap in open_gaps:
            await record_event(
                db,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="compliance.gap.control_reassessed",
                object_type="compliance_gap",
                object_id=str(open_gap.id),
                after_state={"control_id": str(control_id)},
            )

        for framework in frameworks:
            evaluations = await run_framework_assessment(
                db,
                organization_id=organization_id,
                framework=framework,
                actor_user_id=actor_user_id,
            )
            # The triggering control is always cleared, even when it does
            # not appear in any evaluation. A control serving only
            # requirements that turned out not to apply produces no
            # evaluation containing it — but it *was* reassessed, and the
            # answer is "nothing it serves is in scope". Leaving the flag
            # up would strand it as permanently pending forever.
            control_ids = {cid for e in evaluations for cid in e.control_ids}
            control_ids.add(control_id)
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
