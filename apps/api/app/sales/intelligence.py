"""Sales Intelligence (spec §29) — live-computed pipeline aggregates, no
cached rollup to go stale. Every figure is a real query over this org's
own Opportunity/Account/SequenceEnrollment rows.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sales.models import Account, Opportunity, SequenceEnrollment


async def compute_sales_intelligence(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> dict[str, Any]:
    opportunities_result = await db.execute(
        select(Opportunity).where(Opportunity.organization_id == organization_id)
    )
    opportunities = list(opportunities_result.scalars().all())

    pipeline_value_by_stage: dict[str, float] = {}
    for opp in opportunities:
        pipeline_value_by_stage[opp.stage] = pipeline_value_by_stage.get(opp.stage, 0.0) + float(
            opp.value or 0
        )

    closed_won = [o for o in opportunities if o.stage == "closed_won"]
    closed_lost = [o for o in opportunities if o.stage == "closed_lost"]
    total_closed = len(closed_won) + len(closed_lost)
    win_rate_percent = round(100 * len(closed_won) / total_closed, 1) if total_closed else 0.0
    average_deal_size = (
        round(sum(float(o.value or 0) for o in closed_won) / len(closed_won), 2)
        if closed_won
        else 0.0
    )

    top_accounts_result = await db.execute(
        select(Account)
        .where(Account.organization_id == organization_id, Account.icp_score.isnot(None))
        .order_by(Account.icp_score.desc())
        .limit(5)
    )
    top_accounts = list(top_accounts_result.scalars().all())

    total_enrollments = (
        await db.execute(
            select(func.count())
            .select_from(SequenceEnrollment)
            .where(SequenceEnrollment.organization_id == organization_id)
        )
    ).scalar_one()
    completed_enrollments = (
        await db.execute(
            select(func.count())
            .select_from(SequenceEnrollment)
            .where(
                SequenceEnrollment.organization_id == organization_id,
                SequenceEnrollment.status == "completed",
            )
        )
    ).scalar_one()
    sequence_completion_rate_percent = (
        round(100 * completed_enrollments / total_enrollments, 1) if total_enrollments else 0.0
    )

    return {
        "pipeline_value_by_stage": pipeline_value_by_stage,
        "win_rate_percent": win_rate_percent,
        "average_deal_size": average_deal_size,
        "top_accounts_by_icp_score": top_accounts,
        "sequence_completion_rate_percent": sequence_completion_rate_percent,
    }
