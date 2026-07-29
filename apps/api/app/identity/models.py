"""User identity and session models.

Sessions are opaque, server-revocable tokens (docs/SECURITY_ARCHITECTURE.md),
not self-contained JWTs, so that "session revocation" (spec E4) is a single
row update rather than requiring a separate denylist.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    # Email is normalized to lowercase in app.identity.service before every
    # write/read so the unique constraint behaves case-insensitively without
    # requiring the Postgres-only CITEXT extension (keeps SQLite usable for
    # fast unit tests, see tests/conftest.py).
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    mfa_enabled: Mapped[bool] = mapped_column(default=False)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Session(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=True
    )
    session_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Stored as text (not the Postgres-only INET type) to stay portable to
    # SQLite for fast unit tests; format validated at the application layer.
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
