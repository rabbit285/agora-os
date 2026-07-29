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

`register_ai_system` also now creates a linked draft `DPIA` for
high/unacceptable-risk systems — the same "New AI Tool Adoption" chain's
"Privacy assessment" step, extending this hook a second time the way
Phase 8's Security Incident chain extended its own hook twice (ADR-0018
then ADR-0023). `create_dpia` / `decide_dpia_status` give standalone,
directly-created DPIAs their own Approval gate when `risk_level="high"`
— the AI-system-linked hook doesn't create a second Approval, since the
AISystem's own Approval already covers that sign-off. See
docs/DECISIONS.md ADR-0029.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import DPIA, DSAR, AISystem, Control, ControlAssessment
from app.core.models import Approval, Task
from app.db.base import utcnow

_HIGH_RISK_TIERS = {"high", "unacceptable"}
DSAR_RESPONSE_WINDOW_DAYS = 30


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

        # "New AI Tool Adoption" chain's "Privacy assessment" step (spec
        # §69) — no separate Approval here; the AISystem's own Approval
        # already covers sign-off for this registration.
        dpia = DPIA(
            organization_id=organization_id,
            ai_system_id=system.id,
            title=f"DPIA: {name}",
            risk_level="high",
            status="draft",
            owner_id=owner_id,
        )
        db.add(dpia)
        await db.flush()
        await record_event(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="compliance.dpia.created_from_ai_system",
            object_type="dpia",
            object_id=str(dpia.id),
            after_state={"ai_system_id": str(system.id)},
        )

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


async def create_dpia(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    title: str,
    processing_activity_id: uuid.UUID | None,
    risk_level: str,
    owner_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> DPIA:
    dpia = DPIA(
        organization_id=organization_id,
        processing_activity_id=processing_activity_id,
        title=title,
        risk_level=risk_level,
        owner_id=owner_id,
    )
    db.add(dpia)
    await db.flush()

    if risk_level == "high":
        approval = Approval(
            organization_id=organization_id,
            action_type=f"Approve high-risk DPIA: {title}",
            risk_class="high",
            requested_by=actor_user_id,
        )
        db.add(approval)
        await db.flush()
        dpia.approval_id = approval.id

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dpia.created",
        object_type="dpia",
        object_id=str(dpia.id),
        after_state={
            "risk_level": risk_level,
            "approval_id": str(dpia.approval_id) if dpia.approval_id else None,
        },
    )
    return dpia


async def decide_dpia_status(
    db: AsyncSession,
    *,
    dpia: DPIA,
    new_status: str,
    actor_user_id: uuid.UUID | None,
) -> DPIA:
    if new_status == "approved" and dpia.approval_id is not None:
        approval = await db.get(Approval, dpia.approval_id)
        if approval is None or approval.status != "approved":
            raise ValueError(
                "This DPIA requires its pending approval to be granted before it can be "
                "marked approved"
            )

    before_status = dpia.status
    dpia.status = new_status
    await record_event(
        db,
        organization_id=dpia.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dpia.status_changed",
        object_type="dpia",
        object_id=str(dpia.id),
        before_state={"status": before_status},
        after_state={"status": new_status},
    )
    return dpia


async def create_dsar(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    requester_name: str,
    requester_email: str,
    request_type: str,
    assigned_to: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> DSAR:
    dsar = DSAR(
        organization_id=organization_id,
        requester_name=requester_name,
        requester_email=requester_email,
        request_type=request_type,
        due_at=utcnow() + timedelta(days=DSAR_RESPONSE_WINDOW_DAYS),
        assigned_to=assigned_to,
    )
    db.add(dsar)
    await db.flush()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dsar.received",
        object_type="dsar",
        object_id=str(dsar.id),
        after_state={"request_type": request_type, "due_at": dsar.due_at.isoformat()},
    )
    return dsar


async def update_dsar_status(
    db: AsyncSession,
    *,
    dsar: DSAR,
    new_status: str,
    notes: str | None,
    actor_user_id: uuid.UUID | None,
) -> DSAR:
    before_status = dsar.status
    dsar.status = new_status
    if notes is not None:
        dsar.notes = notes
    if new_status == "fulfilled":
        dsar.fulfilled_at = utcnow()
    await record_event(
        db,
        organization_id=dsar.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dsar.status_changed",
        object_type="dsar",
        object_id=str(dsar.id),
        before_state={"status": before_status},
        after_state={"status": new_status},
    )
    return dsar
