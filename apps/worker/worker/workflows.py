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
