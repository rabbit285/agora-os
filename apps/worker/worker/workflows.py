"""Workflow and activity definitions only.

Temporal's Python SDK sandboxes the module that defines a workflow and
statically validates every import it pulls in transitively, rejecting
anything non-deterministic (file/env access, network I/O). Keep this
module's import graph limited to `temporalio` itself — application config,
database, and HTTP clients belong in activities' *implementations*
(imported lazily inside the activity function body) or in `main.py`, which
is never sandboxed because it doesn't define a workflow.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import activity, workflow


@activity.defn
async def ping_activity() -> str:
    return "pong"


@workflow.defn
class HealthCheckWorkflow:
    @workflow.run
    async def run(self) -> str:
        return await workflow.execute_activity(
            ping_activity, start_to_close_timeout=timedelta(seconds=10)
        )
