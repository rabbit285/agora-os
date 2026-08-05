"""Activity implementations.

Unlike workflows, activities run outside Temporal's determinism sandbox,
so they can freely do I/O. Application imports are still done lazily
inside each function body (not at module top) so this module stays cheap
to import from main.py and so nothing here could ever accidentally be
mistaken for workflow-defining code.
"""

from __future__ import annotations

import logging
import uuid

from temporalio import activity

logger = logging.getLogger("agora.worker.activities")


@activity.defn(name="ping_activity")
async def ping_activity() -> str:
    return "pong"


@activity.defn(name="ingest_document_activity")
async def ingest_document_activity(document_id: str) -> str:
    import app.db.register_all_models  # noqa: F401 — see module docstring
    from app.core.models import File
    from app.core.storage import download_object
    from app.db.session import AsyncSessionLocal
    from app.knowledge.models import Document
    from app.knowledge.service import ingest_document

    doc_uuid = uuid.UUID(document_id)
    async with AsyncSessionLocal() as db:
        document = await db.get(Document, doc_uuid)
        if document is None:
            raise LookupError(f"Document {document_id} not found")
        file_record = await db.get(File, document.file_id)
        if file_record is None:
            raise LookupError(f"File {document.file_id} not found")

        file_bytes = download_object(file_record.storage_key)
        status = await ingest_document(db, document_id=doc_uuid, file_bytes=file_bytes)
        logger.info(
            "Document %s ingestion finished with status=%s", document_id, status
        )
        return status


@activity.defn(name="execute_integration_sync_activity")
async def execute_integration_sync_activity(
    connection_id: str, sync_run_id: str
) -> str:
    import app.db.register_all_models  # noqa: F401 — see module docstring
    from app.db.session import AsyncSessionLocal
    from app.integrations.models import IntegrationConnection, SyncRun
    from app.integrations.service import execute_sync_run

    conn_uuid = uuid.UUID(connection_id)
    run_uuid = uuid.UUID(sync_run_id)
    async with AsyncSessionLocal() as db:
        connection = await db.get(IntegrationConnection, conn_uuid)
        if connection is None:
            raise LookupError(f"IntegrationConnection {connection_id} not found")
        sync_run = await db.get(SyncRun, run_uuid)
        if sync_run is None:
            raise LookupError(f"SyncRun {sync_run_id} not found")

        sync_run = await execute_sync_run(db, connection=connection, sync_run=sync_run)
        await db.commit()
        logger.info(
            "Integration sync %s (connection %s) finished with status=%s",
            sync_run_id,
            connection_id,
            sync_run.status,
        )
        return sync_run.status


@activity.defn(name="execute_sales_enrichment_activity")
async def execute_sales_enrichment_activity(job_id: str) -> str:
    import app.db.register_all_models  # noqa: F401 — see module docstring
    from app.db.session import AsyncSessionLocal
    from app.sales.enrichment_job_service import execute_enrichment_job
    from app.sales.provider_models import SalesEnrichmentJob

    job_uuid = uuid.UUID(job_id)
    async with AsyncSessionLocal() as db:
        job = await db.get(SalesEnrichmentJob, job_uuid)
        if job is None:
            raise LookupError(f"SalesEnrichmentJob {job_id} not found")

        job = await execute_enrichment_job(db, job=job)
        await db.commit()
        logger.info(
            "Sales enrichment job %s finished with status=%s (succeeded=%d, failed=%d)",
            job_id,
            job.status,
            job.succeeded_count,
            job.failed_count,
        )
        return job.status


@activity.defn(name="run_workflow_step_batch_activity")
async def run_workflow_step_batch_activity(run_id: str) -> dict[str, object]:
    """Executes as many of a Business Process Automation `WorkflowRun`'s
    remaining steps as it can in one batch — stopping at completion,
    failure, an `awaiting_approval` pause, or a `delay` step (see
    `app.automation.service.advance_run`) — and reports back whether the
    calling `WorkflowRunWorkflow` needs to sleep for a real duration
    (`delay_seconds`) before invoking this activity again."""
    import app.db.register_all_models  # noqa: F401 — see module docstring
    from sqlalchemy import select

    from app.automation.models import Workflow, WorkflowRun, WorkflowStepRun
    from app.automation.service import advance_run
    from app.db.session import AsyncSessionLocal

    run_uuid = uuid.UUID(run_id)
    async with AsyncSessionLocal() as db:
        run = await db.get(WorkflowRun, run_uuid)
        if run is None:
            raise LookupError(f"WorkflowRun {run_id} not found")
        workflow_row = await db.get(Workflow, run.workflow_id)
        if workflow_row is None:
            raise LookupError(f"Workflow {run.workflow_id} not found")

        run = await advance_run(
            db, run=run, workflow=workflow_row, actor_user_id=run.triggered_by
        )
        await db.commit()

        delay_seconds: int | None = None
        if run.status == "running":
            last_step = (
                await db.execute(
                    select(WorkflowStepRun)
                    .where(WorkflowStepRun.run_id == run.id)
                    .order_by(WorkflowStepRun.step_index.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if (
                last_step is not None
                and last_step.step_type == "delay"
                and last_step.output
            ):
                delay_seconds = int(last_step.output.get("waited_seconds", 0))

        logger.info("Workflow run %s batch finished with status=%s", run_id, run.status)
        return {"run_status": run.status, "delay_seconds": delay_seconds}


@activity.defn(name="create_scheduled_workflow_run_activity")
async def create_scheduled_workflow_run_activity(workflow_id: str) -> str | None:
    """Fired by a real Temporal Schedule (spec §38). Returns `None` (the
    `ScheduledWorkflowRunWorkflow` interprets this as "skipped") if the
    workflow was paused/archived/deleted since the schedule was created —
    a schedule firing into a no-longer-active workflow is not an error."""
    import app.db.register_all_models  # noqa: F401 — see module docstring
    from app.automation.models import Workflow
    from app.automation.service import start_run
    from app.db.session import AsyncSessionLocal

    workflow_uuid = uuid.UUID(workflow_id)
    async with AsyncSessionLocal() as db:
        workflow_row = await db.get(Workflow, workflow_uuid)
        if workflow_row is None or workflow_row.status != "active":
            return None

        run = await start_run(
            db,
            organization_id=workflow_row.organization_id,
            workflow=workflow_row,
            trigger_payload={"trigger": "schedule"},
            actor_user_id=None,
        )
        await db.commit()
        logger.info(
            "Scheduled trigger created run %s for workflow %s", run.id, workflow_id
        )
        return str(run.id)
