from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.trust_center.models import TRUST_CENTER_CATEGORIES

_CATEGORY_PATTERN = "^(" + "|".join(TRUST_CENTER_CATEGORIES) + ")$"
_STATUS_PATTERN = "^(planned|in_progress|implemented|independently_assessed|certified)$"


class TrustCenterItemUpsert(BaseModel):
    category: str = Field(pattern=_CATEGORY_PATTERN)
    title: str = Field(min_length=1, max_length=300)
    content: str | None = None
    status: str = Field(default="planned", pattern=_STATUS_PATTERN)
    is_public: bool = False
    policy_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    # Required when status is independently_assessed or certified: those
    # assert an external party's conclusion, which cannot be inferred from
    # anything else in the product.
    attestation_file_id: uuid.UUID | None = None
    attestation_note: str | None = Field(default=None, max_length=1000)


class TrustCenterItemOut(BaseModel):
    id: uuid.UUID
    category: str
    title: str
    content: str | None
    status: str
    is_public: bool
    policy_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    attestation_file_id: uuid.UUID | None = None
    attestation_note: str | None = None
    attested_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvidenceRequestCreate(BaseModel):
    requester_name: str = Field(min_length=1, max_length=300)
    requester_email: str = Field(min_length=3, max_length=320)
    company_name: str | None = None
    message: str | None = None


class EvidenceRequestStatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|fulfilled)$")


class EvidenceRequestOut(BaseModel):
    id: uuid.UUID
    requester_name: str
    requester_email: str
    company_name: str | None
    message: str | None
    status: str
    related_task_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TrustCenterPublicPolicyOut(BaseModel):
    id: uuid.UUID
    title: str


class TrustCenterPublicItemOut(BaseModel):
    category: str
    title: str
    content: str | None
    status: str
    policy: TrustCenterPublicPolicyOut | None


class TrustCenterPublicOut(BaseModel):
    organization_name: str
    items: list[TrustCenterPublicItemOut]
