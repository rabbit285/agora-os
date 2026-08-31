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

What a client gets back is the event *resolved* — a title, the name of
the record it happened to, who did it, and what changed — alongside the
raw fields. The translation happens in `app.audit.presentation` so every
surface reads the same words, and so no screen has to decide for itself
what `compliance.control.assessed` means.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.labels import describe
from app.audit.models import AuditEvent
from app.audit.presentation import (
    AI_ACTIONS,
    SYSTEM_ACTIONS,
    build_views,
)
from app.audit.search import matching_object_ids
from app.db.session import get_db
from app.dependencies import OrgContext, require_permission

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit"])


class AuditChangeOut(BaseModel):
    """One field that moved. `before` is null where the event recorded
    only a new value — most writes do, and inventing a previous value to
    fill the arrow would be a claim the record does not make."""

    label: str
    before: str | None = None
    after: str


class AuditEntityOut(BaseModel):
    """What the event happened to, by name."""

    kind: str
    label: str
    href: str | None = None
    available: bool = True


class AuditEventOut(BaseModel):
    id: uuid.UUID
    # --- what a person reads -----------------------------------------
    title: str
    category: str
    category_label: str
    entity: AuditEntityOut | None = None
    actor_name: str
    # person | ai | system | integration | unknown. Never inferred from
    # whether a user id happens to be recorded — see presentation.py.
    actor_kind: str
    changes: list[AuditChangeOut] = []
    reason: str | None = None
    created_at: datetime
    # --- the technical record, for the details drawer ----------------
    #
    # Still here, deliberately. The redesign hides these from the
    # timeline; it does not remove them, because the raw event is what
    # makes the trail worth keeping.
    action: str
    object_type: str
    object_id: str | None
    actor_user_id: uuid.UUID | None
    actor_email: str | None = None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    correlation_id: uuid.UUID | None = None
    # The same event as a sentence, phrased by app.audit.labels — used by
    # the per-record feeds on a task or a policy, which have their own,
    # terser voice because the record is already named on the page.
    label: str | None = None

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
    q: str | None = Query(
        default=None,
        description=(
            "Search by the name of the affected record, by person, by event "
            "wording, or by a raw id."
        ),
    ),
    actor_kind: str | None = Query(
        default=None,
        description="person | ai | system | integration",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    # Reading the audit trail is itself a privileged action: it exposes
    # who did what and when across the whole organization.
    context: OrgContext = Depends(require_permission("audit.read")),
) -> list[AuditEventOut]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == context.organization_id)
    if action_prefix:
        stmt = stmt.where(AuditEvent.action.startswith(action_prefix))
    if object_id:
        stmt = stmt.where(AuditEvent.object_id == object_id)

    # Who performed it. Expressed as a condition on `action` rather than
    # computed per row, so the filter is applied by the database and the
    # page size means what it says.
    if actor_kind == "ai":
        stmt = stmt.where(AuditEvent.action.in_(AI_ACTIONS))
    elif actor_kind == "system":
        stmt = stmt.where(AuditEvent.action.in_(SYSTEM_ACTIONS))
    elif actor_kind == "integration":
        stmt = stmt.where(AuditEvent.action.startswith("integrations."))
    elif actor_kind == "person":
        stmt = stmt.where(
            AuditEvent.actor_user_id.is_not(None),
            AuditEvent.action.notin_(AI_ACTIONS | SYSTEM_ACTIONS),
            ~AuditEvent.action.startswith("integrations."),
        )

    if q and q.strip():
        term = q.strip()
        # A search box on an audit trail has to answer both "what
        # happened to the AI Governance Policy" and "trace this id".
        # Entity names live in their own tables, so the ids of records
        # matching by name are resolved first and the trail filtered to
        # them — the alternative is filtering after the page is fetched,
        # which silently searches only the rows that happened to load.
        object_ids = await matching_object_ids(
            db, organization_id=context.organization_id, term=term
        )
        conditions = [cast(AuditEvent.action, String).ilike(f"%{term}%")]
        if object_ids:
            conditions.append(AuditEvent.object_id.in_(object_ids))
        # A raw id pasted in still traces, through the same box.
        conditions.append(AuditEvent.object_id == term)
        with contextlib.suppress(ValueError):
            conditions.append(AuditEvent.id == uuid.UUID(term))
        stmt = stmt.where(or_(*conditions))

    result = await db.execute(stmt.order_by(AuditEvent.created_at.desc()).limit(limit))
    events = list(result.scalars().all())

    views = await build_views(
        db, organization_id=context.organization_id, events=events
    )
    return [
        AuditEventOut(
            id=view.id,
            title=view.title,
            category=view.category,
            category_label=view.category_label,
            entity=(
                AuditEntityOut(
                    kind=view.entity.kind,
                    label=view.entity.label,
                    href=view.entity.href,
                    available=view.entity.available,
                )
                if view.entity
                else None
            ),
            actor_name=view.actor_name,
            actor_kind=view.actor_kind,
            changes=[
                AuditChangeOut(label=c.label, before=c.before, after=c.after)
                for c in view.changes
            ],
            reason=view.reason,
            created_at=view.created_at,
            action=view.action,
            object_type=view.object_type,
            object_id=view.object_id,
            actor_user_id=view.actor_user_id,
            actor_email=view.actor_email,
            before_state=view.before_state,
            after_state=view.after_state,
            correlation_id=view.correlation_id,
            label=describe(view.action, view.after_state),
        )
        for view in views
    ]
