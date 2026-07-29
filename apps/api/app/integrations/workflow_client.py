"""Starts the durable integration-sync workflow (spec §49's `sync()`,
mirroring `app.knowledge.workflow_client`'s ingestion pattern): the API only
ever kicks the workflow off and returns immediately, so a slow or
rate-limited provider call never blocks the HTTP request. The `SyncRun`
row already exists (created synchronously by `app.integrations.service`)
before this fires, so the frontend can poll `GET .../sync-runs` for the
`running` -> `succeeded`/`failed` transition without needing a workflow
handle.

Deliberately references the workflow by name and passes plain string
arguments rather than importing anything from `apps/worker` — the API and
worker are separate deployables that only agree on this name + task queue
contract (see apps/worker/worker/workflows.py).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

logger = logging.getLogger("agora.integrations")

WORKFLOW_NAME = "IntegrationSyncWorkflow"
TASK_QUEUE = "agora-default"

SyncStarter = Callable[[uuid.UUID, uuid.UUID], Awaitable[None]]


async def start_sync(connection_id: uuid.UUID, sync_run_id: uuid.UUID) -> None:
    from temporalio.client import Client

    from app.config import settings

    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    await client.start_workflow(
        WORKFLOW_NAME,
        args=[str(connection_id), str(sync_run_id)],
        id=f"integration-sync-{sync_run_id}",
        task_queue=TASK_QUEUE,
    )


async def get_sync_starter() -> SyncStarter:
    return start_sync
