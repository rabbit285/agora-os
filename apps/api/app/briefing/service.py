"""AI Daily Briefing (spec §88). Each section is computed from this
org's own live rows; the "AI suggestion" line reuses
`app.recommendations` rather than inventing a second, independent
suggestion generator — it surfaces the single highest-risk active
Recommendation's own suggested action, or is honestly omitted if there
is none.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.briefing.models import Briefing
from app.compliance.models import DSAR
from app.recommendations.service import list_recommendations, refresh_recommendations
from app.sales.models import Opportunity
from app.secops.models import SecurityAlert
from app.support.models import Ticket


@dataclass
class BriefingItem:
    text: str
    link: str | None


@dataclass
class BriefingSection:
    key: str
    label: str
    headline: str
    items: list[BriefingItem]


async def _count(db: AsyncSession, stmt: Any) -> int:
    result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    return int(result.scalar_one())


async def _urgent_section(db: AsyncSession, organization_id: uuid.UUID) -> BriefingSection:
    alerts_result = await db.execute(
        select(SecurityAlert)
        .where(
            SecurityAlert.organization_id == organization_id,
            SecurityAlert.severity == "critical",
            SecurityAlert.status.notin_(["resolved", "false_positive"]),
        )
        .order_by(SecurityAlert.created_at.desc())
        .limit(5)
    )
    alerts = list(alerts_result.scalars().all())
    total = await _count(
        db,
        select(SecurityAlert.id).where(
            SecurityAlert.organization_id == organization_id,
            SecurityAlert.severity == "critical",
            SecurityAlert.status.notin_(["resolved", "false_positive"]),
        ),
    )
    headline = (
        f"{total} critical security alert{'s' if total != 1 else ''} need attention"
        if total
        else "No critical security alerts open"
    )
    return BriefingSection(
        key="urgent",
        label="Urgent",
        headline=headline,
        items=[BriefingItem(text=a.title, link="/security") for a in alerts],
    )


async def _revenue_section(db: AsyncSession, organization_id: uuid.UUID) -> BriefingSection:
    open_opps_result = await db.execute(
        select(Opportunity)
        .where(
            Opportunity.organization_id == organization_id,
            Opportunity.stage.notin_(["closed_won", "closed_lost"]),
        )
        .order_by(Opportunity.value.desc().nullslast())
    )
    open_opps = list(open_opps_result.scalars().all())
    total_value = sum(float(o.value or 0) for o in open_opps)
    headline = (
        f"{len(open_opps)} open opportunit{'y' if len(open_opps) == 1 else 'ies'} worth "
        f"~€{total_value:,.0f} need follow-up"
        if open_opps
        else "No open opportunities need follow-up"
    )
    return BriefingSection(
        key="revenue",
        label="Revenue",
        headline=headline,
        items=[BriefingItem(text=o.title, link="/sales") for o in open_opps[:5]],
    )


async def _customers_section(db: AsyncSession, organization_id: uuid.UUID) -> BriefingSection:
    now = datetime.now(UTC)
    this_week_start = now - timedelta(days=7)
    last_week_start = now - timedelta(days=14)
    this_week_count = await _count(
        db,
        select(Ticket.id).where(
            Ticket.organization_id == organization_id, Ticket.created_at >= this_week_start
        ),
    )
    last_week_count = await _count(
        db,
        select(Ticket.id).where(
            Ticket.organization_id == organization_id,
            Ticket.created_at >= last_week_start,
            Ticket.created_at < this_week_start,
        ),
    )
    if last_week_count == 0:
        headline = (
            f"{this_week_count} support ticket{'s' if this_week_count != 1 else ''} this week"
            if this_week_count
            else "No support activity this week"
        )
    else:
        change = round(100 * (this_week_count - last_week_count) / last_week_count, 1)
        direction = "increased" if change >= 0 else "decreased"
        headline = f"Support volume {direction} {abs(change)}% week over week"
    return BriefingSection(
        key="customers",
        label="Customers",
        headline=headline,
        items=[],
    )


async def _risk_section(db: AsyncSession, organization_id: uuid.UUID) -> BriefingSection:
    soon = datetime.now(UTC) + timedelta(days=3)
    dsars_result = await db.execute(
        select(DSAR)
        .where(
            DSAR.organization_id == organization_id,
            DSAR.status != "fulfilled",
            DSAR.due_at <= soon,
        )
        .order_by(DSAR.due_at.asc())
        .limit(5)
    )
    dsars = list(dsars_result.scalars().all())
    headline = (
        f"{len(dsars)} DSAR{'s' if len(dsars) != 1 else ''} approaching deadline"
        if dsars
        else "No DSARs approaching deadline"
    )
    return BriefingSection(
        key="risk",
        label="Risk",
        headline=headline,
        items=[
            BriefingItem(text=f"{d.requester_name} — due {d.due_at.date().isoformat()}", link="/compliance")
            for d in dsars
        ],
    )


async def _operations_section(db: AsyncSession, organization_id: uuid.UUID) -> BriefingSection:
    from app.automation.models import WorkflowRun

    recent_cutoff = datetime.now(UTC) - timedelta(hours=24)
    failed_result = await db.execute(
        select(WorkflowRun)
        .where(
            WorkflowRun.organization_id == organization_id,
            WorkflowRun.status == "failed",
            WorkflowRun.started_at >= recent_cutoff,
        )
        .order_by(WorkflowRun.started_at.desc())
        .limit(5)
    )
    failed = list(failed_result.scalars().all())
    headline = (
        f"{len(failed)} workflow run{'s' if len(failed) != 1 else ''} failed in the last 24 hours"
        if failed
        else "No workflow failures in the last 24 hours"
    )
    return BriefingSection(
        key="operations",
        label="Operations",
        headline=headline,
        items=[BriefingItem(text=f"Run {r.id}", link="/automation") for r in failed],
    )


_RISK_RANK = {"high": 3, "medium": 2, "low": 1}


async def _ai_suggestion(db: AsyncSession, organization_id: uuid.UUID) -> str | None:
    await refresh_recommendations(db, organization_id=organization_id)
    active = await list_recommendations(db, organization_id=organization_id)
    if not active:
        return None
    top = max(active, key=lambda r: _RISK_RANK.get(r.risk, 0))
    return f"{top.title}. {top.suggested_action}"


async def _generate_briefing(db: AsyncSession, organization_id: uuid.UUID, today: date) -> Briefing:
    sections = [
        await _urgent_section(db, organization_id),
        await _revenue_section(db, organization_id),
        await _customers_section(db, organization_id),
        await _risk_section(db, organization_id),
        await _operations_section(db, organization_id),
    ]
    ai_suggestion = await _ai_suggestion(db, organization_id)
    briefing = Briefing(
        organization_id=organization_id,
        briefing_date=today,
        sections=[
            {
                "key": s.key,
                "label": s.label,
                "headline": s.headline,
                "items": [{"text": i.text, "link": i.link} for i in s.items],
            }
            for s in sections
        ],
        ai_suggestion=ai_suggestion,
    )
    db.add(briefing)
    await db.commit()
    await db.refresh(briefing)
    return briefing


async def get_or_create_daily_briefing(db: AsyncSession, *, organization_id: uuid.UUID) -> Briefing:
    today = datetime.now(UTC).date()
    existing = (
        await db.execute(
            select(Briefing).where(
                Briefing.organization_id == organization_id, Briefing.briefing_date == today
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    return await _generate_briefing(db, organization_id, today)
