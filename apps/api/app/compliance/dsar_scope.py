"""Which systems a request should reach, ranked, for a person to confirm.

Veyntra proposes; a person confirms; discovery obeys the confirmation
exactly.

Four rules run through the module.

**Relevance is about the person, never about our plumbing.** A source is
likely relevant because the requester's relationship and the activity's
recorded data subjects line up — not because Veyntra happens to be able
to query it cheaply. The two were conflated once, and the result was
that the easiest source to search was also, by construction, the most
"relevant" one. Search capability lives in its own field and never
touches the ranking.

**A processing activity is compliance context, not a database.** "AI
Customer Support" says this person's data may be in the systems used for
that processing. Those systems are resolved separately, each with its own
connection state, and the activity itself is almost never searchable.

**Rank, never filter.** Jane Doe writing from a personal address almost
certainly has nothing in "Employee medical-leave administration", and
saying so saves a reviewer time. Dropping it would hide a source from
somebody who might know she is also a contractor. A wrong ranking costs a
click; a wrong filter costs a response its completeness.

**Reconcile, never duplicate.** `source_key` is derived from what a
source *is*, so re-running suggestion refreshes the reasoning on a row
somebody already decided about instead of adding a second copy of it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import dsar_sources
from app.compliance.dsar_sources import (
    HIGH,
    LOW,
    MANUAL_FOLLOW_UP,
    NOT_CONNECTED,
    POSSIBLE,
    PROCESSOR_FOLLOW_UP,
    RELEVANCE_ORDER,
    SEARCHABLE,
)
from app.compliance.models import (
    DSAR,
    AISystem,
    DsarScopeSource,
    ProcessingActivity,
    ProcessingActivityAISystem,
    ProcessingActivityVendor,
    Vendor,
)
from app.core.models import Organization

# Words that mark an activity as being about the workforce rather than
# the customer base. Deliberately a small, boring list: the point is to
# order a short list for a human, not to classify text.
_EMPLOYEE_WORDS = (
    "employee",
    "staff",
    "worker",
    "personnel",
    "candidate",
    "applicant",
    "contractor",
)
_CUSTOMER_WORDS = ("customer", "client", "subscriber", "user", "consumer", "buyer")

# Free mailbox providers. An address at one of these says the person is
# not writing from the organization's own domain, which is a weak signal
# about their relationship and is treated as weak.
_PUBLIC_MAILBOXES = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "yahoo.com",
        "icloud.com",
        "me.com",
        "proton.me",
        "protonmail.com",
        "aol.com",
        "gmx.com",
        "mail.com",
        "yandex.com",
        "zoho.com",
    }
)


@dataclass
class Relationship:
    """What can be told about the requester from the request itself.

    Everything here is a guess from an email address, and the naming says
    so: `likely_employee` rather than `is_employee`. The product never
    acts on it alone — it orders a list somebody then confirms.
    """

    likely_employee: bool
    likely_customer: bool
    reason: str
    # True when nothing about the requester is knowable. Everything then
    # ranks "possible": over-assuming a relationship is how a scope ends
    # up confidently wrong.
    unknown: bool = False


def _domain(email: str) -> str:
    _, _, domain = (email or "").strip().lower().partition("@")
    return domain


def classify_requester(
    *, email: str, organization: Organization | None, member_domains: set[str]
) -> Relationship:
    """Guess the requester's relationship to the organization.

    A match against a domain the organization's own accounts use is the
    strongest available signal, and it is still only a signal: people use
    personal addresses for work requests and work addresses for personal
    ones.
    """
    domain = _domain(email)
    if not domain:
        return Relationship(
            likely_employee=False,
            likely_customer=False,
            reason="No email domain to reason from.",
            unknown=True,
        )

    if domain in member_domains and domain not in _PUBLIC_MAILBOXES:
        return Relationship(
            likely_employee=True,
            likely_customer=True,
            reason=(
                f"The requester wrote from {domain}, the domain this organization's "
                "own accounts use."
            ),
        )

    if domain in _PUBLIC_MAILBOXES:
        return Relationship(
            likely_employee=False,
            likely_customer=True,
            reason=(
                f"The requester wrote from {domain}, a personal mailbox rather than "
                "this organization's domain, and no employment relationship is known."
            ),
        )

    return Relationship(
        likely_employee=False,
        likely_customer=True,
        reason=(
            f"The requester wrote from {domain}, an external domain, and no "
            "employment relationship is known."
        ),
    )


# Phrases where "employee" means somebody else's staff. A register
# entry covering "customer employees who contact support" is about the
# customer side, and reading it as workforce data would tell a reviewer
# the activity covers their own staff when it does not.
_THIRD_PARTY_STAFF = (
    "customer employee",
    "customers' employee",
    "customer employees",
    "employees of customers",
    "client employee",
    "employees of clients",
    "vendor employee",
    "supplier employee",
)


def _subject_kind(activity: ProcessingActivity) -> tuple[bool, bool]:
    """Whether an activity records employees, customers, or says nothing.

    "Employees" here means *this organization's* workforce. Somebody
    else's staff are customer-side contacts, and the distinction decides
    whether an employee-only activity is ruled out for an outside
    requester.
    """
    text = " ".join(
        filter(
            None,
            [(activity.data_subjects or ""), (activity.name or ""), (activity.purpose or "")],
        )
    ).lower()
    workforce_text = text
    for phrase in _THIRD_PARTY_STAFF:
        workforce_text = workforce_text.replace(phrase, "")
    return (
        any(word in workforce_text for word in _EMPLOYEE_WORDS),
        any(word in text for word in _CUSTOMER_WORDS),
    )


def rank_activity(
    activity: ProcessingActivity, relationship: Relationship, *, request_type: str = "access"
) -> tuple[str, str]:
    """Rank one activity against what is known about the requester.

    Returns the ranking and the argument for it. The argument matters as
    much as the answer: it is what lets a reviewer notice the product has
    reasoned from a fact that happens to be wrong.
    """
    about_employees, about_customers = _subject_kind(activity)

    # An activity recording nothing about its data subjects cannot be
    # ranked down. Missing information is not evidence of irrelevance,
    # and this is exactly the record most likely to be a blind spot.
    if not about_employees and not about_customers:
        return (
            POSSIBLE,
            "No data subjects are recorded for this activity, so its relevance "
            "cannot be judged. Left in scope rather than ranked down — an "
            "incomplete register is not evidence this person's data is absent.",
        )

    # Nothing is known about the requester, so nothing is ruled out.
    if relationship.unknown:
        return (
            POSSIBLE,
            "The requester's relationship to this organization is not known, so "
            "this activity cannot be ruled in or out.",
        )

    if about_employees and about_customers:
        return (
            HIGH,
            "The activity records both employees and customers, so it covers this "
            "requester either way.",
        )

    if about_employees and not relationship.likely_employee:
        return (
            LOW,
            f"The activity covers employees. {relationship.reason} Include it anyway "
            "if this person is also staff or a contractor.",
        )

    if about_customers and relationship.likely_customer:
        return (
            HIGH,
            f"The activity explicitly covers customer records, and this is a "
            f"customer {request_type} request. {relationship.reason}",
        )

    if about_employees and relationship.likely_employee:
        return (
            HIGH,
            f"The activity covers employees. {relationship.reason}",
        )

    return (
        POSSIBLE,
        "The recorded data subjects neither clearly match nor clearly exclude this "
        "requester.",
    )


def source_key_for(kind: str, identifier: str) -> str:
    """The logical identity of a source: what it is, never how it reads."""
    return f"{kind}:{identifier.strip().lower()}"


@dataclass
class Proposal:
    source_key: str
    kind: str
    name: str
    reason: str
    relevance: str
    relevance_reason: str
    linked_systems: list[str]
    search_capability: str
    record_id: uuid.UUID | None
    potential_sources: list[dict] = field(default_factory=list)


async def _member_domains(db: AsyncSession, organization_id: uuid.UUID) -> set[str]:
    """Domains this organization's own accounts use."""
    from app.core.models import Membership
    from app.identity.models import User

    rows = (
        await db.execute(
            select(User.email)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == organization_id)
        )
    ).scalars().all()
    return {domain for email in rows if (domain := _domain(email or ""))}


