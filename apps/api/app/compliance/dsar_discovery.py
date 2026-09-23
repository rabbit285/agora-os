"""Searching the confirmed scope, and being honest about the rest.

The old discovery searched a fixed list of tables and reported a count
per table. Two things were wrong with that, and both mattered.

It ignored the scope. A person could exclude a source and discovery
would search it anyway, which makes confirming the scope theatre.

And it reported everything as searched. A processing activity that names
OpenAI as a processor got the same "0 matches" as a table that had
genuinely been queried and was genuinely empty. Those look identical in
a count and mean opposite things: one is evidence, the other is a gap
being reported as evidence. A case worker reading "0" signs a response
saying no data was found — for a system nobody looked in.

So every source lands in exactly one of five states, and the two that
mean "we did not look" say so in words:

    not_searched      excluded from scope, or added after the last run
    searched_none     queried, and the person is not there
    searched_found    queried, and here is where they appear
    search_failed     queried, and the query errored
    manual_follow_up  no connected source exists; a human must ask

Only `searched_none` is evidence of absence. The rest are various kinds
of "unknown", and the response package renders them as such.

Re-running is safe by construction. Rows are keyed by source, so a
second run updates the same row; a review decision already recorded is
never touched, and a follow-up task already raised is never raised
twice.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance import dsar_sources
from app.compliance.models import DSAR, DsarDiscoveredItem, DsarScopeSource

NOT_SEARCHED = "not_searched"
SEARCHED_NONE = "searched_none"
SEARCHED_FOUND = "searched_found"
SEARCH_FAILED = "search_failed"
MANUAL_FOLLOW_UP = "manual_follow_up"
# A processor holds the data and will not be searched by us; and a system
# nobody has connected. Both are "we have not looked", but they need
# different work from different people, so they are different states.
PROCESSOR_FOLLOW_UP = "processor_follow_up"
NOT_CONNECTED_STATE = "not_connected"

# Every state in which a person still has to do something before the
# response can claim to be complete.
OUTSTANDING = (MANUAL_FOLLOW_UP, PROCESSOR_FOLLOW_UP, NOT_CONNECTED_STATE, SEARCH_FAILED)

# States in which the source told us something about the requester. Used
# by the package builder to separate evidence from gaps.
CONCLUSIVE = (SEARCHED_NONE, SEARCHED_FOUND)


@dataclass
class Plan:
    """§8: what the run will do, before it does it."""

    total: int
    connected: int
    manual: int
    excluded: int
    # Named so the screen can say which sources need a person, rather
    # than only how many.
    manual_sources: list[str]
    connected_sources: list[str]


async def build_plan(db: AsyncSession, *, dsar: DSAR) -> Plan:
    """Describe the run without performing it."""
    scope = list(
        (
            await db.execute(
                select(DsarScopeSource).where(DsarScopeSource.dsar_id == dsar.id)
            )
        )
        .scalars()
        .all()
    )
    included = [row for row in scope if row.included is True]
    connected = [
        row for row in included if row.search_capability == dsar_sources.SEARCHABLE
    ]
    manual = [
        row for row in included if row.search_capability != dsar_sources.SEARCHABLE
    ]
    return Plan(
        total=len(included),
        connected=len(connected),
        manual=len(manual),
        excluded=len([row for row in scope if row.included is False]),
        manual_sources=[row.name for row in manual],
        connected_sources=[row.name for row in connected],
    )


def _searcher_for(source: DsarScopeSource):
    """The function that can actually query this source, if one exists.

    Two ways a source can be searchable, and no third: Veyntra owns the
    store, or the organization connected an integration that has a DSAR
    search adapter. Everything else returns None and becomes an honest
    follow-up rather than a silent zero.
    """
    if source.search_capability != dsar_sources.SEARCHABLE:
        return None
    native = dsar_sources.NATIVE_BY_KEY.get(source.source_key)
    if native is not None:
        return native.search
    return None


# How an unsearchable source is reported. Each capability maps to the
# state describing what actually happened to it, so nothing that was
# never queried can be read as a search that came back empty.
_UNSEARCHED_STATE = {
    dsar_sources.PROCESSOR_FOLLOW_UP: PROCESSOR_FOLLOW_UP,
    dsar_sources.NOT_CONNECTED: NOT_CONNECTED_STATE,
    dsar_sources.MANUAL_FOLLOW_UP: MANUAL_FOLLOW_UP,
    dsar_sources.UNSUPPORTED: MANUAL_FOLLOW_UP,
}


def _unsearched_detail(source: DsarScopeSource) -> str:
    """Why this source was not searched, in the reviewer's terms.

    Where a processing activity resolved to specific systems, they are
    named: "we did not look" is more actionable when it says where
    somebody has to go and look instead.
    """
    systems = [
        f"{row.get('name')} — "
        + dsar_sources.CAPABILITY_LABELS.get(row.get("capability"), str(row.get("capability")))
        for row in (source.potential_sources or [])
    ]
    base = f"Veyntra has not searched {source.name}."
    if systems:
        return base + " Potential sources: " + "; ".join(systems) + "."
    return (
        base
        + " No connected data source is available for it. Request the relevant "
        "records, or confirm retention, with the system owner."
    )


def _sensitivity_flags(source: DsarScopeSource, matches: int) -> list[str]:
    """What a person should look at before this goes out.

    Flags, never decisions. Article 15(4) — the rights and freedoms of
    others — is a legal judgement about specific content, and a product
    that resolved it automatically would be making somebody's exemption
    call for them and hiding it in a green tick.
    """
    if matches == 0:
        return []
    flags: list[str] = []
    if source.kind in ("vendor", "named_processor"):
        flags.append(
            "Held by a third-party processor — confirm what they hold before "
            "describing it as ours."
        )
    if source.kind == "ai_system":
        flags.append(
            "AI system records may contain conversation content with other people's "
            "data in it."
        )
    text = f"{source.name} {source.reason}".lower()
    if any(word in text for word in ("security", "incident", "investigation", "fraud")):
        flags.append(
            "May contain security or investigation material. Disclosing it can be "
            "exempt, but that is a legal decision, not an automatic one."
        )
    if any(word in text for word in ("legal", "counsel", "privileged", "litigation")):
        flags.append("May contain privileged legal content.")
    if any(word in text for word in ("medical", "health", "leave", "sickness")):
        flags.append(
            "May contain special-category health data. Confirm the requester is "
            "entitled to all of it before including."
        )
    return flags


async def _ensure_follow_up_task(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dsar: DSAR,
    item: DsarDiscoveredItem,
    source: DsarScopeSource,
    actor_user_id: uuid.UUID | None,
) -> None:
    """§20: raise the manual follow-up, exactly once.

    Idempotent on the item rather than on a title string: a task whose
    title somebody edited is still that item's task, and matching on
    wording would raise a second one.
    """
    from app.core.models import Task

    if item.task_id is not None:
        existing = await db.get(Task, item.task_id)
        if existing is not None:
            return

    task = Task(
        organization_id=organization_id,
        title=f"Retrieve {dsar.requester_name}'s records from {source.name}",
        description=(
            f"{source.name} is in scope for a {dsar.request_type} request from "
            f"{dsar.requester_name} <{dsar.requester_email}>, and Veyntra has no "
            f"connected data source for it.\n\n"
            f"Why it is in scope: {source.reason}\n\n"
            "Ask the system owner or processor for the records they hold, or confirm "
            "in writing that they hold none, and record the outcome here. The request "
            "cannot be completed until this is closed."
        ),
        module="compliance",
        status="open",
        priority="high",
        # Before the statutory deadline, not on it: the response still
        # has to be assembled after this comes back.
        due_at=dsar.due_at,
        created_by=actor_user_id,
        entity_type="dsar",
        entity_id=str(dsar.id),
    )
    db.add(task)
    await db.flush()
    item.task_id = task.id


async def run(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dsar: DSAR,
    actor_user_id: uuid.UUID | None,
) -> list[DsarDiscoveredItem]:
    """Search every confirmed source Veyntra can reach; flag the rest.

    Safe to re-run. Each source's row is updated in place, review
    decisions are preserved, and follow-up tasks are raised once.
    """
    email = dsar.requester_email.strip().lower()
    scope = list(
        (
            await db.execute(
                select(DsarScopeSource).where(DsarScopeSource.dsar_id == dsar.id)
            )
        )
        .scalars()
        .all()
    )
    existing = {
        row.source_key: row
        for row in (
            await db.execute(
                select(DsarDiscoveredItem).where(DsarDiscoveredItem.dsar_id == dsar.id)
            )
        )
        .scalars()
        .all()
    }

    for source in scope:
        item = existing.get(source.source_key)
        if item is None:
            item = DsarDiscoveredItem(
                organization_id=organization_id,
                dsar_id=dsar.id,
                source_key=source.source_key,
                source_name=source.name,
                search_state=NOT_SEARCHED,
            )
            db.add(item)
            existing[source.source_key] = item
        item.source_name = source.name

        if source.included is not True:  # noqa: SIM102 - reads better flat
            # Excluded, or nobody decided. Either way it was not searched
            # and the record says exactly that.
            item.search_state = NOT_SEARCHED
            item.matches = 0
            item.record_ids = []
            item.state_detail = (
                "Excluded from the confirmed search scope."
                if source.included is False
                else "Not part of the confirmed search scope."
            )
            # Nothing to disclose from a source nobody searched, and
            # nothing for a person to decide about either.
            if item.review_decision == "needs_review":
                item.review_decision = "exclude"
                item.review_reason = item.state_detail
            continue

        searcher = _searcher_for(source)
        if searcher is None:
            # No connected source. This is the case the old code reported
            # as "0 matches" — for tables belonging to product modules
            # this product no longer ships.
            item.search_state = _UNSEARCHED_STATE.get(
                source.search_capability, MANUAL_FOLLOW_UP
            )
            item.matches = 0
            item.record_ids = []
            item.state_detail = _unsearched_detail(source)
            item.sensitivity_flags = _sensitivity_flags(source, matches=1)
            if item.review_decision == "needs_review":
                item.review_reason = None
            await _ensure_follow_up_task(
                db,
                organization_id=organization_id,
                dsar=dsar,
                item=item,
                source=source,
                actor_user_id=actor_user_id,
            )
            continue

        try:
            matches, record_ids = await searcher(
                db, organization_id=organization_id, email=email
            )
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            # A failed search is not an empty one. Recorded as its own
            # state so nothing downstream can read it as "no data".
            item.search_state = SEARCH_FAILED
            item.matches = 0
            item.record_ids = []
            item.state_detail = f"The search could not be completed: {type(exc).__name__}."
            continue

        item.matches = matches
        item.record_ids = record_ids
        item.search_state = SEARCHED_FOUND if matches else SEARCHED_NONE
        item.state_detail = None
        flags = _sensitivity_flags(source, matches)
        item.sensitivity_flags = flags
        # Nothing found is nothing to decide. A record set that exists,
        # or that Veyntra flagged, waits for a person.
        if item.review_decision == "needs_review" and matches == 0:
            item.review_decision = "include"
            item.review_reason = "Searched; no records found."

    dsar.discovery_run_at = datetime.now(UTC)
    # The legacy blob still backs the older read paths. Rebuilt from the
    # rows rather than maintained separately, so the two cannot disagree.
    dsar.discovery_findings = _legacy_findings(email, list(existing.values()))

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dsar.discovery_run",
        object_type="dsar",
        object_id=str(dsar.id),
        after_state={
            "sources": len(existing),
            "searched": sum(
                1 for item in existing.values() if item.search_state in CONCLUSIVE
            ),
            "manual_follow_up": sum(
                1 for item in existing.values() if item.search_state == MANUAL_FOLLOW_UP
            ),
        },
    )
    await db.flush()
    return sorted(existing.values(), key=lambda item: item.source_name.lower())


def _legacy_findings(email: str, items: list[DsarDiscoveredItem]) -> dict[str, Any]:
    """The old findings shape, rebuilt from the rows.

    Kept so existing readers keep working. The coverage note now counts
    what was actually searched rather than claiming the whole list was.
    """
    searched = [item for item in items if item.search_state in CONCLUSIVE]
    manual = [item for item in items if item.search_state == MANUAL_FOLLOW_UP]
    failed = [item for item in items if item.search_state == SEARCH_FAILED]

    note = (
        f"Searched {len(searched)} connected source(s). "
        f"{len(manual)} source(s) require manual follow-up and have not been searched"
        + (f"; {len(failed)} search(es) failed" if failed else "")
        + ". Systems outside Veyntra, and unstructured content such as free-text "
        "notes or attachments, were not searched. A case worker remains responsible "
        "for the completeness of the response."
    )
    return {
        "email": email,
        "sources": [
            {
                "source": item.source_name,
                "matches": item.matches,
                "record_ids": item.record_ids or [],
                "state": item.search_state,
            }
            for item in items
        ],
        "total_matches": sum(item.matches for item in items),
        "coverage_note": note,
    }


__all__ = [
    "CONCLUSIVE",
    "MANUAL_FOLLOW_UP",
    "NOT_SEARCHED",
    "SEARCHED_FOUND",
    "SEARCHED_NONE",
    "SEARCH_FAILED",
    "Plan",
    "build_plan",
    "run",
]
