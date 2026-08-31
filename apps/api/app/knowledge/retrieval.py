"""Similarity search over stored chunk embeddings.

Computes cosine similarity in Python over embeddings pulled from the
database rather than a native pgvector `<=>` query — see docs/DECISIONS.md
ADR-0012. Fine at the chunk volumes a single organization's knowledge base
reaches before this needs revisiting; not fine at scale, and that's the
explicit trade-off, not an oversight.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import DocumentChunk

DEFAULT_TOP_K = 5


@dataclass
class RetrievedChunk:
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    chunk_index: int
    content: str
    score: float
    # Carried through from ingest so a citation can name a place in the
    # document without a second query per result. Both may be None — see
    # DocumentChunk for when and why.
    section_label: str | None = None
    page_number: int | None = None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def search_chunks(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    query_embedding: list[float],
    knowledge_base_id: uuid.UUID | None = None,
    top_k: int = DEFAULT_TOP_K,
    include_superseded: bool = False,
) -> list[RetrievedChunk]:
    """Tenant-scoped: only ever searches chunks belonging to
    `organization_id`, regardless of what the caller asks for.

    Superseded versions are excluded by default. When a policy has been
    revised, the old wording is still readable and still cited by the
    history — but answering "what does our policy say" from text the
    organization has replaced states the wrong rule as the current one,
    which is the specific failure a compliance product cannot have.
    `include_superseded` is for callers reading history deliberately.
    """
    from app.knowledge.models import Document

    query = select(DocumentChunk).where(DocumentChunk.organization_id == organization_id)
    if knowledge_base_id is not None:
        query = query.join(Document, Document.id == DocumentChunk.document_id).where(
            Document.knowledge_base_id == knowledge_base_id
        )

    if not include_superseded:
        from app.core.models import File

        superseded = select(File.id).where(
            File.organization_id == organization_id,
            File.superseded_by_id.is_not(None),
        )
        query = query.where(
            DocumentChunk.document_id.not_in(
                select(Document.id).where(Document.file_id.in_(superseded))
            )
        )

    rows = (await db.execute(query)).scalars().all()

    scored = [
        RetrievedChunk(
            document_id=row.document_id,
            chunk_id=row.id,
            chunk_index=row.chunk_index,
            content=row.content,
            score=cosine_similarity(query_embedding, row.embedding),
            section_label=row.section_label,
            page_number=row.page_number,
        )
        for row in rows
    ]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]
