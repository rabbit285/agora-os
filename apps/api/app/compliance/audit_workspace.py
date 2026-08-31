"""Preparing an audit from the compliance state that already exists.

The audit used to open on a blank finding form. Everything an auditor
needs in order to reach a finding was already in the product — which
requirements bind this organization, which control answers each one, what
evidence is attached, what Veyntra makes of it — and none of it was
brought to the audit. So the auditor either reconstructed it by hand
across four screens, or wrote a sentence with nothing behind it.

Preparation walks the framework's requirements, keeps the ones that bind
this organization, finds the control mapped to each, and asks
`control_assessment` — the one derivation every other screen uses — what
state it is in. The result is one `AuditItem` per requirement, carrying a
**snapshot**: the control, the evidence, the assessment, and the
sentences explaining both.

Snapshot is the important word. Compliance state moves constantly, and an
audit is a record of what was true when somebody looked. Joining live
would mean today's uploads silently rewriting last quarter's conclusions,
which is the opposite of what an audit is for. New evidence arriving
during remediation is visible as *new* — beside the snapshot, never
replacing it.

Nothing here decides anything. Preparation produces the auditor's
worklist and the reasoning behind it; the decision on every row is a
person's, and `decision` stays null until they make it.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.assessment import RequirementEvaluation, evaluate_framework
from app.compliance.control_assessment import (
    EvidenceProvenance,
    evidence_by_control,
)
from app.compliance.models import (
    Audit,
    AuditFinding,
    AuditItem,
    ComplianceGap,
    Control,
    Evidence,
    Framework,
    Policy,
    PolicyVersion,
)
from app.core.models import Task

logger = logging.getLogger("agora.compliance.audit_workspace")

# The sections an auditor works through, most demanding first. This is
# the whole point of the workspace: an auditor should not review 18
# requirements with equal attention when 2 have known gaps and 12 are
# clean.
SECTIONS = (
    "known_gaps",
    "needs_verification",
    "insufficient_evidence",
    "changed_evidence",
    "satisfied",
)

SECTION_LABELS = {
    "known_gaps": "Known gaps",
    "needs_verification": "Needs human verification",
    "insufficient_evidence": "Insufficient evidence",
    "changed_evidence": "Recently changed evidence",
    "satisfied": "Satisfied / no issue found",
}

# Which section each requirement state lands in. The vocabulary is
# `app.compliance.assessment`'s — the same words the readiness screen and
# the gap list use — rather than a second scale invented for audits. An
# auditor and a compliance manager looking at the same requirement should
# not have to translate between two descriptions of it.
_GAP_STATES = frozenset({"not_assessed", "evidence_missing", "assessment_failed"})
_REVIEW_STATES = frozenset({"needs_review"})
_PARTIAL_STATES = frozenset({"deficient"})

# The auditor's decisions, and the finding severity each one raises.
# `no_finding` and `needs_evidence` raise nothing — one is a clean
# result, the other is a request for more information, and recording
# either as a finding would overstate what the auditor concluded.
DECISIONS = (
    "no_finding",
    "observation",
    "minor",
    "major",
    "critical",
    "needs_evidence",
)

DECISION_LABELS = {
    "no_finding": "No finding",
    "observation": "Observation",
    "minor": "Minor finding",
    "major": "Major finding",
    "critical": "Critical finding",
    "needs_evidence": "Needs more evidence",
}

DECISION_SEVERITY = {
    "observation": "low",
    "minor": "medium",
    "major": "high",
    "critical": "critical",
}

# Decisions a person has to explain. A clean result needs no defence; a
# finding against somebody's control does, and "Major finding" with no
# sentence beside it is not something the organization can act on.
REQUIRES_NOTE = ("minor", "major", "critical", "needs_evidence")


class PreparationFailed(Exception):
    """Preparation could not produce a scope, and why.

    `code` is for the API to hand the screen; `message` is the sentence
    a person reads. Both are here rather than at the endpoint so the
    reason travels with the failure instead of being reconstructed from
    an exception type three layers up — which is how "the framework does
    not resolve" and "an unrelated attribute is missing" both became
    "That did not go through. Nothing was changed."
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# What "prepared but empty" means, distinguished rather than collapsed.
# An audit that scoped nothing is not an audit; the three causes need
# three different things from the person looking at it.
NO_REQUIREMENTS_IN_CATALOG = "framework_has_no_requirements"
NONE_APPLICABLE = "no_applicable_requirements"


