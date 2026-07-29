"""Sales domain services.

`send_outreach_message` is the cross-module hook this slice ships (spec
section 91: "Sales AI asks: Can we contact this prospect? Compliance
checks: jurisdiction, data source, marketing basis, opt-out, suppression,
organization policy"). The check implemented here is deliberately the
simplest real instance of that principle — a per-contact suppression flag
— rather than the full jurisdiction/consent/marketing-basis engine the
spec describes; see docs/KNOWN_LIMITATIONS.md for what's not covered yet.
No real email/LinkedIn provider is wired up (spec's progressive trust
model — connectors come later), so "sending" only ever transitions this
row's status; the compliance gate is real regardless.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.sales.models import Contact, OutreachMessage

SUPPRESSED_REASON = "Contact is marked do-not-contact (opted out / suppressed)."


async def send_outreach_message(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    message: OutreachMessage,
    contact: Contact,
    actor_user_id: uuid.UUID | None,
) -> OutreachMessage:
    if contact.do_not_contact:
        message.status = "blocked"
        message.blocked_reason = SUPPRESSED_REASON
        policy_decision = "denied"
    else:
        message.status = "sent"
        message.sent_at = datetime.now(UTC)
        policy_decision = "allowed"

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="sales.outreach.send_attempted",
        object_type="outreach_message",
        object_id=str(message.id),
        policy_decision=policy_decision,
        after_state={"status": message.status, "blocked_reason": message.blocked_reason},
    )
    return message
