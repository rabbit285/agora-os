"""Sales domain services.

`send_outreach_message` ships the Phase 5 cross-module hook (spec
section 91: "Sales AI asks: Can we contact this prospect? Compliance
checks: jurisdiction, data source, marketing basis, opt-out, suppression,
organization policy"). The actual decision now lives in
`app.compliance.governance.check_contact_permission` (Compliance as
Governance Layer, spec §91) — this function calls out to it synchronously
rather than checking the suppression flag inline, so the "Sales asks
Compliance" relationship is an explicit, real function call, not
duplicated logic. No real email/LinkedIn provider is wired up (spec's
progressive trust model — connectors come later), so "sending" only ever
transitions this row's status; the compliance gate is real regardless.

`close_opportunity_won` ships the Phase 8 "New Customer" cross-module
hook (spec section 69: "CRM deal won -> create customer -> create
onboarding project -> send welcome email -> create support profile ->
provision internal tasks -> update billing integration -> assign account
owner -> schedule check-in"). The first time an Opportunity transitions
to `closed_won`, it creates a real `support.Customer` (the "create
customer" / "create support profile" steps — the same entity, not two)
and a `core.Task` due in 7 days (the "provision internal tasks" /
"schedule check-in" steps), reusing Phase 6's and Phase 1's existing
primitives rather than inventing new ones (ADR-0025). "Send welcome
email" and "update billing integration" are not implemented — no email
provider or accounting connector exists yet (see
docs/KNOWN_LIMITATIONS.md). `Opportunity.onboarding_customer_id` is both
the link and the idempotency guard: once set, a later closed_won
transition (e.g. reopened then re-won) is a genuine no-op, not a second
customer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.governance import check_contact_permission
from app.core.models import Task
from app.sales.models import Account, Contact, Opportunity, OutreachMessage
from app.support.models import Customer


async def send_outreach_message(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    message: OutreachMessage,
    contact: Contact,
    actor_user_id: uuid.UUID | None,
) -> OutreachMessage:
    decision = await check_contact_permission(db, organization_id=organization_id, contact=contact)
    if not decision.allowed:
        message.status = "blocked"
        message.blocked_reason = decision.reason
        policy_decision = "denied"
    else:
        message.status = "sent"
        message.sent_at = datetime.now(UTC)
        policy_decision = "allowed"

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="sales.outreach.send_attempted",
        object_type="outreach_message",
        object_id=str(message.id),
        policy_decision=policy_decision,
        after_state={"status": message.status, "blocked_reason": message.blocked_reason},
    )
    return message


async def close_opportunity_won(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    opportunity: Opportunity,
    account: Account,
    actor_user_id: uuid.UUID | None,
) -> Opportunity:
    if opportunity.onboarding_customer_id is not None:
        return opportunity  # already onboarded — idempotent no-op

    primary_contact = (
        await db.execute(
            select(Contact)
            .where(Contact.account_id == account.id)
            .order_by(Contact.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if primary_contact is None:
        # Honest partial-failure: the stage transition itself still
        # succeeds (handled by the caller); onboarding is skipped rather
        # than fabricating a customer with no real contact email.
        await record_event(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="sales.opportunity.onboarding_skipped",
            object_type="sales_opportunity",
            object_id=str(opportunity.id),
            policy_decision="denied",
            after_state={"reason": "no contact with an email exists for this account"},
        )
        return opportunity

    customer = Customer(
        organization_id=organization_id,
        sales_account_id=account.id,
        name=account.name,
        email=primary_contact.email,
        status="active",
    )
    db.add(customer)
    await db.flush()

    account.status = "customer"

    onboarding_task = Task(
        organization_id=organization_id,
        title=f"Onboard new customer: {account.name}",
        description=(
            f'Opportunity "{opportunity.title}" closed won. Schedule the customer '
            "check-in and confirm the onboarding project is underway."
        ),
        module="support",
        priority="high",
        assignee_id=account.owner_id,
        due_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(onboarding_task)
    await db.flush()

    opportunity.onboarding_customer_id = customer.id

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="sales.opportunity.closed_won",
        object_type="sales_opportunity",
        object_id=str(opportunity.id),
        after_state={
            "customer_id": str(customer.id),
            "onboarding_task_id": str(onboarding_task.id),
        },
    )
    return opportunity
