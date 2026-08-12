from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.billing import stripe_client
from app.billing.models import Plan, Subscription
from app.billing.schemas import (
    BillingPortalOut,
    CheckoutRequest,
    CheckoutSessionOut,
    OrganizationPlanOut,
    PlanOut,
    SetPlanRequest,
    SubscriptionOut,
)
from app.billing.service import (
    count_active_members,
    create_billing_portal_url,
    create_checkout_session,
    get_entitlements,
    get_subscription,
    handle_stripe_event,
    request_plan_change,
    resolve_access_state,
)
from app.core.models import Organization
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(db: AsyncSession = Depends(get_db)) -> list[Plan]:
    """Public within an authenticated session (any active member can see
    what each tier includes, the same "show what upgrading gets you"
    transparency a real pricing page would have) — no special permission
    beyond being a member of some organization."""
    result = await db.execute(select(Plan).order_by(Plan.created_at))
    return list(result.scalars().all())


async def _plan_key(db: AsyncSession, organization_id: uuid.UUID) -> str:
    organization = await db.get(Organization, organization_id)
    assert organization is not None
    return organization.plan_key


def _subscription_out(subscription: Subscription | None) -> SubscriptionOut | None:
    if subscription is None:
        return None
    access_state = resolve_access_state(subscription)
    days_remaining: int | None = None
    if subscription.trial_ends_at is not None and access_state == "trialing":
        trial_ends_at = subscription.trial_ends_at
        if trial_ends_at.tzinfo is None:
            trial_ends_at = trial_ends_at.replace(tzinfo=UTC)
        days_remaining = max(0, (trial_ends_at - datetime.now(UTC)).days)
    return SubscriptionOut(
        status=subscription.status,
        access_state=access_state,
        plan_key=subscription.plan_key,
        trial_ends_at=subscription.trial_ends_at,
        trial_days_remaining=days_remaining,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        payments_configured=stripe_client.is_configured(),
        has_payment_method=bool(subscription.stripe_customer_id),
        tax_id=subscription.tax_id,
    )


async def _current_plan_response(
    db: AsyncSession, organization_id: uuid.UUID
) -> OrganizationPlanOut:
    entitlements = await get_entitlements(db, organization_id=organization_id)
    current_users = await count_active_members(db, organization_id=organization_id)
    subscription = await get_subscription(db, organization_id=organization_id)
    return OrganizationPlanOut(
        plan_key=await _plan_key(db, organization_id),
        entitlements=entitlements,
        current_users=current_users,
        subscription=_subscription_out(subscription),
    )


@router.get("/current", response_model=OrganizationPlanOut)
async def get_current_plan(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> OrganizationPlanOut:
    return await _current_plan_response(db, context.organization_id)


@router.put("/current", response_model=OrganizationPlanOut)
async def update_current_plan(
    payload: SetPlanRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> OrganizationPlanOut:
    """Downgrade to Starter. Upgrades do not happen here.

    This endpoint used to grant any plan for free — an org_admin could PUT
    `enterprise` and get it. Now `request_plan_change` refuses anything
    that costs money; Growth and Business are reachable only by completing
    a Stripe Checkout, and Enterprise only through sales.
    """
    before_plan = await _plan_key(db, context.organization_id)
    organization = await request_plan_change(
        db, organization_id=context.organization_id, plan_key=payload.plan_key
    )
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="billing.plan.changed",
        object_type="organization",
        object_id=str(organization.id),
        before_state={"plan_key": before_plan},
        after_state={"plan_key": organization.plan_key},
    )
    await db.commit()
    return await _current_plan_response(db, context.organization_id)


@router.post("/checkout", response_model=CheckoutSessionOut)
async def start_checkout(
    payload: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> CheckoutSessionOut:
    """Create a Stripe Checkout Session and hand back its URL.

    The plan is deliberately not changed here — see
    `app.billing.service.create_checkout_session`. Only the webhook
    activates a paid plan, so abandoning the payment form, or navigating
    straight to the success URL, grants nothing.
    """
    checkout_url = await create_checkout_session(
        db,
        organization_id=context.organization_id,
        plan_key=payload.plan_key,
        user_email=context.user.email,
    )
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="billing.checkout.started",
        object_type="organization",
        object_id=str(context.organization_id),
        after_state={"plan_key": payload.plan_key},
    )
    await db.commit()
    return CheckoutSessionOut(checkout_url=checkout_url)


@router.post("/portal", response_model=BillingPortalOut)
async def open_billing_portal(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("org.settings.manage")),
) -> BillingPortalOut:
    """Stripe-hosted portal for card updates, invoices, and cancellation.

    Using Stripe's portal rather than building these screens keeps card
    data off this system entirely, which is the whole reason Checkout was
    chosen over Elements.
    """
    portal_url = await create_billing_portal_url(db, organization_id=context.organization_id)
    return BillingPortalOut(portal_url=portal_url)


@router.post("/webhook", status_code=status.HTTP_200_OK, include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Stripe's callback — the only path that grants a paid plan.

    Unauthenticated by necessity (Stripe has no session), so the signature
    *is* the authentication: `verify_webhook_signature` HMACs the raw body
    against the endpoint secret and rejects anything stale or unsigned.
    The raw body is read here, before any parsing, because re-serialized
    JSON will not verify.
    """
    payload = await request.body()
    event = stripe_client.verify_webhook_signature(
        payload=payload, signature_header=stripe_signature
    )
    outcome = await handle_stripe_event(db, event)
    await db.commit()
    # Event type and outcome only — never the payload, which carries
    # customer names, addresses, and card metadata.
    logger.info("Stripe webhook %s -> %s", event.get("type"), outcome)
    return {"status": outcome}
