"""What state an audit is in, and what it takes to leave it.

Two ideas that were tangled together, separated here.

**The status and its timestamps are one fact, not three.** The bug this
module exists to end: `completed_at` was written on the way to
`completed` and never cleared on the way back, so an audit sat at
"Planned" with "Completed 8/26/2026" printed beside it. Neither the
column nor the screen was wrong; nothing owned the relationship between
them. Now one function moves both, and the invariants are asserted rather
than assumed.

**Completing an audit is a claim, and claims have preconditions.** An
audit that finishes with an unverified critical finding says something
untrue about the organization. So completion is gated, the gate lists
everything blocking it in the words a person would use, and the API
refuses rather than the screen hiding a button — a client that gets this
wrong must not be able to record a clean audit over an open critical
finding.

Lifecycle (`archived_at`) is a separate dimension and lives on the model,
not here. A completed audit that is archived is still completed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Audit, AuditFinding, AuditItem

# planned    — scoped, not started
# in_progress— the auditor is working through it
# completed  — the auditor has finished and stands behind the result
STATUSES = ("planned", "in_progress", "completed")

LABELS = {
    "planned": "Planned",
    "in_progress": "In progress",
    "completed": "Completed",
}

# What each severity means for finishing the audit. Stated as a table
# because "which findings block completion" is a policy question people
# ask, and burying it in an `in` check makes it something you have to
# read code to answer.
#
#   observation (low) — may stand open. Recorded and visible; it does not
#       contradict "this audit is done".
#   minor (medium)    — may stand open, but only once somebody owns it.
#       An open minor finding with nobody assigned and no date is not a
#       plan, it is a note.
#   major (high)      — blocks. An audit that concludes over an
#       unremediated major finding says something untrue.
#   critical          — blocks.
#
# Major and critical can still be carried, but only through an explicit
# accepted-risk decision with a name against it — see
# `RESOLVED_FINDING_STATUSES`.
SEVERITY_COMPLETION_RULE = {
    "low": "may_remain_open",
    "medium": "needs_owner",
    "high": "blocks",
    "critical": "blocks",
}

BLOCKING_SEVERITIES = tuple(
    severity
    for severity, rule in SEVERITY_COMPLETION_RULE.items()
    if rule == "blocks"
)

# Severities that may stay open at completion provided the work is owned.
OWNED_SEVERITIES = tuple(
    severity
    for severity, rule in SEVERITY_COMPLETION_RULE.items()
    if rule == "needs_owner"
)

# The words the screen uses for an auditor's conclusion. Deliberately not
# the severity keys: "low" is a severity, "Observation" is what the
# auditor concluded, and a report that says "3 low findings" has lost the
# distinction the whole workflow rests on.
CONCLUSION_LABELS = {
    "low": "Observation",
    "medium": "Minor",
    "high": "Major",
    "critical": "Critical",
}

# Finding states that count as resolved for that purpose. `closed` is a
# verified fix; `accepted_risk` is a deliberate decision to live with it.
# `ready_for_verification` is *not* — the work is done and nobody has
# checked it, which is exactly the state completion must not paper over.
RESOLVED_FINDING_STATUSES = ("closed", "accepted_risk")


@dataclass(frozen=True)
class Blocker:
    """One reason an audit cannot be completed."""

    code: str
    message: str


def _now() -> datetime:
    return datetime.now(UTC)


def apply_status(audit: Audit, status: str, *, at: datetime | None = None) -> None:
    """Move an audit to a status, and move its timestamps with it.

    The timestamps are the state. Going backwards clears the stamps that
    have stopped being true rather than leaving them behind as debris —
    a `planned` audit carrying a completion time is a record of something
    that did not happen, and the screen has no way to know it should
    ignore it.

    Idempotent, and safe to call with the status the audit already has.
    """
    if status not in STATUSES:
        raise ValueError(f"Unknown audit status: {status}")

    moment = at or _now()

    if status == "planned":
        audit.started_at = None
        audit.completed_at = None
    elif status == "in_progress":
        # Reopening a completed audit keeps the original start: the
        # engagement did begin when it began.
        audit.started_at = audit.started_at or moment
        audit.completed_at = None
    else:  # completed
        audit.started_at = audit.started_at or moment
        audit.completed_at = audit.completed_at or moment

    audit.status = status


def check_invariants(audit: Audit) -> list[str]:
    """States the audit must never be in. Empty means consistent.

    Written down so a test can assert them and a reader can see what
    "consistent" means, rather than inferring it from `apply_status`.
    """
    problems: list[str] = []
    if audit.status == "planned":
        if audit.started_at is not None:
            problems.append("A planned audit has not started.")
        if audit.completed_at is not None:
            problems.append("A planned audit has not been completed.")
    if audit.status == "in_progress":
        if audit.started_at is None:
            problems.append("An audit in progress has a start time.")
        if audit.completed_at is not None:
            problems.append("An audit in progress has not been completed.")
    if audit.status == "completed":
        if audit.completed_at is None:
            problems.append("A completed audit has a completion time.")
        if audit.started_at is None:
            problems.append("A completed audit has a start time.")
    return problems


@dataclass
class CompletionSummary:
    """What the audit found, for the screen that asks to finish it."""

    scoped: int = 0
    reviewed: int = 0
    no_finding: int = 0
    observations: int = 0
    minor: int = 0
    major: int = 0
    critical: int = 0
    needs_evidence: int = 0
    open_findings: int = 0
    ready_for_verification: int = 0
    evidence_reviewed: int = 0
    remediation_completed: int = 0
    # --- scope, so "3 requirements" is not left unexplained ------------
    not_applicable: int = 0
    excluded: int = 0
    # --- remediation, which is not the same as the finding ------------
    #
    # A finding is the auditor's conclusion; remediation is the work
    # attached to it. Collapsing them is why a completed audit read "3
    # open findings" when all three were observations with fixes under
    # way.
    remediation_open: int = 0
    remediation_in_progress: int = 0
    remediation_ready: int = 0
    remediation_closed: int = 0
    accepted_risk: int = 0

    @property
    def unreviewed(self) -> int:
        return max(self.scoped - self.reviewed, 0)

    @property
    def percent_reviewed(self) -> int:
        """Share of scope the auditor has dispositioned.

        Review progress, not compliance readiness. They are different
        numbers about different things and a screen showing one where the
        other belongs is worse than showing neither.
        """
        return round(100 * self.reviewed / self.scoped) if self.scoped else 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scoped": self.scoped,
            "not_applicable": self.not_applicable,
            "excluded": self.excluded,
            "remediation_open": self.remediation_open,
            "remediation_in_progress": self.remediation_in_progress,
            "remediation_ready": self.remediation_ready,
            "remediation_closed": self.remediation_closed,
            "accepted_risk": self.accepted_risk,
            "reviewed": self.reviewed,
            "unreviewed": self.unreviewed,
            "percent_reviewed": self.percent_reviewed,
            "no_finding": self.no_finding,
            "observations": self.observations,
            "minor": self.minor,
            "major": self.major,
            "critical": self.critical,
            "needs_evidence": self.needs_evidence,
            "open_findings": self.open_findings,
            "ready_for_verification": self.ready_for_verification,
            "evidence_reviewed": self.evidence_reviewed,
            "remediation_completed": self.remediation_completed,
        }


async def summarise(
    db: AsyncSession, *, audit_id: uuid.UUID
) -> CompletionSummary:
    """Everything the completion screen and the audit card need, once."""
    summary = CompletionSummary()

    items = (
        await db.execute(
            select(
                AuditItem.decision,
                AuditItem.evidence_snapshot,
                AuditItem.excluded_at,
            ).where(AuditItem.audit_id == audit_id)
        )
    ).all()

    seen_evidence: set[str] = set()
    for decision, evidence, excluded_at in items:
        if excluded_at is not None:
            # Out of scope for this audit. Counted so the scope line adds
            # up, and not counted as work left to review.
            summary.excluded += 1
            continue
        summary.scoped += 1
        for entry in evidence or []:
            identifier = str(entry.get("evidence_id") or entry.get("title") or "")
            if identifier:
                seen_evidence.add(identifier)
        if decision is None:
            continue
        summary.reviewed += 1
        match decision:
            case "no_finding":
                summary.no_finding += 1
            case "observation":
                summary.observations += 1
            case "minor":
                summary.minor += 1
            case "major":
                summary.major += 1
            case "critical":
                summary.critical += 1
            case "needs_evidence":
                summary.needs_evidence += 1

    summary.evidence_reviewed = len(seen_evidence)

    findings = (
        await db.execute(
            select(AuditFinding.status, AuditFinding.severity).where(
                AuditFinding.audit_id == audit_id
            )
        )
    ).all()
    for status, _severity in findings:
        if status not in RESOLVED_FINDING_STATUSES:
            summary.open_findings += 1
        match status:
            case "open":
                summary.remediation_open += 1
            case "remediation_in_progress":
                summary.remediation_in_progress += 1
            case "ready_for_verification":
                summary.ready_for_verification += 1
                summary.remediation_ready += 1
            case "closed":
                summary.remediation_closed += 1
                summary.remediation_completed += 1
            case "accepted_risk":
                summary.accepted_risk += 1

    return summary


async def start_blockers(db: AsyncSession, *, audit: Audit) -> list[Blocker]:
    """What stands between this audit and being started.

    Starting is the deliberate human checkpoint, and an audit with an
    empty scope is the one thing it must not wave through. A record that
    says "in progress" over nothing examined nothing, and later says
    "completed" over the same nothing — which is how an audit came to sit
    at Completed with 0 scoped requirements and a Prepare form still on
    its page.

    A custom audit is exempt: it scopes itself, and holding it to a
    framework's requirement count would block a legitimate engagement for
    failing a rule that does not apply to it.
    """
    if audit.status != "planned":
        return []

    blockers: list[Blocker] = []

    if audit.framework_id is not None and audit.prepared_at is None:
        blockers.append(
            Blocker(
                code="not_prepared",
                message=(
                    "This audit has not been prepared yet, so there is no "
                    "scope to work through."
                ),
            )
        )

    if audit.framework_id is not None:
        scoped = int(
            (
                await db.execute(
                    select(func.count(AuditItem.id)).where(
                        AuditItem.audit_id == audit.id
                    )
                )
            ).scalar_one()
        )
        if not scoped:
            blockers.append(
                Blocker(
                    code="empty_scope",
                    message=(
                        "No requirements are in scope for this audit, so there "
                        "is nothing to review. Check the framework's "
                        "applicability for this organization, or choose a "
                        "different framework."
                    ),
                )
            )

    return blockers


async def completion_blockers(
    db: AsyncSession, *, audit: Audit
) -> list[Blocker]:
    """What stands between this audit and being called finished.

    All of them, in the order somebody would work through them. An audit
    completed over an unverified critical finding is a document that says
    something untrue, and the person clicking the button is usually the
    one who would be answering for it.
    """
    blockers: list[Blocker] = []

    scoped = int(
        (
            await db.execute(
                select(func.count(AuditItem.id)).where(AuditItem.audit_id == audit.id)
            )
        ).scalar_one()
    )
    if audit.framework_id is not None and not scoped:
        # Nothing was examined, so there is nothing to conclude. Without
        # this, an audit that scoped nothing sails through completion —
        # no unreviewed rows and no findings look exactly like a clean
        # result, and the record then claims a framework was audited.
        blockers.append(
            Blocker(
                code="empty_scope",
                message=(
                    "This audit has no requirements in scope, so there is "
                    "nothing to conclude. Prepare it against a framework "
                    "first."
                ),
            )
        )
        return blockers

    unreviewed = int(
        (
            await db.execute(
                select(func.count(AuditItem.id)).where(
                    AuditItem.audit_id == audit.id,
                    AuditItem.decision.is_(None),
                )
            )
        ).scalar_one()
    )
    if unreviewed:
        blockers.append(
            Blocker(
                code="unreviewed_items",
                message=(
                    f"{unreviewed} scoped requirement"
                    f"{'' if unreviewed == 1 else 's'} "
                    f"{'has' if unreviewed == 1 else 'have'} no auditor decision yet."
                ),
            )
        )

    # §8, the middle rule: a minor finding may stand open at completion,
    # but only once somebody owns the work. An open minor finding with no
    # task behind it is not a plan, it is a note — and an audit that
    # completes over one has recorded an intention nobody holds.
    unowned = list(
        (
            await db.execute(
                select(AuditFinding.title)
                .where(
                    AuditFinding.audit_id == audit.id,
                    AuditFinding.severity.in_(OWNED_SEVERITIES),
                    AuditFinding.status.notin_(RESOLVED_FINDING_STATUSES),
                    AuditFinding.related_task_id.is_(None),
                )
                .order_by(AuditFinding.created_at.asc())
            )
        ).scalars().all()
    )
    if unowned:
        blockers.append(
            Blocker(
                code="unowned_minor_findings",
                message=(
                    f"{len(unowned)} minor finding"
                    f"{'' if len(unowned) == 1 else 's'} "
                    f"{'has' if len(unowned) == 1 else 'have'} no remediation "
                    "attached. A minor finding may stay open when the audit "
                    "completes, but only once somebody owns the work."
                ),
            )
        )

    unresolved = list(
        (
            await db.execute(
                select(AuditFinding.severity, AuditFinding.status, AuditFinding.title)
                .where(
                    AuditFinding.audit_id == audit.id,
                    AuditFinding.severity.in_(BLOCKING_SEVERITIES),
                    AuditFinding.status.notin_(RESOLVED_FINDING_STATUSES),
                )
                .order_by(AuditFinding.created_at.asc())
            )
        ).all()
    )
    if unresolved:
        awaiting = sum(
            1 for _s, status, _t in unresolved if status == "ready_for_verification"
        )
        blockers.append(
            Blocker(
                code="unresolved_findings",
                message=(
                    f"{len(unresolved)} major or critical finding"
                    f"{'' if len(unresolved) == 1 else 's'} "
                    f"{'is' if len(unresolved) == 1 else 'are'} still open."
                    + (
                        f" {awaiting} "
                        f"{'is' if awaiting == 1 else 'are'} waiting on your "
                        "verification."
                        if awaiting
                        else ""
                    )
                ),
            )
        )

    return blockers


__all__ = [
    "BLOCKING_SEVERITIES",
    "CONCLUSION_LABELS",
    "OWNED_SEVERITIES",
    "SEVERITY_COMPLETION_RULE",
    "start_blockers",
    "LABELS",
    "RESOLVED_FINDING_STATUSES",
    "STATUSES",
    "Blocker",
    "CompletionSummary",
    "apply_status",
    "check_invariants",
    "completion_blockers",
    "summarise",
]