async def propose(
    db: AsyncSession, *, organization_id: uuid.UUID, dsar: DSAR
) -> list[Proposal]:
    """Build the ranked candidate scope from the privacy graph.

    Reads only records the organization already maintains. Nothing here
    searches for the requester — that is discovery, and it runs after a
    person has confirmed this list.
    """
    organization = await db.get(Organization, organization_id)
    relationship = classify_requester(
        email=dsar.requester_email,
        organization=organization,
        member_domains=await _member_domains(db, organization_id),
    )
    connected = await dsar_sources.connected_connectors(
        db, organization_id=organization_id
    )

    proposals: list[Proposal] = []

    # --- what Veyntra genuinely holds itself ---------------------------
    for native in dsar_sources.NATIVE_SOURCES:
        proposals.append(
            Proposal(
                source_key=native.key,
                kind="internal",
                name=native.name,
                reason=native.reason,
                relevance=native.relevance,
                relevance_reason=native.relevance_reason,
                linked_systems=[],
                search_capability=SEARCHABLE,
                record_id=None,
            )
        )

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
    if not activities:
        return proposals

    activity_ids = [activity.id for activity in activities]

    systems_by_activity: dict[uuid.UUID, list[AISystem]] = {}
    for system, activity_id in (
        await db.execute(
            select(AISystem, ProcessingActivityAISystem.processing_activity_id)
            .join(
                ProcessingActivityAISystem,
                ProcessingActivityAISystem.ai_system_id == AISystem.id,
            )
            .where(ProcessingActivityAISystem.processing_activity_id.in_(activity_ids))
        )
    ).all():
        systems_by_activity.setdefault(activity_id, []).append(system)

    vendors_by_activity: dict[uuid.UUID, list[Vendor]] = {}
    for vendor, activity_id in (
        await db.execute(
            select(Vendor, ProcessingActivityVendor.processing_activity_id)
            .join(ProcessingActivityVendor, ProcessingActivityVendor.vendor_id == Vendor.id)
            .where(ProcessingActivityVendor.processing_activity_id.in_(activity_ids))
        )
    ).all():
        vendors_by_activity.setdefault(activity_id, []).append(vendor)

    for activity in activities:
        relevance, relevance_reason = rank_activity(
            activity, relationship, request_type=dsar.request_type
        )
        systems = systems_by_activity.get(activity.id, [])
        vendors = vendors_by_activity.get(activity.id, [])

        # Resolve the activity to the systems that actually hold data.
        # This is the step that stops a RoPA entry being mistaken for a
        # database: the activity says where to look next, and each of
        # these answers what can be done about it.
        potential: list[dict] = []
        for system in systems:
            capability, detail = dsar_sources.capability_for_system(
                name=system.name,
                connector_key=dsar_sources.match_connector(system.name),
                connected=connected,
            )
            potential.append(
                {
                    "name": system.name,
                    "kind": "ai_system",
                    "capability": capability,
                    "detail": detail,
                }
            )
        for vendor in vendors:
            # A processor's systems are not ours to search, however well
            # connected we are to them.
            potential.append(
                {
                    "name": vendor.name,
                    "kind": "vendor",
                    "capability": PROCESSOR_FOLLOW_UP,
                    "detail": (
                        f"{vendor.name} processes this data on your behalf"
                        + (f", in {vendor.country}" if vendor.country else "")
                        + ". Ask them what they hold; Veyntra cannot search a "
                        "processor's systems."
                    ),
                }
            )
        named = (activity.processor_named or "").strip()
        if named and not any(row["name"].lower() == named.lower() for row in potential):
            potential.append(
                {
                    "name": named,
                    "kind": "named_processor",
                    "capability": PROCESSOR_FOLLOW_UP,
                    "detail": (
                        f"Named as a processor for {activity.name} in a source "
                        "document, with no vendor record yet."
                    ),
                }
            )

        # The activity itself is searchable only if every system under it
        # is — and today none are. It is a register entry either way.
        capability = (
            SEARCHABLE
            if potential and all(row["capability"] == SEARCHABLE for row in potential)
            else MANUAL_FOLLOW_UP
        )

        proposals.append(
            Proposal(
                source_key=source_key_for("processing_activity", str(activity.id)),
                kind="processing_activity",
                name=activity.name,
                reason=(
                    f"Covers {activity.data_subjects or 'unspecified data subjects'}"
                    + (f" for {activity.purpose}" if activity.purpose else "")
                    + "."
                ),
                relevance=relevance,
                relevance_reason=relevance_reason,
                linked_systems=[row["name"] for row in potential],
                search_capability=capability,
                record_id=activity.id,
                potential_sources=potential,
            )
        )

    return proposals


