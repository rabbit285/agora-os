"""Finding the version relationships that already exist in a library.

Version detection was added after customers had been uploading documents
for months, so every existing organization holds lineages nobody ever
recorded: `AI_Governance_Policy.docx` and `AI_Governance_Policy_v2.docx`
sitting side by side as two unrelated documents, each with its own
evidence, both counting towards coverage.

This finds them. It does **not** link them.

That restraint is the whole design. Accepting a version supersedes a
document, moves what counts as current evidence and reopens approvals
whose wording changed — decisions with an audit trail attached. Making
them in bulk, retroactively, on a similarity score, would rewrite
compliance history for documents nobody was looking at. So the backfill
does exactly what an upload does: it proposes, and the proposal waits on
a person.

Idempotent, because it will be run more than once: a document that
already has a proposal, has already been decided, or is already part of a
chain is left exactly as it is.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.document_versioning import (
    detect_version_label,
    find_version_candidate,
)
from app.core.models import File
from app.knowledge.parsing import extract_text

logger = logging.getLogger(__name__)


@dataclass
class BackfillReport:
    """What the pass looked at and what it proposes."""

    examined: int = 0
    proposed: int = 0
    already_linked: int = 0
    already_proposed: int = 0
    unreadable: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "examined": self.examined,
            "proposed": self.proposed,
            "already_linked": self.already_linked,
            "already_proposed": self.already_proposed,
            "unreadable": self.unreadable,
        }


async def backfill_version_candidates(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dry_run: bool = True,
    limit: int = 200,
) -> BackfillReport:
    """Propose version links for documents uploaded before detection existed.

    `dry_run` is the default deliberately: the first thing anyone should
    do with a bulk pass over a customer's compliance library is read what
    it would do.
    """
    from app.core.storage import download_object

    report = BackfillReport()

    files = list(
        (
            await db.execute(
                select(File)
                .where(
                    File.organization_id == organization_id,
                    File.processing_status == "ready",
                    # A duplicate is settled by its content hash and is
                    # not a version of anything.
                    File.duplicate_of_id.is_(None),
                )
                .order_by(File.created_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    text_cache: dict[uuid.UUID, str] = {}

    def read_text(other: File) -> str:
        if other.id in text_cache:
            return text_cache[other.id]
        try:
            text = extract_text(other.content_type, download_object(other.storage_key))
        except Exception:  # noqa: BLE001 - an unreadable neighbour is not a failure
            text = ""
        text_cache[other.id] = text
        return text

    for file_record in files:
        # Already part of a chain, or already waiting on somebody. Both
        # are answers; neither is improved by asking again.
        if file_record.supersedes_id or file_record.superseded_by_id:
            report.already_linked += 1
            continue
        if file_record.version_candidate_id:
            report.already_proposed += 1
            continue

        document_text = read_text(file_record)
        if not document_text.strip():
            report.unreadable += 1
            continue

        report.examined += 1
        try:
            candidate = await find_version_candidate(
                db,
                organization_id=organization_id,
                file_record=file_record,
                document_text=document_text,
                read_text=read_text,
            )
        except Exception:  # noqa: BLE001 - one bad document must not stop the pass
            logger.warning("Version backfill failed for %s", file_record.id)
            continue

        if candidate is None:
            continue

        report.proposed += 1
        if dry_run:
            continue

        file_record.version_candidate_id = candidate.file_id
        file_record.version_confidence = candidate.confidence
        file_record.version_reasons = candidate.reasons[:4]
        if file_record.version_label is None:
            file_record.version_label = detect_version_label(document_text)

        await record_event(
            db,
            organization_id=organization_id,
            actor_user_id=None,
            action="core.file.version_candidate_detected",
            object_type="file",
            object_id=str(file_record.id),
            after_state={
                "candidate": candidate.title,
                "confidence": candidate.confidence,
                "reasons": candidate.reasons[:4],
                "found_by": "backfill",
            },
        )

    if not dry_run:
        await db.flush()
    return report


__all__ = ["BackfillReport", "backfill_version_candidates"]