@dataclass
class PreparationReport:
    """What preparing the audit scoped, and what it found there."""

    applicable: int = 0
    satisfied: int = 0
    needs_review: int = 0
    gaps: int = 0
    evidence: int = 0
    open_remediation: int = 0
    created: int = 0
    updated: int = 0
    # Requirements that bind nobody here, reported rather than scoped.
    not_applicable: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "applicable": self.applicable,
            "satisfied": self.satisfied,
            "needs_review": self.needs_review,
            "gaps": self.gaps,
            "evidence": self.evidence,
            "open_remediation": self.open_remediation,
            "created": self.created,
            "updated": self.updated,
            "not_applicable": self.not_applicable,
        }


class ExclusionRefused(Exception):
    """A requirement cannot be taken out of scope as asked."""


@dataclass
class ScopeLine:
    """One requirement, and why it is or is not in this audit."""

    reference_code: str
    title: str
    disposition: str
    requirement_id: uuid.UUID | None = None
    reason: str | None = None
    excluded_at: object | None = None


@dataclass
class ItemView:
    """One audit row, with everything needed to decide on it in one place.

    The auditor should not have to open four screens to understand why a
    requirement is flagged. Requirement, control, assessment, evidence
    and what is missing all travel together.
    """

    item: AuditItem
    section: str
    # Evidence attached since the audit was prepared. Shown as new rather
    # than folded into the snapshot: "this arrived after you looked" is
    # the thing an auditor needs to know about it.
    new_evidence: list[dict] = field(default_factory=list)
    open_remediation: int = 0
    # Where the requirement stands today, against the snapshot the
    # auditor assessed. Null when nothing has moved, so the screen only
    # says "then, and now" when there is a now worth showing.
    current_status: str | None = None
    finding: object | None = None


def code_key(reference_code: str) -> tuple:
    """Sort "4.1" before "10.1", the way the standard is numbered.

    A string sort puts §10.1 above §4.1, which is not an ordering any
    auditor recognises — they read the standard in its own sequence, and
    a worklist that reorders it is one more thing to hold in your head.
    """
    parts: list[tuple[int, object]] = []
    for chunk in re.split(r"[.\s-]+", (reference_code or "").strip()):
        if not chunk:
            continue
        # Numbers sort as numbers; anything else sorts as text after them,
        # so "Art. 30" and "A.5" both land somewhere sensible.
        if chunk.isdigit():
            parts.append((0, int(chunk)))
        else:
            leading = re.match(r"^(\d+)(.*)$", chunk)
            if leading:
                parts.append((0, int(leading.group(1))))
                parts.append((1, leading.group(2).lower()))
            else:
                parts.append((1, chunk.lower()))
    return tuple(parts)


def section_for(item: AuditItem, *, has_new_evidence: bool = False) -> str:
    """Which pile this row belongs in.

    Derived, never stored. A stored section would go stale the moment a
    decision was recorded or evidence arrived, and a worklist that lies
    about what is left is worse than no worklist.
    """
    if has_new_evidence and item.decision is None:
        return "changed_evidence"
    if item.prepared_status in _GAP_STATES:
        return "known_gaps"
    if item.prepared_status in _REVIEW_STATES:
        return "needs_verification"
    if item.prepared_status in _PARTIAL_STATES:
        return "insufficient_evidence"
    return "satisfied"


