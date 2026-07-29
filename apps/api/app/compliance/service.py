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

`create_ai_incident` reuses `app.secops.service.create_incident`'s exact
`critical`-severity chain shape (Risk + Task + owner Notification) for a
third time (ADR-0018, ADR-0023, now ADR-0030) — an AI incident that's
`critical` gets the identical treatment a critical security incident
does, since both represent the same underlying obligation (assess and
respond to a serious incident affecting people), not two different
concepts that happen to share a severity field.

`record_vendor_assessment` reuses `record_assessment`'s "assessment
creates a tracked consequence" hook shape (spec §80) for a fourth entity
type: a `critical`/`high` vendor risk conclusion auto-creates a linked
Compliance `Risk`, the same way a failed Control assessment auto-creates
a Task. See docs/DECISIONS.md ADR-0031.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import (
    DPIA,
    DSAR,
    AIIncident,
    AISystem,
    Control,
    ControlAssessment,
    Risk,
    Vendor,
    VendorAssessment,
)
from app.core.models import Approval, Notification, Task
from app.db.base import utcnow

_HIGH_RISK_TIERS = {"high", "unacceptable"}
_HIGH_VENDOR_RISK_TIERS = {"high", "critical"}
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


async def create_ai_incident(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ai_system: AISystem,
    title: str,
    description: str | None,
    severity: str,
    owner_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> AIIncident:
    incident = AIIncident(
        organization_id=organization_id,
        ai_system_id=ai_system.id,
        title=title,
        description=description,
        severity=severity,
        owner_id=owner_id,
    )
    db.add(incident)
    await db.flush()

    if severity == "critical":
        risk = Risk(
            organization_id=organization_id,
            title=f"AI incident: {title}",
            description=(
                "Auto-created from a critical AI incident. Assess EU AI Act Article 73 "
                f"serious-incident reporting obligations for {ai_system.name}."
            ),
            category="ai_governance",
            likelihood="high",
            impact="high",
            owner_id=owner_id,
        )
        db.add(risk)
        await db.flush()
        incident.related_risk_id = risk.id

        response_task = Task(
            organization_id=organization_id,
            title=f"Investigate: {title}",
            description=description,
            module="compliance",
            priority="urgent",
            assignee_id=owner_id,
        )
        db.add(response_task)
        await db.flush()
        incident.related_task_id = response_task.id

        if owner_id is not None:
            db.add(
                Notification(
                    organization_id=organization_id,
                    user_id=owner_id,
                    title="Critical AI incident assigned to you",
                    body=f'"{title}" was just declared critical and needs immediate '
                    "investigation.",
                    link="/compliance",
                )
            )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.ai_incident.created",
        object_type="ai_incident",
        object_id=str(incident.id),
        after_state={
            "ai_system_id": str(ai_system.id),
            "severity": severity,
            "related_risk_id": str(incident.related_risk_id) if incident.related_risk_id else None,
        },
    )
    return incident


async def update_ai_incident_status(
    db: AsyncSession,
    *,
    incident: AIIncident,
    new_status: str,
    actor_user_id: uuid.UUID | None,
) -> AIIncident:
    before_status = incident.status
    incident.status = new_status
    await record_event(
        db,
        organization_id=incident.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.ai_incident.status_changed",
        object_type="ai_incident",
        object_id=str(incident.id),
        before_state={"status": before_status},
        after_state={"status": new_status},
    )
    return incident


async def record_vendor_assessment(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    vendor: Vendor,
    risk_conclusion: str,
    notes: str | None,
    assessed_by: uuid.UUID | None,
) -> VendorAssessment:
    assessment = VendorAssessment(
        organization_id=organization_id,
        vendor_id=vendor.id,
        risk_conclusion=risk_conclusion,
        notes=notes,
        assessed_by=assessed_by,
    )
    db.add(assessment)
    await db.flush()

    vendor.risk_tier = risk_conclusion

    if risk_conclusion in _HIGH_VENDOR_RISK_TIERS:
        risk = Risk(
            organization_id=organization_id,
            title=f"Vendor risk: {vendor.name}",
            description=notes
            or f"Auto-created from a {risk_conclusion}-risk assessment of vendor {vendor.name}.",
            category="vendor",
            likelihood="high" if risk_conclusion == "critical" else "medium",
            impact="high" if risk_conclusion == "critical" else "high",
            owner_id=vendor.owner_id,
        )
        db.add(risk)
        await db.flush()
        assessment.related_risk_id = risk.id

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=assessed_by,
        action="compliance.vendor.assessed",
        object_type="vendor",
        object_id=str(vendor.id),
        after_state={
            "risk_conclusion": risk_conclusion,
            "related_risk_id": str(assessment.related_risk_id)
            if assessment.related_risk_id
            else None,
        },
    )
    return assessment
