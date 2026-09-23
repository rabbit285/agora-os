"""Starting a DPIA from what the organization already recorded.

The DPIA flow began with a title, a risk dropdown and a "Start DPIA"
button — which asks a person to classify the risk *before* the screening
that exists to establish it, and then to retype facts already sitting in
the processing activity they are assessing.

So this assembles the context instead. Everything here is read from
records the organization made: the activity's own purpose and data
subjects, the AI systems it runs through, the processors it names, the
transfers already recorded against it.

**The screening answers are suggestions, and they are marked as such.**
Where a declared fact maps onto a screening criterion — the activity
records special-category data, so the "sensitive data" criterion is
likely met — that answer is pre-ticked with the reason beside it. Every
one is editable, none is assumed, and the criteria nothing in the record
speaks to are left blank rather than answered "no". A screening whose
answers were guessed produces a recommendation about nothing.

And the recommendation stays a recommendation. `dpia_screening` counts
what the controller reported against Article 35(3) and the EDPB's nine
criteria; whether a DPIA is required is the controller's decision, and
the flow requires them to make it explicitly before a DPIA exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    AISystem,
    DataTransfer,
    Evidence,
    ProcessingActivity,
    ProcessingActivityAISystem,
    ProcessingActivityVendor,
    Vendor,
)


@dataclass
class SuggestedAnswer:
    """One screening criterion Veyntra can speak to, and why.

    Never applied silently. The reason travels with it so the person
    screening can see what it was read from and disagree.
    """

    criterion: str
    value: bool
    reason: str


@dataclass
class LinkedRecord:
    id: uuid.UUID
    label: str
    kind: str
    detail: str | None = None


@dataclass
class DpiaContext:
    """What is known about the processing, before anybody types anything."""

    title: str
    purpose: str | None
    data_subjects: str | None
    data_categories: list[str] = field(default_factory=list)
    special_category: bool = False
    processing_activity_id: uuid.UUID | None = None
    ai_system_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    ai_systems: list[LinkedRecord] = field(default_factory=list)
    vendors: list[LinkedRecord] = field(default_factory=list)
    transfers: list[LinkedRecord] = field(default_factory=list)
    evidence_count: int = 0
    # Criteria the record already speaks to, with the reason for each.
    suggested_answers: list[SuggestedAnswer] = field(default_factory=list)
    # What could not be established, so the screen can say so rather
    # than presenting silence as a clean result.
    unknown: list[str] = field(default_factory=list)


def _suggest_from_facts(
    *,
    special_category: bool,
    ai_systems: list[LinkedRecord],
    data_categories: list[str],
) -> list[SuggestedAnswer]:
    """Screening answers the record already supports.

    Deliberately few. Only the criteria a declared fact speaks to
    directly are proposed; inferring "large scale" from the existence of
    a customer database would be the product guessing at the answer it
    was asked to help establish.
    """
    suggestions: list[SuggestedAnswer] = []

    if special_category:
        suggestions.append(
            SuggestedAnswer(
                criterion="sensitive_data",
                value=True,
                reason=(
                    "This processing activity records special-category data."
                ),
            )
        )
    if ai_systems:
        names = ", ".join(system.label for system in ai_systems[:3])
        suggestions.append(
            SuggestedAnswer(
                criterion="innovative_technology",
                value=True,
                reason=(
                    f"This processing runs through {names}, which is registered "
                    "as an AI system."
                ),
            )
        )
    return suggestions


async def build_context(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    processing_activity_id: uuid.UUID | None = None,
    ai_system_id: uuid.UUID | None = None,
) -> DpiaContext | None:
    """Everything known about what is being assessed.

    Either a processing activity or an AI system is the subject. An
    activity is preferred where both are given, because it is the record
    that carries the lawful basis and the data subjects.
    """
    if processing_activity_id is not None:
        activity = await db.get(ProcessingActivity, processing_activity_id)
        if activity is None or activity.organization_id != organization_id:
            return None
        return await _from_activity(db, activity)

    if ai_system_id is not None:
        system = await db.get(AISystem, ai_system_id)
        if system is None or system.organization_id != organization_id:
            return None
        return await _from_ai_system(db, system)

    return None


async def _from_activity(
    db: AsyncSession, activity: ProcessingActivity
) -> DpiaContext:
    ai_rows = (
        await db.execute(
            select(AISystem)
            .join(
                ProcessingActivityAISystem,
                ProcessingActivityAISystem.ai_system_id == AISystem.id,
            )
            .where(ProcessingActivityAISystem.processing_activity_id == activity.id)
        )
    ).scalars().all()
    vendor_rows = (
        await db.execute(
            select(Vendor)
            .join(
                ProcessingActivityVendor,
                ProcessingActivityVendor.vendor_id == Vendor.id,
            )
            .where(ProcessingActivityVendor.processing_activity_id == activity.id)
        )
    ).scalars().all()
    transfer_rows = (
        await db.execute(
            select(DataTransfer).where(
                DataTransfer.processing_activity_id == activity.id
            )
        )
    ).scalars().all()

    ai_systems = [
        LinkedRecord(id=row.id, label=row.name, kind="ai_system") for row in ai_rows
    ]
    vendors = [
        LinkedRecord(
            id=row.id, label=row.name, kind="vendor", detail=row.country or None
        )
        for row in vendor_rows
    ]
    transfers = [
        LinkedRecord(
            id=row.id,
            label=f"{row.recipient_name} ({row.destination_country})",
            kind="transfer",
            detail=row.transfer_mechanism or None,
        )
        for row in transfer_rows
    ]

    evidence_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Evidence)
                .where(Evidence.organization_id == activity.organization_id)
            )
        ).scalar_one()
    )

    return DpiaContext(
        # The DPIA is about the processing, so it is named after it.
        title=f"{activity.name} DPIA",
        purpose=activity.purpose,
        data_subjects=activity.data_subjects,
        data_categories=list(activity.data_categories or []),
        special_category=bool(activity.special_category),
        processing_activity_id=activity.id,
        ai_system_id=ai_systems[0].id if ai_systems else None,
        owner_id=activity.owner_id,
        ai_systems=ai_systems,
        vendors=vendors,
        transfers=transfers,
        evidence_count=evidence_count,
        suggested_answers=_suggest_from_facts(
            special_category=bool(activity.special_category),
            ai_systems=ai_systems,
            data_categories=list(activity.data_categories or []),
        ),
        unknown=[
            # Named so the screen can ask rather than assume. Silence on
            # a criterion is not a "no".
            "large_scale",
            "systematic_monitoring",
            "automated_decision_making",
            "vulnerable_subjects",
            "matching_or_combining",
        ],
    )


async def _from_ai_system(db: AsyncSession, system: AISystem) -> DpiaContext:
    vendor = (
        await db.get(Vendor, system.vendor_id) if system.vendor_id else None
    )
    categories = [
        (entry.get("name") or "").strip()
        for entry in (system.processed_data or [])
        if isinstance(entry, dict) and (entry.get("name") or "").strip()
    ]
    subjects = ", ".join(
        entry.strip() for entry in (system.affected_users or []) if entry.strip()
    )
    linked = [LinkedRecord(id=system.id, label=system.name, kind="ai_system")]

    return DpiaContext(
        title=f"{system.name} DPIA",
        purpose=(system.purpose or "").strip() or (system.description or "").strip(),
        data_subjects=subjects or None,
        data_categories=categories,
        # An AI system registration has no Article 9 flag of its own, so
        # this is left for the person rather than guessed from category
        # names.
        special_category=False,
        ai_system_id=system.id,
        owner_id=system.owner_id,
        ai_systems=linked,
        vendors=(
            [
                LinkedRecord(
                    id=vendor.id,
                    label=vendor.name,
                    kind="vendor",
                    detail=vendor.country or None,
                )
            ]
            if vendor
            else []
        ),
        suggested_answers=_suggest_from_facts(
            special_category=False, ai_systems=linked, data_categories=categories
        ),
        unknown=[
            "large_scale",
            "systematic_monitoring",
            "automated_decision_making",
            "vulnerable_subjects",
            "matching_or_combining",
            "sensitive_data",
        ],
    )


__all__ = ["DpiaContext", "LinkedRecord", "SuggestedAnswer", "build_context"]
