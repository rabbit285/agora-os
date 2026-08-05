"""Workflow definitions only.

Temporal's Python SDK sandboxes the module that defines a workflow and
statically validates its entire import graph, rejecting anything
non-deterministic (file/env/network access) — this bit the health-check
workflow during Phase 1 when it lived in the same module as an import of
`app.config` (which reads a .env file). Keep this module's imports limited
to `temporalio` and the stdlib; application code (DB, storage, the AI
gateway) lives in activities.py, referenced here only by string name so
this module never has to import it.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class HealthCheckWorkflow:
    @workflow.run
    async def run(self) -> str:
        return await workflow.execute_activity(
            "ping_activity", start_to_close_timeout=timedelta(seconds=10)
        )


@workflow.defn
class DocumentIngestionWorkflow:
    @workflow.run
    async def run(self, document_id: str) -> str:
        return await workflow.execute_activity(
            "ingest_document_activity",
            document_id,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class IntegrationSyncWorkflow:
    """Runs a single integration connection sync (spec §49's `sync()`)
    durably rather than inline in the HTTP request — the same
    request/durable-execution split `DocumentIngestionWorkflow` uses.
    Takes `(connection_id, sync_run_id)`: the `SyncRun` row already exists
    (created synchronously by the API so `GET .../sync-runs` can show a
    `running` row immediately) and this workflow finalizes it."""

    @workflow.run
    async def run(self, connection_id: str, sync_run_id: str) -> str:
        # spec §G2 "retries, backoff, rate-limit handling": a real, bounded
        # retry policy rather than relying on Temporal's unlimited default
        # — a provider that's rate-limiting or briefly unavailable gets a
        # few backed-off attempts, not endless retries against the same
        # `SyncRun` row.
        return await workflow.execute_activity(
            "execute_integration_sync_activity",
            args=[connection_id, sync_run_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=1),
                maximum_attempts=3,
            ),
        )


@workflow.defn
class SalesBulkEnrichmentWorkflow:
    """Runs a Sales Lead Finder bulk-enrichment job durably (see
    docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §16) — the same
    request/durable-execution split as `IntegrationSyncWorkflow`. The
    `SalesEnrichmentJob` row already exists (created synchronously by the
    API) and this workflow finalizes it; per-record partial failures are
    handled *inside* the activity (see `execute_sales_enrichment_activity`)
    so one bad record never fails the whole batch."""

    @workflow.run
    async def run(self, job_id: str) -> str:
        return await workflow.execute_activity(
            "execute_sales_enrichment_activity",
            job_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=1),
                maximum_attempts=3,
            ),
        )


@workflow.defn
class SalesCsvImportWorkflow:
    """Runs a Sales Lead Finder CSV import durably for files over the
    synchronous row-count threshold (see
    docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §13, and
    `_SYNC_IMPORT_MAX_ROWS` in app.routers.sales_lead_finder) — the same
    request/durable-execution split as `SalesBulkEnrichmentWorkflow`. The
    `SalesImportJob` row already exists (created synchronously by the API)
    and this workflow finalizes it; per-row failures are handled *inside*
    the activity so one bad row never fails the whole file."""

    @workflow.run
    async def run(self, job_id: str) -> str:
        return await workflow.execute_activity(
            "execute_sales_csv_import_activity",
            job_id,
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=5),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=1),
                maximum_attempts=3,
            ),
        )


@workflow.defn
class WorkflowRunWorkflow:
    """Runs a Business Process Automation `WorkflowRun` durably (spec §36,
    §61) — the `WorkflowRun`/`WorkflowStepRun` rows already exist/are
    created by `run_workflow_step_batch_activity`, which is just
    `app.automation.service.advance_run` invoked from an activity instead
    of inline in the HTTP handler.

    A `human_approval` step pauses this workflow on the `wake` signal
    (sent by `app.automation.workflow_client.signal_workflow_run`, called
    automatically whenever the linked `core.Approval` is decided via
    `/api/v1/approvals/{id}/decide` — see app.routers.approvals) rather
    than a polling loop: genuine push-based resumption, not "check back
    later"."""

    def __init__(self) -> None:
        self._woken = False

    @workflow.signal
    def wake(self) -> None:
        self._woken = True

    @workflow.run
    async def run(self, run_id: str) -> str:
        while True:
            result = await workflow.execute_activity(
                "run_workflow_step_batch_activity",
                run_id,
                start_to_close_timeout=timedelta(minutes=10),
            )
            status = result["run_status"]
            if status == "awaiting_approval":
                self._woken = False
                await workflow.wait_condition(lambda: self._woken)
                continue
            delay_seconds = result.get("delay_seconds")
            if delay_seconds:
                await workflow.sleep(timedelta(seconds=delay_seconds))
                continue
            return status


@workflow.defn
class ScheduledWorkflowRunWorkflow:
    """The target of a real Temporal Schedule (spec §38 "Schedule"
    trigger — see app.automation.workflow_client.create_or_update_schedule).
    Takes a `Workflow.id` (not a `WorkflowRun.id`, which doesn't exist yet
    at schedule-fire time): creates a fresh run via an activity, then runs
    it to completion as a real child workflow, reusing
    `WorkflowRunWorkflow` rather than duplicating its step-execution
    loop."""

    @workflow.run
    async def run(self, workflow_id: str) -> str:
        run_id = await workflow.execute_activity(
            "create_scheduled_workflow_run_activity",
            workflow_id,
            start_to_close_timeout=timedelta(minutes=1),
        )
        if run_id is None:
            return "skipped"
        return await workflow.execute_child_workflow(
            WorkflowRunWorkflow.run, run_id, id=f"automation-run-{run_id}"
        )
