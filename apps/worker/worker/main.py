"""Temporal worker entrypoint.

Phase 1 shipped a health-check workflow to prove worker/Temporal
connectivity end to end. Phase 2 adds the document ingestion workflow
(spec section 61). Future domain workflows (lead enrichment, DSAR,
incident response, ...) register here the same way — see
docs/IMPLEMENTATION_PLAN.md.

This module is intentionally the only place that imports `app.config` on
the worker side — see worker/workflows.py for why workflow-defining
modules can't.
"""

from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from app.config import settings
from app.core.storage import ensure_bucket
from worker.activities import ingest_document_activity, ping_activity
from worker.workflows import DocumentIngestionWorkflow, HealthCheckWorkflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agora.worker")

TASK_QUEUE = "agora-default"


async def main() -> None:
    ensure_bucket()  # local/dev convenience — see app.main's identical call
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[HealthCheckWorkflow, DocumentIngestionWorkflow],
        activities=[ping_activity, ingest_document_activity],
    )
    logger.info("Worker started on task queue '%s'", TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
