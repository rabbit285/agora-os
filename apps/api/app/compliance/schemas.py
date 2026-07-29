from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FrameworkOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None

    model_config = {"from_attributes": True}


class RequirementOut(BaseModel):
    id: uuid.UUID
    reference_code: str
    title: str
    description: str | None

    model_config = {"from_attributes": True}


class ControlCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    owner_id: uuid.UUID | None = None
    requirement_ids: list[uuid.UUID] = Field(default_factory=list)


class ControlOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: str
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ControlAssessmentCreate(BaseModel):
    status: str = Field(pattern="^(pass|fail|partial|not_assessed)$")
    notes: str | None = None


class ControlAssessmentOut(BaseModel):
    id: uuid.UUID
    status: str
    notes: str | None
    assessed_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ControlDetailOut(ControlOut):
    requirements: list[RequirementOut]
    assessments: list[ControlAssessmentOut]


class EvidenceCreate(BaseModel):
    file_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    control_id: uuid.UUID | None = None
    valid_until: datetime | None = None


class EvidenceOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    control_id: uuid.UUID | None
    title: str
    valid_until: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    category: str = "general"
    likelihood: str = Field(pattern="^(low|medium|high)$")
    impact: str = Field(pattern="^(low|medium|high)$")
    control_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None


class RiskUpdate(BaseModel):
    status: str = Field(pattern="^(open|mitigated|accepted)$")


class RiskOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    category: str
    likelihood: str
    impact: str
    status: str
    control_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    file_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None


class PolicyOut(BaseModel):
    id: uuid.UUID
    title: str
    file_id: uuid.UUID | None
    status: str
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
