"""AI Recommendation Engine (spec §87). A `Recommendation` row is a real,
computed artifact — its `sources` field names the exact rows (a Control,
a SecurityFinding, an Account...) that produced it, never an invented
suggestion with no data behind it. `source_key` is a stable per-category
dedup key (e.g. "compliance_gaps") so re-running the generator refreshes
an existing still-active recommendation's content instead of spamming a
duplicate, and never resurrects one the user already dismissed or acted
on (see app.recommendations.service.refresh_recommendations).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Recommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_key", name="uq_recommendation_org_source"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # Stable dedup key per generator, e.g. "compliance_gaps",
    # "security_critical_findings", "sales_icp_no_lead",
    # "automation_failures", "support_satisfaction".
    source_key: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    business_impact: Mapped[str] = mapped_column(String(1000), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Each entry names a real row this recommendation was computed from,
    # e.g. "control:<uuid>" — never a fabricated citation.
    sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)  # low|medium|high
    estimated_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    suggested_action: Mapped[str] = mapped_column(String(500), nullable=False)
    risk: Mapped[str] = mapped_column(String(10), nullable=False)  # low|medium|high
    required_approval: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="new")  # new|dismissed|actioned
