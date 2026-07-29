from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    email: EmailStr
    plan: str | None = None
    sales_account_id: uuid.UUID | None = None


class CustomerOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    plan: str | None
    sales_account_id: uuid.UUID | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketCreate(BaseModel):
    customer_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=300)
    description: str | None = None
    channel: str = Field(default="email", pattern="^(email|chat|api)$")
    category: str = Field(
        default="general", pattern="^(billing|technical|account|security|general)$"
    )
    priority: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")


class TicketUpdate(BaseModel):
    status: str = Field(pattern="^(open|pending|resolved|closed)$")


class TicketOut(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    subject: str
    description: str | None
    channel: str
    category: str
    priority: str
    status: str
    owner_id: uuid.UUID | None
    related_alert_id: uuid.UUID | None
    upsell_lead_id: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketMessageCreate(BaseModel):
    sender_type: str = Field(pattern="^(customer|agent|ai)$")
    body: str = Field(min_length=1, max_length=4000)


class TicketMessageOut(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    sender_type: str
    author_id: uuid.UUID | None
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TicketDetailOut(TicketOut):
    messages: list[TicketMessageOut]


class KnowledgeArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8000)
    category: str | None = None


class KnowledgeArticleUpdate(BaseModel):
    published: bool


class KnowledgeArticleOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    category: str | None
    published: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CSATResponseCreate(BaseModel):
    ticket_id: uuid.UUID
    score: int = Field(ge=1, le=5)
    comment: str | None = None


class CSATResponseOut(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    score: int
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
