from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    industry: str | None = None
    website: str | None = None
    employee_count: int | None = None
    owner_id: uuid.UUID | None = None


class AccountOut(BaseModel):
    id: uuid.UUID
    name: str
    industry: str | None
    website: str | None
    employee_count: int | None
    icp_score: float | None
    status: str
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ContactCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    job_title: str | None = None
    account_id: uuid.UUID | None = None


class ContactUpdate(BaseModel):
    do_not_contact: bool


class ContactOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    job_title: str | None
    account_id: uuid.UUID | None
    do_not_contact: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadCreate(BaseModel):
    source: str | None = None
    account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    score: float | None = None


class LeadUpdate(BaseModel):
    status: str = Field(pattern="^(new|qualified|contacted|disqualified|converted)$")


class LeadOut(BaseModel):
    id: uuid.UUID
    source: str | None
    status: str
    score: float | None
    account_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OpportunityCreate(BaseModel):
    account_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    value: float | None = None
    probability: float | None = None
    expected_close_at: datetime | None = None
    owner_id: uuid.UUID | None = None


class OpportunityUpdate(BaseModel):
    stage: str = Field(
        pattern="^(prospecting|qualification|proposal|negotiation|closed_won|closed_lost)$"
    )


class OpportunityOut(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    title: str
    stage: str
    value: float | None
    probability: float | None
    expected_close_at: datetime | None
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountDetailOut(AccountOut):
    contacts: list[ContactOut]
    opportunities: list[OpportunityOut]


class OutreachMessageCreate(BaseModel):
    contact_id: uuid.UUID
    channel: str = Field(default="email", pattern="^(email|linkedin)$")
    subject: str | None = None
    body: str = Field(min_length=1, max_length=4000)


class OutreachMessageOut(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    channel: str
    subject: str | None
    body: str
    status: str
    blocked_reason: str | None
    created_at: datetime
    sent_at: datetime | None

    model_config = {"from_attributes": True}
