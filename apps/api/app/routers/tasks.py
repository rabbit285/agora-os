from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.audit.service import record_event
from app.core.models import File, Task, TaskComment, TaskEvidence
from app.core.schemas import (
    TaskActivityOut,
    TaskCommentCreate,
    TaskCommentOut,
    TaskCreate,
    TaskEvidenceCreate,
    TaskEvidenceOut,
    TaskOut,
    TaskUpdate,
)
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


async def _get_org_task(db: AsyncSession, task_id: uuid.UUID, organization_id: uuid.UUID) -> Task:
    task = await db.get(Task, task_id)
    if task is None or task.organization_id != organization_id:
        # Identical error for "not found" and "not yours" — no existence leak.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


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


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> Task:
    return await _get_org_task(db, task_id, context.organization_id)


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("core.tasks.manage")),
) -> Task:
    task = Task(
        organization_id=context.organization_id,
        created_by=context.user.id,
        **payload.model_dump(),
    )
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
    task = await _get_org_task(db, task_id, context.organization_id)

    if payload.status is not None:
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

    if payload.checklist is not None:
        before_checklist = task.checklist
        task.checklist = [item.model_dump() for item in payload.checklist]
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="core.task.checklist_updated",
            object_type="task",
            object_id=str(task.id),
            before_state={"checklist": before_checklist},
            after_state={"checklist": task.checklist},
        )

    await db.commit()
    await db.refresh(task)
    return task


@router.get("/{task_id}/comments", response_model=list[TaskCommentOut])
async def list_task_comments(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[TaskComment]:
    await _get_org_task(db, task_id, context.organization_id)
    result = await db.execute(
        select(TaskComment).where(TaskComment.task_id == task_id).order_by(TaskComment.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/{task_id}/comments", response_model=TaskCommentOut, status_code=status.HTTP_201_CREATED
)
async def create_task_comment(
    task_id: uuid.UUID,
    payload: TaskCommentCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("core.tasks.manage")),
) -> TaskComment:
    await _get_org_task(db, task_id, context.organization_id)
    comment = TaskComment(task_id=task_id, author_id=context.user.id, body=payload.body)
    db.add(comment)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="core.task.commented",
        object_type="task",
        object_id=str(task_id),
        after_state={"comment_id": str(comment.id)},
    )
    await db.commit()
    await db.refresh(comment)
    return comment


@router.get("/{task_id}/evidence", response_model=list[TaskEvidenceOut])
async def list_task_evidence(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[TaskEvidence]:
    await _get_org_task(db, task_id, context.organization_id)
    result = await db.execute(
        select(TaskEvidence)
        .where(TaskEvidence.task_id == task_id)
        .order_by(TaskEvidence.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/{task_id}/evidence", response_model=TaskEvidenceOut, status_code=status.HTTP_201_CREATED
)
async def attach_task_evidence(
    task_id: uuid.UUID,
    payload: TaskEvidenceCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("core.tasks.manage")),
) -> TaskEvidence:
    await _get_org_task(db, task_id, context.organization_id)
    file_record = await db.get(File, payload.file_id)
    if file_record is None or file_record.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    evidence = TaskEvidence(task_id=task_id, file_id=payload.file_id, created_by=context.user.id)
    db.add(evidence)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="core.task.evidence_attached",
        object_type="task",
        object_id=str(task_id),
        after_state={"file_id": str(payload.file_id)},
    )
    await db.commit()
    await db.refresh(evidence)
    return evidence


@router.get("/{task_id}/activity", response_model=list[TaskActivityOut])
async def list_task_activity(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[AuditEvent]:
    """spec §44's "Activity" field — reuses the real audit trail every task
    mutation already writes to (`record_event`, `object_type="task"`)
    rather than a second, parallel activity log."""
    await _get_org_task(db, task_id, context.organization_id)
    result = await db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.object_type == "task",
            AuditEvent.object_id == str(task_id),
            AuditEvent.organization_id == context.organization_id,
        )
        .order_by(AuditEvent.created_at)
    )
    return list(result.scalars().all())
