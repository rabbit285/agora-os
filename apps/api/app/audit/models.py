"""Append-only audit event log (spec section B8).

The migration that creates this table also REVOKEs UPDATE/DELETE from the
application database role — see migrations/versions for the revision that
adds audit_events, and docs/SECURITY_ARCHITECTURE.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"

    # Nullable: platform-level events (e.g. a failed login before an
    # organization context exists) have no organization.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(150), nullable=False)
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    policy_decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
