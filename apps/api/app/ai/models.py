from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow


class AiRun(UUIDPrimaryKeyMixin, Base):
    """One call through the Model Gateway. See docs/AI_ARCHITECTURE.md."""

    __tablename__ = "ai_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_template: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_classification: Mapped[str] = mapped_column(String(20), default="internal")
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    policy_result: Mapped[str] = mapped_column(String(20), default="allowed")
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