async def reconcile(
    db: AsyncSession, *, organization_id: uuid.UUID, dsar: DSAR
) -> list[DsarScopeSource]:
    """Persist the proposals, preserving decisions already made.

    Re-running refreshes each source's reasoning, ranking and capability
    and leaves `included` alone. A source that has since disappeared from
    the register is removed only if nobody has decided about it —
    deleting a row somebody deliberately included would quietly narrow an
    approved scope.
    """
    proposals = await propose(db, organization_id=organization_id, dsar=dsar)

    existing = {
        row.source_key: row
        for row in (
            await db.execute(
                select(DsarScopeSource).where(DsarScopeSource.dsar_id == dsar.id)
            )
        )
        .scalars()
        .all()
    }
    proposed_keys = {proposal.source_key for proposal in proposals}

    for proposal in proposals:
        row = existing.get(proposal.source_key)
        if row is None:
            db.add(
                DsarScopeSource(
                    organization_id=organization_id,
                    dsar_id=dsar.id,
                    source_key=proposal.source_key,
                    kind=proposal.kind,
                    name=proposal.name,
                    reason=proposal.reason,
                    relevance=proposal.relevance,
                    relevance_reason=proposal.relevance_reason,
                    linked_systems=proposal.linked_systems,
                    potential_sources=proposal.potential_sources,
                    search_capability=proposal.search_capability,
                    record_id=proposal.record_id,
                    # Anything that might hold this person's data starts
                    # selected; only what the product argues is unrelated
                    # starts unticked. Nothing starts *excluded* — that is
                    # a decision, and the product does not make it.
                    included=None if proposal.relevance == LOW else True,
                )
            )
            continue

        row.name = proposal.name
        row.reason = proposal.reason
        row.relevance = proposal.relevance
        row.relevance_reason = proposal.relevance_reason
        row.linked_systems = proposal.linked_systems
        row.potential_sources = proposal.potential_sources
        row.search_capability = proposal.search_capability

    for key, row in existing.items():
        if key not in proposed_keys and row.included is None and not row.added_by_user:
            await db.delete(row)

    await db.flush()
    return list(
        (
            await db.execute(
                select(DsarScopeSource)
                .where(DsarScopeSource.dsar_id == dsar.id)
                .order_by(DsarScopeSource.name)
            )
        )
        .scalars()
        .all()
    )


def sort_key(source: DsarScopeSource) -> tuple:
    """Screen order: what matters most, first.

    Relevance leads. Capability breaks ties — among equally relevant
    sources, the ones needing a person are worth seeing early, because
    they are the ones with lead time.
    """
    return (
        RELEVANCE_ORDER.get(source.relevance, 1),
        0 if source.search_capability != SEARCHABLE else 1,
        source.name.lower(),
    )


__all__ = [
    "HIGH",
    "LOW",
    "MANUAL_FOLLOW_UP",
    "NOT_CONNECTED",
    "POSSIBLE",
    "PROCESSOR_FOLLOW_UP",
    "SEARCHABLE",
    "Proposal",
    "Relationship",
    "classify_requester",
    "propose",
    "rank_activity",
    "reconcile",
    "sort_key",
    "source_key_for",
]
