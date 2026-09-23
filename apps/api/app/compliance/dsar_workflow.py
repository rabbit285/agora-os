"""Where a data request actually is, and what it needs next.

The old status told you a request was "in progress", which is true of
everything between logging it and sending it — the entire span where
somebody needs to know what to do. This derives the real position from
the record and names the single next action.

Two decisions shape the module.

**The phase is derived, never set.** Nobody can drag a request to
"ready to respond"; it arrives there when the identity is verified, the
scope is confirmed, discovery has run, every finding has a decision, and
a package has been approved. A status somebody can set by hand is a
status that stops describing reality the moment it is convenient.

**Readiness is a list of blockers, not a boolean.** "Cannot complete
yet" is useless; "3 discovered records still need a decision" is
something a person can act on. Each blocker names what is missing and
what would clear it.

The clock is not a phase. A request is overdue *and* somewhere — those
are different axes, and collapsing them loses the one that says what to
do. Deadlines live in `privacy_deadlines`; this module reports them
alongside the phase without letting either overwrite the other.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    DSAR,
    DsarDiscoveredItem,
    DsarResponsePackage,
    DsarScopeSource,
)

RECEIVED = "received"
IDENTITY_VERIFICATION = "identity_verification"
SCOPE_REVIEW = "scope_review"
DISCOVERY = "discovery"
RESPONSE_REVIEW = "response_review"
READY_TO_RESPOND = "ready_to_respond"
COMPLETED = "completed"
BLOCKED = "blocked"

PHASE_LABELS = {
    RECEIVED: "Received",
    IDENTITY_VERIFICATION: "Identity verification",
    SCOPE_REVIEW: "Scope review",
    DISCOVERY: "Discovery",
    RESPONSE_REVIEW: "Response review",
    READY_TO_RESPOND: "Ready to respond",
    COMPLETED: "Completed",
    BLOCKED: "Blocked",
}

# The order a request moves through, used to render progress. Blocked is
# absent on purpose: it is a condition on a phase, not a step between
# two of them.
PHASE_ORDER = (
    RECEIVED,
    IDENTITY_VERIFICATION,
    SCOPE_REVIEW,
    DISCOVERY,
    RESPONSE_REVIEW,
    READY_TO_RESPOND,
    COMPLETED,
)


@dataclass
class Blocker:
    """One thing standing between the request and its next step."""

    code: str
    message: str
    # Where to go to clear it, as a section of the request page.
    anchor: str


@dataclass
class NextAction:
    """The single thing to do now, said as an instruction."""

    label: str
    detail: str
    anchor: str


@dataclass
class WorkflowState:
    phase: str
    phase_label: str
    next_action: NextAction | None
    blockers: list[Blocker] = field(default_factory=list)
    # Counts the screen needs but should not compute by loading every
    # child row itself.
    scope_total: int = 0
    scope_included: int = 0
    scope_undecided: int = 0
    discovered_total: int = 0
    needs_review: int = 0
    manual_follow_ups: int = 0
    open_follow_ups: int = 0
    package_status: str | None = None


@dataclass
class _Children:
    scope: list[DsarScopeSource]
    items: list[DsarDiscoveredItem]
    package: DsarResponsePackage | None


async def _load(db: AsyncSession, dsar: DSAR) -> _Children:
    scope = list(
        (
            await db.execute(
                select(DsarScopeSource).where(DsarScopeSource.dsar_id == dsar.id)
            )
        )
        .scalars()
        .all()
    )
    items = list(
        (
            await db.execute(
                select(DsarDiscoveredItem).where(DsarDiscoveredItem.dsar_id == dsar.id)
            )
        )
        .scalars()
        .all()
    )
    package = (
        (
            await db.execute(
                select(DsarResponsePackage)
                .where(DsarResponsePackage.dsar_id == dsar.id)
                .order_by(DsarResponsePackage.version.desc())
            )
        )
        .scalars()
        .first()
    )
    return _Children(scope=scope, items=items, package=package)


async def _open_follow_up_count(db: AsyncSession, items: list[DsarDiscoveredItem]) -> int:
    """Manual follow-ups still outstanding.

    §20: a source Veyntra cannot search does not fail the request, but
    its task has to be finished before the response claims to be
    complete. Read from the task rather than mirrored onto the item, so
    closing the task in the task list is enough.
    """
    from app.core.models import Task

    task_ids = [item.task_id for item in items if item.task_id is not None]
    if not task_ids:
        return 0
    rows = (
        await db.execute(select(Task.status).where(Task.id.in_(task_ids)))
    ).scalars().all()
    return sum(1 for status in rows if status not in ("done", "cancelled"))


async def _follow_up_done(db: AsyncSession, item: DsarDiscoveredItem) -> bool:
    """Whether the manual search for this source has actually been done.

    The task is the record of the work. A source with no task raised has
    nothing standing in for the search, so it counts as unresolved.
    """
    from app.core.models import Task

    if item.task_id is None:
        return False
    task = await db.get(Task, item.task_id)
    return task is not None and task.status in ("done", "cancelled")


def _requires_disclosure(dsar: DSAR) -> bool:
    """Whether answering this request hands over personal data.

    Access and portability disclose; erasure and rectification act. All
    four still need identity verification — acting on the wrong person's
    record is its own harm — but only the disclosing ones need the full
    review-and-approve path before anything leaves.
    """
    return dsar.request_type in ("access", "portability")


async def evaluate(db: AsyncSession, *, dsar: DSAR) -> WorkflowState:
    """Derive the phase, the next action, and what is blocking."""
    children = await _load(db, dsar)
    scope = children.scope
    items = children.items
    package = children.package

    decided = [row for row in scope if row.included is not None]  # noqa: F841
    included = [row for row in scope if row.included is True]
    undecided = [row for row in scope if row.included is None]
    needs_review = [item for item in items if item.review_decision == "needs_review"]
    manual = [item for item in items if item.search_state == "manual_follow_up"]
    open_follow_ups = await _open_follow_up_count(db, items)

    state = WorkflowState(
        phase=RECEIVED,
        phase_label=PHASE_LABELS[RECEIVED],
        next_action=None,
        scope_total=len(scope),
        scope_included=len(included),
        scope_undecided=len(undecided),
        discovered_total=len(items),
        needs_review=len(needs_review),
        manual_follow_ups=len(manual),
        open_follow_ups=open_follow_ups,
        package_status=package.status if package else None,
    )

    if dsar.status in ("fulfilled", "rejected") or dsar.fulfilled_at is not None:
        state.phase = COMPLETED
        state.phase_label = PHASE_LABELS[COMPLETED]
        return state

    # Identity first, always. Every other step either discloses data or
    # acts on a record, and both are wrong if the requester is not who
    # they say they are.
    if dsar.verification_status == "failed":
        state.phase = BLOCKED
        state.phase_label = PHASE_LABELS[BLOCKED]
        state.blockers.append(
            Blocker(
                "identity_failed",
                "Identity verification failed. Answering this request would risk "
                "disclosing personal data to the wrong person.",
                "identity",
            )
        )
        state.next_action = NextAction(
            "Decide how to proceed",
            "Verification failed. Either re-verify with a different method or reject "
            "the request, recording why.",
            "identity",
        )
        return state

    if dsar.verification_status != "verified":
        state.phase = IDENTITY_VERIFICATION
        state.phase_label = PHASE_LABELS[IDENTITY_VERIFICATION]
        state.blockers.append(
            Blocker(
                "identity_unverified",
                "The requester's identity has not been verified.",
                "identity",
            )
        )
        state.next_action = NextAction(
            "Verify requester identity",
            f"Confirm that {dsar.requester_name} is who they say they are before "
            "anything is searched or disclosed.",
            "identity",
        )
        return state

    if dsar.scope_confirmed_at is None:
        state.phase = SCOPE_REVIEW
        state.phase_label = PHASE_LABELS[SCOPE_REVIEW]
        state.blockers.append(
            Blocker("scope_unconfirmed", "The search scope has not been confirmed.", "scope")
        )
        remaining = len(undecided)
        state.next_action = NextAction(
            "Confirm search scope",
            (
                f"{len(scope)} candidate sources; {remaining} still undecided."
                if remaining
                else f"Review the {len(scope)} suggested sources and confirm the scope."
            ),
            "scope",
        )
        return state

    if dsar.discovery_run_at is None or not items:
        state.phase = DISCOVERY
        state.phase_label = PHASE_LABELS[DISCOVERY]
        state.blockers.append(
            Blocker("discovery_not_run", "Discovery has not been run.", "discovery")
        )
        state.next_action = NextAction(
            "Search confirmed data sources",
            f"{len(included)} confirmed source(s) are ready to search.",
            "discovery",
        )
        return state

    if needs_review:
        state.phase = RESPONSE_REVIEW
        state.phase_label = PHASE_LABELS[RESPONSE_REVIEW]
        state.blockers.append(
            Blocker(
                "items_need_review",
                f"{len(needs_review)} discovered source(s) have no disclosure decision.",
                "results",
            )
        )
        state.next_action = NextAction(
            f"Review {len(needs_review)} discovered record set(s)",
            "Decide what to include, exclude or redact. Veyntra flags what looks "
            "sensitive; the decision is yours.",
            "results",
        )
        return state

    if _requires_disclosure(dsar):
        if package is None:
            state.phase = RESPONSE_REVIEW
            state.phase_label = PHASE_LABELS[RESPONSE_REVIEW]
            state.blockers.append(
                Blocker("no_package", "No response package has been drafted.", "package")
            )
            state.next_action = NextAction(
                "Preview response package",
                "Veyntra will draft the response from the reviewed findings for you "
                "to check before anything is sent.",
                "package",
            )
            return state

        if package.status == "draft":
            state.phase = RESPONSE_REVIEW
            state.phase_label = PHASE_LABELS[RESPONSE_REVIEW]
            state.blockers.append(
                Blocker(
                    "package_unapproved",
                    "The response package has been drafted but not approved.",
                    "package",
                )
            )
            state.next_action = NextAction(
                "Approve response package",
                "Read the draft. What you approve is exactly what gets sent.",
                "package",
            )
            return state

    # Everything that gates the answer is done. An outstanding manual
    # follow-up does not block the response — §20 — but it is the thing
    # most worth saying before somebody signs it off.
    state.phase = READY_TO_RESPOND
    state.phase_label = PHASE_LABELS[READY_TO_RESPOND]
    if open_follow_ups:
        state.blockers.append(
            Blocker(
                "open_follow_ups",
                f"{open_follow_ups} manual follow-up(s) are still open. The response "
                "can be sent, but it will be incomplete until they are done.",
                "results",
            )
        )
    state.next_action = NextAction(
        "Mark response sent",
        "Record that the response reached the requester, and complete the request.",
        "package",
    )
    return state


async def refresh_phase(db: AsyncSession, *, dsar: DSAR) -> WorkflowState:
    """Recompute the stored phase from the record.

    Called after every write that could move a request. The column is a
    cache for lists and filters; this function is the truth.
    """
    state = await evaluate(db, dsar=dsar)
    dsar.phase = state.phase
    dsar.blocked_reason = (
        state.blockers[0].message if state.phase == BLOCKED and state.blockers else None
    )
    return state


async def completion_blockers(db: AsyncSession, *, dsar: DSAR) -> list[Blocker]:
    """§13/§16: everything that must be true before a request can be closed.

    Reported as a list rather than resolved to a yes/no, so the screen
    can show what is outstanding instead of a disabled button with no
    explanation.
    """
    from app.compliance import dsar_discovery

    state = await evaluate(db, dsar=dsar)
    if state.phase == COMPLETED:
        return []

    blockers = list(state.blockers)
    if state.phase != READY_TO_RESPOND and not blockers:  # pragma: no cover - guard
        blockers.append(
            Blocker(
                "not_ready",
                f"This request is still at {PHASE_LABELS.get(state.phase, state.phase)}.",
                "identity",
            )
        )

    # §16: a source that was never searched cannot be quietly left behind
    # by marking the request fulfilled.
    #
    # Two ways to resolve one, and both are decisions on the record: do
    # the manual search — which closes its follow-up task — or exclude
    # the source with a reason. What is refused is the third way, where
    # a source stays unsearched and the request is called finished
    # anyway.
    children = await _load(db, dsar)
    unresolved = [
        item
        for item in children.items
        if item.search_state in dsar_discovery.OUTSTANDING
        and item.review_decision not in ("exclude", "redact")
        and not await _follow_up_done(db, item)
    ]
    if unresolved:
        blockers.append(
            Blocker(
                "sources_unresolved",
                f"{len(unresolved)} source(s) have not been searched: "
                + ", ".join(sorted(item.source_name for item in unresolved)[:5])
                + ". Complete the follow-up, or exclude the source with a reason.",
                "results",
            )
        )
    return blockers


__all__ = [
    "BLOCKED",
    "COMPLETED",
    "DISCOVERY",
    "IDENTITY_VERIFICATION",
    "PHASE_LABELS",
    "PHASE_ORDER",
    "READY_TO_RESPOND",
    "RECEIVED",
    "RESPONSE_REVIEW",
    "SCOPE_REVIEW",
    "Blocker",
    "NextAction",
    "WorkflowState",
    "completion_blockers",
    "evaluate",
    "refresh_phase",
]
