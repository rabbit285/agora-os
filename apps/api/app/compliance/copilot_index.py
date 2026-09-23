"""Making a compliance document answerable by the Copilot.

Two pipelines existed and never met. Uploading a policy ran Document
Intelligence — parse, classify, propose control mappings, create evidence
— and set `File.processing_status = "ready"`. The Copilot searches
`document_chunks`, which only `app.knowledge.service.ingest_document`
ever writes, and nothing in the compliance path called it. An
organization with eighteen processed documents and sixty evidence rows
was told "I don't have any indexed documents to answer this from yet",
which was true and completely misleading.

This is the bridge. A compliance upload gets a knowledge `Document` in a
dedicated knowledge base, and the existing ingest service chunks and
embeds it exactly as it does for anything else — no second retrieval
path, no second chunk table, no duplicated embedding code.

**Indexing failure is not analysis failure.** They are separate columns
because they are separate pipelines: the embedding provider can be down
while parsing and mapping worked perfectly. Reporting the document as
"Analyzed" in that case is what sent people to ask the Copilot about a
document it could not see.

Idempotent throughout: re-indexing the same file reuses its Document row
and `ingest_document` clears the old chunks, so a backfill can run as
often as it likes without duplicating anything.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.core.dedupe import get_or_create
from app.core.models import File
from app.knowledge.models import Document, KnowledgeBase
from app.knowledge.service import ingest_document

logger = logging.getLogger("agora.compliance.copilot_index")

# Kept apart from the "General" knowledge base so a customer browsing
# their knowledge bases sees where these came from, and so a future
# feature can scope retrieval to compliance material alone.
COMPLIANCE_KNOWLEDGE_BASE = "Compliance Documents"


async def _knowledge_base(db: AsyncSession, organization_id: uuid.UUID) -> KnowledgeBase:
    """The compliance knowledge base for this organization, made once.

    Read-then-insert loses the race that an organization's first upload
    reliably produces: two documents submitted together both find no
    knowledge base, both insert, and the second one dies on
    `uq_knowledge_base_org_name` — taking a whole document's processing
    down with it and leaving it marked failed for a reason that had
    nothing to do with the document.

    `get_or_create` inserts with ON CONFLICT DO NOTHING and reads the
    winner back, so both callers end up with the same row and neither
    raises.
    """
    knowledge_base, _ = await get_or_create(
        db,
        KnowledgeBase,
        match={
            "organization_id": organization_id,
            "name": COMPLIANCE_KNOWLEDGE_BASE,
        },
        defaults={
            "description": (
                "Policies and procedures uploaded to Compliance. Indexed so the "
                "Copilot can answer questions from them with citations."
            )
        },
    )
    return knowledge_base


async def _document_for(
    db: AsyncSession, *, file_record: File, organization_id: uuid.UUID
) -> Document:
    """The knowledge Document standing for this compliance file.

    Looked up by `file_id` rather than created blindly, so re-processing a
    document does not leave a second copy of it in the index.
    """
    existing = (
        await db.execute(
            select(Document).where(
                Document.organization_id == organization_id,
                Document.file_id == file_record.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    knowledge_base = await _knowledge_base(db, organization_id)
    document = Document(
        organization_id=organization_id,
        knowledge_base_id=knowledge_base.id,
        file_id=file_record.id,
        title=file_record.original_filename,
        classification=file_record.classification,
        created_by=file_record.uploaded_by,
    )
    db.add(document)
    await db.flush()
    return document


async def index_for_copilot(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_record: File,
    file_bytes: bytes,
    gateway: ModelGateway | None = None,
) -> str:
    """Chunk and embed one compliance document. Returns the index status.

    Never raises: an embedding provider being down must not fail the
    upload, lose the evidence Document Intelligence already extracted, or
    leave the document looking unprocessed. It records the failure on the
    file so the UI can say so and a retry can find it.
    """
    document = await _document_for(
        db, file_record=file_record, organization_id=organization_id
    )

    try:
        status = await ingest_document(
            db,
            document_id=document.id,
            file_bytes=file_bytes,
            gateway=gateway,
        )
    except Exception as exc:  # noqa: BLE001 - a provider fault is not a bug here
        logger.warning(
            "Copilot indexing failed for file %s: %s", file_record.id, exc.__class__.__name__
        )
        file_record.index_status = "failed"
        # The class name, never the message: a provider error can carry a
        # request payload, and this string is shown to the customer.
        file_record.index_error = (
            "The document was read and mapped, but could not be indexed for the "
            "Copilot. Retry from the document list."
        )
        return file_record.index_status

    if status == "ready":
        file_record.index_status = "indexed"
        file_record.index_error = None
        file_record.indexed_at = datetime.now(UTC)
    elif status == "unsupported_format":
        file_record.index_status = "unsupported"
        file_record.index_error = "The Copilot cannot read this file format."
    else:
        file_record.index_status = "failed"
        file_record.index_error = document.error or "No text could be indexed."

    return file_record.index_status


async def backfill_organization(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    gateway: ModelGateway | None = None,
    limit: int = 200,
) -> dict[str, int]:
    """Index every analysed document that never reached the Copilot.

    Indexing was added after documents were already being processed, so
    every existing customer has a library the Copilot cannot see. Rather
    than a one-off script somebody has to remember to run, this is
    idempotent and safe to call whenever: it selects only files that
    analysed successfully and are not already indexed.
    """
    from app.core.storage import download_object

    pending = list(
        (
            await db.execute(
                select(File)
                .where(
                    File.organization_id == organization_id,
                    File.processing_status == "ready",
                    File.index_status.in_(("pending", "failed")),
                    # A generated report must not be retrieved as
                    # evidence for the compliance state it was written
                    # from. Asking about the report itself is a
                    # different question, answered from the record it
                    # belongs to rather than from this index.
                    File.artifact_type == "source",
                )
                .order_by(File.created_at)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    counts = {"indexed": 0, "failed": 0, "unsupported": 0}
    for file_record in pending:
        try:
            file_bytes = download_object(file_record.storage_key)
        except Exception:  # noqa: BLE001 - a missing object is not a crash
            logger.warning("Backfill could not read %s from storage", file_record.id)
            file_record.index_status = "failed"
            file_record.index_error = "The stored file could not be read."
            counts["failed"] += 1
            continue

        status = await index_for_copilot(
            db,
            organization_id=organization_id,
            file_record=file_record,
            file_bytes=file_bytes,
            gateway=gateway,
        )
        counts[status] = counts.get(status, 0) + 1

    await db.commit()
    if any(counts.values()):
        logger.info("Copilot backfill for %s: %s", organization_id, counts)
    return counts


__all__ = [
    "COMPLIANCE_KNOWLEDGE_BASE",
    "backfill_organization",
    "index_for_copilot",
]
