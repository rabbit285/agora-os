"""The privacy decisions that need a person, and what Veyntra found.

The product's argument is that it does the repetitive compliance work and
the human handles the judgements. Privacy had the first half — records
drafted from AI systems, transfers detected from vendors, deadlines
calculated — and no route into the second. The decisions were surfaced on
a privacy overview, which is a second queue, and the whole point of one
queue is that there is only one.

So this produces the privacy half of Review Center. Every item is a
decision somebody can make now, and carries the four things that make it
possible to make:

- **The recommendation**, where there is one. A drafted lawful basis is
  never one of these; a screening outcome is.
- **Why** — the facts it was read from, named.
- **Confidence**, and only for facts. A model's confidence in a *legal
  conclusion* is not a measurement of anything, and printing one beside
  "lawful basis: contract" would dress a guess as an assessment.
- **Where to decide it.**

The split between fact and judgement runs through the whole file.
Veyntra reports what the records say — this vendor is in the US, this
activity records special-category data, this request is due Tuesday —
with high confidence, because those are readable facts. What it never
does is conclude that a lawful basis is contract, that a transfer is
covered, or that a DPIA is not required. Those go to a person with the
evidence attached, and stay open until somebody decides.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    DPIA,
    DSAR,
    AISystem,
    DataTransfer,
    PrivacySuggestion,
    ProcessingActivity,
    ProcessingActivityAISystem,
    ProcessingActivityVendor,
    Vendor,
)
from app.compliance.privacy_deadlines import describe

# What a fact is worth stating with. These are not model scores — they
# are how directly a fact was read from a record, which is the only
# thing the product can honestly quantify.
#
#   declared  the organization typed it into a field
#   linked    read across one relationship the organization created
#   derived   computed from a rule over declared facts
CONFIDENCE = {"declared": 0.99, "linked": 0.95, "derived": 0.90}


@dataclass
class DecisionItem:
    """One privacy judgement waiting on a person."""

    id: str
    kind: str
    title: str
    detail: str
    priority: str
    href: str
    # Present only where Veyntra has something to recommend. A lawful
    # basis never does.
    recommendation: str | None = None
    recommendation_reason: str | None = None
    # The facts behind it, named so the reviewer can check rather than
    # trust. Each carries how directly it was established.
    evidence: list[dict] = field(default_factory=list)
    # What changes if this is approved.
    impact: str | None = None


def _fact(label: str, value: str, basis: str) -> dict:
    return {
        "label": label,
        "value": value,
        "basis": basis,
        "confidence": CONFIDENCE.get(basis, 0.9),
    }


async def _lawful_basis_decisions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[DecisionItem]:
    """Activities recorded without the judgement only a person can make.

    Deliberately carries no recommendation. Which lawful basis applies
    depends on the relationship with the data subject, what was promised
    to them and what the organization is actually relying on — none of
    which is in a database, and a suggested answer here would be
    approved without being thought about.
    """
    activities = (
        await db.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == organization_id,
                ProcessingActivity.status != "archived",
            )
        )
    ).scalars().all()

    items: list[DecisionItem] = []
    for activity in activities:
        if (activity.legal_basis or "").strip():
            continue
        evidence = [
            _fact("Purpose", activity.purpose or "Not recorded", "declared"),
            _fact(
                "Data subjects", activity.data_subjects or "Not recorded", "declared"
            ),
        ]
        if activity.data_categories:
            evidence.append(
                _fact(
                    "Personal data",
                    ", ".join(activity.data_categories),
                    "declared",
                )
            )
        items.append(
            DecisionItem(
                id=f"privacy-basis-{activity.id}",
                kind="lawful_basis",
                title=f"Confirm the lawful basis for {activity.name}",
                detail=(
                    "Veyntra drafted this activity from your records but cannot "
                    "choose a lawful basis — that depends on your relationship "
                    "with the data subjects and what you told them."
                ),
                priority="high",
                href="/compliance/privacy/processing-activities",
                evidence=evidence,
                impact=(
                    "The activity becomes an active RoPA entry once a basis is "
                    "recorded."
                ),
            )
        )
    return items


async def _drafted_activity_decisions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[DecisionItem]:
    """Activities Veyntra drafted, waiting on the one judgement it left.

    The draft is where the lawful basis decision lives — before it, no
    processing activity exists, and a queue that only listed decisions
    on records already created would hide the work Veyntra had done.
    """
    proposals = (
        await db.execute(
            select(PrivacySuggestion).where(
                PrivacySuggestion.organization_id == organization_id,
                PrivacySuggestion.kind == "processing_activity",
                PrivacySuggestion.status == "proposed",
            )
        )
    ).scalars().all()

    items: list[DecisionItem] = []
    for proposal in proposals:
        payload = proposal.payload or {}
        evidence = [
            _fact("Purpose", str(payload.get("purpose") or ""), "declared"),
            _fact("Data subjects", str(payload.get("data_subjects") or ""), "declared"),
        ]
        categories = payload.get("data_categories") or []
        if categories:
            evidence.append(
                _fact("Personal data", ", ".join(categories), "declared")
            )
        evidence.append(
            _fact(
                "Drafted from",
                ", ".join(
                    source.get("label", "") for source in proposal.sources or []
                ),
                "linked",
            )
        )
        items.append(
            DecisionItem(
                id=f"privacy-draft-basis-{proposal.id}",
                kind="lawful_basis",
                title=f"Confirm the lawful basis for {proposal.title}",
                detail=(
                    "Veyntra drafted this activity from your systems and "
                    "vendors. The facts are read from your own records; the "
                    "lawful basis is the judgement it cannot make."
                ),
                priority="high",
                href="/compliance/privacy/processing-activities",
                evidence=evidence,
                impact=(
                    "Approving creates the RoPA entry and links it to the "
                    "systems and processors it was drafted from."
                ),
            )
        )
    return items


async def _article_nine_decisions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[DecisionItem]:
    activities = (
        await db.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == organization_id,
                ProcessingActivity.special_category.is_(True),
                ProcessingActivity.status != "archived",
            )
        )
    ).scalars().all()
    return [
        DecisionItem(
            id=f"privacy-article9-{activity.id}",
            kind="article_9_condition",
            title=f"Confirm the Article 9 condition for {activity.name}",
            detail=(
                "This activity records special-category data, which needs its "
                "own condition in addition to a lawful basis."
            ),
            priority="high",
            href="/compliance/privacy/processing-activities",
            evidence=[
                _fact("Special-category data", "Recorded", "declared"),
                _fact(
                    "Lawful basis",
                    activity.legal_basis or "Not recorded",
                    "declared",
                ),
            ],
        )
        for activity in activities
        if not (activity.special_category_condition or "").strip()
    ]


async def _screening_decisions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[DecisionItem]:
    """Screenings Veyntra ran, waiting for the controller's conclusion.

    This one *does* carry a recommendation, because counting Article
    35(3) cases and EDPB criteria against reported answers is arithmetic
    over a published rule, not a judgement. Whether a DPIA is required
    remains the controller's decision, and the item stays open until
    they make it.
    """
    dpias = (
        await db.execute(select(DPIA).where(DPIA.organization_id == organization_id))
    ).scalars().all()

    items: list[DecisionItem] = []
    for dpia in dpias:
        # Open exactly while the decision is outstanding. This used to
        # test for draft/in_review, which are the states a DPIA reaches
        # *because* somebody decided — so the item was invisible when it
        # mattered and asked for an answered question afterwards.
        if dpia.screening_decision is not None:
            continue
        if dpia.screening_outcome is None:
            continue
        findings = dpia.screening_outcome
        # Already concluded by a person once the DPIA leaves draft.
        recommendation = {
            "required": "A DPIA appears to be required",
            "recommended": "A DPIA may be required",
            "not_indicated": "A DPIA does not currently appear necessary",
        }.get(findings, findings)
        criteria = (dpia.screening_findings or {}).get("criteria_met") or []
        items.append(
            DecisionItem(
                id=f"privacy-screening-{dpia.id}",
                kind="dpia_requirement",
                title=f"Confirm whether {dpia.title} requires a DPIA",
                detail=(
                    "Veyntra counted the criteria you reported. Whether a DPIA "
                    "is required is your decision, and the record of it is "
                    "yours too."
                ),
                priority="high" if findings == "required" else "medium",
                href=f"/compliance/dpias/{dpia.id}",
                recommendation=recommendation,
                recommendation_reason=(
                    (dpia.screening_findings or {}).get("rationale")
                    or "Based on the screening criteria reported."
                ),
                evidence=[
                    _fact("Criterion met", str(entry), "declared")
                    for entry in criteria[:5]
                ],
                impact="Confirming creates the full assessment, pre-filled.",
            )
        )
    return items


async def _dpia_assessment_decisions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[DecisionItem]:
    """Open assessments, and what each is actually waiting on.

    One item per DPIA rather than one per missing thing: a queue that
    lists four rows for one assessment tells somebody they have four
    jobs when they have one screen to open. What is outstanding goes in
    the detail, so the item still says what the work is.
    """
    from app.compliance import dpia_workflow

    dpias = list(
        (
            await db.execute(
                select(DPIA).where(
                    DPIA.organization_id == organization_id,
                    DPIA.status.in_(
                        (
                            dpia_workflow.DRAFT,
                            dpia_workflow.IN_REVIEW,
                            dpia_workflow.APPROVED,
                        )
                    ),
                )
            )
        )
        .scalars()
        .all()
    )

    items: list[DecisionItem] = []
    for dpia in dpias:
        blockers = await dpia_workflow.completion_blockers(
            db, organization_id=organization_id, dpia=dpia
        )
        if not blockers:
            continue
        codes = {blocker.code for blocker in blockers}
        # The most consequential outstanding thing decides the priority.
        # An unapproved high residual rating is a different order of
        # problem from an unreviewed paragraph.
        high = bool(
            codes
            & {
                "high_residual_needs_approval",
                "high_residual_approval_pending",
                "suggested_risks_unreviewed",
            }
        )
        items.append(
            DecisionItem(
                id=f"privacy-dpia-{dpia.id}",
                kind="dpia_assessment",
                title=f"Finish the assessment: {dpia.title}",
                detail=" ".join(blocker.message for blocker in blockers),
                priority="high" if high else "medium",
                href=f"/compliance/dpias/{dpia.id}",
                evidence=[
                    _fact("Outstanding", blocker.message, "declared")
                    for blocker in blockers[:5]
                ],
                impact=(
                    "Completing freezes the assessment as an auditable "
                    "record of what was decided."
                ),
            )
        )
    return items


async def _dpia_reassessment_decisions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[DecisionItem]:
    """Completed DPIAs whose processing has moved on.

    Never a change to the completed record. A DPIA that silently
    absorbed a new vendor country would be claiming somebody assessed a
    transfer they never saw, so this asks a person to look again.
    """
    dpias = list(
        (
            await db.execute(
                select(DPIA).where(
                    DPIA.organization_id == organization_id,
                    DPIA.review_reason.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        DecisionItem(
            id=f"privacy-dpia-review-{dpia.id}",
            kind="dpia_reassessment",
            title=f"Reassess {dpia.title}",
            detail=(
                "The processing this assessment covers has changed since it "
                "was completed. The completed record is unchanged — this asks "
                "whether it still holds."
            ),
            priority="high",
            href=f"/compliance/dpias/{dpia.id}",
            recommendation="A reassessment appears to be needed",
            recommendation_reason=dpia.review_reason,
            evidence=[_fact("Changed since completion", dpia.review_reason, "linked")],
            impact="Nothing changes until you decide it does.",
        )
        for dpia in dpias
    ]


async def _transfer_decisions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[DecisionItem]:
    """Transfers detected from the records, needing a mechanism.

    Carries the destination and the processor as facts, and no
    recommended mechanism. Which one covers a transfer turns on the
    contract and the assessment behind it; a suggestion here would be
    the product making a legal call it cannot defend.
    """
    items: list[DecisionItem] = []

    proposals = (
        await db.execute(
            select(PrivacySuggestion).where(
                PrivacySuggestion.organization_id == organization_id,
                PrivacySuggestion.kind == "transfer",
                PrivacySuggestion.status == "proposed",
            )
        )
    ).scalars().all()
    for proposal in proposals:
        payload = proposal.payload or {}
        items.append(
            DecisionItem(
                id=f"privacy-transfer-draft-{proposal.id}",
                kind="transfer_mechanism",
                title=f"Confirm the transfer mechanism for {payload.get('recipient_name')}",
                detail=str(payload.get("note") or ""),
                priority="high",
                href="/compliance/privacy/transfers",
                evidence=[
                    _fact(
                        "Recipient", str(payload.get("recipient_name", "")), "declared"
                    ),
                    _fact(
                        "Destination",
                        str(payload.get("destination_country", "")),
                        "declared",
                    ),
                    _fact(
                        "Detected from",
                        ", ".join(
                            source.get("label", "") for source in proposal.sources or []
                        ),
                        "linked",
                    ),
                ],
                impact="Approving records the transfer against the activity and the vendor.",
            )
        )

    recorded = (
        await db.execute(
            select(DataTransfer).where(
                DataTransfer.organization_id == organization_id,
                DataTransfer.status != "terminated",
            )
        )
    ).scalars().all()
    for transfer in recorded:
        if (transfer.transfer_mechanism or "").strip():
            continue
        items.append(
            DecisionItem(
                id=f"privacy-transfer-{transfer.id}",
                kind="transfer_mechanism",
                title=f"Record the transfer mechanism for {transfer.recipient_name}",
                detail=(
                    "This transfer is recorded without a mechanism. Veyntra "
                    "does not conclude which one applies."
                ),
                priority="high",
                href=f"/compliance/privacy/transfers/{transfer.id}",
                evidence=[
                    _fact("Recipient", transfer.recipient_name, "declared"),
                    _fact("Destination", transfer.destination_country, "declared"),
                ],
            )
        )
    return items


async def _request_decisions(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[DecisionItem]:
    """Data requests where the clock is the reason to look now."""
    requests = (
        await db.execute(select(DSAR).where(DSAR.organization_id == organization_id))
    ).scalars().all()

    items: list[DecisionItem] = []
    for request in requests:
        if request.status in ("fulfilled", "rejected"):
            continue
        state = describe(
            received_at=request.received_at,
            extension_months=request.extension_months or 0,
        )
        if not (state.overdue or state.due_soon):
            continue
        items.append(
            DecisionItem(
                id=f"privacy-dsar-{request.id}",
                kind="data_request",
                title=f"{request.requester_name}'s request is {state.label.lower()}",
                detail=(
                    "Veyntra calculated the deadline and can suggest where to "
                    "look. What is released, and what is withheld, is your "
                    "decision."
                ),
                priority="high" if state.overdue else "medium",
                href=f"/compliance/dsars/{request.id}",
                evidence=[
                    _fact("Received", f"{request.received_at:%B %d, %Y}", "declared"),
                    _fact("Response due", f"{state.due_at:%B %d, %Y}", "derived"),
                    _fact(
                        "Identity verification",
                        request.verification_status,
                        "declared",
                    ),
                ],
            )
        )
    return items


async def _suggested_updates(
    db: AsyncSession, organization_id: uuid.UUID
) -> list[DecisionItem]:
    """Records a linked fact has moved underneath.

    §9's impact detection, kept deliberately narrow: a transfer whose
    vendor now records a different country than the transfer does. That
    is checkable without inference, and it is the case where being wrong
    matters — a transfer assessed against Ireland does not cover the
    same processing moved to Virginia.

    Never applied. A human-approved privacy record is not something to
    edit because a related row changed.
    """
    transfers = (
        await db.execute(
            select(DataTransfer).where(
                DataTransfer.organization_id == organization_id,
                DataTransfer.vendor_id.is_not(None),
                DataTransfer.status != "terminated",
            )
        )
    ).scalars().all()

    items: list[DecisionItem] = []
    for transfer in transfers:
        vendor = await db.get(Vendor, transfer.vendor_id)
        if vendor is None:
            continue
        recorded = (vendor.country or "").strip().upper()
        if not recorded or recorded == (transfer.destination_country or "").upper():
            continue
        items.append(
            DecisionItem(
                id=f"privacy-update-transfer-{transfer.id}",
                kind="suggested_update",
                title=f"{vendor.name}'s recorded location no longer matches this transfer",
                detail=(
                    f"The transfer records {transfer.destination_country}; the "
                    f"vendor now records {recorded}. A mechanism assessed "
                    "against one destination does not automatically cover "
                    "another."
                ),
                priority="medium",
                href=f"/compliance/privacy/transfers/{transfer.id}",
                recommendation=f"Reassess this transfer against {recorded}",
                recommendation_reason=(
                    "The vendor record and the transfer record disagree about "
                    "where the data goes."
                ),
                evidence=[
                    _fact("Transfer destination", transfer.destination_country, "declared"),
                    _fact("Vendor location", recorded, "declared"),
                    _fact("Mechanism on record", transfer.transfer_mechanism or "None", "declared"),
                ],
                impact="Nothing changes until you decide. The record is untouched.",
            )
        )
    return items


async def privacy_decisions(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[DecisionItem]:
    """Every privacy judgement waiting on a person, worst first."""
    items: list[DecisionItem] = []
    for producer in (
        _request_decisions,
        _drafted_activity_decisions,
        _lawful_basis_decisions,
        _article_nine_decisions,
        _screening_decisions,
        _dpia_assessment_decisions,
        _dpia_reassessment_decisions,
        _transfer_decisions,
        _suggested_updates,
    ):
        items.extend(await producer(db, organization_id))

    # Priority first, then what kind of thing it is — a request with a
    # statutory clock on it outranks a record that is merely incomplete,
    # and letting the alphabet break that tie put a lawful basis above an
    # overdue response.
    priority_order = {"high": 0, "medium": 1, "low": 2}
    kind_order = {
        "data_request": 0,
        "dpia_requirement": 1,
        # A completed assessment that no longer matches reality outranks
        # one still being written: the first is a record the organization
        # is currently relying on.
        "dpia_reassessment": 2,
        "dpia_assessment": 3,
        "transfer_mechanism": 4,
        "article_9_condition": 5,
        "lawful_basis": 6,
        "suggested_update": 7,
    }
    items.sort(
        key=lambda item: (
            priority_order.get(item.priority, 9),
            kind_order.get(item.kind, 9),
            item.title,
        )
    )
    return items


__all__ = ["CONFIDENCE", "DecisionItem", "privacy_decisions"]
