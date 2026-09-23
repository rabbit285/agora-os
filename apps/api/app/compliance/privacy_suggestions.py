"""Privacy records drafted from what the organization already declared.

The privacy module knew nothing about the rest of the product. An
organization that had registered an AI system — its purpose, the people
it affects, the data it processes, the vendor behind it — still had to
type all of that again into a RoPA form, and again into a transfer form.
Four privacy databases, maintained by hand, drifting apart.

So this reads the records that already exist and drafts the privacy
records they imply. Two rules make that safe rather than reckless.

**Nothing here is authoritative.** A RoPA is the statement an
organization makes to a regulator about its own processing. A table
assembled by inference is not that, however good the inference, so
proposals live in `PrivacySuggestion` and accepting one is what creates
the real record. The screens and the overview ignore proposals as
records entirely.

**Nothing here is a legal conclusion.** Every fact drafted is one the
organization already declared somewhere else — the AI system's own
stated purpose, its own `affected_users`, its own `processed_data`, the
vendor it names, the country recorded against that vendor. What is
never drafted is a lawful basis, an Article 9 condition, or a transfer
mechanism. Those are the judgements the review exists to obtain, and
pre-filling them would answer the only question the reviewer was
brought in for. They come back as "needs confirmation", every time.

Idempotence is structural. Each proposal carries a `source_key` derived
from what it is *about* — this AI system, this activity-and-vendor pair
— never from the wording of the draft, which would make identity only as
stable as the phrasing. Analysing the same records twice reconciles
against the existing row; the unique index makes that true under a
concurrent retry rather than merely likely.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import privacy_extraction, ropa_titles
from app.compliance.models import (
    AISystem,
    DataTransfer,
    PrivacySuggestion,
    ProcessingActivity,
    ProcessingActivityAISystem,
    ProcessingActivityVendor,
    Vendor,
)

logger = logging.getLogger("agora.compliance.privacy_suggestions")

PROCESSING_ACTIVITY = "processing_activity"
TRANSFER = "transfer"

# What the product says instead of guessing. Held as a constant because
# it appears in drafts, in the review UI and in the tests that stop a
# future change from quietly filling these in.
NEEDS_CONFIRMATION = "needs_confirmation"

# The EEA, plus the third countries with a standing adequacy decision.
# Deliberately a constant rather than a table: it is regulatory fact, it
# changes rarely, and a tenant editing it would be editing the law.
#
# Adequacy can be withdrawn — it has been before — so this decides only
# whether to *propose* a transfer record for review. It never concludes
# that a transfer is covered.
EEA = frozenset(
    {
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE",
        "GR", "HU", "IE", "IS", "IT", "LV", "LI", "LT", "LU", "MT", "NL",
        "NO", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    }
)

ADEQUACY = frozenset(
    {
        "AD", "AR", "CA", "FO", "GG", "IL", "IM", "JP", "JE", "NZ", "KR",
        "CH", "GB", "UY",
    }
)


def _normalise(value: str | None) -> str:
    return " ".join((value or "").split()).strip().lower()


@dataclass
class Draft:
    """One proposed record, and what it was read out of."""

    kind: str
    source_key: str
    title: str
    sources: list[dict] = field(default_factory=list)
    payload: dict = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """What an analysis pass proposed, and what it left alone."""

    created: int = 0
    # Proposals that already existed. Reported so a caller can tell
    # "nothing new" from "nothing looked at".
    unchanged: int = 0
    # Drafts skipped because a real record already covers them. The
    # product does not propose what somebody has already recorded.
    already_recorded: int = 0

    @property
    def proposed(self) -> int:
        return self.created + self.unchanged


async def _existing_activity_names(
    db: AsyncSession, organization_id: uuid.UUID
) -> set[str]:
    rows = (
        await db.execute(
            select(ProcessingActivity.name).where(
                ProcessingActivity.organization_id == organization_id
            )
        )
    ).all()
    return {_normalise(row[0]) for row in rows}


async def _linked_ai_system_ids(
    db: AsyncSession, organization_id: uuid.UUID
) -> set[uuid.UUID]:
    """AI systems a processing activity already accounts for.

    Proposing an activity for a system somebody has already recorded is
    noise, and the second-worst outcome after proposing a duplicate.
    """
    rows = (
        await db.execute(
            select(ProcessingActivityAISystem.ai_system_id)
            .join(
                ProcessingActivity,
                ProcessingActivity.id
                == ProcessingActivityAISystem.processing_activity_id,
            )
            .where(ProcessingActivity.organization_id == organization_id)
        )
    ).all()
    return {row[0] for row in rows}


def _data_categories(system: AISystem) -> list[str]:
    """The categories the AI system itself declares.

    `processed_data` is a list of `{"name": ..., "classification": ...}`
    the organization filled in when registering the system. Read as
    stated; nothing is added to it.
    """
    categories: list[str] = []
    for entry in system.processed_data or []:
        name = (entry.get("name") if isinstance(entry, dict) else None) or ""
        name = name.strip()
        if name and name not in categories:
            categories.append(name)
    return categories


def _data_subjects(system: AISystem) -> str:
    """Who the system says it affects.

    `affected_users` is the group the organization named as affected
    without necessarily using the system — which is usually exactly the
    data subjects of the processing, and the group an inventory keyed on
    "users" loses entirely.
    """
    people = [entry.strip() for entry in (system.affected_users or []) if entry.strip()]
    if not people:
        people = [
            entry.strip() for entry in (system.internal_users or []) if entry.strip()
        ]
    return ", ".join(people)


def draft_activity_from_ai_system(system: AISystem, vendor: Vendor | None) -> Draft:
    """A processing activity, as the AI system already describes it."""
    sources = [
        {
            "type": "ai_system",
            "id": str(system.id),
            "label": system.name,
        }
    ]
    if vendor is not None:
        sources.append(
            {"type": "vendor", "id": str(vendor.id), "label": vendor.name}
        )

    # §3: the activity is named after the processing, not after the
    # tool. "Support Assistant" is the name of a system; "AI Customer
    # Support" is the name of an operation, and only the second belongs
    # in an Article 30 record.
    purpose = (system.purpose or "").strip() or (system.description or "").strip()
    proposed = ropa_titles.derive(
        purpose=purpose, ai_system_name=system.name, is_ai=True
    )

    payload: dict = {
        "name": proposed.title,
        "title_basis": proposed.basis,
        "title_reason": proposed.reason,
        "title_needs_review": proposed.needs_review,
        "purpose": purpose,
        "data_subjects": _data_subjects(system),
        "data_categories": _data_categories(system),
        "ai_system_ids": [str(system.id)],
        "vendor_ids": [str(vendor.id)] if vendor else [],
        # The three things a person decides. Named rather than omitted,
        # so the review screen has somewhere to put the question.
        "legal_basis": NEEDS_CONFIRMATION,
        "special_category": None,
        "retention_period": None,
    }
    if vendor is not None and (vendor.country or "").strip():
        payload["processor_country"] = vendor.country.strip().upper()
    return Draft(
        kind=PROCESSING_ACTIVITY,
        # The system is the thing being described, so it is the identity —
        # the title can improve as the record does without the proposal
        # losing its place.
        source_key=f"ai_system:{system.id}",
        title=proposed.title,
        sources=sources,
        payload=payload,
    )


def draft_activity_from_document(
    found: privacy_extraction.DocumentPrivacyFacts,
) -> Draft:
    """A processing activity, as the document itself describes it.

    Every field carries the passage it was read from, so a reviewer
    checks the draft against the document rather than taking it on
    trust. The legal fields are absent for the same reason they are
    absent everywhere else: a document stating "we rely on legitimate
    interests" is the organization's claim about a judgement, not the
    judgement.
    """
    facts = found.facts
    stated_name = facts["name"].value if "name" in facts else None
    purpose = facts["purpose"].value if "purpose" in facts else ""

    # A document that names the activity is taken at its word; otherwise
    # the title is derived from the purpose the same way it is for an AI
    # system.
    if stated_name:
        title = stated_name
        title_basis, title_reason = "document", (
            f"Stated in {found.document_title}."
        )
    else:
        proposed = ropa_titles.derive(
            purpose=purpose, is_ai="ai_system" in facts
        )
        title = proposed.title
        title_basis, title_reason = proposed.basis, proposed.reason

    payload: dict = {
        "name": title,
        "title_basis": title_basis,
        "title_reason": title_reason,
        "purpose": purpose,
        "data_subjects": (
            facts["data_subjects"].value if "data_subjects" in facts else ""
        ),
        "data_categories": list(found.data_categories),
        "ai_system_ids": [],
        "vendor_ids": [],
        # Named as written, so a reviewer can link them to real records.
        # Not resolved to ids here: a document naming "OpenAI" is not
        # proof that it means the vendor row of that name, and guessing
        # would attach a processing activity to the wrong processor.
        "ai_system_named": facts["ai_system"].value if "ai_system" in facts else None,
        "vendor_named": facts["vendor"].value if "vendor" in facts else None,
        "destination_named": (
            facts["destination"].value if "destination" in facts else None
        ),
        "destination_country": found.destination_country,
        "retention_stated": facts["retention"].value if "retention" in facts else None,
        "owner_named": facts["owner"].value if "owner" in facts else None,
        # The judgements, named rather than answered — however plainly
        # the document states them.
        "legal_basis": NEEDS_CONFIRMATION,
        "special_category": None,
        "retention_period": None,
        # What a reviewer checks the draft against.
        "quotes": {
            name: fact.quote for name, fact in facts.items()
        },
        "dpia_indicators": [
            {"label": fact.value, "quote": fact.quote}
            for fact in found.dpia_indicators
        ],
    }

    return Draft(
        kind=PROCESSING_ACTIVITY,
        # The document is the thing being read, so it is the identity.
        # Re-analysing it reconciles rather than proposing again.
        source_key=f"document:{found.file_id}",
        title=title,
        sources=[
            {
                "type": "document",
                "id": str(found.file_id),
                "label": found.document_title,
            }
        ],
        payload=payload,
    )


def transfer_disposition(country: str | None) -> str:
    """Whether a destination is worth proposing a transfer record for.

    Three answers, and none of them is "lawful". Inside the EEA there is
    no third-country transfer to record. A country with an adequacy
    decision is a transfer, and one the product will say so about —
    while leaving the mechanism to a person, because adequacy can be
    withdrawn and the controller is the one who has to stand behind it.
    """
    code = (country or "").strip().upper()
    if not code:
        return "unknown"
    if code in EEA:
        return "inside_eea"
    if code in ADEQUACY:
        return "adequacy_candidate"
    return "third_country"


def draft_transfer(
    *,
    activity: ProcessingActivity,
    vendor: Vendor | None,
    disposition: str,
    recipient: str | None = None,
    country: str | None = None,
    detected_from: str | None = None,
) -> Draft:
    """A transfer the records imply, with the mechanism left open.

    `vendor` is optional because a processor a document named may have no
    row in the register yet. That is a transfer worth proposing — the
    data still leaves — and the proposal says the recipient is a name
    somebody wrote rather than a vetted record.
    """
    recipient = (recipient or (vendor.name if vendor else "")).strip()
    country = ((country or (vendor.country if vendor else "")) or "").strip().upper()
    note = (
        "This destination is covered by a standing adequacy decision. "
        "Confirm that it still applies to this transfer and record the "
        "basis you are relying on."
        if disposition == "adequacy_candidate"
        else (
            "This destination has no adequacy decision on record, so a "
            "transfer to it needs a mechanism and, where relevant, "
            "supplementary measures."
        )
    )
    sources: list[dict] = [
        {
            "type": "processing_activity",
            "id": str(activity.id),
            "label": activity.name,
        }
    ]
    if vendor is not None:
        sources.append(
            {"type": "vendor", "id": str(vendor.id), "label": vendor.name}
        )

    return Draft(
        kind=TRANSFER,
        # One transfer per activity-and-recipient pair. Keyed on the
        # recipient's name rather than a vendor id, so the same transfer
        # found through a link and through a document reconciles to one
        # proposal instead of two.
        source_key=f"activity:{activity.id}:recipient:{_normalise(recipient)}",
        title=f"{activity.name} → {recipient} ({country})",
        sources=sources,
        payload={
            "recipient_name": recipient,
            "destination_country": country,
            "vendor_id": str(vendor.id) if vendor else None,
            "processing_activity_id": str(activity.id),
            "disposition": disposition,
            # Where the inference came from, so a reviewer checks it
            # rather than trusting it.
            "detected_from": detected_from,
            # Carried so the review screen can show what is being sent
            # without the reviewer opening the ROPA in another tab.
            "data_subjects": activity.data_subjects,
            "data_categories": list(activity.data_categories or []),
            "purpose": activity.purpose,
            # Never guessed. Which mechanism covers a transfer is the
            # judgement the review exists to obtain, and a draft that
            # fills it in has made the reviewer's decision for them.
            "transfer_mechanism": NEEDS_CONFIRMATION,
            "note": note,
        },
    )


async def _existing_draft(
    db: AsyncSession, *, organization_id: uuid.UUID, draft: Draft
) -> bool:
    """Whether this exact proposal is already on file.

    Distinguishes "the same proposal again" — which reconciles — from
    "a different source proposing the same processing", which is the
    duplicate to suppress.
    """
    found = (
        await db.execute(
            select(PrivacySuggestion.id).where(
                PrivacySuggestion.organization_id == organization_id,
                PrivacySuggestion.kind == draft.kind,
                PrivacySuggestion.source_key == draft.source_key,
            )
        )
    ).first()
    return found is not None


async def _record_draft(
    db: AsyncSession, *, organization_id: uuid.UUID, draft: Draft
) -> bool:
    """Store a proposal, or reconcile with the one already there.

    Returns whether a new row was created. A proposal somebody already
    accepted or dismissed is left exactly as it is: re-analysis must not
    resurrect a decision a person made.
    """
    existing = (
        await db.execute(
            select(PrivacySuggestion).where(
                PrivacySuggestion.organization_id == organization_id,
                PrivacySuggestion.kind == draft.kind,
                PrivacySuggestion.source_key == draft.source_key,
            )
        )
    ).scalars().first()

    if existing is not None:
        if existing.status == "proposed":
            # The underlying records may have moved; the draft catches up
            # while the proposal keeps its identity and its place.
            existing.title = draft.title
            existing.sources = draft.sources
            existing.payload = draft.payload
        return False

    db.add(
        PrivacySuggestion(
            organization_id=organization_id,
            kind=draft.kind,
            source_key=draft.source_key,
            title=draft.title,
            sources=draft.sources,
            payload=draft.payload,
        )
    )
    await db.flush()
    return True


async def analyse(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> AnalysisResult:
    """Draft the privacy records the organization's own data implies.

    Reads AI systems, vendors and processing activities. Writes only
    proposals — never a RoPA entry, never a transfer, never a lawful
    basis.
    """
    result = AnalysisResult()

    vendors = {
        vendor.id: vendor
        for vendor in (
            await db.execute(
                select(Vendor).where(Vendor.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    }
    systems = list(
        (
            await db.execute(
                select(AISystem).where(AISystem.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    recorded_names = await _existing_activity_names(db, organization_id)
    covered_systems = await _linked_ai_system_ids(db, organization_id)
    # Processing already proposed, by the name it would be given. Two
    # registrations of the same tool are two AI-system rows and so two
    # distinct `source_key`s — but they describe one activity, and
    # proposing it twice is the duplicate a reviewer would have to
    # untangle by hand.
    proposed_titles = {
        _normalise(row[0])
        for row in (
            await db.execute(
                select(PrivacySuggestion.title).where(
                    PrivacySuggestion.organization_id == organization_id,
                    PrivacySuggestion.kind == PROCESSING_ACTIVITY,
                    PrivacySuggestion.status == "proposed",
                )
            )
        ).all()
    }

    # --- processing activities from AI systems ---------------------------
    for system in systems:
        if system.id in covered_systems:
            result.already_recorded += 1
            continue
        if _normalise(system.name) in recorded_names:
            # Somebody has already written this down under the same name.
            # Proposing it again would be the product arguing with its
            # own user.
            result.already_recorded += 1
            continue
        vendor = vendors.get(system.vendor_id) if system.vendor_id else None
        draft = draft_activity_from_ai_system(system, vendor)
        # Compared on the drafted title, which is what the activity will
        # be called. Comparing the system's name stopped matching once
        # activities were named after the processing rather than the
        # tool, so a second registration proposed a second activity for
        # processing already on record.
        title_key = _normalise(draft.title)
        if title_key in recorded_names:
            result.already_recorded += 1
            continue
        if title_key in proposed_titles and not await _existing_draft(
            db, organization_id=organization_id, draft=draft
        ):
            # This processing is already waiting on a person under the
            # same name. A second card for it would double the queue
            # without adding a decision.
            result.already_recorded += 1
            continue
        if await _record_draft(db, organization_id=organization_id, draft=draft):
            result.created += 1
            proposed_titles.add(title_key)
        else:
            result.unchanged += 1

    # --- processing activities from privacy documents ---------------------
    #
    # The missing half: a privacy policy or processing description could
    # be analysed, mapped to controls and indexed for the Copilot while
    # the RoPA stayed empty, because nothing read the text.
    for found in await privacy_extraction.facts_from_documents(
        db, organization_id=organization_id
    ):
        draft = draft_activity_from_document(found)
        title_key = _normalise(draft.title)
        if title_key in recorded_names:
            result.already_recorded += 1
            continue
        if title_key in proposed_titles and not await _existing_draft(
            db, organization_id=organization_id, draft=draft
        ):
            result.already_recorded += 1
            continue
        if await _record_draft(db, organization_id=organization_id, draft=draft):
            result.created += 1
            proposed_titles.add(title_key)
        else:
            result.unchanged += 1

    # --- transfers from activities that name a processor ------------------
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
    activity_ids = [activity.id for activity in activities]
    # Scoped to this organization's activities. The query used to select
    # every link row in the database and rely on the vendor lookup below
    # to miss on other tenants' ids — which worked, and read as though
    # cross-tenant rows were expected.
    links = (
        (
            await db.execute(
                select(
                    ProcessingActivityVendor.processing_activity_id,
                    ProcessingActivityVendor.vendor_id,
                ).where(
                    ProcessingActivityVendor.processing_activity_id.in_(activity_ids)
                )
            )
        ).all()
        if activity_ids
        else []
    )
    by_activity: dict[uuid.UUID, list[uuid.UUID]] = {}
    for activity_id, vendor_id in links:
        by_activity.setdefault(activity_id, []).append(vendor_id)

    # An activity linked to an AI system reaches that system's vendor.
    # A document-derived activity has no vendor link of its own, and the
    # processor is a fact about the tool it runs through.
    ai_links = (
        (
            await db.execute(
                select(
                    ProcessingActivityAISystem.processing_activity_id,
                    AISystem.vendor_id,
                )
                .join(AISystem, AISystem.id == ProcessingActivityAISystem.ai_system_id)
                .where(
                    ProcessingActivityAISystem.processing_activity_id.in_(activity_ids),
                    AISystem.vendor_id.is_not(None),
                )
            )
        ).all()
        if activity_ids
        else []
    )
    for activity_id, vendor_id in ai_links:
        known = by_activity.setdefault(activity_id, [])
        if vendor_id not in known:
            known.append(vendor_id)

    # And the vendor register, by name, for what a document called a
    # processor. Matching a written name to a vetted record is exactly
    # the inference this module refuses to make silently — so the match
    # is used to *propose*, and the proposal says where the name came
    # from.
    by_name = {_normalise(vendor.name): vendor for vendor in vendors.values()}

    existing_transfers = {
        (row[0], (row[1] or "").strip().lower())
        for row in (
            await db.execute(
                select(
                    DataTransfer.processing_activity_id, DataTransfer.recipient_name
                ).where(DataTransfer.organization_id == organization_id)
            )
        ).all()
    }

    for activity in activities:
        # One proposal per activity-and-recipient however many edges
        # reach it: a vendor linked directly, through an AI system, and
        # named in the source document is one transfer, not three.
        seen_recipients: set[str] = set()

        candidates: list[tuple[Vendor | None, str, str]] = []
        for vendor_id in by_activity.get(activity.id, []):
            vendor = vendors.get(vendor_id)
            if vendor is not None:
                candidates.append(
                    (vendor, vendor.name, "a processor recorded against this activity")
                )
        if activity.processor_named:
            matched = by_name.get(_normalise(activity.processor_named))
            candidates.append(
                (
                    matched,
                    matched.name if matched else activity.processor_named,
                    f"“{activity.processor_named}” named in the source document",
                )
            )

        for vendor, recipient, detected_from in candidates:
            key = _normalise(recipient)
            if key in seen_recipients:
                continue
            seen_recipients.add(key)

            # The vendor record's country wins where there is one: it is
            # maintained, and a document is a snapshot of what somebody
            # wrote once. The document's destination is the fallback.
            country = (vendor.country if vendor else None) or (
                activity.destination_country_named
            )
            disposition = transfer_disposition(country)
            if disposition in ("inside_eea", "unknown"):
                # No third-country transfer to record, or nowhere
                # recorded to reason about. Neither is a finding.
                continue
            if (activity.id, key) in existing_transfers:
                result.already_recorded += 1
                continue
            draft = draft_transfer(
                activity=activity,
                vendor=vendor,
                disposition=disposition,
                recipient=recipient,
                country=country,
                detected_from=detected_from,
            )
            if await _record_draft(db, organization_id=organization_id, draft=draft):
                result.created += 1
            else:
                result.unchanged += 1

    await db.flush()
    logger.info(
        "Privacy analysis for %s: created=%d unchanged=%d already_recorded=%d",
        organization_id,
        result.created,
        result.unchanged,
        result.already_recorded,
    )
    return result


async def open_suggestions(
    db: AsyncSession, *, organization_id: uuid.UUID, kind: str | None = None
) -> list[PrivacySuggestion]:
    query = select(PrivacySuggestion).where(
        PrivacySuggestion.organization_id == organization_id,
        PrivacySuggestion.status == "proposed",
    )
    if kind:
        query = query.where(PrivacySuggestion.kind == kind)
    return list(
        (await db.execute(query.order_by(PrivacySuggestion.created_at.desc())))
        .scalars()
        .all()
    )


# --- what a data request should look at ---------------------------------


@dataclass
class DataLocation:
    """Somewhere this organization's records say personal data lives."""

    label: str
    kind: str
    record_id: uuid.UUID
    reason: str


