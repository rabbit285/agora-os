"""Turning a proposal into a record somebody stands behind.

`privacy_suggestions` drafts; this is the only place a draft becomes a
real privacy record, and it refuses to do so until the person accepting
it has supplied the parts a draft is not allowed to contain.

That refusal is the design. A RoPA entry without a lawful basis is not a
RoPA entry, and one whose lawful basis was chosen by a machine is worse
— it looks answered. So the accept call takes the lawful basis, the
Article 9 condition where special-category data is involved, and the
transfer mechanism, and rejects the request if they are missing or still
say "needs confirmation".

Accepting is idempotent by decision rather than by retry: a suggestion
already accepted returns the record it created rather than making a
second one.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import (
    DataTransfer,
    PrivacySuggestion,
    ProcessingActivity,
    ProcessingActivityAISystem,
    ProcessingActivityVendor,
)
from app.compliance.privacy_suggestions import NEEDS_CONFIRMATION

logger = logging.getLogger("agora.compliance.privacy_accept")

# GDPR Article 6's six lawful bases. The product does not invent a
# seventh, and does not accept a blank.
LAWFUL_BASES = (
    "consent",
    "contract",
    "legal_obligation",
    "vital_interests",
    "public_task",
    "legitimate_interests",
)

TRANSFER_MECHANISMS = (
    "adequacy_decision",
    "sccs",
    "bcrs",
    "derogation",
    "other",
)


class AcceptRefused(Exception):
    """The suggestion cannot become a record as asked."""


def _now() -> datetime:
    return datetime.now(UTC)


def _requires(value: str | None, *, field: str, allowed: tuple[str, ...]) -> str:
    cleaned = (value or "").strip().lower()
    if not cleaned or cleaned == NEEDS_CONFIRMATION:
        raise AcceptRefused(
            f"{field} has to be chosen before this becomes a record. Veyntra "
            "drafts what your other records already say; this is the part only "
            "you can decide."
        )
    if cleaned not in allowed:
        raise AcceptRefused(f"{cleaned} is not a {field} this product records.")
    return cleaned


async def accept_processing_activity(
    db: AsyncSession,
    *,
    suggestion: PrivacySuggestion,
    legal_basis: str,
    retention_period: str,
    special_category: bool = False,
    special_category_condition: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> ProcessingActivity:
    """Create the RoPA entry, with the judgements a person supplied."""
    if suggestion.status == "accepted" and suggestion.created_record_id:
        existing = await db.get(ProcessingActivity, suggestion.created_record_id)
        if existing is not None:
            return existing

    basis = _requires(legal_basis, field="A lawful basis", allowed=LAWFUL_BASES)
    retention = (retention_period or "").strip()
    if not retention:
        raise AcceptRefused(
            "A retention period has to be recorded. How long personal data is "
            "kept is part of the record, and Veyntra has no basis to infer it."
        )
    condition = (special_category_condition or "").strip() or None
    if special_category and not condition:
        raise AcceptRefused(
            "Special-category processing needs an Article 9 condition in "
            "addition to a lawful basis."
        )

    payload = suggestion.payload or {}
    activity = ProcessingActivity(
        organization_id=suggestion.organization_id,
        name=payload.get("name") or suggestion.title,
        purpose=(payload.get("purpose") or "").strip()
        or "Recorded from an existing system registration.",
        legal_basis=basis,
        data_categories=list(payload.get("data_categories") or []),
        data_subjects=(payload.get("data_subjects") or "").strip() or "Not recorded",
        retention_period=retention,
        special_category=special_category,
        special_category_condition=condition if special_category else None,
        owner_id=actor_user_id,
        # Carried, not resolved. The document said a processor and a
        # destination; acceptance used to drop both, which left the
        # activity with nothing for transfer detection to reason about
        # and made "Review suggestions (0)" the correct answer to a
        # question nobody could see was being asked.
        processor_named=(payload.get("vendor_named") or "").strip() or None,
        destination_country_named=(
            (payload.get("destination_country") or "").strip().upper()[:2] or None
        ),
    )
    db.add(activity)
    await db.flush()

    # The links are the point: the record stays connected to what it was
    # drafted from, so nobody maintains the same fact in two places.
    for raw in payload.get("ai_system_ids") or []:
        db.add(
            ProcessingActivityAISystem(
                processing_activity_id=activity.id, ai_system_id=uuid.UUID(str(raw))
            )
        )
    for raw in payload.get("vendor_ids") or []:
        db.add(
            ProcessingActivityVendor(
                processing_activity_id=activity.id, vendor_id=uuid.UUID(str(raw))
            )
        )

    suggestion.status = "accepted"
    suggestion.created_record_id = activity.id
    suggestion.decided_by = actor_user_id
    suggestion.decided_at = _now()
    await db.flush()

    await record_event(
        db,
        organization_id=suggestion.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.privacy_suggestion.accepted",
        object_type="processing_activity",
        object_id=str(activity.id),
        after_state={
            "name": activity.name,
            "legal_basis": basis,
            "drafted_from": [source.get("label") for source in suggestion.sources or []],
        },
    )
    logger.info("Accepted privacy suggestion %s as activity %s", suggestion.id, activity.id)
    return activity


async def accept_transfer(
    db: AsyncSession,
    *,
    suggestion: PrivacySuggestion,
    transfer_mechanism: str,
    safeguards_description: str | None = None,
    actor_user_id: uuid.UUID | None,
) -> DataTransfer:
    """Create the transfer record, with the mechanism a person chose."""
    if suggestion.status == "accepted" and suggestion.created_record_id:
        existing = await db.get(DataTransfer, suggestion.created_record_id)
        if existing is not None:
            return existing

    mechanism = _requires(
        transfer_mechanism,
        field="A transfer mechanism",
        allowed=TRANSFER_MECHANISMS,
    )
    payload = suggestion.payload or {}
    activity_id = payload.get("processing_activity_id")
    vendor_id = payload.get("vendor_id")

    transfer = DataTransfer(
        organization_id=suggestion.organization_id,
        processing_activity_id=uuid.UUID(str(activity_id)) if activity_id else None,
        vendor_id=uuid.UUID(str(vendor_id)) if vendor_id else None,
        recipient_name=payload.get("recipient_name") or suggestion.title,
        destination_country=(payload.get("destination_country") or "")[:2].upper(),
        transfer_mechanism=mechanism,
        safeguards_description=(safeguards_description or "").strip() or None,
        owner_id=actor_user_id,
        # Carried from the proposal so re-running detection recognises
        # this transfer as already recorded, and so the record says which
        # edge found it rather than looking hand-entered.
        source_key=suggestion.source_key,
        detected_from=payload.get("detected_from"),
    )
    db.add(transfer)
    await db.flush()

    suggestion.status = "accepted"
    suggestion.created_record_id = transfer.id
    suggestion.decided_by = actor_user_id
    suggestion.decided_at = _now()
    await db.flush()

    await record_event(
        db,
        organization_id=suggestion.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.privacy_suggestion.accepted",
        object_type="data_transfer",
        object_id=str(transfer.id),
        after_state={
            "recipient": transfer.recipient_name,
            "destination": transfer.destination_country,
            "mechanism": mechanism,
        },
    )
    return transfer


async def dismiss(
    db: AsyncSession,
    *,
    suggestion: PrivacySuggestion,
    reason: str | None,
    actor_user_id: uuid.UUID | None,
) -> PrivacySuggestion:
    """Record that somebody looked and said no.

    Kept rather than deleted, and never resurrected by a later analysis
    pass: re-proposing something a person has already rejected is how a
    product teaches its users to ignore it.
    """
    if suggestion.status == "proposed":
        suggestion.status = "dismissed"
        suggestion.decided_by = actor_user_id
        suggestion.decided_at = _now()
        payload = dict(suggestion.payload or {})
        if (reason or "").strip():
            payload["dismissal_reason"] = reason.strip()
        suggestion.payload = payload
        await record_event(
            db,
            organization_id=suggestion.organization_id,
            actor_user_id=actor_user_id,
            action="compliance.privacy_suggestion.dismissed",
            object_type="privacy_suggestion",
            object_id=str(suggestion.id),
            after_state={"title": suggestion.title, "reason": reason},
        )
        await db.flush()
    return suggestion


__all__ = [
    "LAWFUL_BASES",
    "TRANSFER_MECHANISMS",
    "AcceptRefused",
    "accept_processing_activity",
    "accept_transfer",
    "dismiss",
]
