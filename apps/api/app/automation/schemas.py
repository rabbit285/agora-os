from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# spec §39's 24 named action types, plus 2 pre-existing extras
# (send_notification, export_data) kept for backward compatibility —
# see app.automation.service.STEP_HANDLERS for what each one actually
# does and docs/KNOWN_LIMITATIONS.md for the credential-gated ones
# (send_email, send_chat_message).
SUPPORTED_STEP_TYPES = {
    "create_task",
    "send_notification",
    "human_approval",
    "export_data",
    "create_record",
    "update_record",
    "send_email",
    "send_chat_message",
    "assign_user",
    "generate_document",
    "analyze_document",
    "extract_data",
    "classify_data",
    "call_api",
    "webhook",
    "search_knowledge",
    "generate_ai_response",
    "run_compliance_assessment",
    "run_security_check",
    "create_lead",
    "update_crm",
    "create_support_ticket",
    "create_report",
    "delay",
    "condition",
    "loop",
}

# spec §38's 16 named trigger types. Not all have a real internal event
# source in this build (see app.automation.triggers for exactly which —
# new_email/form_submission/database_event/new_regulatory_update are
# accepted but never actually fire, the same disclosed-scope pattern used
# throughout this build for connector-dependent features).
SUPPORTED_TRIGGER_TYPES = {
    "manual",
    "schedule",
    "webhook",
    "api",
    "new_email",
    "new_crm_lead",
    "crm_stage_change",
    "new_support_ticket",
    "new_vendor",
    "new_employee",
    "document_uploaded",
    "control_failed",
    "security_alert",
    "form_submission",
    "database_event",
    "new_regulatory_update",
}

StepType = Literal[
    "create_task",
    "send_notification",
    "human_approval",
    "export_data",
    "create_record",
    "update_record",
    "send_email",
    "send_chat_message",
    "assign_user",
    "generate_document",
    "analyze_document",
    "extract_data",
    "classify_data",
    "call_api",
    "webhook",
    "search_knowledge",
    "generate_ai_response",
    "run_compliance_assessment",
    "run_security_check",
    "create_lead",
    "update_crm",
    "create_support_ticket",
    "create_report",
    "delay",
    "condition",
    "loop",
]


class WorkflowStep(BaseModel):
    step_type: StepType
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    trigger_type: str = Field(default="manual")
    schedule_cron: str | None = None
    steps: list[WorkflowStep] = Field(default_factory=list)

    @field_validator("trigger_type")
    @classmethod
    def _validate_trigger_type(cls, value: str) -> str:
        if value not in SUPPORTED_TRIGGER_TYPES:
            raise ValueError(f"Unsupported trigger_type: {value}")
        return value

    @field_validator("steps")
    @classmethod
    def _require_at_least_one_step(cls, steps: list[WorkflowStep]) -> list[WorkflowStep]:
        if not steps:
            raise ValueError("A workflow needs at least one step")
        return steps


class WorkflowStepsUpdate(BaseModel):
    steps: list[WorkflowStep] = Field(min_length=1)


class WorkflowStatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|testing|active|paused|archived)$")


class WorkflowOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    trigger_type: str
    schedule_cron: str | None
    status: str
    steps: list[dict[str, Any]]
    version: int
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunTrigger(BaseModel):
    trigger_payload: dict[str, Any] | None = None


class WorkflowRunOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    trigger_payload: dict[str, Any] | None
    triggered_by: uuid.UUID | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class WorkflowStepRunOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    step_index: int
    step_type: str
    status: str
    output: dict[str, Any] | None
    approval_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunDetailOut(WorkflowRunOut):
    step_runs: list[WorkflowStepRunOut]


class WorkflowVersionOut(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    version_number: int
    steps: list[dict[str, Any]]
    trigger_type: str
    published_by: uuid.UUID | None
    published_at: datetime

    model_config = {"from_attributes": True}


class WorkflowTemplateOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    category: str
    trigger_type: str
    steps: list[dict[str, Any]]

    model_config = {"from_attributes": True}


class WorkflowAnalyticsOut(BaseModel):
    total_workflows: int
    active_workflows: int
    total_runs: int
    runs_by_status: dict[str, int]
    success_rate_percent: float
    awaiting_approval_count: int
