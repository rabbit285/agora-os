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

`close_opportunity_won` ships all 8 steps of the "New Customer"
cross-module hook (spec section 69: "CRM deal won -> create customer ->
create onboarding project -> send welcome email -> create support
profile -> provision internal tasks -> update billing integration ->
assign account owner -> schedule check-in"). The first time an
Opportunity transitions to `closed_won`:

1/4. **Create customer / create support profile** — the same real
   `support.Customer` row (not two entities — a support profile *is* a
   customer record in this build).
2. **Create onboarding project** — a real `core.Task` tracking it.
5. **Provision internal tasks** — a second, distinct `core.Task` for
   support workspace setup.
3. **Send welcome email** — dispatched through the same dev/local
   logging adapter every other transactional email in this build uses
   (`app.identity.service._dispatch_password_reset_email`'s pattern) —
   no real SMTP/SES provider is configured anywhere
   (docs/KNOWN_LIMITATIONS.md); `Customer.welcome_email_sent_at` records
   that the real call happened, not that an inbox actually received it.
6. **Update billing integration** — no real payment/invoicing connector
   exists (Billing, PLAT-19, manages this org's *own* subscription plan,
   not customer invoicing — a different concept), so this is a real,
   tracked `core.Task` asking a human to set it up, not a fabricated
   "integration updated" claim.
7. **Assign account owner** — `Customer.owner_id` carries the closing
   Account's own owner across the sales-to-support handoff.
8. **Schedule check-in** — a third `core.Task` due in 30 days.

All reuse Phase 6's and Phase 1's existing primitives rather than
inventing new ones (ADR-0025, extended ADR-0060). `Opportunity.
onboarding_customer_id` is both the link and the idempotency guard: once
set, a later closed_won transition (e.g. reopened then re-won) is a
genuine no-op, not a second customer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.governance import GovernanceDecision, check_contact_permission
from app.core.models import Task
from app.sales.models import Account, Contact, Opportunity, OutreachMessage
from app.support.models import Customer

logger = logging.getLogger("agora.sales")


def _dispatch_welcome_email(*, to_email: str, customer_name: str) -> None:
    """Same dev/local logging adapter as password reset / email
    verification — logs instead of sending real email
    (docs/KNOWN_LIMITATIONS.md: no SMTP/SES provider is configured)."""
    logger.info("Welcome email to %s for new customer %s", to_email, customer_name)


async def send_outreach_message(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    message: OutreachMessage,
    contact: Contact,
    actor_user_id: uuid.UUID | None,
) -> OutreachMessage:
    decision = await check_contact_permission(db, organization_id=organization_id, contact=contact)
    # Also honors the Lead Finder's own suppression list
    # (sales_suppression_entries) — independent of Contact.do_not_contact
    # since a person can be suppressed before they're ever saved as a
    # Contact (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §12). A
    # superset check: this can only turn an allowed send into a blocked
    # one, never the reverse, so it can't regress the existing
    # do_not_contact-only behavior.
    if decision.allowed:
        from app.sales.suppression_service import find_matching_suppression

        suppression = await find_matching_suppression(
            db, organization_id=organization_id, email=contact.email
        )
        if suppression is not None:
            decision = GovernanceDecision(
                allowed=False, reason=f"Suppressed: {suppression.reason}"
            )
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

    # Steps 1/4: create customer / create support profile — one entity.
    customer = Customer(
        organization_id=organization_id,
        sales_account_id=account.id,
        name=account.name,
        email=primary_contact.email,
        status="active",
        owner_id=account.owner_id,  # step 7: assign account owner
    )
    db.add(customer)
    await db.flush()

    account.status = "customer"

    # Step 3: send welcome email.
    _dispatch_welcome_email(to_email=customer.email, customer_name=customer.name)
    customer.welcome_email_sent_at = datetime.now(UTC)

    # Step 2: create onboarding project.
    onboarding_task = Task(
        organization_id=organization_id,
        title=f"Onboarding project: {account.name}",
        description=f'Opportunity "{opportunity.title}" closed won.',
        module="support",
        priority="high",
        assignee_id=account.owner_id,
        due_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(onboarding_task)

    # Step 5: provision internal tasks.
    workspace_task = Task(
        organization_id=organization_id,
        title=f"Provision support workspace: {account.name}",
        module="support",
        priority="normal",
        assignee_id=account.owner_id,
        due_at=datetime.now(UTC) + timedelta(days=3),
    )
    db.add(workspace_task)

    # Step 6: update billing integration — no real invoicing connector
    # exists, so this is a real, tracked human action, not a fabricated
    # "integration updated" claim.
    billing_task = Task(
        organization_id=organization_id,
        title=f"Set up billing for new customer: {account.name}",
        module="sales",
        priority="high",
        due_at=datetime.now(UTC) + timedelta(days=3),
    )
    db.add(billing_task)

    # Step 8: schedule check-in.
    check_in_task = Task(
        organization_id=organization_id,
        title=f"30-day check-in: {account.name}",
        module="support",
        priority="normal",
        assignee_id=account.owner_id,
        due_at=datetime.now(UTC) + timedelta(days=30),
    )
    db.add(check_in_task)

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
            "workspace_task_id": str(workspace_task.id),
            "billing_task_id": str(billing_task.id),
            "check_in_task_id": str(check_in_task.id),
        },
    )
    return opportunity
