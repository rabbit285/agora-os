"""Starts and signals the durable workflow-run Temporal workflow (spec
§61: never couple workflow execution to the HTTP request — the same
request/durable-execution split `app.integrations.workflow_client` and
`app.knowledge.workflow_client` already use).

Deliberately references the workflow by name and passes plain string
arguments rather than importing anything from `apps/worker` — the API and
worker are separate deployables that only agree on this name + task
queue contract (see apps/worker/worker/workflows.py).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

logger = logging.getLogger("agora.automation")

WORKFLOW_NAME = "WorkflowRunWorkflow"
TASK_QUEUE = "agora-default"

RunStarter = Callable[[uuid.UUID], Awaitable[None]]
RunSignaler = Callable[[uuid.UUID], Awaitable[None]]


def _run_workflow_id(run_id: uuid.UUID) -> str:
    return f"automation-run-{run_id}"


async def start_workflow_run(run_id: uuid.UUID) -> None:
    from temporalio.client import Client

    from app.config import settings

    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    await client.start_workflow(
        WORKFLOW_NAME,
        args=[str(run_id)],
        id=_run_workflow_id(run_id),
        task_queue=TASK_QUEUE,
    )


async def signal_workflow_run(run_id: uuid.UUID) -> None:
    """Wakes a paused (`awaiting_approval`) run's Temporal workflow
    immediately, rather than waiting for it to poll. Safe to call even if
    the run already progressed past the approval, or if no such workflow
    exists (e.g. it already completed and Temporal has retired the
    handle) — failures here are logged, never raised, since this is
    always a best-effort nudge, not something the caller's own request
    should fail on."""
    from temporalio.client import Client

    from app.config import settings

    try:
        client = await Client.connect(
            settings.temporal_address, namespace=settings.temporal_namespace
        )
        handle = client.get_workflow_handle(_run_workflow_id(run_id))
        await handle.signal("wake")
    except Exception:  # noqa: BLE001 - best-effort nudge, never fails the caller
        logger.info("Could not signal workflow run %s (may have already completed)", run_id)


async def get_run_starter() -> RunStarter:
    return start_workflow_run


async def get_run_signaler() -> RunSignaler:
    return signal_workflow_run


SCHEDULED_WORKFLOW_NAME = "ScheduledWorkflowRunWorkflow"

ScheduleSyncer = Callable[[uuid.UUID, str], Awaitable[None]]
ScheduleDeleter = Callable[[uuid.UUID], Awaitable[None]]


def _schedule_id(workflow_id: uuid.UUID) -> str:
    return f"automation-schedule-{workflow_id}"


async def create_or_update_schedule(workflow_id: uuid.UUID, cron: str) -> None:
    """spec §38 "Schedule" trigger — a real recurring Temporal Schedule,
    not a fake cron string stored and never acted on. Deletes any
    existing schedule for this workflow first so re-activating with a
    new cron expression doesn't leave a stale duplicate running."""
    from temporalio.client import (
        Client,
        Schedule,
        ScheduleActionStartWorkflow,
        ScheduleSpec,
    )

    from app.config import settings

    await delete_schedule(workflow_id)
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    await client.create_schedule(
        _schedule_id(workflow_id),
        Schedule(
            action=ScheduleActionStartWorkflow(
                SCHEDULED_WORKFLOW_NAME,
                str(workflow_id),
                id=f"automation-scheduled-run-{workflow_id}",
                task_queue=TASK_QUEUE,
            ),
            spec=ScheduleSpec(cron_expressions=[cron]),
        ),
    )


async def delete_schedule(workflow_id: uuid.UUID) -> None:
    """Best-effort — a workflow being paused/archived that never had a
    schedule (e.g. trigger_type was never "schedule") is not an error."""
    from temporalio.client import Client

    from app.config import settings

    try:
        client = await Client.connect(
            settings.temporal_address, namespace=settings.temporal_namespace
        )
        handle = client.get_schedule_handle(_schedule_id(workflow_id))
        await handle.delete()
    except Exception:  # noqa: BLE001 - no existing schedule is the common case
        logger.debug("No existing schedule to delete for workflow %s", workflow_id)


async def get_schedule_syncer() -> ScheduleSyncer:
    return create_or_update_schedule


async def get_schedule_deleter() -> ScheduleDeleter:
    return delete_schedule
