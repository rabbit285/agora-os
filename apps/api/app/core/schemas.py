from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    assignee_id: uuid.UUID | None = None
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    status: str = Field(pattern="^(open|in_progress|done|cancelled)$")


class TaskOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    module: str
    status: str
    priority: str
    assignee_id: uuid.UUID | None
    due_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    approve: bool
    reason: str | None = None


class ApprovalOut(BaseModel):
    id: uuid.UUID
    action_type: str
    risk_class: str
    status: str
    requested_by: uuid.UUID
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationSettingsOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class OrganizationSettingsUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class LegalEntityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    country: str | None = Field(default=None, min_length=2, max_length=2)


class LegalEntityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    is_default: bool | None = None


class LegalEntityOut(BaseModel):
    id: uuid.UUID
    name: str
    country: str | None
    is_default: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_entity_id: uuid.UUID | None = None


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_entity_id: uuid.UUID | None = None


class TeamOut(BaseModel):
    id: uuid.UUID
    name: str
    legal_entity_id: uuid.UUID | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MembershipOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    roles: list[str]

    model_config = {"from_attributes": True}


class NotificationOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FileUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    content_type: str = Field(min_length=1, max_length=150)
    size_bytes: int = Field(gt=0, le=200 * 1024 * 1024)
    classification: str = Field(
        default="internal", pattern="^(public|internal|confidential|restricted)$"
    )


class FileUploadResponse(BaseModel):
    file_id: uuid.UUID
    upload_url: str


class FileOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    classification: str
    created_at: datetime
    download_url: str | None = None

    model_config = {"from_attributes": True}
