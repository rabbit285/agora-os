from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SUPPORTED_STEP_TYPES = {"create_task", "send_notification", "human_approval"}


class WorkflowStep(BaseModel):
    step_type: Literal["create_task", "send_notification", "human_approval"]
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    # manual (default) or webhook — see app.integrations for how a webhook
    # connection links to a workflow with trigger_type="webhook".
    trigger_type: str = Field(default="manual", pattern="^(manual|webhook)$")
    steps: list[WorkflowStep] = Field(default_factory=list)

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
