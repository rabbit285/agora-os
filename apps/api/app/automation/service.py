"""Business Process Automation domain services.

`advance_run` is the executor: it runs a `Workflow`'s steps in order,
starting after whatever this `WorkflowRun` has already completed. Only
three step types actually execute (`SUPPORTED_STEP_TYPES` — see
`app.automation.models` for why the vocabulary is deliberately small).

`human_approval` is the cross-module hook (spec section 42): it creates a
real `core.Approval` and returns immediately, leaving the run at
`awaiting_approval`. Nothing pushes a decision back into the run — the
caller (the `/runs/{id}/resume` route) re-invokes `advance_run`, which
checks whether the linked Approval has since been decided through the
ordinary `/api/v1/approvals/{id}/decide` endpoint and either continues,
fails the run (rejected), or is a no-op (still pending).

`export_data` is the Compliance-as-Governance-Layer cross-module hook
(spec §91: "Automation asks: Can workflow export personal data?") — it
calls `app.compliance.governance.check_data_export_permission`
synchronously before "exporting" (this build has no real external export
destination yet, so the step's effect is the permission check itself);
a denial fails the run with the governance reason, exactly like a
rejected `human_approval` step.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.automation.models import Workflow, WorkflowRun, WorkflowStepRun
from app.compliance.governance import check_data_export_permission
from app.core.models import Approval, Notification, Task
from app.db.base import utcnow

STEP_CREATE_TASK = "create_task"
STEP_SEND_NOTIFICATION = "send_notification"
STEP_HUMAN_APPROVAL = "human_approval"
STEP_EXPORT_DATA = "export_data"
SUPPORTED_STEP_TYPES = {
    STEP_CREATE_TASK,
    STEP_SEND_NOTIFICATION,
    STEP_HUMAN_APPROVAL,
    STEP_EXPORT_DATA,
}


async def start_run(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    workflow: Workflow,
    trigger_payload: dict[str, Any] | None,
    actor_user_id: uuid.UUID,
) -> WorkflowRun:
    run = WorkflowRun(
        organization_id=organization_id,
        workflow_id=workflow.id,
        status="running",
        trigger_payload=trigger_payload,
        triggered_by=actor_user_id,
        started_at=utcnow(),
    )
    db.add(run)
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="automation.run.started",
        object_type="automation_workflow_run",
        object_id=str(run.id),
        after_state={"workflow_id": str(workflow.id)},
    )

    await advance_run(db, run=run, workflow=workflow, actor_user_id=actor_user_id)
    return run


async def advance_run(
    db: AsyncSession,
    *,
    run: WorkflowRun,
    workflow: Workflow,
    actor_user_id: uuid.UUID | None,
) -> WorkflowRun:
    if run.status not in ("running", "awaiting_approval"):
        return run

    existing = (
        (
            await db.execute(
                select(WorkflowStepRun)
                .where(WorkflowStepRun.run_id == run.id)
                .order_by(WorkflowStepRun.step_index)
            )
        )
        .scalars()
        .all()
    )
    step_runs = list(existing)
    next_index = len(step_runs)

    if step_runs and step_runs[-1].status == "awaiting_approval":
        pending_step = step_runs[-1]
        approval = await db.get(Approval, pending_step.approval_id)
        assert approval is not None  # FK guarantees existence
        if approval.status == "pending":
            return run
        if approval.status == "rejected":
            pending_step.status = "failed"
            run.status = "failed"
            run.completed_at = utcnow()
            await record_event(
                db,
                organization_id=run.organization_id,
                actor_user_id=actor_user_id,
                action="automation.run.failed",
                object_type="automation_workflow_run",
                object_id=str(run.id),
                after_state={"reason": "human_approval step rejected"},
            )
            return run
        pending_step.status = "succeeded"
        run.status = "running"

    for index in range(next_index, len(workflow.steps)):
        step = workflow.steps[index]
        step_type = step["step_type"]
        config = step.get("config") or {}

        if step_type == STEP_CREATE_TASK:
            task = Task(
                organization_id=run.organization_id,
                title=config.get("title", "Automation task"),
                description=config.get("description"),
                module="automation",
                priority=config.get("priority", "normal"),
            )
            db.add(task)
            await db.flush()
            db.add(
                WorkflowStepRun(
                    organization_id=run.organization_id,
                    run_id=run.id,
                    step_index=index,
                    step_type=step_type,
                    status="succeeded",
                    output={"task_id": str(task.id)},
                )
            )
        elif step_type == STEP_SEND_NOTIFICATION:
            notification = Notification(
                organization_id=run.organization_id,
                user_id=run.triggered_by,
                title=config.get("title", "Workflow notification"),
                body=config.get("body"),
            )
            db.add(notification)
            await db.flush()
            db.add(
                WorkflowStepRun(
                    organization_id=run.organization_id,
                    run_id=run.id,
                    step_index=index,
                    step_type=step_type,
                    status="succeeded",
                    output={"notification_id": str(notification.id)},
                )
            )
        elif step_type == STEP_HUMAN_APPROVAL:
            approval = Approval(
                organization_id=run.organization_id,
                action_type=config.get("action_type", f"Workflow approval: {workflow.name}"),
                risk_class=config.get("risk_class", "moderate"),
                requested_by=run.triggered_by or actor_user_id,
            )
            db.add(approval)
            await db.flush()
            db.add(
                WorkflowStepRun(
                    organization_id=run.organization_id,
                    run_id=run.id,
                    step_index=index,
                    step_type=step_type,
                    status="awaiting_approval",
                    approval_id=approval.id,
                )
            )
            run.status = "awaiting_approval"
            await record_event(
                db,
                organization_id=run.organization_id,
                actor_user_id=actor_user_id,
                action="automation.run.awaiting_approval",
                object_type="automation_workflow_run",
                object_id=str(run.id),
                after_state={"approval_id": str(approval.id)},
            )
            return run
        elif step_type == STEP_EXPORT_DATA:
            decision = await check_data_export_permission(
                db,
                organization_id=run.organization_id,
                destination_country=config.get("destination_country", ""),
                data_classification=config.get("data_classification", "internal"),
            )
            db.add(
                WorkflowStepRun(
                    organization_id=run.organization_id,
                    run_id=run.id,
                    step_index=index,
                    step_type=step_type,
                    status="succeeded" if decision.allowed else "failed",
                    output={"allowed": decision.allowed, "reason": decision.reason},
                )
            )
            if not decision.allowed:
                run.status = "failed"
                run.completed_at = utcnow()
                await record_event(
                    db,
                    organization_id=run.organization_id,
                    actor_user_id=actor_user_id,
                    action="automation.run.failed",
                    object_type="automation_workflow_run",
                    object_id=str(run.id),
                    policy_decision="denied",
                    after_state={"reason": decision.reason},
                )
                return run
        else:
            raise ValueError(f"Unsupported step type: {step_type}")

    run.status = "succeeded"
    run.completed_at = utcnow()
    await record_event(
        db,
        organization_id=run.organization_id,
        actor_user_id=actor_user_id,
        action="automation.run.succeeded",
        object_type="automation_workflow_run",
        object_id=str(run.id),
        after_state={"status": run.status},
    )
    return run
