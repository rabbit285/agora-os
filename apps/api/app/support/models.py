"""Customer Support domain (spec sections 30-35 — Phase 6).

Backbone only: Customer -> Ticket -> TicketMessage, plus a standalone
KnowledgeArticle library and CSATResponse. Consolidates the spec's
"support_conversations" concept into `Ticket` (a conversation *is* a
ticket in this build — spec lists them as separate tables with near
-identical shape, same simplification already applied to Security's
findings — ADR-0017) and its "support_intents" into `Ticket.category`
rather than a separate lookup table.

`Ticket.related_alert_id` is the cross-module hook this slice ships (spec
section 35: "Ticket mentions security breach -> mark urgent -> notify
Security -> create incident..."). A ticket categorized `security`
auto-creates a `SecurityAlert` — Security's own triage inbox, not a full
SecurityIncident, since promoting an alert to an incident is a human
security-analyst decision the Security module already models (see
app.secops.models.SecurityAlert / SecurityIncident and ADR-0020).

`Customer.sales_account_id` links a converted Sales Account to its
Support Customer record (spec section 69, "New Customer" cross-module
scenario) without forcing every Support Customer to have originated in
Sales — the field is nullable.

`Ticket.upsell_lead_id` is the Phase 8 cross-module hook (spec section 69
"Support Upsell Signal"): flagging a ticket creates a real `sales.Lead`
and notifies the linked account's owner, reusing Sales' and Phase 1's
existing primitives instead of inventing a new "signal" type — see
app.support.service.flag_upsell_signal and docs/DECISIONS.md ADR-0022.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "support_customers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    sales_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_accounts.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    plan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # active | churned
    status: Mapped[str] = mapped_column(String(20), default="active")


class Ticket(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "support_tickets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("support_customers.id"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # email | chat | api
    channel: Mapped[str] = mapped_column(String(20), default="email")
    # billing | technical | account | security | general
    category: Mapped[str] = mapped_column(String(20), default="general")
    # low | medium | high | urgent
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    # open | pending | resolved | closed
    status: Mapped[str] = mapped_column(String(20), default="open")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Cross-module hook (spec section 35): set when this ticket's category
    # is "security" — see app.support.service.create_ticket.
    related_alert_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("security_alerts.id"), nullable=True
    )
    # Cross-module hook (spec section 69 "Support Upsell Signal"): set when
    # an agent flags this ticket as an expansion signal — see
    # app.support.service.flag_upsell_signal.
    upsell_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_leads.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TicketMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "support_ticket_messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("support_tickets.id"), nullable=False, index=True
    )
    # customer | agent | ai
    sender_type: Mapped[str] = mapped_column(String(10), nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeArticle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "support_knowledge_articles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(String(8000), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    published: Mapped[bool] = mapped_column(default=False)


class CSATResponse(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "support_csat_responses"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("support_tickets.id"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(nullable=False)  # 1-5
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
