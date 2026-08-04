"""Internal trigger dispatch (spec §38) — the non-manual, non-webhook,
non-schedule trigger types that this build can genuinely fire from its
own domain events, without any external connector. `dispatch_event` is
called from a small number of real event-source points across other
modules (Sales, Support, Compliance, Security, Knowledge, identity) — see
each call site's own comment for exactly which domain event it
represents. `schedule` is wired separately via a real Temporal Schedule
(see app.automation.workflow_client.create_or_update_schedule) and
`webhook` via the pre-existing inbound webhook connector
(app.integrations.service.receive_webhook_event) — neither goes through
this dispatcher.

Of spec §38's 16 named trigger types, 4 have no real internal or
connector-based event source anywhere in this build and are honestly
never dispatched: `new_email` (no inbound email parsing),
`form_submission` (no public form-building feature), `database_event`
(spec's own text says "through connectors", which don't exist),
`new_regulatory_update` (no Regulatory Intelligence feed exists yet —
see docs/KNOWN_LIMITATIONS.md). They remain valid, selectable
`trigger_type` values (so a workflow can be authored and left ready for
when a real source exists) but this module's dispatch table simply has
no entry for them — calling `dispatch_event` with one of those values is
a documented no-op, not a silent lie.

Since 2026-08-04 (BIZ-05, spec §90), the same real event also reaches
`app.rules_engine.service.evaluate_rules` — a Business Rule configured
against one of these `trigger_type` values evaluates on the exact same
dispatch a matching Workflow would, rather than a second parallel
event-hook system.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import Workflow
from app.automation.service import start_run
from app.rules_engine.service import evaluate_rules


async def dispatch_event(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    trigger_type: str,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """Starts a run for every `active` Workflow in this org whose
    `trigger_type` matches, and evaluates every active Business Rule
    (spec §90) configured for the same `trigger_type` — one real event,
    two independent real consumers, neither aware of the other. Returns
    the started WorkflowRun ids (empty list if no workflow is listening,
    which is the common case and not an error)."""
    await evaluate_rules(
        db,
        organization_id=organization_id,
        trigger_type=trigger_type,
        payload=payload,
        actor_user_id=actor_user_id,
    )

    result = await db.execute(
        select(Workflow).where(
            Workflow.organization_id == organization_id,
            Workflow.status == "active",
            Workflow.trigger_type == trigger_type,
        )
    )
    workflows = list(result.scalars().all())
    run_ids: list[uuid.UUID] = []
    for workflow in workflows:
        run = await start_run(
            db,
            organization_id=organization_id,
            workflow=workflow,
            trigger_payload=payload,
            actor_user_id=actor_user_id,
        )
        run_ids.append(run.id)
    return run_ids
