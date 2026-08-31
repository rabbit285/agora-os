"""What the audit report says, assembled without writing anything.

An audit report is a statement about a moment: these requirements were
in scope, this is what the auditor concluded about each, this is the
evidence they read. So this module reads the audit's **own snapshot** —
`AuditItem.prepared_*`, `AuditItem.decision`, `AuditFinding.severity` —
and never re-derives a conclusion from today's compliance state. A
control reassessed last week does not retroactively change what an
auditor concluded in August, and a report that let it would be worthless
as a record.

Two clocks run through the report, and they are labelled rather than
merged:

- **Audit conclusion at completion** — the auditor's, frozen. It came
  from a person and cannot move.
- **Current remediation status as of report generation** — where the
  work stands now. It moves constantly, and a reader wants both.

That is the difference between "Audit conclusion: Minor finding" and
"Current remediation: Closed". Collapsing them either erases the finding
or pretends nothing was fixed.

**Veyntra's assessment is not the auditor's conclusion.** The evidence
state is what a machine could establish from the record; the conclusion
is what a person decided. They are reported side by side, in that order,
and the requirement is the subject of both — not the diagnostic sentence
that happened to explain the evidence state. A finding headed "1
document(s) are mapped to this requirement, but Veyntra has no itemised
expectation set for it yet" is the plumbing presented as the finding.

Nothing here writes. Building a preview twice, or opening one and
closing it, must leave the record exactly as it was — see
`app.compliance.audit_report_service` for the half that does write.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.audit_findings import STATUS_LABELS
from app.compliance.audit_identity import (
    UNCONFIGURED_ORGANIZATION,
    AuditorIdentity,
    organization_display_name,
    resolve_auditor,
)
from app.compliance.audit_state import CONCLUSION_LABELS
from app.compliance.audit_workspace import (
    DECISION_LABELS,
    DECISION_SEVERITY,
    code_key,
)
from app.compliance.models import (
    Audit,
    AuditFinding,
    AuditItem,
    AuditReport,
    Policy,
    PolicyVersion,
)
from app.core.models import Organization, Task
from app.identity.models import User

# The wording the product stands behind. An internal audit run inside a
# compliance tool is not a certification, and a report that does not say
# so invites somebody to send it to a customer as though it were one.
DISCLAIMER = (
    "This report represents an internal audit based on the scope and "
    "evidence recorded in Veyntra. It is not an independent certification "
    "or legal opinion."
)

# How an internal audit report is classified by default. Deliberately a
# single string rather than a classification system: the product has no
# document-classification infrastructure for reports, and inventing one
# for a footer label would be a larger change than the label is worth.
CLASSIFICATION = "Confidential"

# How the evidence state read at preparation is described in a document
# somebody outside the audit will read. `control_assessment`'s vocabulary
# is right on a worklist and too terse in prose.
EVIDENCE_STATE_LABELS = {
    "evidenced": "Evidence on file",
    "partially_evidenced": "Partial evidence on file",
    "needs_review": "Needs human verification",
    "evidence_insufficient": "Evidence insufficient",
    "no_evidence": "No evidence on file",
    "not_assessed": "Not assessed",
    "evidence_missing": "No evidence on file",
    "assessment_failed": "Assessment could not be completed",
    "deficient": "Control deficient",
    "not_applicable": "Not applicable",
    "satisfied": "Satisfied",
}

# Severity order for grouping, worst first. A report that lists
# observations above critical findings buries the thing the reader
# opened it for.
SEVERITY_ORDER = ("critical", "high", "medium", "low")

# What one finding is called in prose, as against the band it is grouped
# under. A section heading reads "Minor findings (3)"; the finding itself
# reads "Minor finding", which is the auditor's own word for what they
# recorded — the same phrase they chose on the decision.
FINDING_CONCLUSION_LABELS = {
    severity: DECISION_LABELS[decision]
    for decision, severity in DECISION_SEVERITY.items()
}

# The conclusions a healthy audit can reach, in the order they are
# summarised. Reported with their zeros: "Major 0" is a result, and a
# summary that silently omits it reads as though nobody looked.
CONCLUSION_SCALE = ("no_finding", "observation", "minor", "major", "critical")

# Remediation states, likewise reported with zeros.
REMEDIATION_SCALE = (
    "open",
    "remediation_in_progress",
    "ready_for_verification",
    "closed",
    "accepted_risk",
)

# How the report groups findings. Major and Critical travel together —
# an executive reading the summary treats them the same way, and two
# near-empty sections at the top of a report is worse than one.
SEVERITY_GROUPS = (
    ("major_critical", "Major and critical findings", ("critical", "high")),
    ("minor", "Minor findings", ("medium",)),
    ("observations", "Observations", ("low",)),
)

# What the audit did, said once rather than repeated under every finding.
METHODOLOGY = (
    "The audit was prepared from the requirements, controls, evidence, "
    "assessments and remediation records available in Veyntra at the audit "
    "preparation date. Veyntra assembled and assessed the available "
    "evidence; the formal audit conclusions were recorded by the named "
    "auditor.",
    "Veyntra's evidence state and the auditor's conclusion are separate "
    "claims and are reported separately throughout. Veyntra's assessment "
    "describes what the record supports; it is not an audit conclusion.",
    "Absence of evidence in Veyntra is recorded as such and does not by "
    "itself constitute a failed requirement. Where the auditor concluded "
    "that it did, that conclusion is stated as a finding.",
    "Remediation continues after an audit closes. The remediation status "
    "in this report is as at the generation date shown and may since have "
    "moved; the audit conclusions do not change with it.",
)


@dataclass
class Blocker:
    """A reason this report should not be issued yet."""

    code: str
    message: str


@dataclass
class Metric:
    """One number on the results summary, with its zeros kept."""

    label: str
    value: str
    # Set on the lines an executive reads first, so the renderer can give
    # them weight without the report having to hard-code row indexes.
    emphasis: bool = False


@dataclass
class ConclusionLine:
    """One scoped requirement and what the auditor concluded about it."""

    reference_code: str
    requirement_title: str
    control_title: str | None
    # What Veyntra assessed at preparation. Kept beside the conclusion
    # rather than instead of it: the evidence state is a machine's
    # reading, the conclusion is a person's, and the report has to be
    # able to show a case where they differ.
    evidence_state: str | None
    evidence_state_label: str | None
    decision: str | None
    decision_label: str
    decision_note: str | None
    decided_at: datetime | None
    decided_by: str | None
    evidence_count: int
    # Set when the conclusion raised a finding — the live remediation
    # state, explicitly labelled as "now" rather than "then".
    finding_id: uuid.UUID | None = None
    current_remediation: str | None = None
    current_remediation_label: str | None = None


@dataclass
class FindingLine:
    """One finding, as an audit report states it.

    The requirement is the subject. Veyntra's assessment supports it, the
    auditor's conclusion is the result, and the remediation status is a
    separate, later fact.
    """

    id: uuid.UUID
    reference_code: str | None
    # The requirement this is about, which is what the block is headed
    # with. `title` is what the finding was named — often the same thing,
    # sometimes a diagnostic sentence, and never the heading.
    requirement_title: str | None
    title: str
    description: str | None
    severity: str
    # "Minor finding", not "medium". The report speaks the auditor's
    # language, not the database's.
    conclusion_label: str
    current_status: str
    current_status_label: str
    control_title: str | None
    evidence_state: str | None = None
    evidence_state_label: str | None = None
    # A report-grade sentence for what Veyntra could establish, derived
    # from the evidence state rather than quoting the internal
    # diagnostic. See `_assessment_sentence`.
    assessment: str | None = None
    # The specific thing not evidenced, where preparation named one.
    not_evidenced: str | None = None
    # Why the auditor concluded what they did, in their words. Absent for
    # most decisions, and never invented — a report that fabricates a
    # rationale is worse than one that admits none was recorded.
    auditor_note: str | None = None
    evidence_count: int = 0
    verified_at: datetime | None = None
    verified_by: str | None = None
    verification_note: str | None = None
    remediation_task: str | None = None
    remediation_owner: str | None = None
    remediation_due: datetime | None = None
    superseded_at: datetime | None = None
    superseded_reason: str | None = None
    # §6: the auditor concluded a finding on a requirement whose evidence
    # Veyntra assessed as satisfied, and recorded no reason. Both facts
    # are legitimate — an auditor may well see something the record does
    # not — but printed side by side with nothing between them the report
    # reads as contradicting itself. So the report says which of the two
    # it is: a reason the auditor gave, or a reason nobody recorded.
    rationale_gap: bool = False


@dataclass
class SeverityGroup:
    key: str
    severity: str
    label: str
    count: int
    findings: list[FindingLine] = field(default_factory=list)


@dataclass
class RemediationGroup:
    status: str
    label: str
    count: int


@dataclass
class EvidenceLine:
    """One document the auditor read, and what it was read against."""

    title: str
    filename: str | None
    document_href: str | None
    # The version as it stood when the audit read it — taken from the
    # audit's own snapshot where preparation recorded one, so a document
    # revised since does not retroactively change what the report says
    # was reviewed.
    version: str | None
    version_label: str
    version_source: str
    # What Veyntra made of the requirements this supported, at audit
    # time. An evidence index that lists documents without saying what
    # they were taken to show is a filing cabinet, not an index.
    evidence_states: list[str] = field(default_factory=list)
    requirement_codes: list[str] = field(default_factory=list)


@dataclass
class ReportProgress:
    scoped: int
    reviewed: int
    percent_reviewed: int
    excluded: int
    findings: int
    superseded: int


@dataclass
class SignOff:
    """Who conducted the audit, who issued the report, and when.

    Three roles, kept apart. The auditor conducted the audit; the person
    who pressed generate produced this version of the document; an
    approver would have signed it off. They are often the same person and
    are never the same field.

    Not a signature. The product records no formal approval on an audit,
    and drawing a signature block the organization never signed would be
    a forgery in a document people rely on.
    """

    auditor: AuditorIdentity
    completed_at: datetime | None
    generated_at: datetime
    generated_by: str | None
    report_version: int
    approved_by: str | None = None
    approved_at: datetime | None = None


@dataclass
class AuditReportPreview:
    """Everything the report will say, and nothing written yet."""

    audit_id: uuid.UUID
    title: str
    audit_title: str
    organization_name: str | None
    framework_name: str | None
    # There is no version field on a catalog framework, so the report
    # states the requirement set the audit was actually prepared against
    # instead of inventing a version string.
    framework_basis: str | None
    auditor_name: str | None
    # Who conducted the audit, as a structured identity. A formatted
    # "Jane Smith (external)" reads as part of her name and has nowhere
    # to put the firm she works for.
    auditor: AuditorIdentity
    scope: str | None
    status: str
    status_label: str
    started_at: datetime | None
    completed_at: datetime | None
    prepared_at: datetime | None
    classification: str
    # True when the organization record has no usable name. The report
    # says so rather than substituting anything derived from a person.
    organization_name_configured: bool
    progress: ReportProgress
    # §2: the result, in sentences, before any table.
    executive_summary: list[str]
    metrics: list[Metric]
    methodology: tuple[str, ...]
    conclusions: list[ConclusionLine]
    conclusion_counts: dict[str, int]
    conclusion_summary: list[Metric]
    findings: list[FindingLine]
    findings_by_severity: list[SeverityGroup]
    superseded_findings: list[FindingLine]
    remediation: list[RemediationGroup]
    remediation_rows: list[FindingLine]
    verification: list[FindingLine]
    evidence_index: list[EvidenceLine]
    limitations: list[str]
    disclaimer: str
    sign_off: SignOff
    generated_for: datetime
    digest: str
    next_version: int
    blockers: list[Blocker] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.blockers


def _now() -> datetime:
    return datetime.now(UTC)


async def next_version(db: AsyncSession, *, audit_id: uuid.UUID) -> int:
    highest = (
        await db.execute(
            select(func.max(AuditReport.version)).where(
                AuditReport.audit_id == audit_id
            )
        )
    ).scalar()
    return int(highest or 0) + 1


async def _names(db: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Who did what, by name.

    An audit report that identifies its auditor by UUID is unreadable to
    the person it is written for, and an internal identifier in a
    document that circulates is plumbing nobody outside needs.
    """
    if not user_ids:
        return {}
    rows = (
        await db.execute(select(User).where(User.id.in_(user_ids)))
    ).scalars().all()
    return {
        user.id: (user.full_name or user.email or "Unknown user") for user in rows
    }


