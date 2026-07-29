"""Customer Support domain services.

`create_ticket` is the cross-module hook this slice ships (spec section
35: "Ticket mentions security breach -> mark urgent -> notify Security ->
create incident..."). A ticket categorized `security` automatically
creates a `SecurityAlert` — Security's triage inbox — reusing that
module's existing primitive rather than inventing a support-specific
escalation mechanism. A human security analyst then decides whether to
promote the alert to a full `SecurityIncident`, the same workflow already
used for findings surfaced inside the Security module itself (ADR-0020).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.secops.models import SecurityAlert
from app.support.models import Ticket

_URGENT_SEVERITIES = {"high", "urgent"}


async def create_ticket(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    customer_id: uuid.UUID,
    subject: str,
    description: str | None,
    channel: str,
    category: str,
    priority: str,
    actor_user_id: uuid.UUID | None,
) -> Ticket:
    ticket = Ticket(
        organization_id=organization_id,
        customer_id=customer_id,
        subject=subject,
        description=description,
        channel=channel,
        category=category,
        priority=priority,
    )
    db.add(ticket)
    await db.flush()

    if category == "security":
        ticket.priority = "urgent"
        alert = SecurityAlert(
            organization_id=organization_id,
            title=f"Support ticket flagged as security concern: {subject}",
            description=description,
            severity="high" if priority in _URGENT_SEVERITIES else "medium",
            status="new",
        )
        db.add(alert)
        await db.flush()
        ticket.related_alert_id = alert.id

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="support.ticket.created",
        object_type="support_ticket",
        object_id=str(ticket.id),
        after_state={
            "subject": ticket.subject,
            "category": ticket.category,
            "priority": ticket.priority,
            "related_alert_id": str(ticket.related_alert_id) if ticket.related_alert_id else None,
        },
    )
    return ticket
