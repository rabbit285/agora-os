"""Integrations domain (spec sections 48-49 — Phase 9).

Two connector shapes exist in this build:

1. **Webhook** (`connector_key="webhook"`, Phase 9 slice 1): an inbound
   HTTP receiver secured by a per-connection HMAC secret
   (`webhook_secret`). See ADR-0024.
2. **OAuth2** (`connector_key="hubspot"` today, Phase 9 slice 2): a real
   authorization-code flow. `encrypted_access_token` /
   `encrypted_refresh_token` are encrypted at rest
   (`app/core/crypto.py`, Fernet) — never stored or logged in plaintext.
   `oauth_state` is a short-lived CSRF token generated at
   authorization-start and consumed at callback; the callback route has
   no session, so `oauth_state` (not a cookie) is what proves the
   callback belongs to this pending connection, the same "capability
   token" pattern the Webhook receiver uses for its own auth boundary.

Every other spec §48 connector category (CRM beyond HubSpot, Email,
Marketing, Customer Support, Cloud, Identity, Engineering, Communication,
Documents, Accounting) needs a real third-party OAuth app or API key this
environment doesn't have — none are stubbed as "connected" (spec §82). A
connection's `status` is connector-shape-specific: `webhook` connections
use `active`/`disabled`; OAuth connections use
`not_connected`/`connected`/`error`/`disconnected`. See ADR-0024, ADR-0026.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class IntegrationConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "integration_connections"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # "webhook" | "hubspot"
    connector_key: Mapped[str] = mapped_column(String(50), default="webhook")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # webhook: active|disabled — oauth2: not_connected|connected|error|disconnected
    status: Mapped[str] = mapped_column(String(20), default="active")

    # --- Webhook connector fields (nullable — unused by OAuth connections) ---
    webhook_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Cross-module hook (spec §38 "Webhook" trigger) — see
    # app.integrations.service.receive_webhook_event.
    linked_workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_workflows.id"), nullable=True
    )

    # --- OAuth2 connector fields (nullable — unused by the Webhook connector) ---
    encrypted_access_token: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scopes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    external_account_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Single-use CSRF token for the authorize -> callback round trip.
    oauth_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    oauth_state_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # ok | error — set by the health-check endpoint, not on every request
    health_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class WebhookEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "integration_webhook_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("integration_connections.id"), nullable=False, index=True
    )
    verified: Mapped[bool] = mapped_column(nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    triggered_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_workflow_runs.id"), nullable=True
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyncRun(UUIDPrimaryKeyMixin, Base):
    """A single "sync now" execution against an OAuth connector (spec §49's
    `sync()` capability). Runs synchronously inline in this build, not as a
    durable Temporal job — see docs/KNOWN_LIMITATIONS.md — so this row is
    the only record of what happened, written after the fact rather than
    checkpointed during a long-running job."""

    __tablename__ = "integration_sync_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("integration_connections.id"), nullable=False, index=True
    )
    # running | succeeded | failed
    status: Mapped[str] = mapped_column(String(20), default="running")
    items_synced: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
