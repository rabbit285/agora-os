from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChecklistItem(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    done: bool = False


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high|urgent)$")
    assignee_id: uuid.UUID | None = None
    due_at: datetime | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    checklist: list[ChecklistItem] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|in_progress|done|cancelled)$")
    checklist: list[ChecklistItem] | None = None
    # A remediation plan suggests a *team* — "HR / People" — because we
    # do not know the customer's org chart. Naming the person is theirs
    # to do, and the trail should say when they did it.
    assignee_id: uuid.UUID | None = None


class TaskCommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class TaskCommentOut(BaseModel):
    id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskEvidenceCreate(BaseModel):
    file_id: uuid.UUID


class TaskEvidenceOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskActivityOut(BaseModel):
    action: str
    # The same event as a sentence. Computed rather than stored so the
    # wording can change without rewriting the audit trail, which must
    # stay immutable.
    label: str
    actor_user_id: uuid.UUID | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    module: str
    status: str
    priority: str
    assignee_id: uuid.UUID | None
    due_at: datetime | None
    created_by: uuid.UUID | None
    entity_type: str | None
    entity_id: str | None
    checklist: list[dict[str, Any]]
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
    module: str | None
    ai_generated: bool
    due_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrganizationSettingsOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    notification_webhook_url: str | None
    deletion_requested_at: datetime | None

    model_config = {"from_attributes": True}


class OrganizationSettingsUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    # spec §66 Webhook notification channel target. Not in
    # model_fields_set means "leave unchanged"; explicit null clears it.
    notification_webhook_url: str | None = Field(default=None, max_length=500)


class OrganizationDeletionConfirm(BaseModel):
    # Typing the exact current organization name is the confirmation
    # gate for both requesting and executing deletion — the same
    # "type the name to confirm" pattern real danger-zone UIs use,
    # checked against the organization's real current name server-side.
    confirm_name: str = Field(min_length=1, max_length=200)


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


class RoleOut(BaseModel):
    key: str
    name: str
    permissions: list[str]


class OrganizationPersonOut(BaseModel):
    """A colleague, as a form offers them.

    Deliberately thin. This answers "who could I pick", not "who is in
    this organization and what can they do" — that second question is
    `MembershipOut`, and it needs a permission this one does not.
    """

    id: uuid.UUID
    full_name: str | None = None
    email: str

    model_config = {"from_attributes": True}


class MembershipOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    roles: list[str]
    # Who the member actually is. A picker that offers user ids is not a
    # picker — anywhere the product asks "which person", it has to be
    # able to show their name.
    full_name: str | None = None
    email: str | None = None

    model_config = {"from_attributes": True}


class NotificationOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str | None
    link: str | None
    channels_requested: list[str]
    channels_delivered: list[str]
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationPreferenceOut(BaseModel):
    channel: str
    enabled: bool

    model_config = {"from_attributes": True}


class NotificationPreferenceUpdate(BaseModel):
    channel: str = Field(pattern="^(email|slack|teams|webhook)$")
    enabled: bool


class FileUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    content_type: str = Field(min_length=1, max_length=150)
    size_bytes: int = Field(gt=0, le=200 * 1024 * 1024)
    classification: str = Field(
        default="internal", pattern="^(public|internal|confidential|restricted)$"
    )
    # SHA-256 of the file, computed by the client before uploading.
    #
    # Optional, and treated as a *hint*: uploads are presigned, so the API
    # has no bytes to hash at this point and cannot verify the claim. It
    # is used to answer "you already have this" before the customer waits
    # through an upload and a full analysis, and the pipeline recomputes
    # the hash from the real content the first time it reads the file —
    # a wrong or absent claim costs an upload, never correctness.
    content_hash: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")


class FileUploadResponse(BaseModel):
    file_id: uuid.UUID
    # Null when the file is already held: there is nothing to upload.
    upload_url: str | None = None
    # What the customer is told. `duplicate` means these exact bytes are
    # already an analysed document; `processing` means an upload of them
    # is in flight and a second pipeline must not be started.
    status: str = "new"
    message: str | None = None


class FileOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    classification: str
    created_at: datetime
    download_url: str | None = None

    model_config = {"from_attributes": True}
