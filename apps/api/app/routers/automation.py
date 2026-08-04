from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.analytics import compute_workflow_analytics
from app.automation.models import (
    Workflow,
    WorkflowRun,
    WorkflowStepRun,
    WorkflowTemplate,
    WorkflowVersion,
)
from app.automation.schemas import (
    SUPPORTED_STEP_TYPES,
    WorkflowAnalyticsOut,
    WorkflowCreate,
    WorkflowOut,
    WorkflowRunDetailOut,
    WorkflowRunOut,
    WorkflowRunTrigger,
    WorkflowStatusUpdate,
    WorkflowStepRunOut,
    WorkflowStepsUpdate,
    WorkflowTemplateOut,
    WorkflowVersionOut,
)
from app.automation.service import publish_workflow_version, start_run
from app.automation.workflow_client import (
    RunSignaler,
    RunStarter,
    ScheduleDeleter,
    ScheduleSyncer,
    get_run_signaler,
    get_run_starter,
    get_schedule_deleter,
    get_schedule_syncer,
)
from app.core.pagination import Pagination, paginate, pagination_params
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
        schedule_cron=payload.schedule_cron,
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
    schedule_syncer: ScheduleSyncer = Depends(get_schedule_syncer),
    schedule_deleter: ScheduleDeleter = Depends(get_schedule_deleter),
) -> Workflow:
    workflow = await _get_org_workflow(db, workflow_id, context.organization_id)
    before_status = workflow.status
    workflow.status = payload.status
    if payload.status == "active" and before_status != "active":
        await publish_workflow_version(db, workflow=workflow, published_by=context.user.id)
    await db.commit()
    await db.refresh(workflow)

    if workflow.trigger_type == "schedule" and workflow.schedule_cron:
        if workflow.status == "active":
            await schedule_syncer(workflow.id, workflow.schedule_cron)
        elif before_status == "active":
            await schedule_deleter(workflow.id)

    return workflow


@router.get("/workflows/{workflow_id}/versions", response_model=list[WorkflowVersionOut])
async def list_workflow_versions(
    workflow_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[WorkflowVersion]:
    await _get_org_workflow(db, workflow_id, context.organization_id)
    result = await db.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version_number.desc())
    )
    return list(result.scalars().all())


@router.get("/templates", response_model=list[WorkflowTemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db)) -> list[WorkflowTemplate]:
    """spec §41's Workflow Templates gallery — global catalog data, no
    org scoping (see app.automation.models.WorkflowTemplate)."""
    result = await db.execute(select(WorkflowTemplate).order_by(WorkflowTemplate.name))
    return list(result.scalars().all())


@router.post(
    "/templates/{template_id}/use", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED
)
async def use_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("automation.workflows.manage")),
) -> Workflow:
    template = await db.get(WorkflowTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    workflow = Workflow(
        organization_id=context.organization_id,
        name=template.name,
        description=template.description,
        trigger_type=template.trigger_type,
        steps=template.steps,
        owner_id=context.user.id,
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("/analytics", response_model=WorkflowAnalyticsOut)
async def get_workflow_analytics(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> WorkflowAnalyticsOut:
    data = await compute_workflow_analytics(db, organization_id=context.organization_id)
    return WorkflowAnalyticsOut(**data)


@router.get("/runs", response_model=list[WorkflowRunOut])
async def list_runs(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[WorkflowRun]:
    stmt = (
        select(WorkflowRun)
        .where(WorkflowRun.organization_id == context.organization_id)
        .order_by(WorkflowRun.started_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


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
    run_starter: RunStarter = Depends(get_run_starter),
) -> WorkflowRun:
    """Creates the WorkflowRun row and kicks off its durable Temporal
    execution (spec §61) — this handler never runs a single step itself.
    See app.automation.service.start_run and
    app.automation.workflow_client.start_workflow_run."""
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
    await run_starter(run.id)
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
    run_signaler: RunSignaler = Depends(get_run_signaler),
) -> WorkflowRun:
    """A manual "nudge": signals the run's Temporal workflow to
    immediately re-check its paused `human_approval` step rather than
    waiting for the next scheduled poll. Does not mutate `WorkflowRun`/
    `WorkflowStepRun` state itself — the Temporal workflow (via
    run_workflow_step_batch_activity) is the sole writer of run state
    once a run starts, so this never races with it. Deciding the linked
    Approval (any module, via `/api/v1/approvals/{id}/decide`) already
    sends this same signal automatically — this endpoint exists for a
    manual "check now" affordance in the UI."""
    run = await _get_org_run(db, run_id, context.organization_id)
    if run.status != "awaiting_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Run is not awaiting approval"
        )
    await run_signaler(run.id)
    return run
