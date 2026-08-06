"""Public-site demo requests (docs/PUBLIC_SITE_DESIGN.md §6). Deliberately
not part of `app.sales` — every Sales model is `organization_id`-scoped by
design (a tenant's own pipeline); a demo requester has no organization
yet, so this is a genuinely different shape, not a convenience reuse.
"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DemoRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "demo_requests"

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    work_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_size: Mapped[str] = mapped_column(String(20), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    primary_interest: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # No workflow beyond "someone at Agora followed up" exists yet — see
    # docs/KNOWN_LIMITATIONS.md. A plain string, not an enum, since the
    # real follow-up process this should track isn't defined yet either.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
