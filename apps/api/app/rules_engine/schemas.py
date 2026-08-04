from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.rules_engine.models import ACTION_TYPES, CONDITION_OPERATORS

# The real trigger_type values app.automation.triggers.dispatch_event is
# actually called with (see each call site's comment) — the same
# vocabulary Automation workflows trigger on, so a Business Rule and a
# Workflow can react to the identical real event.
TRIGGER_TYPES = frozenset(
    {
        "new_employee",
        "control_failed",
        "new_vendor",
        "document_uploaded",
        "new_crm_lead",
        "crm_stage_change",
        "security_alert",
        "new_support_ticket",
        "ai_system_registered",
    }
)


class BusinessRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    trigger_type: str
    condition_field: str = Field(min_length=1, max_length=50)
    condition_operator: str
    condition_value: str = Field(min_length=1, max_length=200)
    action_type: str
    action_role_key: str = Field(min_length=1, max_length=50)
    action_risk_class: str | None = Field(default=None, pattern="^(low|moderate|high|critical)$")

    @field_validator("trigger_type")
    @classmethod
    def _validate_trigger_type(cls, value: str) -> str:
        if value not in TRIGGER_TYPES:
            raise ValueError(f"Unknown trigger_type: {value}")
        return value

    @field_validator("condition_operator")
    @classmethod
    def _validate_operator(cls, value: str) -> str:
        if value not in CONDITION_OPERATORS:
            raise ValueError(f"Unknown condition_operator: {value}")
        return value

    @field_validator("action_type")
    @classmethod
    def _validate_action_type(cls, value: str) -> str:
        if value not in ACTION_TYPES:
            raise ValueError(f"Unknown action_type: {value}")
        return value


class BusinessRuleUpdate(BaseModel):
    is_active: bool


class BusinessRuleOut(BaseModel):
    id: uuid.UUID
    name: str
    trigger_type: str
    condition_field: str
    condition_operator: str
    condition_value: str
    action_type: str
    action_role_key: str
    action_risk_class: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
