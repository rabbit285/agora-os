"""Billing (spec §64). `Plan` is a real, seeded, org-wide catalog (four
rows: Starter/Growth/Business/Enterprise, mirroring how
`app.compliance.models.Framework` is seeded catalog data), each carrying
real entitlement values `app.billing.service` resolves and enforces —
never a UI-scattered `if organization.plan_key == "..."` check.

`Subscription` adds the payment state that plan alone cannot express:
whether an organization is in its Starter trial, has actually paid for
Growth/Business through Stripe Checkout, or has lapsed and should be
locked out of premium functionality. It is deliberately a separate row
rather than more columns on `Organization`, because its lifecycle is
driven by an external system (Stripe webhooks) on a different clock than
anything else about the org.

`Organization.plan_key` stays the single source of entitlement truth so
every existing caller of the entitlement service keeps working untouched.
This module never writes it directly — `app.billing.service` does, and
only in response to a verified Stripe event or a real downgrade.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String
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


# The states a subscription can hold. `trialing` and `active` are the only
# two that grant the plan's entitlements; everything else resolves to the
# locked entitlement set in app.billing.service.
SUBSCRIPTION_STATUSES = frozenset(
    {
        "trialing",  # Starter only, 14 days, no card taken
        "active",  # paid and current, or an Enterprise contract set by staff
        "past_due",  # Stripe could not collect; still unlocked during retries
        "trial_expired",  # trial ran out without conversion -> locked
        "canceled",  # subscription ended -> locked
    }
)


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per organization, created at signup with the Starter trial."""

    __tablename__ = "subscriptions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="trialing")
    # The plan this subscription pays for. Kept alongside
    # Organization.plan_key rather than replacing it: plan_key is the
    # *effective* entitlement level (and drops to locked when this
    # subscription lapses), while this records what was actually bought.
    plan_key: Mapped[str] = mapped_column(String(20), nullable=False, default="starter")
    # Null for paid plans — only the Starter trial has an expiry that
    # locks the account rather than a renewal that bills it.
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Stripe's identifiers. Null until the org first goes through Checkout;
    # an org that trials and never converts never gets a Stripe record at
    # all, which is also why no card is required to start.
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    # Collected by Stripe Checkout's tax_id_collection for B2B reverse
    # charge. Stored for display only — Stripe remains the authority on
    # whether reverse charge actually applied to a given invoice.
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tax_id_country: Mapped[str | None] = mapped_column(String(2), nullable=True)


class BillingWebhookEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stripe delivers at-least-once and retries on any non-2xx, so the
    same event id can and will arrive more than once. Recording ids in a
    uniquely-indexed table makes replay a no-op instead of, say, extending
    a billing period twice."""

    __tablename__ = "billing_webhook_events"

    stripe_event_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
