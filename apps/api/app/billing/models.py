"""Billing (spec §64). The section header itself carries the spec's own
"architecture" qualifier ("Plans architecture:") — real payment
collection (Stripe checkout, invoicing) is out of scope, disclosed in
docs/KNOWN_LIMITATIONS.md. What the rest of the section explicitly does
demand as real ("Use entitlement service. Do not hard-code plan checks
across UI.") is built: `Plan` is a real, seeded, org-wide catalog (four
rows: Starter/Growth/Business/Enterprise, mirroring how
`app.compliance.models.Framework` is seeded catalog data), each carrying
real entitlement values `app.billing.service` resolves and enforces —
never a UI-scattered `if organization.plan_key == "..."` check.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plans"

    key: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # spec §64's full "Potential entitlements" list, keyed exactly as
    # named there (see app.billing.service.ENTITLEMENT_KEYS for the
    # canonical key set and which ones are real numeric limits vs.
    # booleans).
    entitlements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
