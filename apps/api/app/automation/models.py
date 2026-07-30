"""Business Process Automation domain (spec sections 36-43 — Phase 7).

All 24 spec §39 action types and all 16 spec §38 trigger types are
supported (accepted in the vocabulary, real execution/dispatch for every
one that doesn't depend on an external connector this build doesn't have
— see `app.automation.service.STEP_HANDLERS` and `app.automation.triggers`
for the exact list and which triggers are honestly disclosed as
not-yet-wired). `Workflow.steps` is a JSON list of
`{"step_type": ..., "config": {...}}` objects.

Execution is Temporal-durable (spec §61: "do not couple workflows
directly to HTTP requests"), the same request/durable-execution split
Knowledge and Integrations already use: `app.automation.service.start_run`
only ever creates the `WorkflowRun` row and returns;
`app.automation.workflow_client.start_workflow_run` kicks off
`WorkflowRunWorkflow` (apps/worker/worker/workflows.py), which calls
`run_workflow_step_batch_activity` — the same `advance_run` function this
build always had, now invoked from an activity instead of inline in the
HTTP handler. A `human_approval` step pauses the *Temporal workflow* on a
signal (`wake`), not a polling loop: deciding the linked `core.Approval`
(via the existing `/api/v1/approvals/{id}/decide` endpoint, any module)
sends that signal automatically — see app.automation.workflow_client and
app.routers.approvals. `POST /runs/{id}/resume` is now a manual "nudge"
that re-sends the same signal rather than mutating run state directly:
the Temporal workflow is the sole writer of `WorkflowRun`/`WorkflowStepRun`
state once a run starts, avoiding a dual-writer race between an HTTP
handler and the durable workflow.

`WorkflowVersion` adds spec §41's "never allow edits to silently change
active workflow behavior... use versioning" — publishing snapshots
`Workflow.steps` immutably. `WorkflowTemplate` adds spec §41's "Workflow
Templates" gallery as global catalog data, the same pattern Compliance's
Frameworks/Requirements already use.

`WorkflowStepRun.approval_id` is the cross-module hook this slice ships
(spec section 42 — Workflow Approvals): a `human_approval` step creates a
real `core.Approval` and pauses the run at `awaiting_approval` until a
human decides it — the first domain module to actually exercise that
Phase 1 primitive. See `app.automation.service`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class Workflow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "automation_workflows"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(30), default="manual")
    # Only used when trigger_type == "schedule" — a standard 5-field cron
    # expression driving a real Temporal Schedule (see
    # app.automation.workflow_client.create_or_update_schedule).
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # draft | testing | active | paused | archived (spec section 41)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # ordered list of {"step_type": str, "config": dict}
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(default=1)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class WorkflowRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "automation_workflow_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_workflows.id"), nullable=False, index=True
    )
    # running | succeeded | failed | awaiting_approval
    status: Mapped[str] = mapped_column(String(20), default="running")
    trigger_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowStepRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "automation_workflow_step_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_workflow_runs.id"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(nullable=False)
    step_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # succeeded | failed | awaiting_approval
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Cross-module hook (spec section 42): set for human_approval steps —
    # see app.automation.service.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approvals.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable publish history (spec §41: "Never allow edits to
    silently change active workflow behavior... Use versioning."). A row
    is written every time a workflow's `steps` change while active/testing
    (see app.automation.service.publish_workflow_version) — the currently
    -editable `Workflow.steps` is a working draft; this table is the
    append-only historical record of what was actually live at each
    `version_number`."""

    __tablename__ = "automation_workflow_versions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_workflows.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowTemplate(UUIDPrimaryKeyMixin, Base):
    """spec §41's "Workflow Templates" gallery — global catalog data
    (organization_id is absent, same pattern as catalog Frameworks/
    Requirements in Compliance), not tenant-scoped. "Using" a template
    (see app.routers.automation) clones its `steps` into a brand new
    tenant-scoped Workflow — the template itself is never executed
    directly."""

    __tablename__ = "automation_workflow_templates"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="general")
    trigger_type: Mapped[str] = mapped_column(String(30), default="manual")
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
