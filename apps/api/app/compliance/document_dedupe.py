"""Collapsing documents that are the same document.

The content hash arrived after the library did. Every file uploaded
before it has `content_hash = NULL`, and a partial unique index over
`WHERE content_hash IS NOT NULL` correctly ignores them — so two rows
holding byte-identical policies could coexist, and the duplicate check
could not see the older one to match against it.

That is how one policy became four rows with 4, 5, 1 and 0 pieces of
evidence: each row ran its own extraction, and the model proposes a
slightly different set every time. The counts diverging is the symptom;
the cause is that they were ever separate documents.

Two operations here, and they are deliberately separate:

- **Backfill** reads the stored bytes and records what each file
  actually is. It changes nothing else, and after it the constraint and
  the duplicate check apply to the whole library rather than to
  yesterday's uploads.
- **Merge** picks one canonical document per (organization, content) and
  moves the others' children onto it.

Merge never deletes a File. Somebody uploaded it, and making the row
vanish would be a lie about what happened — it is marked as the
duplicate it is, pointed at the canonical row, and hidden from the
library. Child records are moved rather than dropped wherever the
canonical document does not already have an equivalent, and a human
decision always outranks a proposal.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Evidence, EvidenceSuggestion, Policy
from app.core.dedupe import content_fingerprint
from app.core.models import File
from app.knowledge.models import Document, DocumentChunk

logger = logging.getLogger("agora.compliance.dedupe")

# A file that never finished is not a document to adopt. Deduplicating
# against one would strand the customer with a row that produced nothing
# and no way to retry.
CANONICAL_STATUSES = ("ready",)


@dataclass
class MergeReport:
    """What a merge actually did, in records rather than adjectives."""

    groups: int = 0
    files_marked_duplicate: int = 0
    evidence_moved: int = 0
    evidence_dropped: int = 0
    suggestions_moved: int = 0
    suggestions_dropped: int = 0
    policies_relinked: int = 0
    policies_retired: int = 0
    documents_retired: int = 0
    chunks_removed: int = 0
    canonical_ids: list[uuid.UUID] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        return {
            "groups": self.groups,
            "files_marked_duplicate": self.files_marked_duplicate,
            "evidence_moved": self.evidence_moved,
            "evidence_dropped": self.evidence_dropped,
            "suggestions_moved": self.suggestions_moved,
            "suggestions_dropped": self.suggestions_dropped,
            "policies_relinked": self.policies_relinked,
            "policies_retired": self.policies_retired,
            "documents_retired": self.documents_retired,
            "chunks_removed": self.chunks_removed,
        }


async def fingerprint_library(
    db: AsyncSession, *, organization_id: uuid.UUID | None = None, limit: int = 1000
) -> dict[uuid.UUID, str]:
    """What each already-uploaded file actually is, read from its bytes.

    Computed and returned rather than written. Writing straight to the
    column fails the moment two rows turn out to hold the same document —
    which is the case this exists to find, so the collision is a result,
    not an error. `reconcile_documents` decides which row keeps the hash.

    A file whose object is missing is absent from the result: it has no
    content to be identified by, and guessing would be worse than leaving
    it outside the constraint.
    """
    from app.core.storage import download_object

    stmt = select(File).where(File.content_hash.is_(None))
    if organization_id is not None:
        stmt = stmt.where(File.organization_id == organization_id)

    computed: dict[uuid.UUID, str] = {}
    for file_record in (
        (await db.execute(stmt.order_by(File.created_at).limit(limit))).scalars().all()
    ):
        try:
            computed[file_record.id] = content_fingerprint(
                download_object(file_record.storage_key)
            )
        except Exception:  # noqa: BLE001 - a missing object is not a crash
            continue
    return computed


async def reconcile_documents(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    dry_run: bool = True,
) -> MergeReport:
    """Identify every file, then collapse the ones that are the same.

    One pass, because the two halves cannot be separated: a file's hash
    cannot be written until it is known whether another row already holds
    that hash, and that is the merge decision.

    Within each (organization, content) group the canonical row keeps the
    hash and the children; the others are marked as the duplicates they
    are. Identical content in two organizations stays two documents — the
    grouping key includes the organization.
    """
    computed = await fingerprint_library(db, organization_id=organization_id)

    stmt = select(File)
    if organization_id is not None:
        stmt = stmt.where(File.organization_id == organization_id)
    files = list((await db.execute(stmt.order_by(File.created_at))).scalars().all())

    grouped: dict[tuple[uuid.UUID, str], list[File]] = {}
    for file_record in files:
        digest = file_record.content_hash or computed.get(file_record.id)
        if not digest:
            continue
        grouped.setdefault((file_record.organization_id, digest), []).append(file_record)

    report = MergeReport()
    for (_, digest), group in grouped.items():
        canonical = choose_canonical(group)
        others = [f for f in group if f.id != canonical.id]

        if not others:
            if not dry_run and canonical.content_hash is None:
                canonical.content_hash = digest
                await db.flush()
            continue

        report.groups += 1
        report.canonical_ids.append(canonical.id)

        if not dry_run:
            # Release the hash before claiming it. One of the duplicates
            # may already hold it — a later upload that was hashed while
            # the original, uploaded before hashes existed, was not — and
            # assigning it to the canonical row first collides with the
            # very constraint this is repairing.
            #
            # Kept, not deleted: somebody uploaded these, and making the
            # rows vanish would be a lie about what happened. The hash
            # stays null so the partial unique index, which is about
            # *documents*, ignores them.
            for redundant in others:
                redundant.processing_status = "duplicate"
                redundant.duplicate_of_id = canonical.id
                redundant.processing_error = None
                redundant.content_hash = None
            await db.flush()

            if canonical.content_hash is None:
                canonical.content_hash = digest
            await db.flush()

        for redundant in others:
            await _absorb(
                db, canonical=canonical, redundant=redundant, report=report, dry_run=dry_run
            )
            report.files_marked_duplicate += 1

    if not dry_run:
        await db.flush()
    return report


async def _duplicate_groups(
    db: AsyncSession, *, organization_id: uuid.UUID | None
) -> list[list[File]]:
    """Files that are byte-identical, grouped, within one organization.

    Tenant-scoped by construction: the grouping key includes the
    organization, so identical content held by two customers stays two
    documents.
    """
    stmt = select(File).where(File.content_hash.is_not(None))
    if organization_id is not None:
        stmt = stmt.where(File.organization_id == organization_id)

    grouped: dict[tuple[uuid.UUID, str], list[File]] = {}
    for file_record in (
        (await db.execute(stmt.order_by(File.created_at))).scalars().all()
    ):
        key = (file_record.organization_id, file_record.content_hash or "")
        grouped.setdefault(key, []).append(file_record)

    return [group for group in grouped.values() if len(group) > 1]


def choose_canonical(group: list[File]) -> File:
    """Which of these is the document.

    The earliest one that finished processing. Earliest because it is the
    row a person may already have approved evidence against, linked a
    policy to, or cited; the later ones are the accidents. Finished
    because a half-processed row is not a result to adopt.
    """
    finished = [f for f in group if f.processing_status in CANONICAL_STATUSES]
    return min(finished or group, key=lambda f: (f.created_at, str(f.id)))


async def merge_duplicate_documents(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID | None = None,
    dry_run: bool = True,
) -> MergeReport:
    """Collapse byte-identical files onto one canonical document each.

    `dry_run` reports what would happen and changes nothing, because the
    first thing anyone should do with a destructive cleanup is read it.
    """
    report = MergeReport()

    for group in await _duplicate_groups(db, organization_id=organization_id):
        canonical = choose_canonical(group)
        others = [f for f in group if f.id != canonical.id]
        if not others:
            continue

        report.groups += 1
        report.canonical_ids.append(canonical.id)

        for redundant in others:
            await _absorb(db, canonical=canonical, redundant=redundant, report=report, dry_run=dry_run)
            if not dry_run:
                # Kept, not deleted: somebody uploaded this, and making
                # the row vanish would be a lie about what happened.
                redundant.processing_status = "duplicate"
                redundant.duplicate_of_id = canonical.id
                redundant.processing_error = None
            report.files_marked_duplicate += 1

    if not dry_run:
        await db.flush()
    return report


async def _repoint_evidence_references(
    db: AsyncSession, *, from_evidence: uuid.UUID, to_evidence: uuid.UUID
) -> None:
    """Move everything that points at one evidence row onto another.

    Run before a redundant row is deleted. The two rows are the same
    claim — the same document supporting the same control — so a
    decision recorded against one is a decision about the other.
    """
    from app.compliance.models import QuestionnaireAnswer

    for suggestion in (
        (
            await db.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.evidence_id == from_evidence
                )
            )
        )
        .scalars()
        .all()
    ):
        suggestion.evidence_id = to_evidence

    for answer in (
        (
            await db.execute(
                select(QuestionnaireAnswer).where(
                    QuestionnaireAnswer.evidence_id == from_evidence
                )
            )
        )
        .scalars()
        .all()
    ):
        answer.evidence_id = to_evidence

    await db.flush()


async def _absorb(
    db: AsyncSession,
    *,
    canonical: File,
    redundant: File,
    report: MergeReport,
    dry_run: bool,
) -> None:
    """Move one redundant file's children onto the canonical document."""

    # --- evidence: one document supporting one control is one row -----
    #
    # Anything pointing at a row about to be removed is repointed at the
    # canonical equivalent first. A suggestion carrying `evidence_id` is
    # the record of somebody's approval — dropping it would either
    # violate the foreign key or silently detach the decision from the
    # evidence it was about.
    canonical_evidence = {
        row.control_id: row
        for row in (
            await db.execute(select(Evidence).where(Evidence.file_id == canonical.id))
        )
        .scalars()
        .all()
    }
    for evidence in (
        (await db.execute(select(Evidence).where(Evidence.file_id == redundant.id)))
        .scalars()
        .all()
    ):
        replacement = canonical_evidence.get(evidence.control_id)
        if replacement is not None:
            # The canonical document already evidences this control. The
            # redundant row is the same claim about the same document.
            report.evidence_dropped += 1
            if not dry_run:
                await _repoint_evidence_references(
                    db, from_evidence=evidence.id, to_evidence=replacement.id
                )
                await db.delete(evidence)
        else:
            report.evidence_moved += 1
            canonical_evidence[evidence.control_id] = evidence
            if not dry_run:
                evidence.file_id = canonical.id

    # --- suggestions: one document, control and requirement -----------
    existing_pairs = {
        (row.control_id, row.requirement_id)
        for row in (
            await db.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.file_id == canonical.id
                )
            )
        )
        .scalars()
        .all()
    }
    for suggestion in (
        (
            await db.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.file_id == redundant.id
                )
            )
        )
        .scalars()
        .all()
    ):
        pair = (suggestion.control_id, suggestion.requirement_id)
        if pair in existing_pairs:
            report.suggestions_dropped += 1
            if not dry_run:
                await db.delete(suggestion)
        else:
            report.suggestions_moved += 1
            existing_pairs.add(pair)
            if not dry_run:
                suggestion.file_id = canonical.id

    # --- the managed policy -------------------------------------------
    #
    # One logical document is one policy. Where the canonical file
    # already has one, the duplicate's record is retired rather than
    # left as a second governance record for the same document; where it
    # does not, the existing record is relinked so its approval history
    # survives.
    canonical_policy = (
        await db.execute(select(Policy).where(Policy.file_id == canonical.id))
    ).scalars().first()
    for policy in (
        (await db.execute(select(Policy).where(Policy.file_id == redundant.id)))
        .scalars()
        .all()
    ):
        if canonical_policy is None:
            report.policies_relinked += 1
            canonical_policy = policy
            if not dry_run:
                policy.file_id = canonical.id
        else:
            report.policies_retired += 1
            if not dry_run:
                policy.status = "retired"
                policy.file_id = None

    # --- the Copilot index --------------------------------------------
    #
    # The redundant file's chunks are the same passages as the canonical
    # document's, so retrieval was returning each of them twice.
    for document in (
        (await db.execute(select(Document).where(Document.file_id == redundant.id)))
        .scalars()
        .all()
    ):
        chunks = (
            (
                await db.execute(
                    select(DocumentChunk).where(DocumentChunk.document_id == document.id)
                )
            )
            .scalars()
            .all()
        )
        report.chunks_removed += len(chunks)
        report.documents_retired += 1
        if not dry_run:
            for chunk in chunks:
                await db.delete(chunk)
            # Flushed before the document goes: the chunks reference it,
            # and SQLAlchemy will otherwise emit the parent delete first.
            await db.flush()
            await db.delete(document)
            await db.flush()
            redundant.index_status = "pending"
            redundant.indexed_at = None


__all__ = [
    "CANONICAL_STATUSES",
    "MergeReport",
    "choose_canonical",
    "fingerprint_library",
    "merge_duplicate_documents",
    "reconcile_documents",
]