async def prepare(
    db: AsyncSession,
    *,
    audit: Audit,
    actor_user_id: uuid.UUID | None,
) -> PreparationReport:
    """Build the audit's worklist from the compliance state as it stands.

    The evaluation itself is `assessment.evaluate_framework` — the same
    read-only pass the readiness screen and the gap list use. Auditing is
    not a second opinion about what the evidence shows; it is a person
    reviewing the position the organization already holds. Deriving it
    again here would create exactly the disagreement an audit is supposed
    to settle.

    Idempotent. Preparing twice reconciles the same rows rather than
    creating a second set — the unique index on (audit, requirement)
    makes that a guarantee rather than an intention.

    **A decision already recorded is never overwritten.** Re-preparing an
    audit somebody has worked through refreshes the snapshot on rows they
    have not reached and leaves their conclusions alone. Anything else
    would let a background refresh erase an auditor's work.
    """
    report = PreparationReport()

    if audit.framework_id is None:
        # A custom audit scopes itself. Not a failure, and deliberately
        # not routed through the framework pipeline at all.
        logger.info("Audit %s has no framework; nothing to prepare", audit.id)
        return report

    framework = await db.get(Framework, audit.framework_id)
    if framework is None:
        raise PreparationFailed(
            "framework_not_found",
            "The selected framework could not be resolved for this "
            "organization. Choose a framework again, or contact support if "
            "it keeps happening.",
        )

    evaluations = await evaluate_framework(
        db, organization_id=audit.organization_id, framework=framework
    )
    if not evaluations:
        raise PreparationFailed(
            NO_REQUIREMENTS_IN_CATALOG,
            f"{framework.name} has no requirements in the catalog yet, so "
            "there is nothing to audit against.",
        )

    existing = {
        item.requirement_id: item
        for item in (
            await db.execute(select(AuditItem).where(AuditItem.audit_id == audit.id))
        )
        .scalars()
        .all()
    }
    evidence_lookup = await _evidence_for(
        db,
        organization_id=audit.organization_id,
        control_ids=[
            control_id
            for evaluation in evaluations
            for control_id in evaluation.control_ids
        ],
    )

    evidence_seen: set[str] = set()

    for evaluation in evaluations:
        if evaluation.status == "not_applicable":
            # A requirement that does not bind this organization is not a
            # finding waiting to happen. Reported, not scoped.
            report.not_applicable += 1
            continue

        report.applicable += 1
        control = await _headline_control(db, evaluation)
        evidence = [
            entry
            for control_id in evaluation.control_ids
            for entry in evidence_lookup.get(control_id, [])
        ]
        for entry in evidence:
            evidence_seen.add(entry["evidence_id"])

        if evaluation.status in _GAP_STATES:
            report.gaps += 1
        elif evaluation.status in _REVIEW_STATES:
            report.needs_review += 1
        elif evaluation.status == "satisfied":
            report.satisfied += 1

        item = existing.get(evaluation.requirement.id)
        if item is None:
            item = AuditItem(
                organization_id=audit.organization_id,
                audit_id=audit.id,
                requirement_id=evaluation.requirement.id,
            )
            db.add(item)
            report.created += 1
        elif item.decision is not None:
            # Somebody has already ruled on this. Their conclusion, and
            # the snapshot they reached it from, both stand.
            continue
        else:
            report.updated += 1

        item.reference_code = evaluation.requirement.reference_code
        item.requirement_title = evaluation.requirement.title
        item.framework_key = framework.key
        item.control_id = control.id if control else None
        item.control_title = control.title if control else None
        item.prepared_status = evaluation.status
        item.prepared_confidence = _confidence_for(evaluation)
        item.prepared_why = evaluation.summary
        item.prepared_missing = _missing_for(evaluation)
        item.evidence_snapshot = evidence
        item.applicability = "applicable"
        item.applicability_reason = None

    if not report.applicable:
        # The framework resolved and has requirements; none of them bind
        # this organization on the facts it has declared. That is a real
        # answer, not an empty audit — and it is a different problem from
        # a framework that resolves to nothing at all.
        raise PreparationFailed(
            NONE_APPLICABLE,
            f"No applicable {framework.name} requirements are currently in "
            f"scope for this organization. {report.not_applicable} "
            f"requirement{'' if report.not_applicable == 1 else 's'} "
            f"{'was' if report.not_applicable == 1 else 'were'} assessed as "
            "not applicable. Review your framework applicability, or choose "
            "a different framework.",
        )

    report.evidence = len(evidence_seen)
    report.open_remediation = await _open_remediation_count(
        db, organization_id=audit.organization_id
    )

    audit.prepared_at = _utcnow()
    audit.prepared_summary = report.as_dict()
    audit.framework_name = framework.name
    await db.flush()

    await record_event(
        db,
        organization_id=audit.organization_id,
        # Preparation reads what is already recorded and decides nothing.
        # Attributing it to whoever opened the audit would put a judgement
        # in their name that they have not made yet.
        actor_user_id=actor_user_id,
        action="compliance.audit.prepared",
        object_type="audit",
        object_id=str(audit.id),
        after_state={
            "title": audit.title,
            "framework": framework.name,
            **report.as_dict(),
        },
    )

    logger.info("Prepared audit %s: %s", audit.id, report.as_dict())
    return report


