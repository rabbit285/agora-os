from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

GOAL_KEYS = frozenset(
    {
        "improve_compliance",
        "improve_security",
        "find_more_customers",
        "automate_customer_support",
        "automate_business_operations",
    }
)


class OnboardingProfileOut(BaseModel):
    industry: str | None
    employee_count_range: str | None
    selected_goals: list[str]
    selected_framework_keys: list[str]
    primary_cloud_provider: str | None
    sales_focus: str | None
    support_channels: list[str]
    current_step: int
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class CompanyStepUpdate(BaseModel):
    industry: str = Field(min_length=1, max_length=150)
    employee_count_range: str = Field(pattern=r"^(1-10|11-50|51-200|201-1000|1000\+)$")


class GoalsStepUpdate(BaseModel):
    selected_goals: list[str] = Field(min_length=1)

    @field_validator("selected_goals")
    @classmethod
    def _validate_keys(cls, value: list[str]) -> list[str]:
        unknown = set(value) - GOAL_KEYS
        if unknown:
            raise ValueError(f"Unknown goal key(s): {sorted(unknown)}")
        return value


class ComplianceProfileStepUpdate(BaseModel):
    selected_framework_keys: list[str]


class SecurityProfileStepUpdate(BaseModel):
    primary_cloud_provider: str | None = Field(
        default=None, pattern="^(aws|azure|gcp|none)$"
    )


class SalesProfileStepUpdate(BaseModel):
    sales_focus: str = Field(min_length=1, max_length=200)


class SupportProfileStepUpdate(BaseModel):
    support_channels: list[str]


class ReadinessDimensionOut(BaseModel):
    label: str
    percent: float


class ReadinessOpportunityOut(BaseModel):
    title: str
    detail: str


class ReadinessOut(BaseModel):
    compliance: ReadinessDimensionOut
    security: ReadinessDimensionOut
    sales_automation: ReadinessDimensionOut
    support_automation: ReadinessDimensionOut
    process_automation: ReadinessDimensionOut
    opportunities: list[ReadinessOpportunityOut]
