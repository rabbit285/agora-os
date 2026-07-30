"""Sales domain (spec sections 20-29 — Phase 5).

Backbone only: Account -> Contact -> Lead/Opportunity, plus a minimal
Outreach model. Real lead-finding, enrichment, and message *sending* all
depend on external data sources and email providers that don't exist yet
in this build (spec's progressive trust model — read-only connectors
first, spec §B1) — see docs/KNOWN_LIMITATIONS.md.

`Contact.do_not_contact` is the field the cross-module hook checks: spec
section 91 — "Sales AI asks: Can we contact this prospect? Compliance
checks: jurisdiction, data source, marketing basis, opt-out, suppression,
organization policy." `app.sales.service.send_outreach_message` is where
that check actually happens.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_accounts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(nullable=True)
    icp_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    # prospect | customer | churned
    status: Mapped[str] = mapped_column(String(20), default="prospect")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_contacts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_accounts.id"), nullable=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Suppression flag — spec section 91, checked by
    # app.sales.service.send_outreach_message before any send.
    do_not_contact: Mapped[bool] = mapped_column(default=False)


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_leads"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_accounts.id"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_contacts.id"), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # new | qualified | contacted | disqualified | converted
    status: Mapped[str] = mapped_column(String(20), default="new")
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)


class Opportunity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sales_opportunities"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_accounts.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # prospecting|qualification|proposal|security_review|negotiation|closed_won|closed_lost
    # security_review is set by app.compliance.service.start_security_review,
    # not chosen freehand — see docs/DECISIONS.md ADR-0035.
    stage: Mapped[str] = mapped_column(String(20), default="prospecting")
    value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    probability: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    expected_close_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Cross-module hook (spec §69 "New Customer", ADR-0025): set once, the
    # first time this opportunity transitions to closed_won, by
    # app.sales.service.close_opportunity_won. Its presence is also the
    # idempotency guard — a second closed_won transition is a no-op.
    onboarding_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("support_customers.id"), nullable=True
    )


class OutreachMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sales_outreach_messages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_contacts.id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), default="email")  # email | linkedin
    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
    # draft | sent | blocked
    status: Mapped[str] = mapped_column(String(20), default="draft")
    blocked_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
