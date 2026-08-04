"""AI Daily Briefing (spec §88). One real `Briefing` row per
organization per calendar day — "daily" means generated once and held
stable for the rest of that day, not recomputed on every page load the
way `app.recommendations` is. `sections` holds the 5 spec-named
sections (Urgent/Revenue/Customers/Risk/Operations), each item real and
clickable (`link`), never the spec's own literal example numbers.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Briefing(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "briefings"
    __table_args__ = (
        UniqueConstraint("organization_id", "briefing_date", name="uq_briefing_org_date"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    briefing_date: Mapped[date] = mapped_column(Date, nullable=False)
    # [{key, label, headline, items: [{text, link}]}] — see
    # app.briefing.schemas.BriefingSectionOut for the validated shape.
    sections: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    ai_suggestion: Mapped[str | None] = mapped_column(String(500), nullable=True)
