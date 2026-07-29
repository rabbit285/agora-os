"""Document ingestion pipeline: parse -> chunk -> embed -> persist.

This is the pure business-logic layer, deliberately decoupled from how it
gets invoked — the API can call it directly for tests, and the Temporal
worker's activity calls it for the real durable execution path (spec
section 61: don't couple workflows directly to HTTP requests). Neither
caller needs to know about the other.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.core.models import File
from app.knowledge.chunking import chunk_text, estimate_token_count
from app.knowledge.models import Document, DocumentChunk, KnowledgeBase
from app.knowledge.parsing import UnsupportedFormatError, extract_text

DEFAULT_KNOWLEDGE_BASE_NAME = "General"


async def get_or_create_default_knowledge_base(
    db: AsyncSession, organization_id: uuid.UUID
) -> KnowledgeBase:
    existing = (
        await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.organization_id == organization_id,
                KnowledgeBase.name == DEFAULT_KNOWLEDGE_BASE_NAME,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    knowledge_base = KnowledgeBase(
        organization_id=organization_id,
        name=DEFAULT_KNOWLEDGE_BASE_NAME,
        description="Default knowledge base for uploaded documents.",
    )
    db.add(knowledge_base)
    await db.flush()
    return knowledge_base


async def ingest_document(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    file_bytes: bytes,
    gateway: ModelGateway | None = None,
) -> str:
    """Runs the full pipeline for one document. Returns the final status.

    `file_bytes` is passed in rather than fetched here so this function
    doesn't need to know about object storage — the caller (activity or
    test) is responsible for getting the bytes, keeping this testable
    without a real S3/MinIO connection.
    """
    document = await db.get(Document, document_id)
    if document is None:
        raise LookupError(f"Document {document_id} not found")

    file_record = await db.get(File, document.file_id)
    if file_record is None:
        raise LookupError(f"File {document.file_id} not found for document {document_id}")

    document.status = "processing"
    await db.flush()

    try:
        text = extract_text(file_record.content_type, file_bytes)
    except UnsupportedFormatError as exc:
        document.status = "unsupported_format"
        document.error = str(exc)
        await db.commit()
        return document.status

    chunks = chunk_text(text)
    if not chunks:
        document.status = "failed"
        document.error = "No extractable text content"
        await db.commit()
        return document.status

    # Clear any chunks from a previous attempt before re-ingesting.
    existing = (
        await db.execute(select(DocumentChunk).where(DocumentChunk.document_id == document.id))
    ).scalars()
    for chunk_row in existing:
        await db.delete(chunk_row)
    await db.flush()

    gateway = gateway or ModelGateway()
    embeddings = await gateway.embed(
        db,
        organization_id=document.organization_id,
        requested_by=document.created_by,
        task_type="knowledge.embed_document",
        texts=chunks,
    )

    for index, (chunk_content, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
        db.add(
            DocumentChunk(
                organization_id=document.organization_id,
                document_id=document.id,
                chunk_index=index,
                content=chunk_content,
                embedding=embedding,
                token_count=estimate_token_count(chunk_content),
            )
        )

    document.status = "ready"
    document.error = None
    await db.commit()
    return document.status
