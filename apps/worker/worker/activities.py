"""Activity implementations.

Unlike workflows, activities run outside Temporal's determinism sandbox,
so they can freely do I/O. Application imports are still done lazily
inside each function body (not at module top) so this module stays cheap
to import from main.py and so nothing here could ever accidentally be
mistaken for workflow-defining code.
"""

from __future__ import annotations

import logging
import uuid

from temporalio import activity

logger = logging.getLogger("agora.worker.activities")


@activity.defn(name="ping_activity")
async def ping_activity() -> str:
    return "pong"


@activity.defn(name="ingest_document_activity")
async def ingest_document_activity(document_id: str) -> str:
    import app.db.register_all_models  # noqa: F401 — see module docstring
    from app.core.models import File
    from app.core.storage import download_object
    from app.db.session import AsyncSessionLocal
    from app.knowledge.models import Document
    from app.knowledge.service import ingest_document

    doc_uuid = uuid.UUID(document_id)
    async with AsyncSessionLocal() as db:
        document = await db.get(Document, doc_uuid)
        if document is None:
            raise LookupError(f"Document {document_id} not found")
        file_record = await db.get(File, document.file_id)
        if file_record is None:
            raise LookupError(f"File {document.file_id} not found")

        file_bytes = download_object(file_record.storage_key)
        status = await ingest_document(db, document_id=doc_uuid, file_bytes=file_bytes)
        logger.info("Document %s ingestion finished with status=%s", document_id, status)
        return status
