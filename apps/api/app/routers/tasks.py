from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.labels import describe
from app.audit.models import AuditEvent
from app.audit.service import record_event
from app.core.models import File, Membership, Task, TaskComment, TaskEvidence
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
from app.identity.models import User

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

    if payload.assignee_id is not None and payload.assignee_id != task.assignee_id:
        # Membership, not User.organization_id — a user belongs to an
        # organization through a membership row, and checking anything
        # else would let a task be assigned across tenants.
        assignee = (
            await db.execute(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(
                    User.id == payload.assignee_id,
                    Membership.organization_id == context.organization_id,
                    Membership.status == "active",
                )
            )
        ).scalar_one_or_none()
        if assignee is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        before_assignee = task.assignee_id
        task.assignee_id = payload.assignee_id
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="core.task.assigned",
            object_type="task",
            object_id=str(task.id),
            before_state={"assignee_id": str(before_assignee) if before_assignee else None},
            after_state={
                "assignee_id": str(assignee.id),
                "assignee_name": assignee.full_name or assignee.email,
            },
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
) -> list[TaskActivityOut]:
    """spec §44's "Activity" field — reuses the real audit trail every task
    mutation already writes to (`record_event`, `object_type="task"`)
    rather than a second, parallel activity log.

    A remediation task's history is not only its own. The interesting
    events — the plan being generated, a document arriving that might
    close it, the control being reassessed, the gap closing — are
    recorded against the compliance gap, because that is the object
    they happened to. Reading only `object_type="task"` is why these
    tasks showed an empty activity list while the work was in fact
    being logged the whole time.

    Events with no reader-facing phrasing are dropped rather than shown
    raw: this feed is read by someone who does not work in compliance
    daily, and an internal action name is not a sentence.
    """
    task = await _get_org_task(db, task_id, context.organization_id)

    subjects = [("task", str(task_id))]
    if task.entity_type and task.entity_id:
        subjects.append((task.entity_type, task.entity_id))

    result = await db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == context.organization_id,
            tuple_(AuditEvent.object_type, AuditEvent.object_id).in_(subjects),
        )
        .order_by(AuditEvent.created_at)
    )

    activity: list[TaskActivityOut] = []
    for event in result.scalars().all():
        label = describe(event.action, event.after_state)
        if label is None:
            continue
        activity.append(
            TaskActivityOut(
                action=event.action,
                label=label,
                actor_user_id=event.actor_user_id,
                before_state=event.before_state,
                after_state=event.after_state,
                created_at=event.created_at,
            )
        )
    return activity
