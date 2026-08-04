from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Notification, NotificationPreference
from app.core.pagination import Pagination, paginate, pagination_params
from app.core.schemas import (
    NotificationOut,
    NotificationPreferenceOut,
    NotificationPreferenceUpdate,
)
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(
            Notification.organization_id == context.organization_id,
            Notification.user_id == context.user.id,
        )
        .order_by(Notification.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> Notification:
    notification = await db.get(Notification, notification_id)
    if (
        notification is None
        or notification.organization_id != context.organization_id
        or notification.user_id != context.user.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.read_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(notification)
    return notification


@router.get("/preferences", response_model=list[NotificationPreferenceOut])
async def list_notification_preferences(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[NotificationPreference]:
    """Self-scoped — any active member manages their own channel
    preferences, no special permission required (spec §66 "User
    preferences"), the same "manage your own account" scope
    `/auth/mfa/*` already uses."""
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == context.user.id)
    )
    return list(result.scalars().all())


@router.put("/preferences", response_model=NotificationPreferenceOut)
async def set_notification_preference(
    payload: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> NotificationPreference:
    existing = (
        await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == context.user.id,
                NotificationPreference.channel == payload.channel,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = NotificationPreference(
            organization_id=context.organization_id,
            user_id=context.user.id,
            channel=payload.channel,
            enabled=payload.enabled,
        )
        db.add(existing)
    else:
        existing.enabled = payload.enabled
    await db.commit()
    await db.refresh(existing)
    return existing
