"""Business Process Automation domain (spec sections 36-43 — Phase 7).

Deliberately not a general workflow interpreter: spec section 37 lists a
large step vocabulary (Trigger/Action/Condition/AI Step/Human
Approval/Delay/Loop/Data Transform/Webhook/Notification/Subworkflow) and
building all of it in one slice would mean a stub of everything rather
than a real vertical (spec section 80/82). `Workflow.steps` is a JSON
list of `{"step_type": ..., "config": {...}}` objects; only the step
types in `app.automation.service.SUPPORTED_STEP_TYPES` actually execute.
`Workflow.trigger_type` is "manual" only — every other trigger in spec
section 38 (new email, webhook, CRM stage change, ...) depends on
external connectors that don't exist yet (progressive trust model,
spec §B1).

`WorkflowRun` / `WorkflowStepRun` make execution inspectable after the
fact (spec section 41: "workflow logs"), not just pass/fail.

`WorkflowStepRun.approval_id` is the cross-module hook this slice ships
(spec section 42 — Workflow Approvals): a `human_approval` step creates a
real `core.Approval` and pauses the run at `awaiting_approval` until a
human decides it through the existing `/api/v1/approvals/{id}/decide`
endpoint — the first domain module to actually exercise that Phase 1
primitive. See `app.automation.service`.
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
    # manual only today — see module docstring
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual")
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
