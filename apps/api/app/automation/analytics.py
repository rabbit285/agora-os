"""Automation Analytics dashboard (spec §43) — live-computed aggregates
over this org's own Workflow/WorkflowRun rows, no cached rollup to go
stale.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import Workflow, WorkflowRun

TERMINAL_STATUSES = ("succeeded", "failed")


async def compute_workflow_analytics(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> dict[str, Any]:
    total_workflows = (
        await db.execute(
            select(func.count())
            .select_from(Workflow)
            .where(Workflow.organization_id == organization_id)
        )
    ).scalar_one()
    active_workflows = (
        await db.execute(
            select(func.count())
            .select_from(Workflow)
            .where(Workflow.organization_id == organization_id, Workflow.status == "active")
        )
    ).scalar_one()

    runs_result = await db.execute(
        select(WorkflowRun).where(WorkflowRun.organization_id == organization_id)
    )
    runs = list(runs_result.scalars().all())
    runs_by_status: dict[str, int] = {}
    for run in runs:
        runs_by_status[run.status] = runs_by_status.get(run.status, 0) + 1

    terminal_runs = [r for r in runs if r.status in TERMINAL_STATUSES]
    succeeded_runs = [r for r in runs if r.status == "succeeded"]
    success_rate_percent = (
        round(100 * len(succeeded_runs) / len(terminal_runs), 1) if terminal_runs else 0.0
    )

    return {
        "total_workflows": total_workflows,
        "active_workflows": active_workflows,
        "total_runs": len(runs),
        "runs_by_status": runs_by_status,
        "success_rate_percent": success_rate_percent,
        "awaiting_approval_count": runs_by_status.get("awaiting_approval", 0),
    }
