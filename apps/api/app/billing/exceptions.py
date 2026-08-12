"""Billing failures that must reach the browser as something actionable.

Same lesson as `app.ai.exceptions`: an unhandled exception inside a
route produces a bare 500 that has already passed CORSMiddleware, so the
browser reports an opaque "Failed to fetch" and the user is left staring
at a checkout button that did nothing. Every Stripe call site raises one
of these instead, and `app.main` maps them to real status codes.
"""

from __future__ import annotations


class BillingError(Exception):
    """Base for every billing failure that should not surface as a 500."""


class StripeNotConfigured(BillingError):
    """No STRIPE_SECRET_KEY, or no price id for the requested plan.

    Deliberately never falls back to pretending the purchase succeeded —
    the same rule the integrations catalog follows (spec §82: never a fake
    "connected" state).
    """


class StripeApiError(BillingError):
    """Stripe rejected the call or was unreachable.

    `message` is safe to show a user; raw Stripe payloads are not
    forwarded, so an internal detail cannot leak through the API.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class WebhookSignatureError(BillingError):
    """The Stripe-Signature header was missing, malformed, stale, or did
    not verify. Always a 400 — never processed, never retried into."""


class PlanChangeNotAllowed(BillingError):
    """A plan transition that must not happen without money or a contract.

    Growth and Business require a completed Stripe Checkout; Enterprise
    requires a signed agreement. Neither can be granted by asking the API
    nicely, which is exactly what the pre-billing build allowed.
    """
