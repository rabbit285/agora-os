from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.models import Task
from app.core.schemas import TaskCreate, TaskOut, TaskUpdate
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Task]:
    result = await db.execute(
        select(Task)
        .where(Task.organization_id == context.organization_id)
        .order_by(Task.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("core.tasks.manage")),
) -> Task:
    task = Task(organization_id=context.organization_id, **payload.model_dump())
    db.add(task)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="core.task.created",
        object_type="task",
        object_id=str(task.id),
        after_state={"title": task.title, "status": task.status},
    )
    await db.commit()
    await db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("core.tasks.manage")),
) -> Task:
    task = await db.get(Task, task_id)
    if task is None or task.organization_id != context.organization_id:
        # Identical error for "not found" and "not yours" — no existence leak.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    before_status = task.status
    task.status = payload.status
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="core.task.status_changed",
        object_type="task",
        object_id=str(task.id),
        before_state={"status": before_status},
        after_state={"status": task.status},
    )
    await db.commit()
    await db.refresh(task)
    return task
