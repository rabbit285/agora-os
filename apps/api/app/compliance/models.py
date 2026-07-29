"""Compliance domain (spec sections 12, 50 — Phase 3).

Follows the spec's core chain: Framework -> Requirement -> Control ->
Evidence / Assessment -> Risk. Frameworks and Requirements are global
catalog data (organization_id is nullable/absent, same pattern as system
Roles in app.core.rbac) since regulatory text doesn't vary per tenant;
everything an organization actually does — Control, ControlAssessment,
Evidence, Risk, Policy — is tenant-scoped.

Deliberately not modeled yet (see docs/KNOWN_LIMITATIONS.md): framework
versioning, evidence versioning, audits (auditor portal), regulatory
updates (external intelligence feed), RoPA/DPIA/DSAR (privacy-specific
workflows), vendor risk, questionnaires, Trust Center. Each is a
substantial feature in its own right; this slice ships the backbone they
would all attach to.

`AISystem` / `AIAssessment` add the spec §12 "AI System Inventory" / "AI
Risk Assessment" screens (EU AI Act governance). `AISystem.approval_id`
is the cross-module hook (spec §69 "New AI Tool Adoption": "... -> AI
risk assessment -> Approval -> Add to AI inventory -> ..."): registering
a `high` or `unacceptable`-risk system creates a real `core.Approval`,
and it cannot be moved to `approved` status until that Approval is
granted — see app.compliance.service.register_ai_system /
decide_ai_system_status and docs/DECISIONS.md ADR-0027.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Uuid

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
