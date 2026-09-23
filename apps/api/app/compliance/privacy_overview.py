"""What a privacy team has to deal with today.

The privacy page was four lists stacked vertically, each with its form
permanently open. That works at three records and fails at fifty: the
question a privacy officer opens the product with is not "show me every
processing activity", it is "what needs me this week".

So this derives the second question from the same records. Every item
here is a **deficiency somebody can act on**, computed from what is
recorded rather than stored as a flag — a stored "overdue" is wrong the
moment the clock passes it and nobody has run a job — and each one
carries the route to the exact record it is about. A dashboard whose
numbers do not lead anywhere is a decoration.

Nothing here concludes anything legal. "Missing lawful basis" is a fact
about a form field; "transfer mechanism needs review" says a person
should look, not that a transfer is unlawful. The difference matters
because the product cannot know the second thing and should not imply
it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    DPIA,
    DSAR,
    DataTransfer,
    ProcessingActivity,
)
from app.compliance.privacy_deadlines import DUE_SOON_DAYS, as_utc, describe

# Ordering for the attention list. Something already past a statutory
# deadline outranks something that has not been reviewed this year, and
# a list that mixes them by insertion order buries the first behind the
# second.
SEVERITY_ORDER = {"overdue": 0, "urgent": 1, "attention": 2, "info": 3}


@dataclass
class Metric:
    """One number on the overview, and where its records live."""

    key: str
    label: str
    value: int
    href: str
    # Set where the number is itself a problem rather than a size.
    tone: str = "neutral"


@dataclass
class AttentionItem:
    """One thing a person can do something about, and the way to it."""

    key: str
    severity: str
    title: str
    detail: str
    href: str
    # What kind of record this is, so the screen can group without
    # parsing the route.
    record_type: str
    record_id: uuid.UUID | None = None


@dataclass
class PrivacyOverview:
    metrics: list[Metric] = field(default_factory=list)
    attention: list[AttentionItem] = field(default_factory=list)

    @property
    def needs_attention(self) -> int:
        return len(self.attention)


def _now() -> datetime:
    return datetime.now(UTC)


def _activities_route(query: str = "") -> str:
    return f"/compliance/privacy/processing-activities{query}"


async def build_overview(
    db: AsyncSession, *, organization_id: uuid.UUID, now: datetime | None = None
) -> PrivacyOverview:
    """The counts and the worklist, from the records themselves."""
    moment = now or _now()
    overview = PrivacyOverview()

    activities = list(
        (
            await db.execute(
                select(ProcessingActivity).where(
                    ProcessingActivity.organization_id == organization_id,
                    ProcessingActivity.status != "archived",
                )
            )
        )
        .scalars()
        .all()
    )
    dpias = list(
        (
            await db.execute(select(DPIA).where(DPIA.organization_id == organization_id))
        )
        .scalars()
        .all()
    )
    requests = list(
        (
            await db.execute(select(DSAR).where(DSAR.organization_id == organization_id))
        )
        .scalars()
        .all()
    )
    transfers = list(
        (
            await db.execute(
                select(DataTransfer).where(
                    DataTransfer.organization_id == organization_id,
                    DataTransfer.status != "terminated",
                )
            )
        )
        .scalars()
        .all()
    )

    open_requests = [r for r in requests if r.status not in ("fulfilled", "rejected")]

    # --- the numbers -----------------------------------------------------
    needs_review = [
        activity
        for activity in activities
        if activity.status == "needs_review"
        or (
            activity.next_review_at is not None
            and as_utc(activity.next_review_at) <= moment
        )
    ]
    open_dpias = [dpia for dpia in dpias if dpia.status in ("draft", "in_review")]
    due_soon = [
        request
        for request in open_requests
        if describe(
            received_at=request.received_at,
            extension_months=request.extension_months or 0,
            now=moment,
        ).due_soon
    ]

    overview.metrics = [
        Metric(
            "processing_activities",
            "Processing activities",
            len(activities),
            _activities_route(),
        ),
        Metric(
            "activities_need_review",
            "Need review",
            len(needs_review),
            _activities_route("?filter=needs_review"),
            tone="attention" if needs_review else "neutral",
        ),
        Metric("open_dpias", "Open DPIAs", len(open_dpias), "/compliance/privacy/dpias"),
        Metric(
            "open_requests",
            "Data requests open",
            len(open_requests),
            "/compliance/privacy/data-requests",
        ),
        Metric(
            "requests_due_soon",
            f"Due within {DUE_SOON_DAYS} days",
            len(due_soon),
            "/compliance/privacy/data-requests?filter=due_soon",
            tone="attention" if due_soon else "neutral",
        ),
        Metric(
            "transfers",
            "International transfers",
            len(transfers),
            "/compliance/privacy/transfers",
        ),
    ]

    # --- what needs somebody ---------------------------------------------
    #
    # Data requests first: they are the only privacy record with a
    # statutory clock on it.
    for request in open_requests:
        state = describe(
            received_at=request.received_at,
            extension_months=request.extension_months or 0,
            now=moment,
        )
        # The list lives under /compliance/privacy/data-requests, but a
        # single request's workflow — verification, scope, discovery,
        # export — is at /compliance/dsars/{id}. An alert that lands on a
        # 404 is worse than no alert: it teaches people the overdue
        # warnings are broken and can be ignored.
        href = f"/compliance/dsars/{request.id}"
        if state.overdue:
            overview.attention.append(
                AttentionItem(
                    key=f"dsar-overdue-{request.id}",
                    severity="overdue",
                    title=f"Data request from {request.requester_name} is overdue",
                    detail=f"{state.label}. The response was due {state.due_at:%B %d, %Y}.",
                    href=href,
                    record_type="data_request",
                    record_id=request.id,
                )
            )
        elif state.due_soon:
            overview.attention.append(
                AttentionItem(
                    key=f"dsar-due-{request.id}",
                    severity="urgent",
                    title=f"Data request from {request.requester_name} is {state.label.lower()}",
                    detail=f"Response due {state.due_at:%B %d, %Y}.",
                    href=href,
                    record_type="data_request",
                    record_id=request.id,
                )
            )
        if request.verification_status == "pending" and not state.overdue:
            overview.attention.append(
                AttentionItem(
                    key=f"dsar-identity-{request.id}",
                    severity="attention",
                    title="Identity verification pending",
                    detail=(
                        f"{request.requester_name}'s request cannot be answered "
                        "until their identity is verified."
                    ),
                    href=href,
                    record_type="data_request",
                    record_id=request.id,
                )
            )

    # Processing activities: a missing lawful basis is a gap in the
    # record, not a legal conclusion about the processing.
    for activity in activities:
        href = f"/compliance/privacy/processing-activities/{activity.id}"
        if not (activity.legal_basis or "").strip():
            overview.attention.append(
                AttentionItem(
                    key=f"ropa-basis-{activity.id}",
                    severity="attention",
                    title=f"{activity.name} has no lawful basis recorded",
                    detail="A lawful basis is a judgement somebody has to make and record.",
                    href=href,
                    record_type="processing_activity",
                    record_id=activity.id,
                )
            )
        if activity.special_category and not (
            activity.special_category_condition or ""
        ).strip():
            overview.attention.append(
                AttentionItem(
                    key=f"ropa-article9-{activity.id}",
                    severity="attention",
                    title=f"{activity.name} processes special-category data",
                    detail=(
                        "No Article 9 condition is recorded. Special-category "
                        "processing needs one in addition to a lawful basis."
                    ),
                    href=href,
                    record_type="processing_activity",
                    record_id=activity.id,
                )
            )
        if activity in needs_review:
            when = (
                f" Review was due {activity.next_review_at:%B %d, %Y}."
                if activity.next_review_at
                else ""
            )
            overview.attention.append(
                AttentionItem(
                    key=f"ropa-review-{activity.id}",
                    severity="attention",
                    title=f"{activity.name} is due for review",
                    detail=f"Confirm the record still describes what happens.{when}",
                    href=href,
                    record_type="processing_activity",
                    record_id=activity.id,
                )
            )

    # DPIAs awaiting a person.
    for dpia in dpias:
        if dpia.status == "in_review":
            overview.attention.append(
                AttentionItem(
                    key=f"dpia-review-{dpia.id}",
                    severity="attention",
                    title=f"{dpia.title} is awaiting review",
                    detail="A DPIA in review needs somebody to reach a conclusion on it.",
                    href=f"/compliance/dpias/{dpia.id}",
                    record_type="dpia",
                    record_id=dpia.id,
                )
            )
        elif dpia.status == "draft" and dpia.screening_outcome is None:
            overview.attention.append(
                AttentionItem(
                    key=f"dpia-screening-{dpia.id}",
                    severity="info",
                    title=f"{dpia.title} has not been screened",
                    detail=(
                        "Screening records whether a full assessment is needed, "
                        "and why."
                    ),
                    href=f"/compliance/dpias/{dpia.id}",
                    record_type="dpia",
                    record_id=dpia.id,
                )
            )

    # Transfers: an incomplete mechanism needs review. It is not a
    # finding that the transfer is unlawful — the product cannot know
    # that, and saying it would be worse than saying nothing.
    for transfer in transfers:
        href = f"/compliance/privacy/transfers/{transfer.id}"
        if not (transfer.transfer_mechanism or "").strip():
            overview.attention.append(
                AttentionItem(
                    key=f"transfer-mechanism-{transfer.id}",
                    severity="attention",
                    title=f"Transfer to {transfer.recipient_name} has no mechanism recorded",
                    detail=(
                        "Record the basis for this transfer, or mark it for review "
                        "if the basis is still being established."
                    ),
                    href=href,
                    record_type="transfer",
                    record_id=transfer.id,
                )
            )
        elif transfer.transfer_mechanism in ("sccs", "bcrs") and not (
            transfer.safeguards_description or ""
        ).strip():
            overview.attention.append(
                AttentionItem(
                    key=f"transfer-safeguards-{transfer.id}",
                    severity="attention",
                    title=f"Transfer to {transfer.recipient_name} records no safeguards",
                    detail=(
                        "The mechanism is recorded; the supplementary measures "
                        "relied on are not."
                    ),
                    href=href,
                    record_type="transfer",
                    record_id=transfer.id,
                )
            )
        if (
            transfer.next_review_at is not None
            and as_utc(transfer.next_review_at) <= moment
        ):
            overview.attention.append(
                AttentionItem(
                    key=f"transfer-review-{transfer.id}",
                    severity="info",
                    title=f"Transfer to {transfer.recipient_name} is due for review",
                    detail=(
                        f"Review was due {transfer.next_review_at:%B %d, %Y}. "
                        "Mechanisms change; confirm this one still holds."
                    ),
                    href=href,
                    record_type="transfer",
                    record_id=transfer.id,
                )
            )

    overview.attention.sort(
        key=lambda item: (SEVERITY_ORDER.get(item.severity, 9), item.title)
    )
    overview.metrics.append(
        Metric(
            "needs_attention",
            "Needs attention",
            overview.needs_attention,
            "/compliance/privacy",
            tone="attention" if overview.attention else "neutral",
        )
    )
    return overview


__all__ = [
    "AttentionItem",
    "Metric",
    "PrivacyOverview",
    "build_overview",
]
