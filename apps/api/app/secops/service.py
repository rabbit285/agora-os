"""Security domain services.

`create_incident` ships two cross-module hooks, both gated on
`severity == "critical"` and both firing from the same event (spec
section 69 "Security Incident": "Creates incident -> ... -> Compliance
module assesses GDPR breach obligations -> Creates incident response
tasks -> Notifies responsible team -> ..."):

1. (Phase 4, ADR-0018) Auto-creates a linked Compliance `Risk` so the
   GDPR breach-notification obligation is tracked somewhere real.
2. (Phase 8, ADR-0023) Auto-creates a `core.Task` ("Investigate and
   contain: ...") and, if the incident has an `owner_id`, a
   `core.Notification` to that owner — reusing the Phase 1 Task and
   Notification primitives rather than inventing incident-specific
   response-tracking types.

Both extend the same hook rather than adding a second one, since spec
§69's chain is a single event with multiple shared-primitive
consequences, not two separate triggers.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import Risk
from app.core.models import Task
from app.core.notifications import notify
from app.secops.models import SecurityAlert, SecurityFinding, SecurityIncident


async def create_incident(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    title: str,
    description: str | None,
    severity: str,
    owner_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> SecurityIncident:
    incident = SecurityIncident(
        organization_id=organization_id,
        title=title,
        description=description,
        severity=severity,
        owner_id=owner_id,
    )
    db.add(incident)
    await db.flush()

    response_task_id: uuid.UUID | None = None
    if severity == "critical":
        risk = Risk(
            organization_id=organization_id,
            title=f"Security incident: {title}",
            description=(
                "Auto-created from a critical security incident. Assess GDPR breach "
                "notification obligations (spec section 19)."
            ),
            category="security",
            likelihood="high",
            impact="high",
            owner_id=owner_id,
        )
        db.add(risk)
        await db.flush()
        incident.related_risk_id = risk.id

        response_task = Task(
            organization_id=organization_id,
            title=f"Investigate and contain: {title}",
            description=description,
            module="security",
            priority="urgent",
            assignee_id=owner_id,
        )
        db.add(response_task)
        await db.flush()
        incident.related_task_id = response_task.id
        response_task_id = response_task.id

        if owner_id is not None:
            await notify(
                db,
                organization_id=organization_id,
                user_id=owner_id,
                title="Critical security incident assigned to you",
                body=f'"{title}" was just declared critical and needs immediate '
                "investigation and containment.",
                link="/security",
                channels=["email"],
            )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="security.incident.created",
        object_type="security_incident",
        object_id=str(incident.id),
        after_state={
            "title": incident.title,
            "severity": incident.severity,
            "response_task_id": str(response_task_id) if response_task_id else None,
        },
    )
    return incident


async def compute_security_score(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """The same simple, transparent deduction model `GET /security/overview`
    computes (spec §13) — extracted here so it has one real implementation
    used by both that dashboard and the Onboarding readiness score
    (spec §68), rather than two independently-drifting copies."""

    async def _count(stmt: Any) -> int:
        result = await db.execute(select(func.count()).select_from(stmt.subquery()))
        return int(result.scalar_one())

    critical_alerts = await _count(
        select(SecurityAlert.id).where(
            SecurityAlert.organization_id == organization_id,
            SecurityAlert.severity == "critical",
            SecurityAlert.status.notin_(["resolved", "false_positive"]),
        )
    )
    open_critical_findings = await _count(
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == organization_id,
            SecurityFinding.severity == "critical",
            SecurityFinding.status.notin_(["resolved", "false_positive", "risk_accepted"]),
        )
    )
    open_high_findings = await _count(
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == organization_id,
            SecurityFinding.severity == "high",
            SecurityFinding.status.notin_(["resolved", "false_positive", "risk_accepted"]),
        )
    )
    open_incidents = await _count(
        select(SecurityIncident.id).where(
            SecurityIncident.organization_id == organization_id,
            SecurityIncident.status != "closed",
        )
    )
    deductions = (
        critical_alerts * 10
        + open_critical_findings * 8
        + open_high_findings * 4
        + open_incidents * 6
    )
    return max(0, 100 - deductions)