def _utcnow():
    from datetime import UTC, datetime

    return datetime.now(UTC)


def _confidence_for(evaluation: RequirementEvaluation) -> int:
    """How well the evidence covers this requirement, 0-100.

    From the coverage analysis where there is one. A requirement with no
    expectation list scores on whether anything is cited at all, which is
    the honest answer rather than a fabricated percentage.
    """
    coverage = evaluation.coverage
    if coverage is None:
        return 100 if evaluation.status == "satisfied" else 0
    total = len(coverage.met) + len(coverage.unmet)
    if not total:
        return 100 if evaluation.status == "satisfied" else 0
    return round(100 * len(coverage.met) / total)


def _missing_for(evaluation: RequirementEvaluation) -> str | None:
    """What is not covered, named rather than left to the reader.

    "Partially evidenced" tells an auditor nothing they can act on. The
    unmet conditions are what turns a status into a question they can put
    to the organization.
    """
    if evaluation.status == "not_assessed":
        return "No control is mapped to this requirement."
    coverage = evaluation.coverage
    if coverage is None:
        return None
    if coverage.unmet:
        return "; ".join(coverage.unmet)
    if coverage.uncertainty:
        return coverage.uncertainty
    return None


async def _headline_control(
    db: AsyncSession, evaluation: RequirementEvaluation
) -> Control | None:
    """The control the row names.

    Where several serve one requirement, the first is the headline and
    the evidence below still comes from all of them — the row is about
    the requirement, not about any one control's average.
    """
    if not evaluation.control_ids:
        return None
    return await db.get(Control, evaluation.control_ids[0])


async def _evidence_for(
    db: AsyncSession, *, organization_id: uuid.UUID, control_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict]]:
    """Evidence on file for each control, in the shape a row shows it.

    The resolution itself is `control_assessment.evidence_by_control` —
    the same call the controls list and the readiness screen make. This
    module had its own copy, which read `evidence_type`,
    `source_location` and `model_confidence` straight off the `Evidence`
    row. None of the three is a column there: the type comes from the
    file, and the location and confidence from the suggestion that
    proposed the mapping. Every organization with evidence attached to a
    control hit an AttributeError the moment their audit was prepared,
    and every organization without any never reached the line.
    """
    provenance = await evidence_by_control(
        db, organization_id=organization_id, control_ids=list(set(control_ids))
    )
    # The version each document was filed under, resolved once and frozen
    # into the snapshot. Looked up here rather than when a report is
    # written, so a document revised afterwards cannot change what the
    # report says the auditor reviewed.
    file_ids = {
        entry.file_id
        for items in provenance.values()
        for entry in items
        if entry.file_id
    }
    versions = await _document_versions(db, file_ids)
    return {
        control_id: [
            _evidence_entry(item, versions.get(item.file_id) if item.file_id else None)
            for item in items
        ]
        for control_id, items in provenance.items()
    }


def _evidence_entry(item: EvidenceProvenance, version: str | None = None) -> dict:
    """One evidence item, as the audit row shows it.

    Chunk identifiers deliberately do not travel. `source_location` is
    the human-readable place in the document and `document_href` opens
    it — an auditor asked to trust "chunk 41f9a" has been shown the
    plumbing instead of the evidence.

    `document_version` is frozen here rather than looked up when a report
    is written. A document revised after the audit must not retroactively
    change which version the report says was reviewed — that is the one
    thing an evidence index exists to pin down.
    """
    return {
        "evidence_id": str(item.evidence_id),
        "file_id": str(item.file_id) if item.file_id else None,
        "title": item.title or item.filename,
        "filename": item.filename,
        "document_href": item.document_href,
        "source_location": item.source_location,
        "evidence_type": item.evidence_type,
        "model_confidence": item.model_confidence,
        "document_version": version,
    }


