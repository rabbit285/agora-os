"""Security domain services.

`create_incident` is the cross-module hook this slice ships (spec section
19: "Integrate incidents with the GDPR breach process... this connection
between security and compliance is critical") — a critical-severity
incident automatically creates a linked Compliance Risk, reusing that
module's existing primitive rather than inventing a security-specific
breach-tracking mechanism.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import Risk
from app.secops.models import SecurityIncident


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

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="security.incident.created",
        object_type="security_incident",
        object_id=str(incident.id),
        after_state={"title": incident.title, "severity": incident.severity},
    )
    return incident