# --- language ----------------------------------------------------------
#
# The evidence state is a machine's finding about the record. These turn
# it into a sentence an audit report can carry, rather than quoting the
# internal diagnostic that explains it to a compliance operator. The
# diagnostic is still true and still stored; it is simply not what a
# finding should be headed with.


def _assessment_sentence(status: str | None, evidence_count: int) -> str:
    documents = (
        "No documents are"
        if evidence_count == 0
        else "One document is"
        if evidence_count == 1
        else f"{evidence_count} documents are"
    )
    match status:
        case "evidenced" | "satisfied":
            return (
                f"{documents} mapped to this requirement and the evidence on "
                "file was assessed as supporting it."
            )
        case "partially_evidenced":
            return (
                f"{documents} mapped to this requirement, and the evidence on "
                "file supports it only in part."
            )
        case "needs_review":
            return (
                f"{documents} mapped to this requirement, but the available "
                "evidence does not allow Veyntra to verify full coverage."
            )
        case "evidence_insufficient":
            return (
                f"{documents} mapped to this requirement, and the evidence on "
                "file was assessed as insufficient to demonstrate it."
            )
        case "deficient":
            return (
                "The mapped control does not fully address this requirement "
                "on the evidence available."
            )
        case "no_evidence" | "evidence_missing":
            return (
                "Sufficient evidence demonstrating this requirement was not "
                "found in Veyntra at audit preparation."
            )
        case "not_assessed":
            return "No control is mapped to this requirement."
        case "assessment_failed":
            return (
                "Veyntra could not complete an assessment of this "
                "requirement from the records available."
            )
        case "not_applicable":
            return "This requirement was assessed as not applicable."
        case _:
            return (
                f"{documents} mapped to this requirement. No assessment "
                "state was recorded."
            )


