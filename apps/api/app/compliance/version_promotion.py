"""Accepting one document as the next version of another.

The hard part is not the link. It is what happens to the compliance
state that was built on the old version: evidence a person approved,
mappings a control depends on, a policy somebody signed off.

Four outcomes per piece of evidence, and each is a different promise:

- **Unchanged** — the passage survived the edit. The mapping carries
  forward *with its approval*, because asking somebody to re-approve text
  they already read is how a product teaches people to click Approve
  without reading.
- **Modified** — the passage changed. The mapping carries forward but the
  approval does not: somebody signed off on wording that no longer
  exists, and their name must not stay attached to text they never saw.
- **Added** — new in this version. A new proposal, routed by the usual
  rules.
- **Removed** — the passage is gone. The evidence stays, attached to the
  version it came from, and stops counting towards current coverage. A
  superseded policy is not what the organization does now.

The old version is superseded, never deleted. Its evidence is history,
and history is the thing an audit trail exists to keep.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import EvidenceSuggestion, Policy
from app.core.dedupe import text_fingerprint
from app.core.models import File


class VersionAlreadySuperseded(Exception):
    """Two people accepted a version against the same document at once.

    Raised only when the database refuses the second write, so it always
    means the chain is intact and somebody else's acceptance is the one
    that stands.
    """


@dataclass
class ReconciliationReport:
    """What the new version did to the old version's evidence."""

    unchanged: int = 0
    modified: int = 0
    added: int = 0
    removed: int = 0
    approvals_preserved: int = 0
    approvals_reopened: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def _passage_identity(suggestion: EvidenceSuggestion) -> str:
    """What makes two citations the same citation.

    The section and the quoted words, normalized — so a re-flowed
    paragraph is the same passage and a rewritten one is not.
    """
    return suggestion.passage_hash or text_fingerprint(
        suggestion.source_location, suggestion.quoted_passage
    )


async def reconcile_evidence(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    previous: File,
    current: File,
) -> ReconciliationReport:
    """Move the old version's evidence onto the new one where it survived.

    Runs *after* the new version has been analysed, so the new version's
    own suggestions already exist. This decides what happens to the old
    ones.
    """
    report = ReconciliationReport()

    previous_rows = list(
        (
            await db.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.organization_id == organization_id,
                    EvidenceSuggestion.file_id == previous.id,
                )
            )
        )
        .scalars()
        .all()
    )
    current_rows = list(
        (
            await db.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.organization_id == organization_id,
                    EvidenceSuggestion.file_id == current.id,
                )
            )
        )
        .scalars()
        .all()
    )

    current_by_control = {
        (row.control_id, row.requirement_id): row for row in current_rows
    }
    previous_identities = {_passage_identity(row) for row in previous_rows}

    for old in previous_rows:
        key = (old.control_id, old.requirement_id)
        new = current_by_control.get(key)

        if new is None:
            # The new version says nothing about this control. The old
            # evidence stays where it is — attached to the version it
            # came from — and stops counting, because that version is no
            # longer what the organization does.
            report.removed += 1
            continue

        if _passage_identity(old) == _passage_identity(new):
            report.unchanged += 1
            # The passage survived. So does the decision about it.
            if old.status in ("approved", "auto_approved") and new.status == "proposed":
                new.status = old.status
                new.decided_by = old.decided_by
                new.decided_at = old.decided_at
                new.evidence_id = old.evidence_id
                report.approvals_preserved += 1
        else:
            report.modified += 1
            if old.status in ("approved", "auto_approved"):
                # Somebody approved wording that no longer exists. The
                # mapping survives; the approval does not.
                new.status = "proposed"
                new.decided_by = None
                new.decided_at = None
                new.routing_reason = (
                    "The passage this was approved from changed in the new version of the "
                    "document. Check the new wording before approving it again."
                )
                report.approvals_reopened += 1

    for new in current_rows:
        if _passage_identity(new) not in previous_identities:
            report.added += 1

    await db.flush()
    return report


