"""Thin async Stripe REST client.

Deliberately not the official `stripe` package: it is synchronous, and
every call here happens inside an async request handler, so the SDK would
have to be thread-offloaded at every call site to avoid blocking the event
loop. Stripe's REST surface is form-encoded and small enough that `httpx`
— already a dependency for every other outbound call in this codebase —
is the simpler and more honest dependency.

Nothing here touches the database or decides policy. It makes calls and
translates failures; `app.billing.service` owns what those results mean.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx

from app.billing.exceptions import (
    StripeApiError,
    StripeNotConfigured,
    WebhookSignatureError,
)
from app.config import settings

logger = logging.getLogger(__name__)

STRIPE_API_BASE_URL = "https://api.stripe.com/v1"
# Pinned so a Stripe-side default upgrade cannot silently change response
# shapes underneath this code.
STRIPE_API_VERSION = "2024-06-20"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Stripe rejects webhook timestamps outside this window to blunt replay
# attacks; 5 minutes is Stripe's own documented default tolerance.
WEBHOOK_TOLERANCE_SECONDS = 300


def is_configured() -> bool:
    return bool(settings.stripe_secret_key)


def price_id_for_plan(plan_key: str) -> str | None:
    """The Stripe Price each self-serve paid plan maps to.

    Starter is trial-only and Enterprise is contract-only, so neither has
    a self-serve price — both correctly return None.
    """
    return {
        "growth": settings.stripe_price_growth,
        "business": settings.stripe_price_business,
    }.get(plan_key)


def _require_secret_key() -> str:
    if not settings.stripe_secret_key:
        raise StripeNotConfigured(
            "Payments are not configured on this deployment. "
            "Set STRIPE_SECRET_KEY to enable checkout."
        )
    return settings.stripe_secret_key


async def _request(method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    secret_key = _require_secret_key()
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Stripe-Version": STRIPE_API_VERSION,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.request(
                method, f"{STRIPE_API_BASE_URL}{path}", headers=headers, data=data
            )
    except httpx.HTTPError as exc:
        # The URL is safe to log; the Authorization header is not, and is
        # never part of the exception text we emit.
        logger.warning("Stripe request failed: %s %s (%s)", method, path, type(exc).__name__)
        raise StripeApiError("Could not reach the payment provider. Please try again.") from exc

    if response.status_code >= 400:
        # Stripe's own `message` is written for end users ("Your card was
        # declined."), so it is worth surfacing — but only the message,
        # never the whole payload.
        try:
            detail = response.json().get("error", {}).get("message")
        except ValueError:
            detail = None
        logger.warning("Stripe API error: %s %s -> %s", method, path, response.status_code)
        raise StripeApiError(
            detail or "The payment provider rejected this request.",
            status_code=response.status_code,
        )

    return dict(response.json())


async def create_customer(
    *, organization_id: str, organization_name: str, email: str
) -> dict[str, Any]:
    return await _request(
        "POST",
        "/customers",
        {
            "name": organization_name,
            "email": email,
            # Lets a Stripe-side operator trace any customer back to the
            # org without a database lookup, and lets webhook handling
            # recover the org if a subscription id is ever missing.
            "metadata[organization_id]": organization_id,
        },
    )


async def create_checkout_session(
    *,
    customer_id: str,
    price_id: str,
    organization_id: str,
    plan_key: str,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    """A subscription-mode Checkout Session with EU VAT handling on.

    `automatic_tax` makes Stripe Tax compute the right VAT rate for the
    customer's location, and `tax_id_collection` prompts business buyers
    for a VAT number — which is what lets Stripe apply B2B reverse charge
    instead of adding VAT. Both require the customer's address, hence
    `billing_address_collection=required` and `customer_update[address]`.
    """
    return await _request(
        "POST",
        "/checkout/sessions",
        {
            "mode": "subscription",
            "customer": customer_id,
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "billing_address_collection": "required",
            "automatic_tax[enabled]": "true",
            "tax_id_collection[enabled]": "true",
            "customer_update[address]": "auto",
            "customer_update[name]": "auto",
            # Echoed back on the completed event, so the webhook can
            # activate the right plan for the right org without trusting
            # anything the browser sends back.
            "metadata[organization_id]": organization_id,
            "metadata[plan_key]": plan_key,
            "subscription_data[metadata][organization_id]": organization_id,
            "subscription_data[metadata][plan_key]": plan_key,
        },
    )


async def create_billing_portal_session(*, customer_id: str, return_url: str) -> dict[str, Any]:
    """Stripe-hosted portal for updating a card, downloading invoices, or
    cancelling — all of which would otherwise be screens handling card
    data, and none of which need to exist here."""
    return await _request(
        "POST",
        "/billing_portal/sessions",
        {"customer": customer_id, "return_url": return_url},
    )


async def get_subscription(subscription_id: str) -> dict[str, Any]:
    return await _request("GET", f"/subscriptions/{subscription_id}")


async def cancel_subscription(subscription_id: str) -> dict[str, Any]:
    """Cancels at period end rather than immediately — the organization
    paid through that date and should keep what it paid for."""
    return await _request(
        "POST", f"/subscriptions/{subscription_id}", {"cancel_at_period_end": "true"}
    )


def verify_webhook_signature(*, payload: bytes, signature_header: str | None) -> dict[str, Any]:
    """Verify `Stripe-Signature` and return the parsed event.

    Implements Stripe's documented scheme directly: the header carries a
    timestamp `t` and one or more `v1` HMAC-SHA256 digests over
    `"{t}.{raw_body}"`, keyed by the endpoint's signing secret. The raw
    body matters — re-serialized JSON will not verify.

    This is the only thing standing between the internet and an endpoint
    that grants paid plans, so every failure path rejects rather than
    falls through.
    """
    if not settings.stripe_webhook_secret:
        raise StripeNotConfigured(
            "STRIPE_WEBHOOK_SECRET is not set — webhook events cannot be verified."
        )
    if not signature_header:
        raise WebhookSignatureError("Missing Stripe-Signature header")

    timestamp: str | None = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v1":
            signatures.append(value)

    if timestamp is None or not signatures:
        raise WebhookSignatureError("Malformed Stripe-Signature header")

    try:
        event_age = time.time() - int(timestamp)
    except ValueError as exc:
        raise WebhookSignatureError("Malformed Stripe-Signature timestamp") from exc
    if abs(event_age) > WEBHOOK_TOLERANCE_SECONDS:
        raise WebhookSignatureError("Stripe-Signature timestamp is outside the tolerance window")

    expected = hmac.new(
        settings.stripe_webhook_secret.encode("utf-8"),
        msg=f"{timestamp}.".encode() + payload,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # compare_digest, not ==, so a mismatch cannot be found one byte at a
    # time by timing the response.
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise WebhookSignatureError("Stripe-Signature verification failed")

    try:
        return dict(json.loads(payload))
    except ValueError as exc:
        raise WebhookSignatureError("Webhook payload was not valid JSON") from exc