def _not_evidenced(item: AuditItem | None) -> str | None:
    """The specific thing preparation named as missing, when it named one.

    `prepared_missing` is two things wearing one field: sometimes an item
    an auditor can act on ("The approved AI policy"), sometimes a
    paragraph explaining Veyntra's own limits. The first belongs in a
    report; the second is what made a finding read like a system dump.
    """
    if item is None:
        return None
    missing = (item.prepared_missing or "").strip()
    if not missing or "Veyntra" in missing or len(missing) > 120:
        return None
    return missing.rstrip(".")


def _finding_heading(line: FindingLine) -> str:
    """The requirement, which is the subject of the finding."""
    parts = [part for part in (line.reference_code, line.requirement_title) if part]
    return " — ".join(parts) if parts else line.title


def _digest_payload(
    *,
    audit: Audit,
    items: list[AuditItem],
    findings: list[AuditFinding],
) -> str:
    """A fingerprint of everything the report asserts.

    Covers what would make a reissued report say something different:
    the audit's own state, every conclusion, and every finding's live
    remediation and verification. Deliberately not the whole row — an
    `updated_at` touched by an unrelated write would report the audit as
    changed when nothing a reader could see had.
    """
    payload = {
        "status": audit.status,
        "scope": audit.scope,
        "title": audit.title,
        "auditor": audit.auditor_name,
        "framework": audit.framework_name,
        "started_at": audit.started_at.isoformat() if audit.started_at else None,
        "completed_at": (
            audit.completed_at.isoformat() if audit.completed_at else None
        ),
        "items": sorted(
            [
                {
                    "code": item.reference_code,
                    "decision": item.decision,
                    "note": item.decision_note,
                    "excluded": item.excluded_at is not None,
                }
                for item in items
            ],
            key=lambda entry: entry["code"] or "",
        ),
        "findings": sorted(
            [
                {
                    "id": str(finding.id),
                    "severity": finding.severity,
                    "status": finding.status,
                    "verified": (
                        finding.verified_at.isoformat()
                        if finding.verified_at
                        else None
                    ),
                    "superseded": finding.superseded_at is not None,
                }
                for finding in findings
            ],
            key=lambda entry: entry["id"],
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _executive_summary(
    *,
    audit: Audit,
    progress: ReportProgress,
    conclusion_counts: dict[str, int],
    severity_counts: dict[str, int],
    remediation_counts: dict[str, int],
) -> list[str]:
    """The result, in the two or three sentences an executive reads.

    Assembled entirely from counts. No judgement is added and no
    narrative is inferred: a report that editorialises about what the
    numbers mean is asserting something the auditor did not.
    """
    framework = audit.framework_name or "in-scope"
    scoped = progress.scoped
    reviewed = progress.reviewed

    opening = (
        f"This internal audit assessed {scoped} {framework} requirement"
        f"{'' if scoped == 1 else 's'} within the defined scope."
    )
    if reviewed == scoped:
        opening += f" All {scoped} were reviewed."
    else:
        opening += (
            f" {reviewed} of {scoped} were reviewed; "
            f"{scoped - reviewed} carry no auditor conclusion."
        )

    raised = [
        (label, count)
        for label, count in (
            (FINDING_CONCLUSION_LABELS.get(severity, severity), severity_counts.get(severity, 0))
            for severity in SEVERITY_ORDER
        )
        if count
    ]
    if not raised:
        result = "The auditor recorded no findings."
    else:
        listed = ", ".join(
            f"{count} {label.lower()}{'' if count == 1 else 's'}"
            for label, count in reversed(raised)
        )
        result = f"The auditor recorded {listed}."
        absent = [
            FINDING_CONCLUSION_LABELS[severity]
            for severity in ("critical", "high")
            if not severity_counts.get(severity)
        ]
        if len(absent) == 2:
            result += " No major or critical findings were raised."
        elif absent:
            result += f" No {absent[0].lower()}s were raised."

    clean = conclusion_counts.get(DECISION_LABELS["no_finding"], 0)
    if clean:
        result += (
            f" {clean} requirement{'' if clean == 1 else 's'} "
            f"{'was' if clean == 1 else 'were'} concluded with no finding."
        )

    live = sum(remediation_counts.values())
    if not live:
        remediation = "No remediation items were opened by this audit."
    else:
        # "1 remediation in progress" reads as a category name pasted into
        # a sentence, because it is one. The summary uses the phrase a
        # person would say.
        phrasing = {"remediation_in_progress": "in progress"}
        parts = [
            f"{remediation_counts[status]} "
            f"{phrasing.get(status, STATUS_LABELS[status].lower())}"
            for status in REMEDIATION_SCALE
            if remediation_counts.get(status)
        ]
        remediation = (
            "At the time this report was generated, remediation stood at: "
            + ", ".join(parts)
            + "."
        )

    return [opening, result, remediation]


def _limitations(
    *,
    audit: Audit,
    items: list[AuditItem],
    excluded: list[AuditItem],
    superseded: list[FindingLine],
    undecided: list[AuditItem],
) -> list[str]:
    """What this report does not cover, said plainly.

    A compliance document that states only its findings overstates its
    own reach. Anybody relying on it needs to know what was left out and
    on what basis the rest was concluded.
    """
    lines: list[str] = []
    if audit.framework_id is None:
        lines.append(
            "This audit was scoped manually and is not mapped to a framework's "
            "requirement set. Coverage reflects the auditor's scope statement "
            "only."
        )
    if excluded:
        one = len(excluded) == 1
        codes = ", ".join(item.reference_code for item in excluded[:12])
        more = f" and {len(excluded) - 12} more" if len(excluded) > 12 else ""
        lines.append(
            f"{len(excluded)} requirement{'' if one else 's'} "
            f"{'was' if one else 'were'} excluded from scope by the auditor and "
            f"not examined: {codes}{more}."
        )
    if undecided:
        one = len(undecided) == 1
        lines.append(
            f"{len(undecided)} scoped requirement{'' if one else 's'} "
            f"{'carries' if one else 'carry'} no auditor conclusion and "
            f"{'is' if one else 'are'} reported as unreviewed."
        )
    no_evidence = [
        item
        for item in items
        if not (item.evidence_snapshot or []) and item.excluded_at is None
    ]
    if no_evidence:
        one = len(no_evidence) == 1
        lines.append(
            f"{len(no_evidence)} scoped requirement{'' if one else 's'} had no "
            "evidence on file at the time of review. Absence of evidence is "
            "recorded as such and is not itself a finding."
        )
    if superseded:
        one = len(superseded) == 1
        lines.append(
            f"{len(superseded)} earlier conclusion{'' if one else 's'} "
            f"{'was' if one else 'were'} replaced during the audit and "
            f"{'is' if one else 'are'} listed separately. "
            f"{'It is' if one else 'They are'} retained for traceability and "
            f"excluded from the finding counts."
        )
    lines.append(
        "Evidence was reviewed as recorded in Veyntra at the time of the audit. "
        "Documents may have been superseded since."
    )
    lines.append(
        "Remediation status reflects the generation date of this report and "
        "continues to change after an audit closes. The audit conclusions do "
        "not."
    )
    return lines


async def _evidence_versions(
    db: AsyncSession, file_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str]]:
    """The version each file was filed under, and where that came from.

    `policy_versions` is keyed on the file, so it answers "what version
    is this document" — which is the question an evidence index asks.
    `policies.version` answers "what version is this policy now", which
    is a different question and only used when the first has no row.
    """
    if not file_ids:
        return {}
    resolved: dict[uuid.UUID, tuple[str, str]] = {}
    for file_id, version in (
        await db.execute(
            select(PolicyVersion.file_id, PolicyVersion.version).where(
                PolicyVersion.file_id.in_(file_ids)
            )
        )
    ).all():
        if file_id is not None and version:
            resolved[file_id] = (version, "version_record")
    missing = file_ids - set(resolved)
    if missing:
        for file_id, version in (
            await db.execute(
                select(Policy.file_id, Policy.version).where(
                    Policy.file_id.in_(missing)
                )
            )
        ).all():
            if file_id is not None and version:
                resolved[file_id] = (version, "policy")
    return resolved


async def build_preview(db: AsyncSession, *, audit: Audit) -> AuditReportPreview:
    """Assemble the report contents. Writes nothing.

    Everything comes from the audit's own snapshot rows. The only live
    reads are the ones the report explicitly labels as live: a finding's
    current remediation status, its owner and due date, and its
    verification.
    """
    items = list(
        (
            await db.execute(select(AuditItem).where(AuditItem.audit_id == audit.id))
        )
        .scalars()
        .all()
    )
    items.sort(key=lambda item: code_key(item.reference_code))
    scoped = [item for item in items if item.excluded_at is None]
    excluded = [item for item in items if item.excluded_at is not None]
    item_by_id = {item.id: item for item in items}

    findings = list(
        (
            await db.execute(
                select(AuditFinding).where(AuditFinding.audit_id == audit.id)
            )
        )
        .scalars()
        .all()
    )
    by_id = {finding.id: finding for finding in findings}

    task_ids = {f.related_task_id for f in findings if f.related_task_id}
    tasks: dict[uuid.UUID, Task] = {}
    if task_ids:
        for task in (
            (await db.execute(select(Task).where(Task.id.in_(task_ids))))
            .scalars()
            .all()
        ):
            tasks[task.id] = task

    actor_ids = (
        {item.decided_by for item in items if item.decided_by}
        | {finding.verified_by for finding in findings if finding.verified_by}
        | {task.assignee_id for task in tasks.values() if task.assignee_id}
        | ({audit.auditor_user_id} if audit.auditor_user_id else set())
    )
    names = await _names(db, {i for i in actor_ids if i})

    # --- conclusions -----------------------------------------------------
    conclusions: list[ConclusionLine] = []
    conclusion_counts: dict[str, int] = {}
    for item in scoped:
        finding = by_id.get(item.finding_id) if item.finding_id else None
        label = (
            DECISION_LABELS.get(item.decision, item.decision or "")
            if item.decision
            else "Not reviewed"
        )
        conclusion_counts[label] = conclusion_counts.get(label, 0) + 1
        conclusions.append(
            ConclusionLine(
                reference_code=item.reference_code,
                requirement_title=item.requirement_title,
                control_title=item.control_title,
                evidence_state=item.prepared_status,
                evidence_state_label=EVIDENCE_STATE_LABELS.get(
                    item.prepared_status, item.prepared_status
                ),
                decision=item.decision,
                decision_label=label,
                decision_note=item.decision_note,
                decided_at=item.decided_at,
                decided_by=names.get(item.decided_by) if item.decided_by else None,
                evidence_count=len(item.evidence_snapshot or []),
                finding_id=finding.id if finding else None,
                current_remediation=finding.status if finding else None,
                current_remediation_label=(
                    STATUS_LABELS.get(finding.status, finding.status)
                    if finding
                    else None
                ),
            )
        )

    # --- findings, live and superseded -----------------------------------
    # What Veyntra reads as "the evidence supports this". A finding
    # raised over one of these is the interesting case §6 is about.
    satisfied_states = {"evidenced", "satisfied", "partially_evidenced"}

    def _line(finding: AuditFinding) -> FindingLine:
        item = (
            item_by_id.get(finding.audit_item_id) if finding.audit_item_id else None
        )
        evidence_count = len(finding.evidence_snapshot or [])
        state = item.prepared_status if item else None
        task = (
            tasks.get(finding.related_task_id) if finding.related_task_id else None
        )
        note = (finding.description or None) or (
            item.decision_note if item else None
        )
        return FindingLine(
            id=finding.id,
            reference_code=finding.requirement_code,
            requirement_title=item.requirement_title if item else None,
            title=finding.title,
            description=finding.description,
            severity=finding.severity,
            conclusion_label=FINDING_CONCLUSION_LABELS.get(
                finding.severity, finding.severity.title()
            ),
            current_status=finding.status,
            current_status_label=STATUS_LABELS.get(finding.status, finding.status),
            control_title=finding.control_title,
            evidence_state=state,
            evidence_state_label=(
                EVIDENCE_STATE_LABELS.get(state, state) if state else None
            ),
            assessment=_assessment_sentence(state, evidence_count),
            not_evidenced=_not_evidenced(item),
            # The auditor's own reason, where they gave one. `description`
            # carries the note recorded with the decision.
            auditor_note=note,
            rationale_gap=bool(state in satisfied_states and not note),
            evidence_count=evidence_count,
            verified_at=finding.verified_at,
            verified_by=(
                names.get(finding.verified_by) if finding.verified_by else None
            ),
            verification_note=finding.verification_note,
            remediation_task=task.title if task else None,
            remediation_owner=(
                names.get(task.assignee_id) if task and task.assignee_id else None
            ),
            remediation_due=task.due_at if task else None,
            superseded_at=finding.superseded_at,
            superseded_reason=finding.superseded_reason,
        )

    live = [_line(f) for f in findings if f.superseded_at is None]
    superseded = [_line(f) for f in findings if f.superseded_at is not None]

    order = {severity: index for index, severity in enumerate(SEVERITY_ORDER)}
    live.sort(
        key=lambda line: (
            order.get(line.severity, 9),
            code_key(line.reference_code or ""),
        )
    )
    superseded.sort(key=lambda line: (order.get(line.severity, 9), line.title))

    # §10: grouped, and empty groups left out rather than printed as
    # headings over nothing.
    findings_by_severity = [
        SeverityGroup(
            key=key,
            severity=severities[0],
            label=label,
            count=len(group),
            findings=group,
        )
        for key, label, severities in SEVERITY_GROUPS
        if (group := [line for line in live if line.severity in severities])
    ]

    severity_counts = {
        severity: sum(1 for line in live if line.severity == severity)
        for severity in SEVERITY_ORDER
    }
    remediation_counts = {
        status: sum(1 for line in live if line.current_status == status)
        for status in REMEDIATION_SCALE
    }
    remediation = [
        RemediationGroup(
            status=status,
            label=STATUS_LABELS[status],
            count=remediation_counts[status],
        )
        for status in REMEDIATION_SCALE
        # Accepted risk is only shown when something is in it; the other
        # four are the standing scale and are reported with their zeros.
        if status != "accepted_risk" or remediation_counts[status]
    ]

    verification = sorted(
        [line for line in live + superseded if line.verified_at is not None],
        key=lambda line: line.verified_at or _now(),
    )

    # --- evidence index --------------------------------------------------
    #
    # One row per document, naming every requirement it was read against
    # and what Veyntra made of each. Deduplicated on the file, because
    # the same policy answering six requirements is one document the
    # reader may want to check, not six.
    grouped: dict[str, dict] = {}
    for item in scoped:
        for entry in item.evidence_snapshot or []:
            key = str(
                entry.get("file_id") or entry.get("evidence_id") or entry.get("title")
            )
            record = grouped.setdefault(
                key,
                {
                    "title": entry.get("title") or entry.get("filename") or "Evidence",
                    "filename": entry.get("filename"),
                    "document_href": entry.get("document_href"),
                    "file_id": entry.get("file_id"),
                    # Recorded into the snapshot at preparation from
                    # `d1a7f3b9c204` onward. Older audits have none, and
                    # fall back below.
                    "version": entry.get("document_version"),
                    "codes": [],
                    "states": [],
                },
            )
            if entry.get("document_version") and not record["version"]:
                record["version"] = entry["document_version"]
            if item.reference_code not in record["codes"]:
                record["codes"].append(item.reference_code)
            state = EVIDENCE_STATE_LABELS.get(
                item.prepared_status, item.prepared_status
            )
            if state and state not in record["states"]:
                record["states"].append(state)

    needs_lookup = {
        uuid.UUID(str(record["file_id"]))
        for record in grouped.values()
        if record["file_id"] and not record["version"]
    }
    resolved = await _evidence_versions(db, needs_lookup)

    evidence_index: list[EvidenceLine] = []
    for record in grouped.values():
        version = record["version"]
        source = "snapshot" if version else "unrecorded"
        if not version and record["file_id"]:
            found = resolved.get(uuid.UUID(str(record["file_id"])))
            if found:
                version, source = found
        evidence_index.append(
            EvidenceLine(
                title=record["title"],
                filename=record["filename"],
                document_href=record["document_href"],
                version=version,
                # §16: a blank dash tells the reader nothing about
                # whether a version exists and was not captured, or
                # nobody ever recorded one.
                version_label=version or "Version not recorded",
                version_source=source,
                evidence_states=list(record["states"]),
                requirement_codes=sorted(record["codes"], key=code_key),
            )
        )
    evidence_index.sort(key=lambda line: line.title.lower())

    # --- state -----------------------------------------------------------
    undecided = [item for item in scoped if item.decision is None]
    reviewed = len(scoped) - len(undecided)
    percent = round(reviewed / len(scoped) * 100) if scoped else 0
    progress = ReportProgress(
        scoped=len(scoped),
        reviewed=reviewed,
        percent_reviewed=percent,
        excluded=len(excluded),
        findings=len(live),
        superseded=len(superseded),
    )

    metrics = [
        Metric("Requirements in scope", str(progress.scoped), emphasis=True),
        Metric(
            "Requirements reviewed",
            f"{progress.reviewed} / {progress.scoped}",
            emphasis=True,
        ),
    ]
    if progress.excluded:
        metrics.append(Metric("Excluded from scope", str(progress.excluded)))
    if progress.superseded:
        # Reported so the finding count reconciles with the conclusion
        # count on its face. Without it a reader sees 18 conclusions and
        # 18 findings over a table with 19 rows in it.
        metrics.append(
            Metric("Conclusions replaced", str(progress.superseded))
        )
    # §2/§9: every conclusion on the scale, zeros included.
    conclusion_summary = [
        Metric(
            DECISION_LABELS[decision],
            str(
                conclusion_counts.get(DECISION_LABELS[decision], 0)
                if decision == "no_finding"
                else severity_counts.get(DECISION_SEVERITY[decision], 0)
            ),
        )
        for decision in CONCLUSION_SCALE
    ]
    metrics += conclusion_summary
    metrics += [
        Metric(STATUS_LABELS[status], str(remediation_counts[status]))
        for status in REMEDIATION_SCALE
        if status != "accepted_risk" or remediation_counts[status]
    ]

    blockers: list[Blocker] = []
    if audit.status != "completed":
        blockers.append(
            Blocker(
                code="audit_not_completed",
                message=(
                    "This audit is not complete. A report issued now would state "
                    "conclusions the auditor has not finished reaching."
                ),
            )
        )
    if not scoped:
        blockers.append(
            Blocker(
                code="nothing_in_scope",
                message="This audit has no scoped requirements to report on.",
            )
        )

    version = await next_version(db, audit_id=audit.id)
    generated_for = _now()
    # Both identities from their own authoritative records: the
    # organization from the organization row, the auditor from what the
    # audit recorded about membership. Neither is derived from the other,
    # and neither from whoever is logged in.
    organization = await db.get(Organization, audit.organization_id)
    organization_name = organization_display_name(organization)
    auditor = await resolve_auditor(db, audit=audit)

    return AuditReportPreview(
        audit_id=audit.id,
        title=f"{audit.title} — Internal Audit Report",
        audit_title=audit.title,
        organization_name=organization_name or UNCONFIGURED_ORGANIZATION,
        organization_name_configured=organization_name is not None,
        framework_name=audit.framework_name,
        framework_basis=(
            (
                f"{len(items)} requirement{'' if len(items) == 1 else 's'} as "
                "catalogued when this audit was prepared"
                + (
                    f" on {audit.prepared_at.strftime('%B %d, %Y')}"
                    if audit.prepared_at
                    else ""
                )
            )
            if audit.framework_name
            else None
        ),
        auditor_name=auditor.name,
        auditor=auditor,
        scope=audit.scope,
        status=audit.status,
        status_label=audit.status.replace("_", " ").title(),
        started_at=audit.started_at,
        completed_at=audit.completed_at,
        prepared_at=audit.prepared_at,
        classification=CLASSIFICATION,
        progress=progress,
        executive_summary=_executive_summary(
            audit=audit,
            progress=progress,
            conclusion_counts=conclusion_counts,
            severity_counts=severity_counts,
            remediation_counts=remediation_counts,
        ),
        metrics=metrics,
        methodology=METHODOLOGY,
        conclusions=conclusions,
        conclusion_counts=conclusion_counts,
        conclusion_summary=conclusion_summary,
        findings=live,
        findings_by_severity=findings_by_severity,
        superseded_findings=superseded,
        remediation=remediation,
        # §12: one row per finding, worst first — the same order the
        # findings section uses, so a reader can move between them.
        remediation_rows=list(live),
        verification=verification,
        evidence_index=evidence_index,
        limitations=_limitations(
            audit=audit,
            items=scoped,
            excluded=excluded,
            superseded=superseded,
            undecided=undecided,
        ),
        disclaimer=DISCLAIMER,
        sign_off=SignOff(
            auditor=auditor,
            completed_at=audit.completed_at,
            generated_at=generated_for,
            generated_by=None,
            report_version=version,
        ),
        generated_for=generated_for,
        digest=_digest_payload(audit=audit, items=items, findings=findings),
        next_version=version,
        blockers=blockers,
    )


async def current_digest(db: AsyncSession, *, audit: Audit) -> str:
    """The audit's fingerprint now, for "changed since generated".

    Cheaper than building a whole preview, and used on every load of the
    audit page to decide whether an issued report still describes the
    audit as it stands.
    """
    items = list(
        (
            await db.execute(select(AuditItem).where(AuditItem.audit_id == audit.id))
        )
        .scalars()
        .all()
    )
    findings = list(
        (
            await db.execute(
                select(AuditFinding).where(AuditFinding.audit_id == audit.id)
            )
        )
        .scalars()
        .all()
    )
    return _digest_payload(audit=audit, items=items, findings=findings)


__all__ = [
    "CLASSIFICATION",
    "DISCLAIMER",
    "METHODOLOGY",
    "AuditReportPreview",
    "Blocker",
    "build_preview",
    "current_digest",
    "next_version",
]
