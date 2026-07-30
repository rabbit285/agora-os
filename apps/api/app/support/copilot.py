"""AI-grounded ticket response (spec §32) — real retrieval-grounded
generation via the existing AI Copilot, not a canned template. Whether
the resulting message is a pending draft or gets auto-sent depends on the
org's `AIAgentConfig` and whether the answer was actually grounded — see
`app.support.models.AIAgentConfig`'s docstring for the honest "confidence"
proxy this uses.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot import ask_copilot
from app.support.models import AIAgentConfig, Ticket, TicketMessage


async def get_ai_agent_config(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> AIAgentConfig | None:
    result = await db.execute(
        select(AIAgentConfig).where(AIAgentConfig.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def draft_ticket_reply(
    db: AsyncSession, *, organization_id: uuid.UUID, ticket: Ticket, requested_by: uuid.UUID | None
) -> TicketMessage:
    prior_messages_result = await db.execute(
        select(TicketMessage)
        .where(TicketMessage.ticket_id == ticket.id)
        .order_by(TicketMessage.created_at.asc())
    )
    thread = "\n".join(f"{m.sender_type}: {m.body}" for m in prior_messages_result.scalars().all())
    question = (
        f'Draft a helpful support reply to this ticket. Subject: "{ticket.subject}". '
        f"Description: {ticket.description or '(none)'}.\n"
        f"Conversation so far:\n{thread or '(no messages yet)'}"
    )
    answer = await ask_copilot(
        db, organization_id=organization_id, requested_by=requested_by, question=question
    )

    config = await get_ai_agent_config(db, organization_id=organization_id)
    auto_send = bool(
        config and config.enabled and config.auto_send_grounded_replies and answer.grounded
    )

    message = TicketMessage(
        organization_id=organization_id,
        ticket_id=ticket.id,
        sender_type="ai",
        body=answer.text,
        status="sent" if auto_send else "draft",
    )
    db.add(message)
    await db.flush()
    return message
