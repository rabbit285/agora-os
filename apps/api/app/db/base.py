"""Shared declarative base and column mixins.

Conventions from docs/DATABASE_MODEL.md: UUID primary keys, UTC timestamps,
organization_id on every tenant-scoped table.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_aware_utc(value: datetime) -> datetime:
    """SQLite (used in tests) does not preserve tzinfo on DateTime(timezone=True)
    columns and returns naive datetimes on read, even though Postgres does
    not have this problem. Comparisons against `utcnow()` must go through
    this helper so the same code works against both backends."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# There is deliberately no TenantScopedMixin: SQLAlchemy declarative columns
# must be assigned directly in the class body to participate correctly in
# mapping, so every tenant-scoped model declares its own:
#
#   organization_id: Mapped[uuid.UUID] = mapped_column(
#       Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
#   )
#
# This is a convention enforced by code review and the tenant-isolation test
# suite (tests/test_tenant_isolation.py), not by inheritance.
