from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent


async def record_event(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    action: str,
    object_type: str,
    object_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    policy_decision: str = "allowed",
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    correlation_id: uuid.UUID | None = None,
) -> AuditEvent:
    """Write one append-only audit event. Never update or delete these rows."""
    if object_id == "None":
        raise ValueError(
            "record_event() received the literal string 'None' as object_id — this "
            "means the referenced object was passed before being flushed "
            "(SQLAlchemy only assigns a Python-side UUID default at flush time). "
            "Call `await db.flush()` after `db.add(obj)` before passing "
            "`str(obj.id)` here."
        )
    event = AuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        ip_address=ip_address,
        user_agent=user_agent,
        policy_decision=policy_decision,
        before_state=before_state,
        after_state=after_state,
        correlation_id=correlation_id or uuid.uuid4(),
    )
    db.add(event)
    await db.flush()
    return event
