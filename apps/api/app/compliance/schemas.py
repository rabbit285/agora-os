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


class AISystemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    vendor: str | None = None
    purpose: str = Field(min_length=1, max_length=2000)
    risk_classification: str = Field(
        default="minimal", pattern="^(minimal|limited|high|unacceptable)$"
    )
    owner_id: uuid.UUID | None = None


class AISystemStatusUpdate(BaseModel):
    status: str = Field(pattern="^(in_review|approved|rejected|retired)$")


class AISystemOut(BaseModel):
    id: uuid.UUID
    name: str
    vendor: str | None
    purpose: str
    risk_classification: str
    status: str
    owner_id: uuid.UUID | None
    approval_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIAssessmentCreate(BaseModel):
    status: str = Field(pattern="^(pass|fail|partial|not_assessed)$")
    notes: str | None = None


class AIAssessmentOut(BaseModel):
    id: uuid.UUID
    ai_system_id: uuid.UUID
    status: str
    notes: str | None
    assessed_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AISystemDetailOut(AISystemOut):
    assessments: list[AIAssessmentOut]


class ProcessingActivityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=2000)
    legal_basis: str = Field(
        pattern="^(consent|contract|legal_obligation|vital_interests|public_task|"
        "legitimate_interests)$"
    )
    data_categories: list[str] = Field(default_factory=list)
    data_subjects: str = Field(min_length=1, max_length=300)
    retention_period: str = Field(min_length=1, max_length=300)
    owner_id: uuid.UUID | None = None


class ProcessingActivityOut(BaseModel):
    id: uuid.UUID
    name: str
    purpose: str
    legal_basis: str
    data_categories: list[str]
    data_subjects: str
    retention_period: str
    status: str
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DPIACreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    processing_activity_id: uuid.UUID | None = None
    risk_level: str = Field(default="low", pattern="^(low|medium|high)$")
    owner_id: uuid.UUID | None = None


class DPIAStatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|in_review|approved|rejected)$")
    findings: str | None = None


class DPIAOut(BaseModel):
    id: uuid.UUID
    processing_activity_id: uuid.UUID | None
    ai_system_id: uuid.UUID | None
    title: str
    risk_level: str
    status: str
    findings: str | None
    approval_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DSARCreate(BaseModel):
    requester_name: str = Field(min_length=1, max_length=300)
    requester_email: str = Field(min_length=3, max_length=320)
    request_type: str = Field(pattern="^(access|deletion|rectification|portability)$")
    assigned_to: uuid.UUID | None = None


class DSARStatusUpdate(BaseModel):
    status: str = Field(pattern="^(received|in_progress|fulfilled|rejected)$")
    notes: str | None = None


class DSAROut(BaseModel):
    id: uuid.UUID
    requester_name: str
    requester_email: str
    request_type: str
    status: str
    due_at: datetime
    fulfilled_at: datetime | None
    notes: str | None
    assigned_to: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIIncidentCreate(BaseModel):
    ai_system_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    owner_id: uuid.UUID | None = None


class AIIncidentStatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|investigating|resolved|closed)$")


class AIIncidentOut(BaseModel):
    id: uuid.UUID
    ai_system_id: uuid.UUID
    title: str
    description: str | None
    severity: str
    status: str
    related_risk_id: uuid.UUID | None
    related_task_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