async def accept_new_version(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    previous: File,
    current: File,
    actor_user_id: uuid.UUID | None,
    version_label: str | None = None,
) -> ReconciliationReport:
    """Make `current` the version that replaces `previous`.

    Idempotent: a retry of the same acceptance finds the link already
    made and reconciles again over the same rows, which is a no-op.

    Two *different* uploads accepted against the same previous version
    concurrently is a different matter. The endpoint's "has this already
    been superseded?" guard is a read before a write, so it loses that
    race. `uq_file_supersedes` and
    `uq_file_superseded_by` make the second writer fail instead of
    forking the chain, and `VersionAlreadySuperseded` turns that into
    something the caller can tell a person.
    """
    if current.supersedes_id == previous.id and previous.superseded_by_id == current.id:
        # Already linked. Reconciliation is safe to repeat.
        return await reconcile_evidence(
            db, organization_id=organization_id, previous=previous, current=current
        )

    # Inside a savepoint, so a rejected link unwinds just this write.
    # A plain `db.rollback()` here would discard the caller's whole
    # transaction — work this function knows nothing about — to recover
    # from a conflict that touched two columns.
    try:
        async with db.begin_nested():
            current.supersedes_id = previous.id
            current.version_label = version_label or current.version_label
            previous.superseded_by_id = current.id
            await db.flush()
    except IntegrityError as exc:
        # Somebody else linked a different upload to this version between
        # the check and here. Theirs won; nothing of this one is written.
        raise VersionAlreadySuperseded(
            "Another version of this document was accepted while you were "
            "deciding. Open the current version and upload against that."
        ) from exc

    report = await reconcile_evidence(
        db, organization_id=organization_id, previous=previous, current=current
    )

    # A policy keeps its identity across versions. The governance record
    # is the same record; what changes is which document it points at,
    # and that a person has to look at it again.
    policy = (
        await db.execute(
            select(Policy).where(
                Policy.organization_id == organization_id, Policy.file_id == previous.id
            )
        )
    ).scalars().first()
    if policy is not None:
        from app.compliance.policy_governance import promote_document_to_current_version

        await promote_document_to_current_version(
            db,
            organization_id=organization_id,
            policy=policy,
            file_record=current,
            actor_user_id=actor_user_id,
            version=version_label or current.version_label,
        )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="core.file.version_added",
        object_type="file",
        object_id=str(current.id),
        before_state={"version": previous.version_label or "previous"},
        after_state={
            "version": current.version_label or "new",
            "supersedes": previous.original_filename,
            **report.as_dict(),
        },
    )

    # Evidence changed, so whatever the affected controls last concluded
    # is stale. Flagged rather than recomputed inline: reassessment is a
    # separate, idempotent pass, and doing it here would make accepting a
    # version wait on it.
    await _flag_affected_controls(
        db, organization_id=organization_id, previous=previous, current=current
    )
    await db.flush()
    return report


async def _flag_affected_controls(
    db: AsyncSession, *, organization_id: uuid.UUID, previous: File, current: File
) -> None:
    """Mark for reassessment only the controls this version touched.

    Recomputing every control because one document changed is wasteful
    and, worse, moves numbers on screens nobody edited.
    """
    from app.compliance.models import Control

    control_ids = {
        row.control_id
        for row in (
            await db.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.organization_id == organization_id,
                    EvidenceSuggestion.file_id.in_([previous.id, current.id]),
                )
            )
        )
        .scalars()
        .all()
        if row.control_id
    }
    if not control_ids:
        return

    for control in (
        (await db.execute(select(Control).where(Control.id.in_(control_ids))))
        .scalars()
        .all()
    ):
        control.needs_reassessment = True


async def current_version_of(
    db: AsyncSession, *, file_record: File
) -> File:
    """Walk to the head of the chain.

    Bounded, because a cycle in the data must not become a hang: the
    unique index makes one impossible, and this still refuses to trust
    it.
    """
    seen: set[uuid.UUID] = {file_record.id}
    head = file_record
    while head.superseded_by_id is not None and len(seen) < 50:
        nxt = await db.get(File, head.superseded_by_id)
        if nxt is None or nxt.id in seen:
            break
        seen.add(nxt.id)
        head = nxt
    return head


async def version_history(
    db: AsyncSession, *, organization_id: uuid.UUID, file_record: File
) -> list[File]:
    """Every version of this document, oldest first.

    Walks back to the original and forward to the current one, so any
    version in the chain returns the whole chain — a citation into a
    superseded version still shows the reader where it sits.
    """
    oldest = file_record
    seen: set[uuid.UUID] = {oldest.id}
    while oldest.supersedes_id is not None and len(seen) < 50:
        previous = await db.get(File, oldest.supersedes_id)
        if previous is None or previous.id in seen:
            break
        seen.add(previous.id)
        oldest = previous

    chain = [oldest]
    while chain[-1].superseded_by_id is not None and len(chain) < 50:
        nxt = await db.get(File, chain[-1].superseded_by_id)
        if nxt is None or any(nxt.id == row.id for row in chain):
            break
        chain.append(nxt)
    return chain


__all__ = [
    "ReconciliationReport",
    "VersionAlreadySuperseded",
    "accept_new_version",
    "current_version_of",
    "reconcile_evidence",
    "version_history",
]
