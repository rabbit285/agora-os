"""Security domain (spec sections 13-19 — Phase 4).

Named `secops`, not `security`, because `app/security.py` already exists
(password hashing / token helpers) — see docs/DECISIONS.md for the naming
note.

Consolidates the spec's parallel "vulnerabilities / cloud_findings /
identity_findings" concepts into one `SecurityFinding` with a `category`
discriminator rather than three near-identical tables (spec's own data
model lists them side by side with the same shape: asset, severity,
status, owner). `SecurityAlert` is the inbox/triage concept (spec §18);
`SecurityIncident` is the escalated workspace (spec §19), which is where
the explicit compliance link lives — spec §19: "Integrate incidents with
the GDPR breach process... This connection between security and
compliance is critical." It also carries the Phase 8 cross-module hook
(spec §69 "Security Incident" chain, ADR-0023): a critical incident
creates a response `core.Task` and notifies its owner — see
app.secops.service.create_incident.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SecurityAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "security_assets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    # cloud_account|server|container|endpoint|application|api|repository|saas|database|domain|user|privileged_account
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    environment: Mapped[str] = mapped_column(String(20), default="production")
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    criticality: Mapped[str] = mapped_column(
        String(10), default="medium"
    )  # low|medium|high|critical
    data_classification: Mapped[str] = mapped_column(String(20), default="internal")
    internet_exposed: Mapped[bool] = mapped_column(default=False)
    # healthy | at_risk | compromised
    status: Mapped[str] = mapped_column(String(20), default="healthy")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    last_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class SecurityFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "security_findings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("security_assets.id"), nullable=True, index=True
    )
    # vulnerability | cloud_misconfiguration | identity | other
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # low|medium|high|critical
    cve: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # open | investigating | resolved | false_positive | risk_accepted
    status: Mapped[str] = mapped_column(String(20), default="open")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SecurityAlert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "security_alerts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("security_findings.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # low|medium|high|critical
    # new | investigating | contained | resolved | false_positive
    status: Mapped[str] = mapped_column(String(20), default="new")


class SecurityIncident(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "security_incidents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # low|medium|high|critical
    # detected|triage|investigation|containment|eradication|recovery|postmortem|closed
    status: Mapped[str] = mapped_column(String(20), default="detected")
    # Cross-module link (spec §19): a critical incident creates/links a
    # Compliance Risk so the GDPR-breach-notification obligation is
    # tracked somewhere real, not just implied. See app.secops.service.
    related_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risks.id"), nullable=True
    )
    # Phase 8 cross-module hook (spec §69 "Security Incident" chain,
    # ADR-0023): a critical incident also creates a core.Task for the
    # response work, and (if owner_id is set) notifies the owner.
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
