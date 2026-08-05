"""CSV import job orchestration (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §13, §16). Mirrors
`enrichment_job_service`'s create/execute/run three-way split exactly:
`create_import_job` writes the `running` row synchronously so the frontend
sees it immediately, `execute_import_job` does the real download/parse/
dedupe-aware save and is directly callable in tests without a live Temporal
worker, and `run_import_job` composes both for the small-file synchronous
path (see `_SYNC_IMPORT_MAX_ROWS` in app.routers.sales_lead_finder)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.models import File
from app.core.storage import download_object
from app.sales import csv_import
from app.sales.provider_models import SalesImportJob


async def create_import_job(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    record_type: str,
    file_id: uuid.UUID,
    column_mapping: dict[str, str | None],
    total_rows: int,
    ip_address: str | None,
    user_agent: str | None,
) -> SalesImportJob:
    job = SalesImportJob(
        organization_id=organization_id,
        record_type=record_type,
        status="running",
        file_id=file_id,
        column_mapping=column_mapping,
        total_rows=total_rows,
        requested_by_user_id=actor_user_id,
    )
    db.add(job)
    await db.flush()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="sales.lead_finder.import.started",
        object_type="sales_import_job",
        object_id=str(job.id),
        after_state={"record_type": record_type, "total_rows": total_rows},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return job


async def execute_import_job(db: AsyncSession, *, job: SalesImportJob) -> SalesImportJob:
    """Idempotency guard mirrors `execute_enrichment_job`: a Temporal
    activity replay after a crash calls this again with the same job row —
    if it's already finalized, return unchanged rather than re-importing
    (and re-counting) the same rows."""
    if job.status != "running":
        return job

    file_record = await db.get(File, job.file_id) if job.file_id else None
    if file_record is None:
        job.status = "failed"
        job.completed_at = datetime.now(UTC)
        job.error_rows = [{"row_number": 0, "error": "Source file no longer exists"}]
        await record_event(
            db,
            organization_id=job.organization_id,
            actor_user_id=job.requested_by_user_id,
            action="sales.lead_finder.import.failed",
            object_type="sales_import_job",
            object_id=str(job.id),
            after_state={"status": job.status},
            policy_decision="error",
        )
        return job

    file_bytes = download_object(file_record.storage_key)
    rows = csv_import.read_all_rows(file_bytes)
    result = await csv_import.import_rows(
        db,
        organization_id=job.organization_id,
        actor_user_id=job.requested_by_user_id,
        record_type=job.record_type,
        rows=rows,
        column_mapping=job.column_mapping,
        ip_address=None,
        user_agent=None,
    )
    await db.flush()

    job.total_rows = result.total_rows
    job.imported_rows = result.imported_rows
    job.skipped_rows = result.skipped_rows
    job.error_rows = result.error_rows
    job.completed_at = datetime.now(UTC)
    job.status = "succeeded" if result.skipped_rows == 0 else (
        "partial" if result.imported_rows > 0 else "failed"
    )

    await record_event(
        db,
        organization_id=job.organization_id,
        actor_user_id=job.requested_by_user_id,
        action=(
            "sales.lead_finder.import.failed"
            if job.status == "failed"
            else "sales.lead_finder.import.completed"
        ),
        object_type="sales_import_job",
        object_id=str(job.id),
        after_state={
            "status": job.status,
            "imported": result.imported_rows,
            "skipped": result.skipped_rows,
        },
        policy_decision="allowed" if job.status != "failed" else "error",
    )
    return job


async def run_import_job(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    record_type: str,
    file_id: uuid.UUID,
    column_mapping: dict[str, str | None],
    total_rows: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SalesImportJob:
    """Convenience wrapper for the small-file synchronous path and for
    tests — the large-file (Temporal) path uses `create_import_job` +
    `SalesCsvImportWorkflow` instead (see `app.sales.workflow_client`)."""
    job = await create_import_job(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        record_type=record_type,
        file_id=file_id,
        column_mapping=column_mapping,
        total_rows=total_rows,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return await execute_import_job(db, job=job)
