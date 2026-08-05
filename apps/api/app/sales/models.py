"""Sales domain (spec sections 20-29 — Phase 5).

Account -> Contact -> Lead/Opportunity, plus Outreach, ICP scoring
(`ICPProfile`, `app.sales.icp`), Sequences/Campaigns
(`Sequence`/`SequenceStep`/`SequenceEnrollment`/`Campaign`,
`app.sales.sequences`), and Meetings (`Meeting`, `app.sales.meetings`).
Message *sending* still has no real email/LinkedIn provider (spec's
progressive trust model — read-only connectors first, spec §B1); every
send path (manual outreach and Sequence/Campaign steps alike) only ever
transitions a message's own status, gated by the same real Compliance
check — see docs/KNOWN_LIMITATIONS.md. Company enrichment
(`app.sales.enrichment`) is real when a Clearbit API key is configured,
honestly "not configured" otherwise — the same credential-gated pattern
as the AI providers, OAuth integrations, and AWS Cloud Security scanning.

`Contact.do_not_contact` is the field the cross-module hook checks: spec
section 91 — "Sales AI asks: Can we contact this prospect? Compliance
checks: jurisdiction, data source, marketing basis, opt-out, suppression,
organization policy." `app.sales.service.send_outreach_message` is where
that check actually happens, and every Sequence/Campaign step reuses the
exact same function rather than a parallel send path.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

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
    # A manually-approved profile URL only — never scraped, never used to
    # drive automated login/connection-requests/messaging (spec's explicit
    # LinkedIn prohibitions). See app.sales.linkedin_task_service: the only
    # things this build ever does with it are store it, open it in a new
    # tab, and let a human draft a message that becomes a real core.Task.
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # An exact-email duplicate Contact is never legitimate (see
    # docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §10) — declared on the model
    # itself, not only as an Alembic migration op, so it's also present
    # when tests build the schema via Base.metadata.create_all().
    __table_args__ = (
        Index(
            "ix_sales_contacts_org_email_unique",
            "organization_id",
            func.lower(email),
            unique=True,
        ),
    )


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
    # spec §69 "Support Upsell Signal" chain step "Generate account brief"
    # — real retrieval-grounded text via the existing AI Copilot (same
    # pattern as Meeting Assistant's prep notes, app.sales.meetings), not
    # a canned template.
    ai_account_brief: Mapped[str | None] = mapped_column(String(4000), nullable=True)


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


class ICPProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One Ideal Customer Profile per organization (spec §20 "ICP
    Builder"). Saving a profile triggers `app.sales.icp.rescore_accounts`
    to recompute every Account's `icp_score` against it — see that
    module for the scoring formula."""

    __tablename__ = "sales_icp_profiles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, unique=True
    )
    # Empty list means "no industry preference" (full credit on that axis).
    target_industries: Mapped[list[str]] = mapped_column(JSON, default=list)
    min_employee_count: Mapped[int | None] = mapped_column(nullable=True)
    max_employee_count: Mapped[int | None] = mapped_column(nullable=True)


class Sequence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A multi-step outreach cadence (spec §23 "Sequences"/"Sequence
    Builder"). Steps live in `SequenceStep`; enrolled contacts advance
    through them via `SequenceEnrollment` — see
    app.sales.sequences.advance_due_enrollments."""

    __tablename__ = "sales_sequences"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    # active | paused
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class SequenceStep(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sales_sequence_steps"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    sequence_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_sequences.id"), nullable=False, index=True
    )
    order_index: Mapped[int] = mapped_column(nullable=False)
    # Days after the previous step fires (or after enrollment, for step 0)
    # before this step becomes due.
    wait_days: Mapped[int] = mapped_column(default=0)
    channel: Mapped[str] = mapped_column(String(20), default="email")  # email | linkedin
    subject_template: Mapped[str | None] = mapped_column(String(300), nullable=True)
    body_template: Mapped[str] = mapped_column(String(4000), nullable=False)


class SequenceEnrollment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sales_sequence_enrollments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    sequence_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_sequences.id"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_contacts.id"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_campaigns.id"), nullable=True, index=True
    )
    # active | completed | exited
    status: Mapped[str] = mapped_column(String(20), default="active")
    current_step_index: Mapped[int] = mapped_column(default=0)
    next_step_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Campaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named, tracked bulk-enrollment into one Sequence (spec §23
    "Campaigns"). Deliberately not a parallel messaging mechanism —
    launching a campaign enrolls its target contacts into `sequence_id`
    via the same `SequenceEnrollment` machinery Sequences already use, so
    the same compliance-gated send path (spec §91) applies to campaign
    sends too."""

    __tablename__ = "sales_campaigns"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    sequence_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_sequences.id"), nullable=False, index=True
    )
    # draft | active | completed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Meeting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """spec §26 "Meetings"/"Meeting Assistant". `prep_notes` is populated by
    a real retrieval-grounded AI Copilot call (`app.sales.meetings.
    generate_prep_notes`), not a canned template — see that module for
    the honest no-evidence fallback when the org's knowledge base has
    nothing relevant."""

    __tablename__ = "sales_meetings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_accounts.id"), nullable=True, index=True
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_opportunities.id"), nullable=True, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_contacts.id"), nullable=True, index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    prep_notes: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # scheduled | completed | no_show | cancelled
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
