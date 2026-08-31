"""Catching documents up with an organization that has moved on.

Two situations, one idea: a document was understood correctly at the time
it was uploaded, and something has since changed that gives Veyntra more
to say about it. Neither is the customer's problem to solve by
re-uploading anything.

**Controls appeared.** A document uploaded on day one, before any
framework was adopted, was classified, governed and indexed — but had
nothing to map evidence to. When the organization adopts ISO 42001 and
forty controls appear, that document should be reconsidered against
them. Asking the customer to re-upload a file the product already holds,
already read, and already understands would be asking them to work
around a gap in our bookkeeping.

**Classification was skipped.** Documents processed before classification
was pulled out of the mapping call came back with no `document_type` at
all, because the combined call returned early when there were no
controls. Those documents are readable and indexed but have no Managed
Policy, and never will until something classifies them.

Both passes are idempotent and both reuse the ordinary pipeline rather
than a parallel copy of it — the whole failure being repaired here is
what happens when one path does something another does not.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Control
from app.core.models import File

logger = logging.getLogger("agora.compliance.reconcile")

# A ceiling on one pass. A library of thousands re-read in a single
# request would be a self-inflicted outage on the model provider; the
# pass is idempotent, so the remainder is picked up by the next one.
DEFAULT_LIMIT = 50


@dataclass
class ReconcileReport:
    """What a pass looked at and what it changed."""

    examined: int = 0
    classified: int = 0
    policies_created: int = 0
    mapped: int = 0
    skipped: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "examined": self.examined,
            "classified": self.classified,
            "policies_created": self.policies_created,
            "mapped": self.mapped,
            "skipped": self.skipped,
            "failed": self.failed,
        }


async def _analysed_documents(
    db: AsyncSession, *, organization_id: uuid.UUID, limit: int
) -> list[File]:
    """Documents that were read successfully and are the current version.

    Superseded versions and duplicates are excluded: neither is what the
    organization is held to now, and mapping evidence from a replaced
    document would put stale wording back into current coverage.
    """
    return list(
        (
            await db.execute(
                select(File)
                .where(
                    File.organization_id == organization_id,
                    File.processing_status == "ready",
                    File.duplicate_of_id.is_(None),
                    File.superseded_by_id.is_(None),
                )
                .order_by(File.created_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )


async def backfill_classification(
    organization_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    limit: int = DEFAULT_LIMIT,
    dry_run: bool = True,
) -> ReconcileReport:
    """Classify documents that were processed before classification ran.

    Finds readable documents with no `document_type`, classifies them,
    and creates the Managed Policy the classification implies. Does not
    re-upload, re-parse from scratch, or touch anything already
    classified.

    `dry_run` defaults to true: the first thing anybody should do with a
    bulk pass over a customer's library is read what it would do.
    """
    from app.compliance.classification import classify_document
    from app.compliance.policy_governance import ensure_policy_for_document
    from app.core.storage import download_object
    from app.db.session import AsyncSessionLocal
    from app.knowledge.parsing import extract_text

    factory = session_factory or AsyncSessionLocal
    report = ReconcileReport()

    async with factory() as db:
        candidates = [
            row
            for row in await _analysed_documents(
                db, organization_id=organization_id, limit=limit
            )
            if not row.document_type
        ]

        for file_record in candidates:
            report.examined += 1
            if dry_run:
                continue

            try:
                file_bytes = download_object(file_record.storage_key)
                document_text = extract_text(file_record.content_type, file_bytes)
            except Exception:  # noqa: BLE001 - one unreadable file must not stop the pass
                logger.warning("Backfill could not read %s", file_record.id)
                report.failed += 1
                continue

            try:
                document_type = await classify_document(
                    db,
                    organization_id=organization_id,
                    file_record=file_record,
                    document_text=document_text,
                    actor_user_id=actor_user_id,
                )
                if document_type:
                    report.classified += 1

                policy = await ensure_policy_for_document(
                    db,
                    organization_id=organization_id,
                    file_record=file_record,
                    document_text=document_text,
                    actor_user_id=actor_user_id,
                )
                if policy is not None:
                    report.policies_created += 1
                await db.commit()
            except Exception:  # noqa: BLE001 - one bad document must not stop the pass
                await db.rollback()
                logger.exception("Backfill classification failed for %s", file_record.id)
                report.failed += 1

    return report


async def map_documents_to_new_controls(
    organization_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> ReconcileReport:
    """Reconsider already-analysed documents against controls that now exist.

    Run when controls appear — a framework adopted, applicability
    answers changed, controls created by hand. A document uploaded before
    any of that happened was understood correctly and simply had nothing
    to map to; this is the moment it does.

    Idempotent by construction. `_should_extract` returns False for a
    document whose content and control set are both unchanged since it
    was last read, so a second run over the same state maps nothing, and
    the suggestion identity index stops a re-run producing a second copy
    of a mapping that already exists.
    """
    from app.compliance.evidence_ai import _should_extract, suggest_evidence_mappings
    from app.core.storage import download_object
    from app.db.session import AsyncSessionLocal

    factory = session_factory or AsyncSessionLocal
    report = ReconcileReport()

    async with factory() as db:
        controls = (
            await db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id
                )
            )
        ).scalar_one()
        if not controls:
            # Nothing to map to. Not a failure — just nothing to do.
            return report

        for file_record in await _analysed_documents(
            db, organization_id=organization_id, limit=limit
        ):
            report.examined += 1

            if not await _should_extract(
                db, organization_id=organization_id, file_record=file_record
            ):
                # Same content, same controls as last time. Reading it
                # again would ask a non-deterministic model the same
                # question and take whatever it says this time.
                report.skipped += 1
                continue

            try:
                file_bytes = download_object(file_record.storage_key)
                outcome = await suggest_evidence_mappings(
                    db,
                    organization_id=organization_id,
                    file_record=file_record,
                    file_bytes=file_bytes,
                    actor_user_id=actor_user_id,
                )
                if outcome.suggestions:
                    report.mapped += 1
                # `processed_at` is what `_should_extract` compares new
                # controls against. Moving it forward is what stops the
                # next pass re-reading this document for controls it has
                # now already considered.
                file_record.processed_at = datetime.now(UTC)
                await db.commit()
            except Exception:  # noqa: BLE001 - one bad document must not stop the pass
                await db.rollback()
                logger.exception("Mapping existing document %s failed", file_record.id)
                report.failed += 1

    logger.info(
        "Reconciled %s documents against new controls for %s: %s",
        report.examined,
        organization_id,
        report.as_dict(),
    )
    return report


__all__ = [
    "DEFAULT_LIMIT",
    "ReconcileReport",
    "backfill_classification",
    "map_documents_to_new_controls",
]
