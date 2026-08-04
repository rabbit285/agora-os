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
    ai_account_brief: str | None
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
        pattern="^(prospecting|qualification|proposal|security_review|negotiation|closed_won|closed_lost)$"
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
    onboarding_customer_id: uuid.UUID | None
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


class LeadDetailOut(LeadOut):
    account: AccountOut | None
    contact: ContactOut | None


class ContactDetailOut(ContactOut):
    account: AccountOut | None
    outreach: list[OutreachMessageOut]


class OpportunityDetailOut(OpportunityOut):
    account: AccountOut


class ICPProfileIn(BaseModel):
    target_industries: list[str] = Field(default_factory=list)
    min_employee_count: int | None = None
    max_employee_count: int | None = None


class ICPProfileOut(BaseModel):
    id: uuid.UUID
    target_industries: list[str]
    min_employee_count: int | None
    max_employee_count: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class LeadFinderResultOut(BaseModel):
    created_leads: list[LeadOut]
    candidates_considered: int


class EnrichmentResultOut(BaseModel):
    configured: bool
    updated_fields: list[str] = Field(default_factory=list)


class SequenceStepCreate(BaseModel):
    wait_days: int = Field(ge=0, default=0)
    channel: str = Field(default="email", pattern="^(email|linkedin)$")
    subject_template: str | None = None
    body_template: str = Field(min_length=1, max_length=4000)


class SequenceStepOut(BaseModel):
    id: uuid.UUID
    order_index: int
    wait_days: int
    channel: str
    subject_template: str | None
    body_template: str

    model_config = {"from_attributes": True}


class SequenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)


class SequenceOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SequenceEnrollmentOut(BaseModel):
    id: uuid.UUID
    sequence_id: uuid.UUID
    contact_id: uuid.UUID
    campaign_id: uuid.UUID | None
    status: str
    current_step_index: int
    next_step_due_at: datetime
    enrolled_at: datetime

    model_config = {"from_attributes": True}


class SequenceDetailOut(SequenceOut):
    steps: list[SequenceStepOut]
    enrollments: list[SequenceEnrollmentOut]


class SequenceEnrollRequest(BaseModel):
    contact_ids: list[uuid.UUID] = Field(min_length=1)


class ProcessDueStepsResultOut(BaseModel):
    processed: int


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    sequence_id: uuid.UUID
    contact_ids: list[uuid.UUID] = Field(default_factory=list)


class CampaignOut(BaseModel):
    id: uuid.UUID
    name: str
    sequence_id: uuid.UUID
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CampaignStatsOut(BaseModel):
    enrolled: int
    messages_sent: int
    messages_blocked: int
    completed: int


class CampaignDetailOut(CampaignOut):
    stats: CampaignStatsOut


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    account_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    scheduled_at: datetime
    notes: str | None = Field(default=None, max_length=4000)
    owner_id: uuid.UUID | None = None


class MeetingUpdate(BaseModel):
    status: str = Field(pattern="^(scheduled|completed|no_show|cancelled)$")


class MeetingOut(BaseModel):
    id: uuid.UUID
    title: str
    account_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    scheduled_at: datetime
    notes: str | None
    prep_notes: str | None
    status: str
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SalesIntelligenceOut(BaseModel):
    pipeline_value_by_stage: dict[str, float]
    win_rate_percent: float
    average_deal_size: float
    top_accounts_by_icp_score: list[AccountOut]
    sequence_completion_rate_percent: float
