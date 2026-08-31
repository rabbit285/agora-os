"""Finding audits that are in states the workflow cannot produce.

Records exist from before the state machine did. The reported one sat at
**Completed with 0 scoped requirements** — started, finished, and having
examined nothing, because completion counted unreviewed rows and findings
and an empty audit has neither. Zero of zero looks exactly like a clean
result.

Two kinds of problem, handled differently on purpose:

- **Contradictions the rules can settle.** A planned audit carrying a
  completion time, or one in progress with no start. There is exactly one
  consistent reading of each, so they are corrected.
- **Conclusions nobody can reconstruct.** An audit that says it completed
  against a framework it never scoped. Deciding whether that was a real
  engagement or a test record means knowing something this code does not,
  so it is flagged and left alone. Inventing the history would be worse
  than leaving it visibly wrong.

Idempotent: a second pass finds nothing to correct and reports the same
flags.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance import audit_state
from app.compliance.models import Audit, AuditItem

logger = logging.getLogger("agora.compliance.audit_reconcile")


@dataclass
class AuditProblem:
    """One audit that is in a state the workflow cannot produce."""

    audit_id: uuid.UUID
    title: str
    status: str
    code: str
    detail: str
    repaired: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "audit_id": str(self.audit_id),
            "title": self.title,
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
            "repaired": self.repaired,
        }


@dataclass
class ReconcileReport:
    examined: int = 0
    repaired: int = 0
    flagged: int = 0
    problems: list[AuditProblem] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "examined": self.examined,
            "repaired": self.repaired,
            "flagged": self.flagged,
            "problems": [problem.as_dict() for problem in self.problems],
        }


async def reconcile_audits(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    dry_run: bool = True,
) -> ReconcileReport:
    """Correct what can be settled; flag what cannot.

    `dry_run` defaults to true. The first thing to do with a pass that
    rewrites audit conclusions is read what it would rewrite.
    """
    report = ReconcileReport()

    audits = list(
        (
            await db.execute(
                select(Audit)
                .where(Audit.organization_id == organization_id)
                .order_by(Audit.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    for audit in audits:
        report.examined += 1
        scoped = int(
            (
                await db.execute(
                    select(func.count(AuditItem.id)).where(
                        AuditItem.audit_id == audit.id
                    )
                )
            ).scalar_one()
        )

        # --- a conclusion drawn over nothing --------------------------
        #
        # Not repaired. "This audit completed" and "this audit examined
        # nothing" cannot both be true, and which one to keep is a
        # question about what actually happened.
        if (
            audit.status == "completed"
            and audit.framework_id is not None
            and scoped == 0
        ):
            report.flagged += 1
            report.problems.append(
                AuditProblem(
                    audit_id=audit.id,
                    title=audit.title,
                    status=audit.status,
                    code="completed_without_scope",
                    detail=(
                        "This audit is recorded as completed against a "
                        "framework, but no requirements were ever in scope, so "
                        "nothing was examined. Reopen it and prepare it, or "
                        "archive it as a record that should not have been "
                        "completed."
                    ),
                )
            )
            continue

        # A custom audit that completed. Legal — it scopes itself — but
        # only if it says what it covered. One with neither requirements
        # nor a scope statement concluded over nothing describable, and
        # whether that was a real engagement or a discarded test is not
        # something the data can settle.
        if audit.status == "completed" and audit.framework_id is None:
            if scoped == 0 and not (audit.scope or "").strip():
                report.flagged += 1
                report.problems.append(
                    AuditProblem(
                        audit_id=audit.id,
                        title=audit.title,
                        status=audit.status,
                        code="completed_without_anything",
                        detail=(
                            "This audit is recorded as completed, but it has no "
                            "framework, no requirements in scope and no scope "
                            "statement — so there is no record of what it "
                            "examined. Reopen and scope it, or archive it."
                        ),
                    )
                )
            continue

        # --- contradictions with one consistent reading ---------------
        problems = audit_state.check_invariants(audit)
        if not problems:
            continue

        before = {
            "status": audit.status,
            "started_at": audit.started_at.isoformat() if audit.started_at else None,
            "completed_at": (
                audit.completed_at.isoformat() if audit.completed_at else None
            ),
        }

        problem = AuditProblem(
            audit_id=audit.id,
            title=audit.title,
            status=audit.status,
            code="inconsistent_timestamps",
            detail="; ".join(problems),
        )

        if not dry_run:
            # The status is what somebody set; the timestamps are what
            # nothing maintained. So the status wins and the stamps are
            # brought into line with it, rather than the other way round.
            audit_state.apply_status(audit, audit.status)
            problem.repaired = True
            report.repaired += 1
            await record_event(
                db,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="compliance.audit.state_reconciled",
                object_type="audit",
                object_id=str(audit.id),
                before_state=before,
                after_state={
                    "status": audit.status,
                    "started_at": (
                        audit.started_at.isoformat() if audit.started_at else None
                    ),
                    "completed_at": (
                        audit.completed_at.isoformat() if audit.completed_at else None
                    ),
                    "reason": problem.detail,
                },
            )
        else:
            report.flagged += 1

        report.problems.append(problem)

    if not dry_run:
        await db.flush()

    logger.info(
        "Audit reconciliation for %s: examined=%d repaired=%d flagged=%d",
        organization_id,
        report.examined,
        report.repaired,
        report.flagged,
    )
    return report


__all__ = ["AuditProblem", "ReconcileReport", "reconcile_audits"]
