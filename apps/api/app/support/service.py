"""Customer Support domain services.

`create_ticket` ships the Phase 6 cross-module hook (spec section 35:
"Ticket mentions security breach -> mark urgent -> notify Security ->
create incident..."). A ticket categorized `security` automatically
creates a `SecurityAlert` — Security's triage inbox — reusing that
module's existing primitive rather than inventing a support-specific
escalation mechanism. A human security analyst then decides whether to
promote the alert to a full `SecurityIncident`, the same workflow already
used for findings surfaced inside the Security module itself (ADR-0020).

`flag_upsell_signal` ships all 4 steps of the Phase 8 cross-module hook
(spec section 69 "Support Upsell Signal": customer repeatedly asks about
enterprise features -> create sales signal -> notify account manager ->
create opportunity suggestion -> generate account brief). Rather than
inventing new entities, this reuses primitives that already exist:

1. **Create sales signal** — a real `sales.Lead` (`source=
   "support_upsell_signal"`).
2. **Notify account manager** — a real `core.Notification` to the linked
   Sales Account's owner (ADR-0022).
3. **Create opportunity suggestion** — a real *suggestion*, not an
   auto-created `Opportunity` (a Lead becoming an Opportunity is a
   deliberate Sales-side decision this build already models via `Lead.
   status="converted"` — auto-creating one here would jump that funnel
   dishonestly). The suggestion itself reuses the AI Recommendation
   Engine (spec §87, BIZ-02) outright: `app.recommendations.service`'s
   `_support_upsell_signals` generator surfaces every open upsell-signal
   Lead as a real Recommendation with a real "Act on this" suggested
   action, the same pattern every other recommendation already uses,
   not a second suggestion mechanism.
4. **Generate account brief** — real retrieval-grounded text via the
   existing AI Copilot (`app.sales.meetings.generate_prep_notes`'s exact
   pattern), stored on `Lead.ai_account_brief`.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot import ask_copilot
from app.audit.service import record_event
from app.core.notifications import notify
from app.sales.models import Account, Lead
from app.secops.models import SecurityAlert
from app.support.models import Customer, Ticket

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


async def flag_upsell_signal(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ticket: Ticket,
    customer: Customer,
    actor_user_id: uuid.UUID,
) -> Ticket:
    lead = Lead(
        organization_id=organization_id,
        account_id=customer.sales_account_id,
        source="support_upsell_signal",
        status="new",
    )
    db.add(lead)
    await db.flush()
    ticket.upsell_lead_id = lead.id

    brief_question = (
        f'Prepare a brief account summary for "{customer.name}", who has shown a '
        f'possible expansion signal via support ticket "{ticket.subject}". Summarize '
        "anything in our knowledge base relevant to this account, including past "
        "interactions, product fit, and expansion potential."
    )
    brief_answer = await ask_copilot(
        db, organization_id=organization_id, requested_by=actor_user_id, question=brief_question
    )
    lead.ai_account_brief = brief_answer.text

    notified_user_id = actor_user_id
    if customer.sales_account_id is not None:
        account = await db.get(Account, customer.sales_account_id)
        if account is not None and account.owner_id is not None:
            notified_user_id = account.owner_id

    await notify(
        db,
        organization_id=organization_id,
        user_id=notified_user_id,
        title="Expansion signal detected",
        body=f'Customer "{customer.name}" may be a good fit for an upsell — '
        f'flagged from support ticket "{ticket.subject}".',
        link="/sales" if lead.account_id is None else f"/sales/accounts/{lead.account_id}",
    )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="support.ticket.upsell_signal_flagged",
        object_type="support_ticket",
        object_id=str(ticket.id),
        after_state={"lead_id": str(lead.id), "notified_user_id": str(notified_user_id)},
    )
    return ticket
