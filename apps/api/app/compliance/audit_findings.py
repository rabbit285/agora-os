"""What the auditor decides, and what happens to it afterwards.

A finding used to be a title, a severity and a paragraph, typed into a
form that knew nothing about the audit it belonged to. Which requirement?
Which control? What evidence had the auditor actually read? None of it
was recorded, so a finding could not be traced back to what it was about
or forward to the work that fixed it.

Here a finding is raised **from a row in the audit workspace**, and
inherits that row's context: the requirement, the control, the evidence
snapshot the auditor was looking at when they decided. Nobody retypes
anything, and the record says what it was based on.

Three rules the rest of this module exists to hold:

- **A decision is a person's.** Veyntra prepares, explains, and can
  suggest; it never records a finding nobody made, and never closes one.
- **Remediation is reused, not duplicated.** A requirement with an open
  compliance gap already has work attached to it. An audit finding about
  the same requirement links to that work rather than opening a second
  task for one problem.
- **Fixing is not closing.** The team can do the work and attach the
  evidence; whether that answers the finding is the auditor's call. The
  finding reaches `ready_for_verification` on its own and stops there.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.audit_workspace import (
    DECISION_LABELS,
    DECISION_SEVERITY,
    DECISIONS,
    REQUIRES_NOTE,
)
from app.compliance.models import (
    Audit,
    AuditFinding,
    AuditItem,
    ComplianceGap,
)
from app.core.models import Task

logger = logging.getLogger("agora.compliance.audit_findings")

# open                   — raised, nothing happening yet
# remediation_in_progress— work is attached and under way
# ready_for_verification — the team says it is done; the auditor has not
#                          looked
# closed                 — an auditor verified it
# accepted_risk          — a deliberate decision to live with it
STATUSES = (
    "open",
    "remediation_in_progress",
    "ready_for_verification",
    "closed",
    "accepted_risk",
)

STATUS_LABELS = {
    "open": "Open",
    "remediation_in_progress": "Remediation in progress",
    "ready_for_verification": "Ready for verification",
    "closed": "Closed",
    "accepted_risk": "Accepted risk",
}

# Severities that get remediation attached automatically.
#
# Minor is included because completion requires a minor finding to be
# owned (see `audit_state.SEVERITY_COMPLETION_RULE`), and a rule the
# normal flow cannot satisfy is a trap: the auditor records a minor
# finding and then cannot finish the audit, with nothing on screen
# offering to attach the work.
#
# Observations still get none. They are recorded and visible, and a task
# per observation turns the remediation board into a list nobody reads —
# which is also why an observation may simply stay open at completion.
REMEDIATED_SEVERITIES = ("medium", "high", "critical")


class DecisionRefused(Exception):
    """The decision cannot be recorded as asked."""


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class DecisionResult:
    """What recording a decision did."""

    item: AuditItem
    finding: AuditFinding | None = None
    finding_created: bool = False
    task_id: uuid.UUID | None = None
    task_reused: bool = False
    # A closed finding this decision replaced, if the auditor changed
    # their conclusion after verifying the previous one.
    superseded: AuditFinding | None = None


def default_title(item: AuditItem, decision: str) -> str:
    """What to call a finding nobody has named.

    The requirement is the subject. This used to lead with
    `prepared_missing`, on the reasoning that "Finding on §6.1" tells a
    reader nothing — true, but the cure was worse: that field is
    sometimes a specific gap and sometimes Veyntra explaining its own
    limits, so findings ended up titled "1 document(s) are mapped to this
    requirement, but Veyntra has no itemised expectation set for it yet".
    That is the plumbing presented as the audit result.

    So: the conclusion and the requirement, plus the specific gap where
    preparation named one short enough to read as a subtitle.
    """
    label = DECISION_LABELS.get(decision, decision)
    base = f"{label}: {item.requirement_title}"
    missing = (item.prepared_missing or "").strip().rstrip(".")
    if missing and len(missing) <= 80 and "Veyntra" not in missing:
        return f"{base} — {missing}"
    return base


async def _existing_remediation(
    db: AsyncSession, *, item: AuditItem
) -> tuple[uuid.UUID | None, ComplianceGap | None]:
    """Work already attached to this requirement's deficiency.

    The audit is looking at the same compliance state the gap list is.
    When a requirement already has an open gap with a task on it, an
    audit finding about that requirement is a second description of one
    problem — and opening a second task would put two rows on somebody's
    board for one piece of work, which then get half-done each.
    """
    gap = (
        await db.execute(
            select(ComplianceGap).where(
                ComplianceGap.organization_id == item.organization_id,
                ComplianceGap.requirement_id == item.requirement_id,
                ComplianceGap.status != "resolved",
            )
        )
    ).scalars().first()
    if gap is None:
        return None, None
    return gap.task_id, gap


async def record_decision(
    db: AsyncSession,
    *,
    audit: Audit,
    item: AuditItem,
    decision: str,
    note: str | None,
    actor_user_id: uuid.UUID | None,
    title: str | None = None,
) -> DecisionResult:
    """Record what the auditor concluded about one scoped requirement.

    Idempotent in the way that matters: deciding the same way twice
    updates the one finding rather than raising a second. Changing the
    decision moves the existing finding rather than leaving the old one
    behind — an auditor correcting themselves should not leave a
    contradiction in the record.
    """
    if decision not in DECISIONS:
        raise DecisionRefused(f"Unknown decision: {decision}")

    cleaned = (note or "").strip() or None
    if decision in REQUIRES_NOTE and not cleaned:
        raise DecisionRefused(
            f"{DECISION_LABELS[decision]} needs a reason. "
            "A finding against somebody's control has to say what is wrong "
            "with it."
        )

    before = item.decision
    item.decision = decision
    item.decision_note = cleaned
    item.decided_by = actor_user_id
    item.decided_at = _now()

    result = DecisionResult(item=item)
    severity = DECISION_SEVERITY.get(decision)

    if severity is None:
        # `no_finding` and `needs_evidence` assert no deficiency. Any
        # finding raised by an earlier decision on this row is withdrawn
        # rather than left standing over a conclusion that replaced it.
        if item.finding_id is not None:
            await _withdraw(
                db,
                item=item,
                actor_user_id=actor_user_id,
                reason=f"Decision changed to {DECISION_LABELS[decision]}.",
            )
        await _record_decision_event(
            db, audit=audit, item=item, before=before, actor_user_id=actor_user_id
        )
        await db.flush()
        return result

    finding = (
        await db.get(AuditFinding, item.finding_id)
        if item.finding_id is not None
        else None
    )
    replaced: AuditFinding | None = None
    if finding is not None and finding.status in ("closed", "accepted_risk"):
        # A verified finding is history. Changing the decision on the row
        # raises a fresh finding rather than reopening a closed
        # verification somebody signed.
        #
        # The old one is marked as replaced on the way past. It keeps its
        # severity, its status and its verification — nothing about what
        # happened is rewritten — but it stops counting as a live finding
        # on this audit. Leaving it unlabelled is what made a completed
        # audit read "18 conclusions, 19 findings" with nothing on screen
        # accounting for the difference.
        replaced = finding
        finding = None

    if finding is None:
        finding = AuditFinding(
            organization_id=item.organization_id,
            audit_id=audit.id,
            audit_item_id=item.id,
        )
        db.add(finding)
        result.finding_created = True

    finding.requirement_id = item.requirement_id
    finding.requirement_code = item.reference_code
    finding.control_id = item.control_id
    finding.control_title = item.control_title
    finding.title = (title or "").strip() or default_title(item, decision)
    finding.description = cleaned
    finding.severity = severity
    # What the auditor was looking at. Frozen: "the evidence I reviewed"
    # is a claim about a moment, and a live join would let it change
    # underneath the finding.
    finding.evidence_snapshot = list(item.evidence_snapshot or [])
    if finding.status not in STATUSES:  # pragma: no cover - defaulted
        finding.status = "open"

    await db.flush()
    item.finding_id = finding.id
    result.finding = finding
    if replaced is not None:
        replaced.superseded_at = _now()
        replaced.superseded_by_id = finding.id
        replaced.superseded_reason = (
            f"Replaced by a {DECISION_LABELS[decision].lower()} recorded later "
            "on the same requirement."
        )
        result.superseded = replaced
        await record_event(
            db,
            organization_id=item.organization_id,
            actor_user_id=actor_user_id,
            action="compliance.audit_finding.superseded",
            object_type="audit_finding",
            object_id=str(replaced.id),
            before_state={"severity": replaced.severity, "status": replaced.status},
            after_state={
                "superseded_by": str(finding.id),
                "requirement": item.reference_code,
                "reason": replaced.superseded_reason,
            },
        )

    if severity in REMEDIATED_SEVERITIES:
        task_id, gap = await _existing_remediation(db, item=item)
        if task_id is not None:
            # §13: one problem, one piece of work.
            finding.related_task_id = task_id
            finding.status = "remediation_in_progress"
            result.task_id = task_id
            result.task_reused = True
            logger.info(
                "Audit finding %s linked to existing remediation task %s",
                finding.id,
                task_id,
            )
        elif finding.related_task_id is None:
            task = Task(
                organization_id=item.organization_id,
                title=f"Remediate audit finding: {finding.title}",
                description=_task_description(item, finding),
                module="compliance",
                priority="urgent" if severity == "critical" else "high",
                assignee_id=audit.owner_id,
                entity_type="audit_finding",
                entity_id=str(finding.id),
            )
            db.add(task)
            await db.flush()
            finding.related_task_id = task.id
            finding.status = "remediation_in_progress"
            result.task_id = task.id
            if gap is not None:
                # Point the gap at the same work, so the compliance side
                # and the audit side are looking at one task.
                gap.task_id = task.id

    await _record_decision_event(
        db, audit=audit, item=item, before=before, actor_user_id=actor_user_id
    )
    if result.finding_created:
        await record_event(
            db,
            organization_id=item.organization_id,
            actor_user_id=actor_user_id,
            action="compliance.audit_finding.created",
            object_type="audit_finding",
            object_id=str(finding.id),
            after_state={
                "audit_id": str(audit.id),
                "title": finding.title,
                "severity": finding.severity,
                "requirement": item.reference_code,
                "control": item.control_title,
                "remediation_reused": result.task_reused,
            },
        )

    await db.flush()
    return result


def _task_description(item: AuditItem, finding: AuditFinding) -> str:
    """What the person doing the work needs to know.

    The requirement, what the auditor said, and what evidence would
    answer it — so the task is actionable without opening the audit.
    """
    lines = [
        f"Raised by audit finding against {item.framework_key or 'framework'} "
        f"{item.reference_code} — {item.requirement_title}.",
    ]
    if item.control_title:
        lines.append(f"Control: {item.control_title}")
    if finding.description:
        lines.append(f"Auditor's reason: {finding.description}")
    if item.prepared_missing:
        lines.append(f"Evidence needed: {item.prepared_missing}")
    return "\n\n".join(lines)


async def _withdraw(
    db: AsyncSession,
    *,
    item: AuditItem,
    actor_user_id: uuid.UUID | None,
    reason: str,
) -> None:
    """Take back a finding the auditor has replaced with a clean decision."""
    finding = await db.get(AuditFinding, item.finding_id)
    item.finding_id = None
    if finding is None:  # pragma: no cover - the id came from a real row
        return
    if finding.status in ("closed", "accepted_risk"):
        # Verified history is not withdrawn. It stays, marked as replaced
        # by the conclusion that took its place — visible in the record,
        # and out of the live counts.
        finding.superseded_at = _now()
        finding.superseded_reason = reason
        await record_event(
            db,
            organization_id=item.organization_id,
            actor_user_id=actor_user_id,
            action="compliance.audit_finding.superseded",
            object_type="audit_finding",
            object_id=str(finding.id),
            before_state={"severity": finding.severity, "status": finding.status},
            after_state={"requirement": item.reference_code, "reason": reason},
        )
        return
    await record_event(
        db,
        organization_id=item.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.audit_finding.withdrawn",
        object_type="audit_finding",
        object_id=str(finding.id),
        before_state={"status": finding.status},
        after_state={"reason": reason},
    )
    await db.delete(finding)


async def _record_decision_event(
    db: AsyncSession,
    *,
    audit: Audit,
    item: AuditItem,
    before: str | None,
    actor_user_id: uuid.UUID | None,
) -> None:
    if before == item.decision:
        # A retry, not a decision. Nothing moved, so nothing is news.
        return
    await record_event(
        db,
        organization_id=item.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.audit_item.decided",
        object_type="audit_item",
        object_id=str(item.id),
        before_state={"decision": before},
        after_state={
            "decision": item.decision,
            "requirement": item.reference_code,
            "audit_id": str(audit.id),
            "note": item.decision_note,
        },
    )


async def mark_ready_for_verification(
    db: AsyncSession,
    *,
    finding: AuditFinding,
    actor_user_id: uuid.UUID | None,
) -> bool:
    """The team says the work is done.

    Deliberately not a closure. Whether the fix answers the finding is a
    judgement about evidence, and the person who did the work is not the
    person who gets to make it.
    """
    if finding.status in ("closed", "accepted_risk", "ready_for_verification"):
        return False
    before = finding.status
    finding.status = "ready_for_verification"
    await record_event(
        db,
        organization_id=finding.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.audit_finding.ready_for_verification",
        object_type="audit_finding",
        object_id=str(finding.id),
        before_state={"status": before},
        after_state={"status": finding.status, "title": finding.title},
    )
    await db.flush()
    return True


async def verify_and_close(
    db: AsyncSession,
    *,
    finding: AuditFinding,
    note: str | None,
    actor_user_id: uuid.UUID | None,
    evidence: list[dict] | None = None,
) -> bool:
    """The auditor accepts the fix, and says on what basis.

    The note is required. A closure with no reasoning is the same
    document as no closure at all to anybody reading the audit later, and
    this is the record that says the organization's problem was actually
    solved.
    """
    if finding.status == "closed":
        return False
    cleaned = (note or "").strip()
    if not cleaned:
        raise DecisionRefused(
            "Closing a finding needs a verification note — what you checked, "
            "and what it showed."
        )

    before = finding.status
    finding.status = "closed"
    finding.verified_by = actor_user_id
    finding.verified_at = _now()
    finding.verification_note = cleaned
    if evidence:
        # What the closure relied on, kept beside the original snapshot
        # rather than replacing it: the record shows both what was wrong
        # and what fixed it.
        finding.evidence_snapshot = list(finding.evidence_snapshot or []) + list(
            evidence
        )

    await record_event(
        db,
        organization_id=finding.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.audit_finding.closed",
        object_type="audit_finding",
        object_id=str(finding.id),
        before_state={"status": before},
        after_state={
            "status": "closed",
            "title": finding.title,
            "verification_note": cleaned,
            "remediation_task_id": (
                str(finding.related_task_id) if finding.related_task_id else None
            ),
        },
    )
    await db.flush()
    return True


async def reopen(
    db: AsyncSession,
    *,
    finding: AuditFinding,
    note: str | None,
    actor_user_id: uuid.UUID | None,
) -> bool:
    """The auditor is not satisfied. Back to the team."""
    if finding.status == "open":
        return False
    before = finding.status
    finding.status = "open"
    finding.verified_by = None
    finding.verified_at = None
    finding.verification_note = (note or "").strip() or None
    await record_event(
        db,
        organization_id=finding.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.audit_finding.reopened",
        object_type="audit_finding",
        object_id=str(finding.id),
        before_state={"status": before},
        after_state={"status": "open", "reason": finding.verification_note},
    )
    await db.flush()
    return True


__all__ = [
    "REMEDIATED_SEVERITIES",
    "STATUSES",
    "STATUS_LABELS",
    "DecisionRefused",
    "DecisionResult",
    "default_title",
    "mark_ready_for_verification",
    "record_decision",
    "reopen",
    "verify_and_close",
]
