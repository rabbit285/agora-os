"""Real entitlement service (spec §64: "Use entitlement service. Do not
hard-code plan checks across UI."). Every caller — API routers, other
services — resolves what an organization's current plan allows through
`get_entitlements`/`check_boolean_entitlement`/`check_numeric_limit`, never
by reading `Organization.plan_key` directly and branching on it inline.

Plan assignment is backed by real money. Growth and Business can only be
reached by completing a Stripe Checkout, and only a signature-verified
Stripe webhook activates them — the API cannot be talked into granting a
paid plan. Starter is a 14-day, no-card trial that locks premium
functionality when it lapses without ever destroying the organization or
its data. Enterprise is contract-only and is not self-serve at all.

The locking mechanism is deliberately expressed as entitlements rather
than a separate "is the account locked" flag threaded through every
router: a lapsed organization resolves to LOCKED_ENTITLEMENTS, so every
existing enforcement call site already blocks the right things with no
change, and read/export paths keep working — which is what makes
"preserve the organization and its data" true rather than aspirational.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import stripe_client
from app.billing.exceptions import PlanChangeNotAllowed, StripeNotConfigured
from app.billing.models import BillingWebhookEvent, Plan, Subscription
from app.config import settings
from app.core.models import Membership, Organization

logger = logging.getLogger(__name__)

# Plans a customer can buy without talking to anyone. Starter is the
# trial, Enterprise needs a signed agreement.
SELF_SERVE_PAID_PLANS = frozenset({"growth", "business"})

# spec §64's exact "Potential entitlements" list. `int` values are
# monthly/total limits (None means "unlimited" at that tier); `bool`
# values are feature flags.
ENTITLEMENT_KEYS = frozenset(
    {
        "max_users",
        "max_ai_usage_monthly",
        "max_documents",
        "max_storage_gb",
        "max_frameworks",
        "max_ai_systems",
        "max_security_connectors",
        "max_sales_leads",
        "max_outreach_volume_monthly",
        "max_support_conversations_monthly",
        "max_automation_runs_monthly",
        "max_integrations",
        "sso_enabled",
        "scim_enabled",
        "api_enabled",
        "custom_frameworks_enabled",
        "trust_center_enabled",
        "advanced_reporting_enabled",
        "data_residency_enabled",
    }
)

# spec §64's four named plans, seeded once (mirrors
# app.compliance.models.Framework's seeded-catalog pattern). Numeric
# limits step up per tier; boolean features unlock at the tier spec's own
# ordering implies (SSO/API at Growth+, SCIM/advanced reporting/data
# residency at Enterprise only — a defensible, disclosed judgment call
# since spec doesn't spell out the exact per-tier cutoffs).
PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "starter": {
        "name": "Starter",
        "entitlements": {
            "max_users": 5,
            "max_ai_usage_monthly": 100,
            "max_documents": 100,
            "max_storage_gb": 5,
            "max_frameworks": 1,
            "max_ai_systems": 5,
            "max_security_connectors": 1,
            "max_sales_leads": 100,
            "max_outreach_volume_monthly": 200,
            "max_support_conversations_monthly": 100,
            "max_automation_runs_monthly": 100,
            "max_integrations": 2,
            "sso_enabled": False,
            "scim_enabled": False,
            "api_enabled": False,
            "custom_frameworks_enabled": False,
            "trust_center_enabled": False,
            "advanced_reporting_enabled": False,
            "data_residency_enabled": False,
        },
    },
    "growth": {
        "name": "Growth",
        "entitlements": {
            "max_users": 25,
            "max_ai_usage_monthly": 1000,
            "max_documents": 1000,
            "max_storage_gb": 50,
            "max_frameworks": 3,
            "max_ai_systems": 25,
            "max_security_connectors": 3,
            "max_sales_leads": 1000,
            "max_outreach_volume_monthly": 2000,
            "max_support_conversations_monthly": 1000,
            "max_automation_runs_monthly": 1000,
            "max_integrations": 5,
            "sso_enabled": True,
            "scim_enabled": False,
            "api_enabled": True,
            "custom_frameworks_enabled": False,
            "trust_center_enabled": True,
            "advanced_reporting_enabled": False,
            "data_residency_enabled": False,
        },
    },
    "business": {
        "name": "Business",
        "entitlements": {
            "max_users": 100,
            "max_ai_usage_monthly": 10000,
            "max_documents": 10000,
            "max_storage_gb": 500,
            "max_frameworks": 8,
            "max_ai_systems": 100,
            "max_security_connectors": 7,
            "max_sales_leads": 10000,
            "max_outreach_volume_monthly": 20000,
            "max_support_conversations_monthly": 10000,
            "max_automation_runs_monthly": 10000,
            "max_integrations": 7,
            "sso_enabled": True,
            "scim_enabled": True,
            "api_enabled": True,
            "custom_frameworks_enabled": True,
            "trust_center_enabled": True,
            "advanced_reporting_enabled": True,
            "data_residency_enabled": False,
        },
    },
    "enterprise": {
        "name": "Enterprise",
        "entitlements": {
            "max_users": None,
            "max_ai_usage_monthly": None,
            "max_documents": None,
            "max_storage_gb": None,
            "max_frameworks": None,
            "max_ai_systems": None,
            "max_security_connectors": None,
            "max_sales_leads": None,
            "max_outreach_volume_monthly": None,
            "max_support_conversations_monthly": None,
            "max_automation_runs_monthly": None,
            "max_integrations": None,
            "sso_enabled": True,
            "scim_enabled": True,
            "api_enabled": True,
            "custom_frameworks_enabled": True,
            "trust_center_enabled": True,
            "advanced_reporting_enabled": True,
            "data_residency_enabled": True,
        },
    },
}


# What an organization keeps after its trial lapses or its subscription is
# cancelled. Every numeric limit is 0 and every feature flag is False.
#
# This alone does NOT lock the product: only two call sites in the whole
# codebase consult entitlements (invitation creation and SSO login), so
# zeroing these values would leave a "locked" org still able to create
# documents, workflows, and everything else. The actual lock is enforced
# centrally in `app.dependencies._enforce_subscription_lock`, which blocks
# mutating requests; these values are what the UI reads to grey the right
# things out, and what the two existing checks see.
#
# Reads are untouched by both mechanisms. Nothing is deleted and nothing
# stops an existing member logging in, reading what they built, or
# exporting it — locking a customer out of their own records because an
# invoice lapsed would be a data-hostage pattern, and for EU customers it
# would also collide with their right to their data.
LOCKED_ENTITLEMENTS: dict[str, Any] = {
    key: (False if key.endswith("_enabled") else 0) for key in sorted(ENTITLEMENT_KEYS)
}


async def ensure_plan_catalog(db: AsyncSession) -> None:
    """Idempotently seed the 4 plans — safe to call on every startup, the
    same convention `app.core.rbac.ensure_system_roles` established."""
    for key, spec in PLAN_CATALOG.items():
        existing = (await db.execute(select(Plan).where(Plan.key == key))).scalar_one_or_none()
        if existing is None:
            db.add(Plan(key=key, name=spec["name"], entitlements=spec["entitlements"]))
        else:
            # Keep seeded entitlement values in sync with this catalog on
            # every boot — the same "additive/refreshing" idempotency
            # ensure_system_roles uses, so a later change to
            # PLAN_CATALOG reaches already-seeded plans without a
            # migration.
            existing.name = spec["name"]
            existing.entitlements = spec["entitlements"]
    await db.commit()


async def get_plan(db: AsyncSession, plan_key: str) -> Plan:
    plan = (await db.execute(select(Plan).where(Plan.key == plan_key))).scalar_one_or_none()
    if plan is None:
        raise LookupError(f"Plan '{plan_key}' has not been seeded — call ensure_plan_catalog()")
    return plan


async def get_subscription(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> Subscription | None:
    result = await db.execute(
        select(Subscription).where(Subscription.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


async def start_trial(db: AsyncSession, *, organization_id: uuid.UUID) -> Subscription:
    """Called once, at signup. No card, no Stripe customer, no network
    call — an organization that never converts never touches Stripe."""
    existing = await get_subscription(db, organization_id=organization_id)
    if existing is not None:
        return existing
    subscription = Subscription(
        organization_id=organization_id,
        status="trialing",
        plan_key="starter",
        trial_ends_at=datetime.now(UTC) + timedelta(days=settings.trial_period_days),
    )
    db.add(subscription)
    return subscription


def is_trial_expired(subscription: Subscription) -> bool:
    if subscription.status != "trialing" or subscription.trial_ends_at is None:
        return False
    trial_ends_at = subscription.trial_ends_at
    # Postgres hands these back tz-aware, SQLite does not; normalize so
    # the comparison cannot raise on either backend.
    if trial_ends_at.tzinfo is None:
        trial_ends_at = trial_ends_at.replace(tzinfo=UTC)
    return datetime.now(UTC) >= trial_ends_at


def resolve_access_state(subscription: Subscription | None) -> str:
    """The single definition of whether an org is entitled to its plan.

    Trial expiry is evaluated here from `trial_ends_at` rather than by a
    scheduled job flipping statuses, so an expired trial is locked the
    moment it expires even if no worker ran — a cron that didn't fire
    must not silently hand out free access.
    """
    if subscription is None:
        # Pre-billing organizations, created before subscriptions existed.
        # Treated as entitled: retroactively locking paying-era customers
        # out on deploy would be the wrong failure direction.
        return "active"
    if is_trial_expired(subscription):
        return "locked"
    if subscription.status in {"trial_expired", "canceled"}:
        return "locked"
    # past_due stays unlocked on purpose: Stripe retries a failed payment
    # for days, and killing access on the first decline punishes customers
    # for an expiring card.
    return subscription.status


async def get_entitlements(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, Any]:
    organization = await db.get(Organization, organization_id)
    assert organization is not None
    subscription = await get_subscription(db, organization_id=organization_id)
    if resolve_access_state(subscription) == "locked":
        return dict(LOCKED_ENTITLEMENTS)
    plan = await get_plan(db, organization.plan_key)
    return dict(plan.entitlements)


async def check_boolean_entitlement(
    db: AsyncSession, *, organization_id: uuid.UUID, key: str
) -> bool:
    entitlements = await get_entitlements(db, organization_id=organization_id)
    return bool(entitlements.get(key, False))


async def require_boolean_entitlement(
    db: AsyncSession, *, organization_id: uuid.UUID, key: str, feature_name: str
) -> None:
    if not await check_boolean_entitlement(db, organization_id=organization_id, key=key):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{feature_name} is not included in this organization's current plan",
        )


async def require_numeric_capacity(
    db: AsyncSession, *, organization_id: uuid.UUID, key: str, current_usage: int, feature_name: str
) -> None:
    """`limit is None` means unlimited at this tier (Enterprise)."""
    entitlements = await get_entitlements(db, organization_id=organization_id)
    limit = entitlements.get(key)
    if limit is not None and current_usage >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{feature_name} limit reached for this organization's current plan "
            f"({current_usage}/{limit})",
        )


async def count_active_members(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(
            select(Membership.id)
            .where(Membership.organization_id == organization_id, Membership.status == "active")
            .subquery()
        )
    )
    return int(result.scalar_one())


async def set_organization_plan(
    db: AsyncSession, *, organization_id: uuid.UUID, plan_key: str
) -> Organization:
    """Move an org to a plan. Internal — callers are the Stripe webhook
    and the downgrade path, both of which have already established that
    the change is paid for or free. Never call this straight from a
    request handler; `request_plan_change` is the guarded entry point."""
    if plan_key not in PLAN_CATALOG:
        raise ValueError(f"Unknown plan: {plan_key}")
    organization = await db.get(Organization, organization_id)
    assert organization is not None
    organization.plan_key = plan_key
    return organization


async def request_plan_change(
    db: AsyncSession, *, organization_id: uuid.UUID, plan_key: str
) -> Organization:
    """The only plan change a request handler may perform directly, and it
    is a downgrade to Starter.

    Before billing existed, an org_admin could PUT any plan_key and get
    Enterprise for free. That endpoint still exists for downgrades, so the
    guard lives here rather than in the router — anything reaching for a
    paid tier has to go through money instead.
    """
    if plan_key not in PLAN_CATALOG:
        raise ValueError(f"Unknown plan: {plan_key}")
    if plan_key in SELF_SERVE_PAID_PLANS:
        raise PlanChangeNotAllowed(
            f"{PLAN_CATALOG[plan_key]['name']} requires payment. "
            "Start a checkout session to subscribe."
        )
    if plan_key == "enterprise":
        raise PlanChangeNotAllowed(
            "Enterprise is arranged with our sales team and cannot be self-assigned."
        )

    # Downgrading to Starter. If they are paying, stop the renewal at the
    # end of the period they already bought rather than cutting it short.
    subscription = await get_subscription(db, organization_id=organization_id)
    if subscription is not None and subscription.stripe_subscription_id:
        if stripe_client.is_configured():
            await stripe_client.cancel_subscription(subscription.stripe_subscription_id)
        subscription.cancel_at_period_end = True
    if subscription is not None:
        subscription.plan_key = "starter"
        # A former paying customer moving to Starter is not put back on a
        # second free trial.
        if subscription.status == "trialing" and is_trial_expired(subscription):
            subscription.status = "trial_expired"

    return await set_organization_plan(db, organization_id=organization_id, plan_key="starter")


async def create_checkout_session(
    db: AsyncSession, *, organization_id: uuid.UUID, plan_key: str, user_email: str
) -> str:
    """Start a Stripe Checkout for a self-serve paid plan; returns the URL
    to redirect the browser to.

    Nothing about the organization's plan changes here. The plan is
    granted only when Stripe tells us the money moved (see
    `handle_stripe_event`) — a user who reaches the success URL by typing
    it, or abandons the payment form, gets nothing.
    """
    if plan_key not in SELF_SERVE_PAID_PLANS:
        raise PlanChangeNotAllowed(
            "Only the Growth and Business plans can be purchased online. "
            "Starter is a free trial and Enterprise is arranged with sales."
        )
    price_id = stripe_client.price_id_for_plan(plan_key)
    if not price_id:
        raise StripeNotConfigured(
            f"No Stripe price is configured for the {plan_key} plan "
            f"(set STRIPE_PRICE_{plan_key.upper()})."
        )

    organization = await db.get(Organization, organization_id)
    assert organization is not None
    subscription = await get_subscription(db, organization_id=organization_id)
    if subscription is None:
        subscription = await start_trial(db, organization_id=organization_id)
        await db.flush()

    if not subscription.stripe_customer_id:
        customer = await stripe_client.create_customer(
            organization_id=str(organization_id),
            organization_name=organization.name,
            email=user_email,
        )
        subscription.stripe_customer_id = str(customer["id"])
        # Committed before Checkout so a failure mid-flow cannot leave us
        # creating a second Stripe customer for the same organization on
        # the next attempt.
        await db.commit()

    session = await stripe_client.create_checkout_session(
        customer_id=subscription.stripe_customer_id,
        price_id=price_id,
        organization_id=str(organization_id),
        plan_key=plan_key,
        success_url=f"{settings.app_url}/settings/billing?checkout=success",
        cancel_url=f"{settings.app_url}/settings/billing?checkout=cancelled",
    )
    return str(session["url"])


async def create_billing_portal_url(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> str:
    subscription = await get_subscription(db, organization_id=organization_id)
    if subscription is None or not subscription.stripe_customer_id:
        raise PlanChangeNotAllowed(
            "This organization has no payment method on file yet."
        )
    session = await stripe_client.create_billing_portal_session(
        customer_id=subscription.stripe_customer_id,
        return_url=f"{settings.app_url}/settings/billing",
    )
    return str(session["url"])


def _period_end_from(raw: Any) -> datetime | None:
    if not isinstance(raw, int):
        return None
    return datetime.fromtimestamp(raw, tz=UTC)


async def handle_stripe_event(db: AsyncSession, event: dict[str, Any]) -> str:
    """Apply one verified Stripe event. Returns a short outcome string for
    logging. The caller has already checked the signature.

    Idempotent by event id: Stripe retries on any non-2xx and can deliver
    the same event twice regardless, so a replay must not extend a period
    or re-grant a plan.
    """
    event_id = str(event.get("id", ""))
    event_type = str(event.get("type", ""))
    if not event_id:
        return "ignored: no event id"

    already_seen = await db.execute(
        select(BillingWebhookEvent.id).where(BillingWebhookEvent.stripe_event_id == event_id)
    )
    if already_seen.scalar_one_or_none() is not None:
        return "duplicate"
    db.add(BillingWebhookEvent(stripe_event_id=event_id, event_type=event_type))

    obj = event.get("data", {}).get("object", {})
    if not isinstance(obj, dict):
        return "ignored: unexpected payload"

    metadata = obj.get("metadata") or {}
    organization_id: uuid.UUID | None = None
    raw_org_id = metadata.get("organization_id")
    if raw_org_id:
        try:
            organization_id = uuid.UUID(str(raw_org_id))
        except ValueError:
            organization_id = None

    subscription: Subscription | None = None
    if organization_id is not None:
        subscription = await get_subscription(db, organization_id=organization_id)
    if subscription is None:
        # Fall back to the Stripe ids, which cover events that carry no
        # metadata of their own (invoice.* in particular).
        stripe_subscription_id = obj.get("subscription") or (
            obj.get("id") if obj.get("object") == "subscription" else None
        )
        lookup = None
        if stripe_subscription_id:
            lookup = await db.execute(
                select(Subscription).where(
                    Subscription.stripe_subscription_id == str(stripe_subscription_id)
                )
            )
        elif obj.get("customer"):
            lookup = await db.execute(
                select(Subscription).where(
                    Subscription.stripe_customer_id == str(obj["customer"])
                )
            )
        subscription = lookup.scalar_one_or_none() if lookup is not None else None

    if subscription is None:
        # Recorded as seen so Stripe stops retrying something we can never
        # match, but nothing is granted.
        logger.warning("Stripe event %s (%s) matched no organization", event_id, event_type)
        return "unmatched"

    if event_type == "checkout.session.completed":
        plan_key = str(metadata.get("plan_key") or subscription.plan_key)
        if plan_key not in SELF_SERVE_PAID_PLANS:
            logger.warning("Checkout completed for non-self-serve plan %s", plan_key)
            return "ignored: unexpected plan"
        if obj.get("subscription"):
            subscription.stripe_subscription_id = str(obj["subscription"])
        subscription.status = "active"
        subscription.plan_key = plan_key
        # The trial is over the moment they pay — it must not linger and
        # later lock a paying customer out.
        subscription.trial_ends_at = None
        subscription.cancel_at_period_end = False
        _apply_tax_ids(subscription, obj)
        await set_organization_plan(
            db, organization_id=subscription.organization_id, plan_key=plan_key
        )
        return f"activated:{plan_key}"

    if event_type in {"customer.subscription.updated", "customer.subscription.created"}:
        subscription.current_period_end = _period_end_from(obj.get("current_period_end"))
        subscription.cancel_at_period_end = bool(obj.get("cancel_at_period_end"))
        stripe_status = str(obj.get("status", ""))
        if stripe_status in {"active", "trialing"}:
            subscription.status = "active"
        elif stripe_status in {"past_due", "unpaid"}:
            subscription.status = "past_due"
        elif stripe_status == "canceled":
            subscription.status = "canceled"
            await set_organization_plan(
                db, organization_id=subscription.organization_id, plan_key="starter"
            )
        return f"subscription:{stripe_status or 'unknown'}"

    if event_type == "customer.subscription.deleted":
        subscription.status = "canceled"
        subscription.stripe_subscription_id = None
        # Entitlements resolve to locked from here (resolve_access_state);
        # the org and its data stay exactly where they are.
        await set_organization_plan(
            db, organization_id=subscription.organization_id, plan_key="starter"
        )
        return "canceled"

    if event_type == "invoice.payment_failed":
        subscription.status = "past_due"
        return "past_due"

    if event_type == "invoice.payment_succeeded":
        if subscription.status == "past_due":
            subscription.status = "active"
        subscription.current_period_end = _period_end_from(obj.get("period_end"))
        return "paid"

    return f"ignored:{event_type}"


def _apply_tax_ids(subscription: Subscription, session: dict[str, Any]) -> None:
    """Record the VAT number Stripe collected, for display on the billing
    page. Stripe itself decides whether reverse charge applied — this is
    never used to compute tax."""
    details = session.get("customer_details") or {}
    tax_ids = details.get("tax_ids") or []
    if tax_ids and isinstance(tax_ids, list) and isinstance(tax_ids[0], dict):
        subscription.tax_id = str(tax_ids[0].get("value") or "") or None
    country = details.get("address", {}).get("country") if details.get("address") else None
    if country:
        subscription.tax_id_country = str(country)[:2]
