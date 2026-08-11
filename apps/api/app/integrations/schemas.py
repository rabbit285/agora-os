from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ConnectionUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(active|disabled)$")
    linked_workflow_id: uuid.UUID | None = None
    unlink_workflow: bool = False


class ConnectionOut(BaseModel):
    """Deliberately has no field for `encrypted_access_token` /
    `encrypted_refresh_token`: token material must never be serializable
    to the browser, so it is absent from the response model rather than
    filtered out later (see docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md §13)."""

    id: uuid.UUID
    connector_key: str
    name: str
    status: str
    webhook_secret: str | None
    linked_workflow_id: uuid.UUID | None
    scopes: list[str] | None
    external_account_id: str | None
    health_status: str | None
    last_health_check_at: datetime | None
    last_synced_at: datetime | None
    last_error: str | None
    created_at: datetime

    # Customer-connected provider identity/lifecycle (Apollo).
    provider_user_email: str | None = None
    provider_workspace_id: str | None = None
    provider_workspace_name: str | None = None
    connected_at: datetime | None = None
    refreshed_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_code: str | None = None
    reauthorization_required_at: datetime | None = None
    disconnected_at: datetime | None = None

    model_config = {"from_attributes": True}


class WebhookEventOut(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    verified: bool
    payload: dict[str, Any] | None
    triggered_run_id: uuid.UUID | None
    received_at: datetime

    model_config = {"from_attributes": True}


class ProviderCatalogEntry(BaseModel):
    connector_key: str
    name: str
    auth_type: str
    configured: bool
    scopes: list[str] = Field(default_factory=list)


class OAuthStartResponse(BaseModel):
    connection_id: uuid.UUID
    authorization_url: str


class SyncRunOut(BaseModel):
    id: uuid.UUID
    connection_id: uuid.UUID
    status: str
    items_synced: int | None
    error: str | None
    cursor_used: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
