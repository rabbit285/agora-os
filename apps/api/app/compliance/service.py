"""Compliance domain services.

`record_assessment` ships the Phase 3 cross-module hook (spec section 80:
do not build disconnected modules) — a failed control assessment creates
a shared `core.Task` automatically, the same primitive Tasks/Approvals
already use, rather than the Compliance module inventing its own
follow-up mechanism.

`register_ai_system` / `decide_ai_system_status` ship a second hook (spec
section 69 "New AI Tool Adoption": "... -> AI risk assessment -> Approval
-> Add to AI inventory -> ..."): registering a `high` or
`unacceptable`-risk AI system creates a real `core.Approval`, and
`decide_ai_system_status` refuses to move that system to `approved`
until the Approval is actually granted — reusing the same primitive
Automation's `human_approval` step already exercises (ADR-0021), not a
compliance-specific gate. See docs/DECISIONS.md ADR-0027.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import AISystem, Control, ControlAssessment
from app.core.models import Approval, Task

_HIGH_RISK_TIERS = {"high", "unacceptable"}


async def record_assessment(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    control: Control,
    status: str,
    notes: str | None,
    assessed_by: uuid.UUID | None,
) -> ControlAssessment:
    assessment = ControlAssessment(
        organization_id=organization_id,
        control_id=control.id,
        status=status,
        notes=notes,
        assessed_by=assessed_by,
    )
    db.add(assessment)
    await db.flush()

    control.status = "needs_review" if status in ("fail", "partial") else "implemented"

    if status == "fail":
        db.add(
            Task(
                organization_id=organization_id,
                title=f"Remediate failed control: {control.title}",
                description=notes,
                module="compliance",
                priority="high",
                status="open",
            )
        )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=assessed_by,
        action="compliance.control.assessed",
        object_type="control",
        object_id=str(control.id),
        after_state={"status": status},
    )
    return assessment


async def register_ai_system(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    name: str,
    vendor: str | None,
    purpose: str,
    risk_classification: str,
    owner_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> AISystem:
    system = AISystem(
        organization_id=organization_id,
        name=name,
        vendor=vendor,
        purpose=purpose,
        risk_classification=risk_classification,
        owner_id=owner_id,
    )
    db.add(system)
    await db.flush()

    if risk_classification in _HIGH_RISK_TIERS:
        approval = Approval(
            organization_id=organization_id,
            action_type=f"Approve high-risk AI system: {name}",
            risk_class="critical" if risk_classification == "unacceptable" else "high",
            requested_by=actor_user_id,
        )
        db.add(approval)
        await db.flush()
        system.approval_id = approval.id

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.ai_system.registered",
        object_type="ai_system",
        object_id=str(system.id),
        after_state={
            "risk_classification": risk_classification,
            "approval_id": str(system.approval_id) if system.approval_id else None,
        },
    )
    return system


async def decide_ai_system_status(
    db: AsyncSession,
    *,
    system: AISystem,
    new_status: str,
    actor_user_id: uuid.UUID | None,
) -> AISystem:
    if new_status == "approved" and system.approval_id is not None:
        approval = await db.get(Approval, system.approval_id)
        if approval is None or approval.status != "approved":
            raise ValueError(
                "This AI system requires its pending approval to be granted "
                "before it can be marked approved"
            )

    before_status = system.status
    system.status = new_status
    await record_event(
        db,
        organization_id=system.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.ai_system.status_changed",
        object_type="ai_system",
        object_id=str(system.id),
        before_state={"status": before_status},
        after_state={"status": new_status},
    )
    return system
