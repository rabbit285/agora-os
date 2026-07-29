from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import Workflow, WorkflowRun, WorkflowStepRun
from app.automation.schemas import (
    SUPPORTED_STEP_TYPES,
    WorkflowCreate,
    WorkflowOut,
    WorkflowRunDetailOut,
    WorkflowRunOut,
    WorkflowRunTrigger,
    WorkflowStatusUpdate,
    WorkflowStepRunOut,
    WorkflowStepsUpdate,
)
from app.automation.service import advance_run, start_run
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


async def _get_org_workflow(
    db: AsyncSession, workflow_id: uuid.UUID, organization_id: uuid.UUID
) -> Workflow:
    workflow = await db.get(Workflow, workflow_id)
    if workflow is None or workflow.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


async def _get_org_run(
    db: AsyncSession, run_id: uuid.UUID, organization_id: uuid.UUID
) -> WorkflowRun:
    run = await db.get(WorkflowRun, run_id)
    if run is None or run.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get("/workflows", response_model=list[WorkflowOut])
async def list_workflows(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Workflow]:
    result = await db.execute(
        select(Workflow)
        .where(Workflow.organization_id == context.organization_id)
        .order_by(Workflow.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/workflows", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("automation.workflows.manage")),
) -> Workflow:
    workflow = Workflow(
        organization_id=context.organization_id,
        name=payload.name,
        description=payload.description,
        trigger_type=payload.trigger_type,
        steps=[step.model_dump() for step in payload.steps],
        owner_id=context.user.id,
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("/workflows/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> Workflow:
    return await _get_org_workflow(db, workflow_id, context.organization_id)


@router.patch("/workflows/{workflow_id}/steps", response_model=WorkflowOut)
async def update_workflow_steps(
    workflow_id: uuid.UUID,
    payload: WorkflowStepsUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("automation.workflows.manage")),
) -> Workflow:
    workflow = await _get_org_workflow(db, workflow_id, context.organization_id)
    if workflow.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Steps can only be edited while the workflow is in draft status "
            "(spec §41: never let edits silently change active behavior)",
        )
    workflow.steps = [step.model_dump() for step in payload.steps]
    workflow.version += 1
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.patch("/workflows/{workflow_id}/status", response_model=WorkflowOut)
async def update_workflow_status(
    workflow_id: uuid.UUID,
    payload: WorkflowStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("automation.workflows.manage")),
) -> Workflow:
    workflow = await _get_org_workflow(db, workflow_id, context.organization_id)
    workflow.status = payload.status
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("/runs", response_model=list[WorkflowRunOut])
async def list_runs(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[WorkflowRun]:
    result = await db.execute(
        select(WorkflowRun)
        .where(WorkflowRun.organization_id == context.organization_id)
        .order_by(WorkflowRun.started_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/workflows/{workflow_id}/run",
    response_model=WorkflowRunOut,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_run(
    workflow_id: uuid.UUID,
    payload: WorkflowRunTrigger,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("automation.runs.manage")),
) -> WorkflowRun:
    workflow = await _get_org_workflow(db, workflow_id, context.organization_id)
    if workflow.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only active workflows can be run",
        )
    unsupported = [
        step["step_type"]
        for step in workflow.steps
        if step["step_type"] not in SUPPORTED_STEP_TYPES
    ]
    if unsupported:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported step type(s): {unsupported}",
        )
    run = await start_run(
        db,
        organization_id=context.organization_id,
        workflow=workflow,
        trigger_payload=payload.trigger_payload,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/runs/{run_id}", response_model=WorkflowRunDetailOut)
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> WorkflowRunDetailOut:
    run = await _get_org_run(db, run_id, context.organization_id)
    step_runs_result = await db.execute(
        select(WorkflowStepRun)
        .where(WorkflowStepRun.run_id == run.id)
        .order_by(WorkflowStepRun.step_index)
    )
    return WorkflowRunDetailOut(
        **WorkflowRunOut.model_validate(run).model_dump(),
        step_runs=[WorkflowStepRunOut.model_validate(s) for s in step_runs_result.scalars().all()],
    )


@router.post("/runs/{run_id}/resume", response_model=WorkflowRunOut)
async def resume_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("automation.runs.manage")),
) -> WorkflowRun:
    run = await _get_org_run(db, run_id, context.organization_id)
    if run.status != "awaiting_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Run is not awaiting approval"
        )
    workflow = await _get_org_workflow(db, run.workflow_id, context.organization_id)
    run = await advance_run(db, run=run, workflow=workflow, actor_user_id=context.user.id)
    await db.commit()
    await db.refresh(run)
    return run
