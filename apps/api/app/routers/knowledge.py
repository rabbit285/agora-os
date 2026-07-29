from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.models import File
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context
from app.knowledge.models import Document, DocumentChunk, KnowledgeBase
from app.knowledge.schemas import (
    DocumentChunkOut,
    DocumentCreate,
    DocumentOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
)
from app.knowledge.service import get_or_create_default_knowledge_base
from app.knowledge.workflow_client import IngestionStarter, get_ingestion_starter

logger = logging.getLogger("agora.knowledge")

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseOut])
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[KnowledgeBase]:
    result = await db.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.organization_id == context.organization_id)
        .order_by(KnowledgeBase.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/knowledge-bases", response_model=KnowledgeBaseOut, status_code=status.HTTP_201_CREATED
)
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> KnowledgeBase:
    knowledge_base = KnowledgeBase(organization_id=context.organization_id, **payload.model_dump())
    db.add(knowledge_base)
    await db.commit()
    await db.refresh(knowledge_base)
    return knowledge_base


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.organization_id == context.organization_id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    start_ingestion: IngestionStarter = Depends(get_ingestion_starter),
) -> Document:
    file_record = await db.get(File, payload.file_id)
    if file_record is None or file_record.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if payload.knowledge_base_id is not None:
        knowledge_base = await db.get(KnowledgeBase, payload.knowledge_base_id)
        if knowledge_base is None or knowledge_base.organization_id != context.organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found"
            )
    else:
        knowledge_base = await get_or_create_default_knowledge_base(db, context.organization_id)

    document = Document(
        organization_id=context.organization_id,
        knowledge_base_id=knowledge_base.id,
        file_id=file_record.id,
        title=payload.title,
        classification=file_record.classification,
        created_by=context.user.id,
    )
    db.add(document)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="knowledge.document.created",
        object_type="document",
        object_id=str(document.id),
        after_state={"title": document.title, "file_id": str(file_record.id)},
    )
    await db.commit()
    await db.refresh(document)

    try:
        await start_ingestion(document.id)
    except Exception:  # noqa: BLE001 — starting the workflow is best-effort
        # Temporal being unreachable must not fail document creation; the
        # document simply stays "pending" until ingestion can be retried
        # (spec C2: graceful degradation, not a crash).
        logger.warning("Failed to start ingestion workflow for document %s", document.id)

    return document


@router.get("/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> Document:
    document = await db.get(Document, document_id)
    if document is None or document.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.get("/documents/{document_id}/chunks", response_model=list[DocumentChunkOut])
async def list_document_chunks(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[DocumentChunk]:
    document = await db.get(Document, document_id)
    if document is None or document.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(result.scalars().all())
