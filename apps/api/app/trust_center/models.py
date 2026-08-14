"""Trust Center domain (spec section B4 — Phase 3 extension).

A deliberately separate module from `app.compliance`, unlike Vendor Risk,
Security Questionnaires, and Audits (all added directly to
`app.compliance.models`): the Trust Center's defining feature is a
genuinely public, unauthenticated surface (spec B4: "a public and
customer-facing Trust Center"), a fundamentally different security model
from every other Compliance sub-feature, which are all tenant-scoped and
require a session. See app.routers.trust_center for the public
`GET /api/v1/trust-center/public/{org_slug}` route (no `OrgContext`
dependency — the same "no session, a different capability boundary"
pattern already established by the Phase 9 webhook receiver and OAuth
callback, ADR-0024) alongside the authenticated management endpoints.

`TrustCenterItem.category` follows spec B4's own fixed bullet list
(security overview, privacy overview, subprocessors, ...) rather than a
freeform tag, and `status` follows spec B4's own five-value vocabulary
(planned/in_progress/implemented/independently_assessed/certified) —
critically, spec B4 says "Do not falsely claim certifications that have
not been earned," so this status is never auto-advanced; only a human
sets it. `TrustCenterItem.policy_id` is an optional link to an existing
`compliance.Policy` — the "downloadable approved documents" spec B4
asks for reuse the existing Policy/File primitives rather than a second
document-storage path (spec §80), and only a `published` Policy is ever
actually surfaced publicly, even if the item itself is `is_public`.

`EvidenceRequest` backs spec B4's "evidence request workflow" — a public,
unauthenticated submission from a prospective customer, which
automatically creates a `core.Task` for the org to act on (see
app.trust_center.service.create_evidence_request), the same
"submission creates a tracked consequence" hook shape used across this
build (spec §80), here applied to a request with no authenticated actor.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# spec B4's exact bullet list.
TRUST_CENTER_CATEGORIES = (
    "security_overview",
    "privacy_overview",
    "subprocessors",
    "data_locations",
    "encryption_practices",
    "availability",
    "vulnerability_reporting",
    "compliance_roadmap",
    "dpa_availability",
    "incident_communication",
    "responsible_ai",
    "ai_provider_disclosures",
    "retention_deletion",
    "business_continuity",
)


class TrustCenterItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "trust_center_items"
    __table_args__ = (
        UniqueConstraint("organization_id", "category", name="uq_trust_center_item_org_category"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # planned | in_progress | implemented | independently_assessed | certified
    #
    # The top two are claims about what a third party concluded, not about
    # what we built, and they are the only statements on this page a buyer
    # cannot verify for themselves. Publishing "ISO 27001 certified"
    # without a certificate is the single most damaging thing this product
    # could do for a customer, so those two states require an attestation
    # document and a named person — see app.trust_center.service.
    status: Mapped[str] = mapped_column(String(30), default="planned")
    # The certificate or audit report behind an `independently_assessed`
    # or `certified` claim.
    attestation_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    attestation_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    attested_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    attested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_public: Mapped[bool] = mapped_column(default=False)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("policies.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class EvidenceRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A public, unauthenticated request for compliance/security evidence
    (spec B4's "evidence request workflow"). Always creates a linked
    `core.Task` — see app.trust_center.service.create_evidence_request."""

    __tablename__ = "trust_center_evidence_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    requester_name: Mapped[str] = mapped_column(String(300), nullable=False)
    requester_email: Mapped[str] = mapped_column(String(320), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # open | fulfilled
    status: Mapped[str] = mapped_column(String(20), default="open")
    # Cross-module hook: set on creation.
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
