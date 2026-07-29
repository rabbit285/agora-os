"""Temporal worker entrypoint.

Phase 1 registers a single health-check workflow/activity pair so the
worker service, Temporal connectivity, and deployment shape all exist and
are provable end to end (docs/N10 Final Verification). Domain workflows
(document processing, lead enrichment, DSAR, incident response, ...) are
added module by module starting Phase 2 — see docs/IMPLEMENTATION_PLAN.md.

This module is intentionally the *only* place that imports `app.config` —
see worker/workflows.py for why workflow-defining modules can't.
"""

from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from app.config import settings
from worker.workflows import HealthCheckWorkflow, ping_activity

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agora.worker")

TASK_QUEUE = "agora-default"


async def main() -> None:
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[HealthCheckWorkflow],
        activities=[ping_activity],
    )
    logger.info("Worker started on task queue '%s'", TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
