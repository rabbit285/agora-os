from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanOut(BaseModel):
    key: str
    name: str
    entitlements: dict[str, Any]

    model_config = {"from_attributes": True}


class OrganizationPlanOut(BaseModel):
    plan_key: str
    entitlements: dict[str, Any]
    current_users: int


class SetPlanRequest(BaseModel):
    plan_key: str = Field(pattern="^(starter|growth|business|enterprise)$")
