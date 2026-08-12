from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PlanOut(BaseModel):
    key: str
    name: str
    entitlements: dict[str, Any]

    model_config = {"from_attributes": True}


class SubscriptionOut(BaseModel):
    """Billing state, separate from entitlements so the UI can explain
    *why* something is unavailable rather than just showing it greyed."""

    status: str
    # "trialing" | "active" | "past_due" | "locked" — what the entitlement
    # service actually resolved, which is not always `status` (an expired
    # trial still reads `trialing` in the row until a write touches it).
    access_state: str
    plan_key: str
    trial_ends_at: datetime | None = None
    trial_days_remaining: int | None = None
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False
    # Whether this deployment can actually take a payment. False means the
    # upgrade buttons must say so instead of leading to a dead end.
    payments_configured: bool = False
    has_payment_method: bool = False
    tax_id: str | None = None


class OrganizationPlanOut(BaseModel):
    plan_key: str
    entitlements: dict[str, Any]
    current_users: int
    subscription: SubscriptionOut | None = None


class SetPlanRequest(BaseModel):
    plan_key: str = Field(pattern="^(starter|growth|business|enterprise)$")


class CheckoutRequest(BaseModel):
    # Only the two self-serve paid plans are accepted at the schema layer;
    # the service re-checks, since a schema is a convenience and not a
    # security boundary.
    plan_key: str = Field(pattern="^(growth|business)$")


class CheckoutSessionOut(BaseModel):
    checkout_url: str


class BillingPortalOut(BaseModel):
    portal_url: str