async def data_locations(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[DataLocation]:
    """Where to look when answering a data request.

    Assembled from the organization's own inventory: the processing
    activities it recorded, the AI systems it registered, the processors
    it named. This is a **search scope**, not a search — nothing here
    reads anybody's personal data or discloses any of it. Deciding what
    was actually found, and what may lawfully be released, stays with
    the person answering the request.
    """
    locations: list[DataLocation] = []

    for activity in (
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
    ):
        locations.append(
            DataLocation(
                label=activity.name,
                kind="processing_activity",
                record_id=activity.id,
                reason=(
                    f"Recorded as processing {activity.data_subjects or 'personal data'}."
                ),
            )
        )

    for system in (
        (
            await db.execute(
                select(AISystem).where(AISystem.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    ):
        categories = _data_categories(system)
        locations.append(
            DataLocation(
                label=system.name,
                kind="ai_system",
                record_id=system.id,
                reason=(
                    f"Registered as processing {', '.join(categories[:3])}."
                    if categories
                    else "Registered as an AI system that processes personal data."
                ),
            )
        )

    for vendor in (
        (
            await db.execute(
                select(Vendor).where(
                    Vendor.organization_id == organization_id,
                    Vendor.status == "active",
                )
            )
        )
        .scalars()
        .all()
    ):
        where = f" in {vendor.country}" if (vendor.country or "").strip() else ""
        locations.append(
            DataLocation(
                label=vendor.name,
                kind="vendor",
                record_id=vendor.id,
                reason=f"Processor on record{where}.",
            )
        )

    return locations


__all__ = [
    "ADEQUACY",
    "EEA",
    "NEEDS_CONFIRMATION",
    "PROCESSING_ACTIVITY",
    "TRANSFER",
    "AnalysisResult",
    "DataLocation",
    "Draft",
    "analyse",
    "data_locations",
    "draft_activity_from_ai_system",
    "draft_transfer",
    "open_suggestions",
    "transfer_disposition",
]
