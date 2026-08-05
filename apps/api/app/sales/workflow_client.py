"""Starts the durable bulk-enrichment workflow (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §16), mirroring
`app.integrations.workflow_client`'s pattern exactly: the API only ever
kicks the workflow off and returns immediately so a slow/rate-limited
provider call never blocks the HTTP request. The `SalesEnrichmentJob` row
already exists (created synchronously by
`app.sales.enrichment_job_service.create_enrichment_job`) before this
fires, so the frontend can poll `GET .../enrichment-jobs/{id}` for the
`running` -> `succeeded`/`partial`/`failed` transition without needing a
workflow handle.

Deliberately references the workflow by name and passes plain string
arguments rather than importing anything from `apps/worker` — the API and
worker are separate deployables that only agree on this name + task queue
contract (see apps/worker/worker/workflows.py).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

WORKFLOW_NAME = "SalesBulkEnrichmentWorkflow"
TASK_QUEUE = "agora-default"

EnrichmentStarter = Callable[[uuid.UUID], Awaitable[None]]


async def start_bulk_enrichment(job_id: uuid.UUID) -> None:
    from temporalio.client import Client

    from app.config import settings

    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    await client.start_workflow(
        WORKFLOW_NAME,
        args=[str(job_id)],
        id=f"sales-enrichment-{job_id}",
        task_queue=TASK_QUEUE,
    )


async def get_enrichment_starter() -> EnrichmentStarter:
    return start_bulk_enrichment
