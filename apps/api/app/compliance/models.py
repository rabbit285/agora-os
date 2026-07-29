"""Compliance domain (spec sections 12, 50 — Phase 3).

Follows the spec's core chain: Framework -> Requirement -> Control ->
Evidence / Assessment -> Risk. Frameworks and Requirements are global
catalog data (organization_id is nullable/absent, same pattern as system
Roles in app.core.rbac) since regulatory text doesn't vary per tenant;
everything an organization actually does — Control, ControlAssessment,
Evidence, Risk, Policy — is tenant-scoped.

Deliberately not modeled yet (see docs/KNOWN_LIMITATIONS.md): framework
versioning, evidence versioning, audits (auditor portal), regulatory
updates (external intelligence feed), data transfers, vendor risk,
questionnaires, Trust Center. Each is a substantial feature in its own
right; this slice ships the backbone they would all attach to.

`AISystem` / `AIAssessment` add the spec §12 "AI System Inventory" / "AI
Risk Assessment" screens (EU AI Act governance). `AISystem.approval_id`
is the cross-module hook (spec §69 "New AI Tool Adoption": "... -> AI
risk assessment -> Approval -> Add to AI inventory -> ..."): registering
a `high` or `unacceptable`-risk system creates a real `core.Approval`,
and it cannot be moved to `approved` status until that Approval is
granted — see app.compliance.service.register_ai_system /
decide_ai_system_status and docs/DECISIONS.md ADR-0027.

`ProcessingActivity` / `DPIA` / `DSAR` add spec §12's Privacy sub-features
(Module 1 — AI Compliance explicitly lists "privacy operations, RoPA,
DPIAs, DSARs" alongside frameworks/controls, not as a separate module).
`DPIA.ai_system_id` extends the same "New AI Tool Adoption" hook a second
time: registering a high/unacceptable-risk AI system now also creates a
linked draft DPIA — the chain's "Privacy assessment" step (spec §69) —
see app.compliance.service.register_ai_system and docs/DECISIONS.md
ADR-0029. A `high`-risk-level DPIA created directly (not via that hook)
gets its own real `core.Approval`, gating `approved` the same way
`AISystem` does (GDPR Article 35: a DPIA concluding high residual risk
requires supervisory-authority consultation / formal sign-off before the
processing can proceed).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class Framework(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Catalog data: GDPR, EU AI Act, ISO 27001, etc. Seeded once,
    shared across every organization — never tenant-scoped."""

    __tablename__ = "frameworks"

    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class Requirement(UUIDPrimaryKeyMixin, Base):
    """Catalog data: one clause/article of a Framework. Global, like
    Framework — an organization's own response to it is a Control mapped
    via ControlMapping, not a copy of this row."""

    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint("framework_id", "reference_code", name="uq_requirement_framework_code"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("frameworks.id"), nullable=False, index=True
    )
    reference_code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class Control(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An organization's own implemented measure. May satisfy zero or more
    catalog Requirements (see ControlMapping)."""

    __tablename__ = "controls"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # not_started | in_progress | implemented | needs_review
    status: Mapped[str] = mapped_column(String(30), default="not_started")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ControlMapping(Base):
    __tablename__ = "control_mappings"

    control_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), primary_key=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("requirements.id"), primary_key=True
    )


class ControlAssessment(UUIDPrimaryKeyMixin, Base):
    """Point-in-time judgement of whether a Control is operating
    effectively. A `fail` assessment creates a remediation Task — see
    app.compliance.service.record_assessment and docs/DECISIONS.md."""

    __tablename__ = "control_assessments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    control_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=False, index=True
    )
    # pass | fail | partial | not_assessed
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    assessed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A stored artifact (reuses the Phase 1 File primitive — spec section
    80: shared platform primitives, not a duplicate storage path) that
    supports a Control, or stands alone in the evidence library."""

    __tablename__ = "evidence"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=True, index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Risk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "risks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="general")
    likelihood: Mapped[str] = mapped_column(String(10), nullable=False)  # low|medium|high
    impact: Mapped[str] = mapped_column(String(10), nullable=False)  # low|medium|high
    # open | mitigated | accepted
    status: Mapped[str] = mapped_column(String(20), default="open")
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Policy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "policies"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class AISystem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One entry in the AI System Inventory (spec §12/§55, EU AI Act
    governance). `risk_classification` follows the EU AI Act's own risk
    tiers rather than inventing a parallel scale."""

    __tablename__ = "ai_systems"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    purpose: Mapped[str] = mapped_column(String(2000), nullable=False)
    # minimal | limited | high | unacceptable (EU AI Act risk tiers)
    risk_classification: Mapped[str] = mapped_column(String(20), default="minimal")
    # in_review | approved | rejected | retired
    status: Mapped[str] = mapped_column(String(20), default="in_review")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Cross-module hook (spec §69 "New AI Tool Adoption") — set when
    # risk_classification is high/unacceptable. See
    # app.compliance.service.register_ai_system / decide_ai_system_status.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approvals.id"), nullable=True
    )


class AIAssessment(UUIDPrimaryKeyMixin, Base):
    """Point-in-time risk/impact assessment of an AISystem — mirrors
    ControlAssessment's shape deliberately (same judgement vocabulary)."""

    __tablename__ = "ai_assessments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    # pass | fail | partial | not_assessed
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    assessed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessingActivity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One entry in the Record of Processing Activities (RoPA, GDPR
    Article 30) — an organization's own catalog of what personal data it
    processes and why. Tenant-scoped, unlike Framework/Requirement's
    global catalog data: this is the organization's own record, not
    shared regulatory text."""

    __tablename__ = "processing_activities"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(String(2000), nullable=False)
    # consent | contract | legal_obligation | vital_interests | public_task | legitimate_interests
    # (GDPR Article 6's six lawful bases)
    legal_basis: Mapped[str] = mapped_column(String(30), nullable=False)
    data_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    data_subjects: Mapped[str] = mapped_column(String(300), nullable=False)
    retention_period: Mapped[str] = mapped_column(String(300), nullable=False)
    # active | archived
    status: Mapped[str] = mapped_column(String(20), default="active")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class DPIA(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Data Protection Impact Assessment (GDPR Article 35). May be
    conducted for an organization's own `ProcessingActivity`, created
    automatically for a high/unacceptable-risk `AISystem` (the "New AI
    Tool Adoption" chain's Privacy assessment step — see
    app.compliance.service.register_ai_system), or both."""

    __tablename__ = "dpias"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    processing_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processing_activities.id"), nullable=True, index=True
    )
    # Cross-module hook (spec §69 "New AI Tool Adoption" -> "Privacy assessment").
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # low | medium | high — DPIA's own concluded risk level, not necessarily
    # the same scale as AISystem.risk_classification
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    # draft | in_review | approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="draft")
    findings: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Set only when a `high`-risk-level DPIA is created directly (not via
    # the AISystem hook, which already has its own Approval) — see
    # app.compliance.service.create_dpia / decide_dpia_status.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approvals.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class DSAR(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Data Subject Access Request (GDPR Articles 15-20: access,
    rectification, erasure, portability). `due_at` defaults to 30 days
    from creation — GDPR Article 12(3)'s one-month response deadline."""

    __tablename__ = "dsars"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    requester_name: Mapped[str] = mapped_column(String(300), nullable=False)
    requester_email: Mapped[str] = mapped_column(String(320), nullable=False)
    # access | deletion | rectification | portability
    request_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # received | in_progress | fulfilled | rejected
    status: Mapped[str] = mapped_column(String(20), default="received")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
