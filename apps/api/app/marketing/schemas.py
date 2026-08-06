from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

CompanySize = Literal["1-10", "11-50", "51-200", "201-500", "500+"]

PrimaryInterest = Literal[
    "compliance",
    "security",
    "sales",
    "support",
    "automation",
    "ai_governance",
    "knowledge_management",
    "ai_copilot",
    "other",
]


class DemoRequestIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    work_email: EmailStr
    company_name: str = Field(min_length=1, max_length=200)
    company_size: CompanySize
    country: str = Field(min_length=1, max_length=100)
    primary_interest: PrimaryInterest
    message: str | None = Field(default=None, max_length=2000)


class DemoRequestOut(BaseModel):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
