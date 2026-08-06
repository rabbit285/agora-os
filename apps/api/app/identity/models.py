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
    # Optional, unchecked-by-default opt-in captured on signup — kept
    # separate from Terms/Privacy acceptance (which is a plain UI gate, not
    # persisted, since it isn't a GDPR-relevant processing consent the way
    # marketing contact is; see docs/PUBLIC_SITE_DESIGN.md).
    marketing_consent: Mapped[bool] = mapped_column(default=False)
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


class EmailVerificationToken(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SsoLoginAttempt(UUIDPrimaryKeyMixin, Base):
    """spec §59 SSO — a single-use CSRF token for the pre-login
    authorize→callback round trip, the same "capability token" pattern
    `IntegrationConnection.oauth_state` uses for the (post-login,
    org-scoped) Integrations OAuth flow. SSO has no session/org context
    yet when the callback fires, so this table (not a cookie or an
    existing row) is what proves a callback belongs to a request this
    server actually issued."""

    __tablename__ = "sso_login_attempts"

    state_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    # False only for a session created by a login for an mfa_enabled user,
    # until a correct TOTP code is submitted to /auth/mfa/verify — gates
    # app.dependencies.get_org_context (see docs there), not get_current_user,
    # so /auth/me and /auth/mfa/verify still work mid-challenge.
    mfa_verified: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
