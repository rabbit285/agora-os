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
    related_task_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    closed_at: datetime | None
    ai_summary: str | None
    personal_data_impact: bool
    root_cause: str | None
    lessons_learned: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class IncidentPostmortemUpdate(BaseModel):
    root_cause: str | None = Field(default=None, max_length=4000)
    lessons_learned: str | None = Field(default=None, max_length=4000)


class TimelineEntryCreate(BaseModel):
    entry_type: str = Field(default="update", pattern="^(update|communication)$")
    body: str = Field(min_length=1, max_length=4000)


class TimelineEntryOut(BaseModel):
    id: uuid.UUID
    entry_type: str
    body: str
    author_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AffectedAssetLink(BaseModel):
    asset_id: uuid.UUID


class IncidentDetailOut(IncidentOut):
    timeline: list[TimelineEntryOut]
    affected_assets: list[AssetOut]


class AssetDetailOut(AssetOut):
    findings: list[FindingOut]
    incidents: list[IncidentOut]


class AlertDetailOut(AlertOut):
    finding: FindingOut | None


class CloudScanResultOut(BaseModel):
    configured: bool
    checks_run: list[str]
    findings_created: int


class SecurityOverviewOut(BaseModel):
    """Security Overview dashboard (spec §13) — every field is a real,
    computed aggregate over this org's own data, never a placeholder
    number."""

    security_score: int
    critical_alerts: int
    high_risks: int
    assets_monitored: int
    vulnerabilities_open: int
    identity_issues_open: int
    cloud_misconfigurations_open: int
    open_incidents: int
    evidence_coverage_percent: float
