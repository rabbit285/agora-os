"""Starts the durable ingestion workflow (spec section 61: workflows are
not coupled directly to HTTP requests — the API only ever kicks one off
and returns immediately).

Deliberately references the workflow by name and passes a plain string
argument rather than importing anything from `apps/worker` — the API and
worker are separate deployables that only agree on this name + task queue
contract (see apps/worker/worker/workflows.py).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable

logger = logging.getLogger("agora.knowledge")

WORKFLOW_NAME = "DocumentIngestionWorkflow"
TASK_QUEUE = "agora-default"

IngestionStarter = Callable[[uuid.UUID], Awaitable[None]]


async def start_ingestion(document_id: uuid.UUID) -> None:
    from temporalio.client import Client

    from app.config import settings

    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    await client.start_workflow(
        WORKFLOW_NAME,
        str(document_id),
        id=f"ingest-document-{document_id}",
        task_queue=TASK_QUEUE,
    )


async def get_ingestion_starter() -> IngestionStarter:
    return start_ingestion
