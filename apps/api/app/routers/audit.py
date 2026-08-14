"""Read access to the audit trail.

`audit_events` has been written to since the beginning and is protected
at the database level by a trigger that blocks UPDATE and DELETE — but
nothing could read it back, which made the guarantee unverifiable by the
people who most need it. An append-only log nobody can inspect provides
assurance to no one.

Read-only by construction: there is no POST here and there never should
be. Events are written by `app.audit.service.record_event` as a side
effect of the action being audited, so an endpoint that let a client
insert one would let a client forge history.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.db.session import get_db
from app.dependencies import OrgContext, require_permission

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit"])


class AuditEventOut(BaseModel):
    id: uuid.UUID
    action: str
    object_type: str
    object_id: str | None
    actor_user_id: uuid.UUID | None
    actor_email: str | None = None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AuditEventOut])
async def list_audit_events(
    action_prefix: str | None = Query(
        default=None,
        description="Filter to one area, e.g. 'compliance.' or 'compliance.gap.'",
    ),
    object_id: str | None = Query(
        default=None, description="Trace every event recorded against one entity."
    ),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    # Reading the audit trail is itself a privileged action: it exposes
    # who did what and when across the whole organization.
    context: OrgContext = Depends(require_permission("audit.read")),
) -> list[AuditEvent]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == context.organization_id)
    if action_prefix:
        stmt = stmt.where(AuditEvent.action.startswith(action_prefix))
    if object_id:
        stmt = stmt.where(AuditEvent.object_id == object_id)
    result = await db.execute(stmt.order_by(AuditEvent.created_at.desc()).limit(limit))
    return list(result.scalars().all())
