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
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
