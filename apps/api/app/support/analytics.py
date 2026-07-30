"""Support Analytics / QA dashboard (spec §32) — live-computed aggregates
over this org's own Ticket/CSATResponse/TicketQAScore rows, no cached
rollup to go stale.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.support.models import CSATResponse, Ticket, TicketQAScore

OPEN_STATUSES = ("open", "pending")


async def compute_support_analytics(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> dict[str, Any]:
    tickets_result = await db.execute(
        select(Ticket).where(Ticket.organization_id == organization_id)
    )
    tickets = list(tickets_result.scalars().all())

    tickets_by_status: dict[str, int] = {}
    resolution_seconds: list[float] = []
    for ticket in tickets:
        tickets_by_status[ticket.status] = tickets_by_status.get(ticket.status, 0) + 1
        if ticket.resolved_at is not None:
            resolution_seconds.append((ticket.resolved_at - ticket.created_at).total_seconds())

    average_resolution_hours = (
        round(sum(resolution_seconds) / len(resolution_seconds) / 3600, 1)
        if resolution_seconds
        else 0.0
    )

    csat_result = await db.execute(
        select(CSATResponse.score).where(CSATResponse.organization_id == organization_id)
    )
    csat_scores = [row[0] for row in csat_result.all()]
    average_csat = round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else 0.0

    qa_result = await db.execute(
        select(TicketQAScore.score).where(TicketQAScore.organization_id == organization_id)
    )
    qa_scores = [row[0] for row in qa_result.all()]
    average_qa_score = round(sum(qa_scores) / len(qa_scores), 2) if qa_scores else 0.0

    open_tickets = (
        await db.execute(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.organization_id == organization_id, Ticket.status.in_(OPEN_STATUSES))
        )
    ).scalar_one()

    return {
        "total_tickets": len(tickets),
        "open_tickets": open_tickets,
        "tickets_by_status": tickets_by_status,
        "average_resolution_hours": average_resolution_hours,
        "average_csat": average_csat,
        "csat_response_count": len(csat_scores),
        "average_qa_score": average_qa_score,
        "qa_score_count": len(qa_scores),
    }
