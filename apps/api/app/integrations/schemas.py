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
    webhook_secret: str
    linked_workflow_id: uuid.UUID | None
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
