"""The response, drafted by Veyntra and approved by a person.

Modelled on `audit_report_service` deliberately — §12 asks for the same
principle and the reasoning transfers exactly. A preview is built from
live records and carries a digest of them. Approving stores the snapshot.
Sending renders the stored snapshot, never the live records.

That last sentence is the whole design. If the response were rebuilt at
send time, the answer could change between the moment somebody read it
and the moment it went out, and what changed would be a person's
personal data. The approval has to be of a specific text, or it is not
an approval of anything.

What the draft says about gaps is the other half. A source that could
not be searched appears in the response as not searched — under its own
heading, in the requester's copy. A response that quietly omitted it
would be telling a data subject the controller had looked everywhere.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance import dsar_discovery, dsar_workflow
from app.compliance.models import DSAR, DsarDiscoveredItem, DsarResponsePackage
from app.identity.models import User


class ResponseRefused(Exception):
    """A response package this system will not produce as asked."""


@dataclass
class SourceLine:
    name: str
    state: str
    state_label: str
    matches: int
    decision: str
    decision_reason: str | None
    flags: list[str] = field(default_factory=list)


@dataclass
class Coverage:
    """What the search actually covered.

    "Searched and empty" and "not searched at all" are counted
    separately, because a package that adds them together claims a
    completeness it does not have.
    """

    scope_confirmed: int
    automatically_searched: int
    manual_completed: int
    outstanding: int
    searched_no_matches: int
    records_found: int
    complete: bool


@dataclass
class Preview:
    dsar_id: uuid.UUID
    requester_name: str
    requester_email: str
    request_type: str
    received_at: str
    due_at: str
    identity_method: str | None
    identity_notes: str | None
    identity_verified_at: str | None
    identity_verified_by: str | None
    letter: str
    included: list[SourceLine] = field(default_factory=list)
    excluded: list[SourceLine] = field(default_factory=list)
    redacted: list[SourceLine] = field(default_factory=list)
    not_searched: list[SourceLine] = field(default_factory=list)
    follow_ups: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    coverage: Coverage | None = None
    digest: str = ""


_STATE_LABELS = {
    dsar_discovery.NOT_SEARCHED: "Not searched",
    dsar_discovery.SEARCHED_NONE: "Searched — no records found",
    dsar_discovery.SEARCHED_FOUND: "Searched — records found",
    dsar_discovery.SEARCH_FAILED: "Search failed",
    dsar_discovery.MANUAL_FOLLOW_UP: "Manual follow-up required",
}


def _line(item: DsarDiscoveredItem) -> SourceLine:
    return SourceLine(
        name=item.source_name,
        state=item.search_state,
        state_label=_STATE_LABELS.get(item.search_state, item.search_state),
        matches=item.matches,
        decision=item.review_decision,
        decision_reason=item.review_reason,
        flags=list(item.sensitivity_flags or []),
    )


def _digest(preview: Preview) -> str:
    """A fingerprint of what the response *says*.

    Deliberately excludes `blockers`. Those describe the workflow around
    the response, not its content, and they change as a direct result of
    approving — "no response package has been drafted" is true right up
    until the moment it is not. Including them would make every digest
    stale the instant it was acted on, which is the opposite of what a
    drift check is for.

    What remains is the letter and the source lines: change any of those
    and the thing somebody read is not the thing they are approving.
    """
    payload = asdict(preview)
    payload.pop("digest", None)
    payload.pop("blockers", None)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


# Blockers that describe the drafting step itself. Approving is the act
# that clears them, so treating them as reasons to refuse would make the
# gate circular.
_SELF_CLEARING = frozenset({"no_package", "package_unapproved", "open_follow_ups"})


def _snapshot(preview: Preview) -> dict:
    """The preview as storable JSON.

    `asdict` leaves the UUID as a UUID, which the JSON column rejects.
    Round-tripping through the same serializer the digest uses also means
    the stored snapshot is exactly the bytes that were fingerprinted,
    rather than a near-copy that happens to hash the same today.
    """
    return json.loads(json.dumps(asdict(preview), sort_keys=True, default=str))


def _letter(dsar: DSAR, included: list[SourceLine], gaps: list[SourceLine]) -> str:
    """The covering letter, drafted for a person to edit.

    Written plainly and without promising completeness. Where a source
    could not be searched the letter says so — a data subject is entitled
    to know the answer is partial, and burying that in an appendix is how
    a controller ends up having implied something untrue.
    """
    lines = [
        f"Dear {dsar.requester_name},",
        "",
        f"We received your {dsar.request_type} request on "
        f"{dsar.received_at:%d %B %Y} and have completed our search.",
        "",
    ]
    if included:
        lines.append("We hold personal data about you in the following places:")
        lines.append("")
        for source in included:
            if source.state == dsar_discovery.SEARCHED_FOUND:
                lines.append(f"  - {source.name}: {source.matches} record(s)")
            elif source.state == dsar_discovery.SEARCHED_NONE:
                lines.append(f"  - {source.name}: no records found")
        lines.append("")
    else:
        lines += [
            "Our search of the systems covered by this request did not locate "
            "personal data about you.",
            "",
        ]

    if gaps:
        lines += [
            "Some sources could not be searched directly and are being followed up "
            "separately. We will write again if they hold anything about you:",
            "",
        ]
        lines += [f"  - {source.name}" for source in gaps]
        lines.append("")

    lines += [
        "If you believe this response is incomplete, or you would like to exercise "
        "another of your rights, please reply to this message.",
        "",
        "Yours sincerely,",
        "",
        "[Name] — Data Protection contact",
    ]
    return "\n".join(lines)


async def build_preview(
    db: AsyncSession, *, organization_id: uuid.UUID, dsar: DSAR
) -> Preview:
    """Draft the response from the reviewed findings.

    Reads live records. Nothing is stored until somebody approves.
    """
    items = list(
        (
            await db.execute(
                select(DsarDiscoveredItem)
                .where(DsarDiscoveredItem.dsar_id == dsar.id)
                .order_by(DsarDiscoveredItem.source_name)
            )
        )
        .scalars()
        .all()
    )

    verified_by = None
    if dsar.verified_by is not None:
        person = await db.get(User, dsar.verified_by)
        if person is not None:
            verified_by = person.full_name or person.email

    included = [
        _line(item)
        for item in items
        if item.review_decision == "include"
        and item.search_state in dsar_discovery.CONCLUSIVE
    ]
    redacted = [_line(item) for item in items if item.review_decision == "redact"]
    excluded = [
        _line(item)
        for item in items
        if item.review_decision == "exclude"
        and item.search_state != dsar_discovery.NOT_SEARCHED
    ]
    # Everything that did not actually get searched, whatever the reason.
    # Grouped together because from the requester's point of view they
    # are one thing: places we have not looked.
    gaps = [
        _line(item)
        for item in items
        if item.search_state
        in (
            dsar_discovery.MANUAL_FOLLOW_UP,
            dsar_discovery.SEARCH_FAILED,
        )
    ]

    state = await dsar_workflow.evaluate(db, dsar=dsar)

    # Counted from the rows rather than from the letter, so the summary
    # and the body cannot disagree.
    outstanding = [
        item
        for item in items
        if item.search_state in dsar_discovery.OUTSTANDING
        and item.review_decision not in ("exclude", "redact")
    ]
    resolved_manually = [
        item
        for item in items
        if item.search_state in dsar_discovery.OUTSTANDING
        and item.review_decision in ("include", "redact")
    ]
    coverage = Coverage(
        scope_confirmed=len(items),
        automatically_searched=len(
            [item for item in items if item.search_state in dsar_discovery.CONCLUSIVE]
        ),
        manual_completed=len(resolved_manually),
        outstanding=len(outstanding),
        searched_no_matches=len(
            [item for item in items if item.search_state == dsar_discovery.SEARCHED_NONE]
        ),
        records_found=sum(
            item.matches
            for item in items
            if item.search_state == dsar_discovery.SEARCHED_FOUND
        ),
        complete=not outstanding,
    )

    preview = Preview(
        dsar_id=dsar.id,
        requester_name=dsar.requester_name,
        requester_email=dsar.requester_email,
        request_type=dsar.request_type,
        received_at=dsar.received_at.isoformat(),
        due_at=dsar.due_at.isoformat(),
        identity_method=dsar.verification_method,
        identity_notes=dsar.verification_notes,
        identity_verified_at=(
            dsar.verified_at.isoformat() if dsar.verified_at else None
        ),
        identity_verified_by=verified_by,
        letter=_letter(dsar, included, gaps),
        included=included,
        excluded=excluded,
        redacted=redacted,
        not_searched=gaps,
        follow_ups=[
            item.state_detail or item.source_name
            for item in items
            if item.search_state == dsar_discovery.MANUAL_FOLLOW_UP
        ],
        blockers=[blocker.message for blocker in state.blockers],
        coverage=coverage,
    )
    preview.digest = _digest(preview)
    return preview


async def _next_version(db: AsyncSession, *, dsar_id: uuid.UUID) -> int:
    latest = (
        (
            await db.execute(
                select(DsarResponsePackage.version)
                .where(DsarResponsePackage.dsar_id == dsar_id)
                .order_by(DsarResponsePackage.version.desc())
            )
        )
        .scalars()
        .first()
    )
    return (latest or 0) + 1


async def approve(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dsar: DSAR,
    confirm_digest: str,
    actor_user_id: uuid.UUID | None,
    letter_override: str | None = None,
) -> DsarResponsePackage:
    """Freeze the previewed response as the approved one.

    Refuses on two grounds, in the order a person meets them: the request
    moved since the preview, or something still blocks the response.
    """
    preview = await build_preview(db, organization_id=organization_id, dsar=dsar)

    # Drift is checked against the preview as it was built. The person's
    # own edit to the letter is not drift — it is the thing they are
    # approving — so it is applied after this comparison, not before.
    if preview.digest != confirm_digest:
        raise ResponseRefused(
            "This request has changed since the response was previewed. Open the "
            "preview again to see what the response would say now."
        )

    state = await dsar_workflow.evaluate(db, dsar=dsar)
    real_blockers = [
        blocker for blocker in state.blockers if blocker.code not in _SELF_CLEARING
    ]
    if real_blockers:
        raise ResponseRefused(
            "This response cannot be approved yet: "
            + " ".join(blocker.message for blocker in real_blockers)
        )

    # §12 puts human edits between preview and approval.
    if letter_override is not None and letter_override.strip():
        preview.letter = letter_override
        preview.digest = _digest(preview)

    existing = (
        (
            await db.execute(
                select(DsarResponsePackage)
                .where(
                    DsarResponsePackage.dsar_id == dsar.id,
                    DsarResponsePackage.status == "approved",
                )
                .order_by(DsarResponsePackage.version.desc())
            )
        )
        .scalars()
        .first()
    )
    if existing is not None and existing.source_digest == preview.digest:
        # §18: approving the same unchanged response twice is one
        # approval, not two packages.
        return existing

    package = DsarResponsePackage(
        organization_id=organization_id,
        dsar_id=dsar.id,
        version=await _next_version(db, dsar_id=dsar.id),
        status="approved",
        contents=_snapshot(preview),
        source_digest=preview.digest,
        approved_by=actor_user_id,
        approved_at=datetime.now(UTC),
    )
    db.add(package)
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dsar.response_approved",
        object_type="dsar",
        object_id=str(dsar.id),
        after_state={"version": package.version, "digest": package.source_digest},
    )
    return package


async def draft(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dsar: DSAR,
    actor_user_id: uuid.UUID | None,
) -> DsarResponsePackage:
    """Store the current preview as a draft package.

    Distinct from approving: this is Veyntra doing the drafting work so
    there is something to read. It carries no signature and blocks
    nothing — a draft can be replaced whenever the findings move.
    """
    preview = await build_preview(db, organization_id=organization_id, dsar=dsar)

    existing = (
        (
            await db.execute(
                select(DsarResponsePackage)
                .where(
                    DsarResponsePackage.dsar_id == dsar.id,
                    DsarResponsePackage.status == "draft",
                )
                .order_by(DsarResponsePackage.version.desc())
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        # Refresh the draft in place. A new row per refresh would fill
        # the history with drafts nobody read.
        existing.contents = _snapshot(preview)
        existing.source_digest = preview.digest
        return existing

    package = DsarResponsePackage(
        organization_id=organization_id,
        dsar_id=dsar.id,
        version=await _next_version(db, dsar_id=dsar.id),
        status="draft",
        contents=_snapshot(preview),
        source_digest=preview.digest,
    )
    db.add(package)
    await db.flush()
    return package


def render(package: DsarResponsePackage) -> str:
    """The response package as text, from the approved snapshot.

    Reads only `contents`. Nothing here touches live records — that is
    the point of the snapshot.
    """
    data = dict(package.contents or {})
    lines = [
        "DATA SUBJECT REQUEST — RESPONSE PACKAGE",
        f"Version {package.version}",
        "",
        f"Data subject: {data.get('requester_name')} <{data.get('requester_email')}>",
        f"Request type: {data.get('request_type')}",
        f"Received: {data.get('received_at')}",
        f"Response due: {data.get('due_at')}",
        "",
        "IDENTITY VERIFICATION",
        f"  Method: {data.get('identity_method') or 'not recorded'}",
        f"  Notes: {data.get('identity_notes') or 'none recorded'}",
        f"  Verified at: {data.get('identity_verified_at') or 'not verified'}",
        f"  Verified by: {data.get('identity_verified_by') or 'not recorded'}",
        "",
    ]

    def block(title: str, key: str, empty: str) -> None:
        rows = list(data.get(key) or [])
        lines.append(title)
        if not rows:
            lines.append(f"  {empty}")
        for row in rows:
            lines.append(f"  - {row.get('name')}: {row.get('state_label')}")
            if row.get("matches"):
                lines.append(f"      {row['matches']} record reference(s)")
            if row.get("decision_reason"):
                lines.append(f"      Reason: {row['decision_reason']}")
            for flag in row.get("flags") or []:
                lines.append(f"      Flagged: {flag}")
        lines.append("")

    block("SOURCES INCLUDED", "included", "None.")
    block("SOURCES REDACTED", "redacted", "None.")
    block("SOURCES EXCLUDED", "excluded", "None.")
    # Named in the package itself, not only in an internal note: the
    # difference between "we found nothing" and "we did not look" is the
    # requester's to know.
    block("NOT SEARCHED — FOLLOW-UP REQUIRED", "not_searched", "None.")

    coverage = dict(data.get("coverage") or {})
    if coverage:
        lines += [
            "SEARCH COVERAGE",
            f"  Search scope confirmed: {coverage.get('scope_confirmed', 0)} source(s)",
            f"  Automatically searched: {coverage.get('automatically_searched', 0)}",
            f"  Manual sources completed: {coverage.get('manual_completed', 0)}",
            f"  Outstanding: {coverage.get('outstanding', 0)}",
            f"  Searched with no matches: {coverage.get('searched_no_matches', 0)}",
            f"  Records found: {coverage.get('records_found', 0)}",
        ]
        if not coverage.get("complete", False):
            # Said in the package, not left to be inferred from the
            # numbers above it.
            lines.append(
                "  This response is partial: some sources in scope have not been "
                "searched."
            )
        lines.append("")

    lines += ["RESPONSE LETTER", "", str(data.get("letter") or "")]
    return "\n".join(lines)


async def mark_sent(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dsar: DSAR,
    package: DsarResponsePackage,
    actor_user_id: uuid.UUID | None,
) -> DsarResponsePackage:
    """Record that the approved response reached the requester."""
    if package.status != "approved":
        raise ResponseRefused(
            "Only an approved response package can be marked as sent."
        )
    if package.sent_at is not None:
        # §18: recording the same send twice is one send.
        return package

    package.status = "sent"
    package.sent_at = datetime.now(UTC)
    dsar.status = "fulfilled"
    dsar.fulfilled_at = package.sent_at

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dsar.response_sent",
        object_type="dsar",
        object_id=str(dsar.id),
        after_state={"version": package.version},
    )
    return package


__all__ = [
    "Preview",
    "ResponseRefused",
    "SourceLine",
    "approve",
    "build_preview",
    "draft",
    "mark_sent",
    "render",
]
