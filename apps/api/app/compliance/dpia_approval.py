"""Article 36: the residual risk a controller cannot sign off alone.

When a DPIA lands on a high residual rating, the organization is saying
that after everything it intends to do, a high risk to data subjects
remains. GDPR Article 36(1) treats that as the case where the controller
consults the supervisory authority before processing — and inside the
product it is the case where completion cannot be a button somebody
presses on their own.

So a high residual rating raises an `Approval`, and
`dpia_workflow.completion_blockers` refuses completion until that
approval is granted. The approval is raised from the *rating*, not from
a status change, because the rating is the fact that makes it necessary.

Two things this deliberately does not do.

It does not hardcode who approves. The existing Approval Center decides
that; wiring a DPO in here would assert a role structure the customer
may not have. And it does not raise a second approval when the rating is
recalculated — one high residual risk is one decision, however many
times the arithmetic runs.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import DPIA
from app.core.models import Approval

HIGH = "high"


async def sync_high_residual_approval(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dpia: DPIA,
    actor_user_id: uuid.UUID | None,
) -> Approval | None:
    """Raise the approval a high residual rating needs, once.

    Returns the approval governing this DPIA, or None where none is
    required. A rating that falls back below high leaves any existing
    approval alone: it is a record that somebody was asked, and deleting
    it would erase the question along with the answer.
    """
    if dpia.residual_risk_level != HIGH:
        return (
            await db.get(Approval, dpia.approval_id) if dpia.approval_id else None
        )

    if dpia.approval_id is not None:
        existing = await db.get(Approval, dpia.approval_id)
        if existing is not None:
            # One high residual risk is one decision, however many times
            # the residual arithmetic is re-run.
            return existing

    approval = Approval(
        organization_id=organization_id,
        action_type=f"Accept high residual risk: {dpia.title}",
        risk_class=HIGH,
        requested_by=actor_user_id,
        module="compliance",
    )
    db.add(approval)
    await db.flush()
    dpia.approval_id = approval.id

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dpia.residual_approval_required",
        object_type="dpia",
        object_id=str(dpia.id),
        after_state={
            "approval_id": str(approval.id),
            "residual_risk": dpia.residual_risk_level,
        },
    )
    await db.flush()
    return approval


__all__ = ["HIGH", "sync_high_residual_approval"]
