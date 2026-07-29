from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    asset_type: str = Field(
        pattern="^(cloud_account|server|container|endpoint|application|api|repository|saas|database|domain|user|privileged_account)$"
    )
    environment: str = "production"
    provider: str | None = None
    criticality: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    data_classification: str = Field(
        default="internal", pattern="^(public|internal|confidential|restricted)$"
    )
    internet_exposed: bool = False
    owner_id: uuid.UUID | None = None


class AssetOut(BaseModel):
    id: uuid.UUID
    name: str
    asset_type: str
    environment: str
    provider: str | None
    criticality: str
    data_classification: str
    internet_exposed: bool
    status: str
    owner_id: uuid.UUID | None
    last_observed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FindingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    category: str = Field(pattern="^(vulnerability|cloud_misconfiguration|identity|other)$")
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    cve: str | None = None
    asset_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    due_at: datetime | None = None


class FindingUpdate(BaseModel):
    status: str = Field(pattern="^(open|investigating|resolved|false_positive|risk_accepted)$")


class FindingOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    category: str
    severity: str
    cve: str | None
    status: str
    asset_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    due_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    finding_id: uuid.UUID | None = None


class AlertUpdate(BaseModel):
    status: str = Field(pattern="^(new|investigating|contained|resolved|false_positive)$")


class AlertOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    severity: str
    status: str
    finding_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    owner_id: uuid.UUID | None = None


class IncidentUpdate(BaseModel):
    status: str = Field(
        pattern="^(detected|triage|investigation|containment|eradication|recovery|postmortem|closed)$"
    )


class IncidentOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    severity: str
    status: str
    related_risk_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    closed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