async def _document_versions(
    db: AsyncSession, file_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """The version each file was filed under, at preparation time.

    `policy_versions` is keyed on the file, so it answers "what version
    is this document" — the question an evidence index asks. `policies`
    answers "what version is this policy now", which is a different
    question and only consulted when the first has no row.
    """
    if not file_ids:
        return {}
    found: dict[uuid.UUID, str] = {}
    for file_id, version in (
        await db.execute(
            select(PolicyVersion.file_id, PolicyVersion.version).where(
                PolicyVersion.file_id.in_(file_ids)
            )
        )
    ).all():
        if file_id is not None and version:
            found[file_id] = version
    missing = file_ids - set(found)
    if missing:
        for file_id, version in (
            await db.execute(
                select(Policy.file_id, Policy.version).where(
                    Policy.file_id.in_(missing)
                )
            )
        ).all():
            if file_id is not None and version:
                found[file_id] = version
    return found


async def _open_remediation_count(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> int:
    return int(
        (
            await db.execute(
                select(func.count(ComplianceGap.id)).where(
                    ComplianceGap.organization_id == organization_id,
                    ComplianceGap.status != "resolved",
                )
            )
        ).scalar_one()
    )


async def item_views(
    db: AsyncSession, *, audit: Audit
) -> list[ItemView]:
    """Every row, with its section and anything that arrived since.

    Sorted the way an auditor works: gaps first, clean rows last, and
    within a section by reference code so the list reads like the
    standard it is auditing against.
    """
    items = list(
        (
            await db.execute(
                select(AuditItem)
                .where(AuditItem.audit_id == audit.id)
                .order_by(AuditItem.reference_code.asc())
            )
        )
        .scalars()
        .all()
    )
    if not items:
        return []

    new_by_control = await _evidence_added_since(
        db,
        organization_id=audit.organization_id,
        control_ids=[item.control_id for item in items if item.control_id],
        since=audit.prepared_at,
    )

    # §14: where each requirement stands today, against the snapshot the
    # auditor assessed. Only computed for a completed audit — while one is
    # running, the snapshot is the current state.
    current: dict[uuid.UUID, str] = {}
    if audit.status == "completed" and audit.framework_id is not None:
        framework = await db.get(Framework, audit.framework_id)
        if framework is not None:
            current = {
                evaluation.requirement.id: evaluation.status
                for evaluation in await evaluate_framework(
                    db, organization_id=audit.organization_id, framework=framework
                )
            }

    findings = {
        finding.audit_item_id: finding
        for finding in (
            await db.execute(
                select(AuditFinding).where(AuditFinding.audit_id == audit.id)
            )
        )
        .scalars()
        .all()
        if finding.audit_item_id is not None
    }

    views: list[ItemView] = []
    for item in items:
        known = {entry.get("evidence_id") for entry in item.evidence_snapshot or []}
        arrived = [
            entry
            for entry in new_by_control.get(item.control_id, [])
            if entry["evidence_id"] not in known
        ]
        now = current.get(item.requirement_id)
        views.append(
            ItemView(
                item=item,
                section=section_for(item, has_new_evidence=bool(arrived)),
                new_evidence=arrived,
                # Null when nothing moved, so the screen only says "then,
                # and now" where there is a now worth showing.
                current_status=now if now and now != item.prepared_status else None,
                finding=findings.get(item.id),
            )
        )

    order = {section: index for index, section in enumerate(SECTIONS)}
    views.sort(
        key=lambda view: (order.get(view.section, 99), code_key(view.item.reference_code))
    )
    return views


async def _evidence_added_since(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    control_ids: list[uuid.UUID],
    since,
) -> dict[uuid.UUID, list[dict]]:
    """Evidence attached to these controls after the audit was prepared.

    This is what makes remediation visible without rewriting history. The
    snapshot stays as it was; what arrived afterwards is shown as having
    arrived afterwards.
    """
    if not control_ids or since is None:
        return {}
    recent = {
        evidence_id
        for evidence_id in (
            await db.execute(
                select(Evidence.id).where(
                    Evidence.organization_id == organization_id,
                    Evidence.control_id.in_(list(set(control_ids))),
                    Evidence.created_at > since,
                )
            )
        ).scalars()
    }
    if not recent:
        return {}
    # Resolved the same way as everything else, so a newly arrived
    # document opens at the same place an original one does.
    everything = await _evidence_for(
        db, organization_id=organization_id, control_ids=control_ids
    )
    return {
        control_id: [
            entry for entry in entries if entry["evidence_id"] in recent
        ]
        for control_id, entries in everything.items()
        if any(entry["evidence_id"] in recent for entry in entries)
    }


async def set_exclusion(
    db: AsyncSession,
    *,
    audit: Audit,
    item: AuditItem,
    reason: str | None,
    excluded: bool,
    actor_user_id: uuid.UUID | None,
) -> bool:
    """Take a requirement out of this audit's scope, or put it back.

    Audit-specific and nothing else. The organization's framework
    applicability is untouched: a limited internal audit leaving Art. 22
    out says nothing about whether Art. 22 binds the company, and
    conflating the two would let the shape of one report quietly rewrite
    what the company is held to.

    Refused once the auditor has ruled on the row. Excluding something
    they already concluded on would leave a finding attached to a
    requirement the report says was never examined.
    """
    if excluded == (item.excluded_at is not None):
        return False

    if excluded:
        if not (reason or "").strip():
            raise ExclusionRefused(
                "Excluding a requirement needs a reason. Scope decisions are "
                "the first thing a reviewer questions."
            )
        if item.decision is not None:
            raise ExclusionRefused(
                "This requirement already has an auditor conclusion. Excluding "
                "it now would leave a finding against something the report "
                "says was not examined."
            )
        item.excluded_at = _utcnow()
        item.excluded_by = actor_user_id
        item.exclusion_reason = (reason or "").strip()
    else:
        item.excluded_at = None
        item.excluded_by = None
        item.exclusion_reason = None

    await record_event(
        db,
        organization_id=item.organization_id,
        actor_user_id=actor_user_id,
        action=(
            "compliance.audit_item.excluded"
            if excluded
            else "compliance.audit_item.included"
        ),
        object_type="audit_item",
        object_id=str(item.id),
        after_state={
            "audit_id": str(audit.id),
            "requirement": item.reference_code,
            "reason": item.exclusion_reason,
        },
    )
    await db.flush()
    return True


async def scope_lines(db: AsyncSession, *, audit: Audit) -> list[ScopeLine]:
    """Every requirement the framework has, and where it stands.

    Included, not applicable, or excluded by the auditor — with the
    reason for each. Nothing is hidden: a compliance manager defending a
    report needs to explain the fifteen absences as readily as the three
    inclusions.
    """
    if audit.framework_id is None:
        return []

    framework = await db.get(Framework, audit.framework_id)
    if framework is None:  # pragma: no cover
        return []

    scoped = {
        item.requirement_id: item
        for item in (
            await db.execute(select(AuditItem).where(AuditItem.audit_id == audit.id))
        )
        .scalars()
        .all()
    }

    lines: list[ScopeLine] = []
    for evaluation in await evaluate_framework(
        db, organization_id=audit.organization_id, framework=framework
    ):
        requirement = evaluation.requirement
        item = scoped.get(requirement.id)
        if item is not None and item.excluded_at is not None:
            lines.append(
                ScopeLine(
                    requirement_id=requirement.id,
                    reference_code=requirement.reference_code,
                    title=requirement.title,
                    disposition="excluded",
                    reason=item.exclusion_reason,
                    excluded_at=item.excluded_at,
                )
            )
        elif item is not None:
            lines.append(
                ScopeLine(
                    requirement_id=requirement.id,
                    reference_code=requirement.reference_code,
                    title=requirement.title,
                    disposition="included",
                    reason=None,
                )
            )
        else:
            lines.append(
                ScopeLine(
                    requirement_id=requirement.id,
                    reference_code=requirement.reference_code,
                    title=requirement.title,
                    disposition="not_applicable",
                    # Why it does not bind this organization, in the
                    # applicability engine's own words.
                    reason=evaluation.summary,
                )
            )

    lines.sort(key=lambda line: code_key(line.reference_code))
    return lines


async def open_finding_count(db: AsyncSession, *, audit_id: uuid.UUID) -> int:
    from app.compliance.audit_state import RESOLVED_FINDING_STATUSES

    return int(
        (
            await db.execute(
                select(func.count(AuditFinding.id)).where(
                    AuditFinding.audit_id == audit_id,
                    AuditFinding.status.notin_(RESOLVED_FINDING_STATUSES),
                )
            )
        ).scalar_one()
    )


__all__ = [
    "DECISIONS",
    "ExclusionRefused",
    "ScopeLine",
    "scope_lines",
    "set_exclusion",
    "NONE_APPLICABLE",
    "NO_REQUIREMENTS_IN_CATALOG",
    "PreparationFailed",
    "code_key",
    "DECISION_LABELS",
    "DECISION_SEVERITY",
    "REQUIRES_NOTE",
    "SECTIONS",
    "SECTION_LABELS",
    "ItemView",
    "PreparationReport",
    "item_views",
    "open_finding_count",
    "prepare",
    "section_for",
]
