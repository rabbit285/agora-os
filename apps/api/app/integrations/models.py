"""Integrations domain (spec sections 48-49 — Phase 9).

Connector SDK backbone, deliberately narrow: spec §48 lists a dozen-plus
provider categories (CRM, Email, Cloud, Identity, Engineering,
Communication, Documents, Accounting), every one of which needs a real
third-party OAuth app or API key this environment doesn't have and
shouldn't fabricate (spec §82 "No Fake Features", §C2 "app must boot
without paid API keys"). `connector_key` supports exactly one value —
`"webhook"` — the one category buildable with zero external credentials:
an inbound HTTP receiver secured by a per-connection HMAC secret, not an
outbound OAuth flow.

`IntegrationConnection.linked_workflow_id` is the cross-module hook this
slice ships (spec section 69's automation trigger list, §38: "Webhook"):
a verified event on a connection linked to an `active` Automation
workflow triggers that workflow via the existing
`app.automation.service.start_run`, giving Automation its first
non-manual trigger without building a second execution engine. See
app.integrations.service and docs/DECISIONS.md ADR-0024.

`WebhookEvent` is the audit trail spec §49 calls for ("Connections must
store... Last sync, Last error") at the individual-event level — every
inbound call is recorded whether or not its signature verified, so a
misconfigured sender is diagnosable rather than silently dropped.
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
    # "webhook" only in this build — see module docstring.
    connector_key: Mapped[str] = mapped_column(String(50), default="webhook")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # active | disabled
    status: Mapped[str] = mapped_column(String(20), default="active")
    webhook_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    # Cross-module hook (spec §38 "Webhook" trigger) — see
    # app.integrations.service.receive_webhook_event.
    linked_workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_workflows.id"), nullable=True
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
