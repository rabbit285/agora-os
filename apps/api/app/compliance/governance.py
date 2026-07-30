"""Compliance as Governance Layer (spec §91): "Compliance must govern the
other modules" — a synchronous, in-request question the *asking* module
poses before taking an action, not a queued or best-effort check. This is
the mirror image of the "assessment creates a tracked consequence" hook
shape used everywhere else in this codebase (spec §80: Compliance reacting
to events after the fact) — these three functions are Compliance being
asked *before* the fact instead.

Each function below answers one of spec §91's three named examples:

1. "Sales AI asks: Can we contact this prospect?" -> `check_contact_permission`
2. "Support AI asks: Can we disclose this customer information?" ->
   `check_customer_disclosure_permission`
3. "Automation asks: Can workflow export personal data?" ->
   `check_data_export_permission`

These are deliberately the simplest real instance of each principle (a
suppression flag; a pending-deletion-DSAR check; an on-file transfer
mechanism for the destination), not a full jurisdiction/consent engine —
see docs/KNOWN_LIMITATIONS.md for what a fuller version would add. Pure
decision functions with no side effects: the calling module records its
own action-specific audit event using the returned decision, the same way
`app.sales.service.send_outreach_message` already records
`sales.outreach.send_attempted` with `policy_decision` reflecting the
outcome.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import DSAR, DataTransfer
from app.sales.models import Contact
from app.support.models import Customer

_PENDING_DELETION_STATUSES = ("received", "in_progress")
_CLASSIFICATIONS_REQUIRING_TRANSFER_REVIEW = ("confidential", "restricted")


@dataclass
class GovernanceDecision:
    allowed: bool
    reason: str | None = None


async def check_contact_permission(
    db: AsyncSession, *, organization_id: uuid.UUID, contact: Contact
) -> GovernanceDecision:
    """Sales AI asks: Can we contact this prospect? (spec §91: jurisdiction,
    data source, marketing basis, opt-out, suppression, organization
    policy) — this build's real signal is the contact's own suppression
    flag."""
    if contact.do_not_contact:
        return GovernanceDecision(
            allowed=False,
            reason="Contact is marked do-not-contact (opted out / suppressed).",
        )
    return GovernanceDecision(allowed=True)


async def check_customer_disclosure_permission(
    db: AsyncSession, *, organization_id: uuid.UUID, customer: Customer
) -> GovernanceDecision:
    """Support AI asks: Can we disclose this customer's information? (spec
    §91: Compliance/security checks authorization) — denies while a
    deletion DSAR for this person is pending, since disclosing more data
    about someone mid-erasure request works against the request itself."""
    pending_deletion = (
        await db.execute(
            select(DSAR).where(
                DSAR.organization_id == organization_id,
                DSAR.requester_email == customer.email,
                DSAR.request_type == "deletion",
                DSAR.status.in_(_PENDING_DELETION_STATUSES),
            )
        )
    ).scalar_one_or_none()
    if pending_deletion is not None:
        return GovernanceDecision(
            allowed=False,
            reason=(
                "A deletion request for this person is pending — disclosure is paused "
                "until it is resolved."
            ),
        )
    return GovernanceDecision(allowed=True)


async def check_data_export_permission(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    destination_country: str,
    data_classification: str,
) -> GovernanceDecision:
    """Automation asks: Can this workflow export personal data? (spec §91:
    destination, purpose, permissions, classification) — confidential or
    restricted data requires an active, on-file Compliance `DataTransfer`
    record for the destination country (a real transfer mechanism —
    adequacy/SCCs/BCRs/derogation — not a bare unreviewed export)."""
    if data_classification not in _CLASSIFICATIONS_REQUIRING_TRANSFER_REVIEW:
        return GovernanceDecision(allowed=True)

    transfer = (
        await db.execute(
            select(DataTransfer).where(
                DataTransfer.organization_id == organization_id,
                DataTransfer.destination_country == destination_country,
                DataTransfer.status == "active",
            )
        )
    ).scalar_one_or_none()
    if transfer is None:
        return GovernanceDecision(
            allowed=False,
            reason=(
                f"No active data transfer mechanism on file for {destination_country} — "
                "register one in Compliance before exporting classified data there."
            ),
        )
    return GovernanceDecision(allowed=True)
