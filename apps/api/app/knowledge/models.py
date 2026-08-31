"""Knowledge domain (spec sections 11, 46, 50 — Phase 2).

Embeddings are stored as a JSON float array today, not a native pgvector
column — see docs/DECISIONS.md ADR-0007. Similarity search (cosine
distance queries) is deferred to whichever Phase 2+ feature first needs
retrieval (the AI Copilot's RAG pipeline); this module only needs to
ingest and store chunks correctly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class KnowledgeBase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_knowledge_base_org_name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("knowledge_bases.id"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # pending -> processing -> ready | failed | unsupported_format
    status: Mapped[str] = mapped_column(String(30), default="pending")
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    classification: Mapped[str] = mapped_column(String(20), default="internal")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class DocumentChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(String(8000), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    token_count: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Where this chunk came from, in the document's own terms. Resolved at
    # ingest (app.knowledge.headings) because it is a property of the
    # source text, not of the answer, and re-deriving it per citation
    # would mean re-parsing the file on every question.
    #
    # Both are nullable and mean it: a document with no headings has no
    # section, and a .docx has no pages. A citation says what it knows and
    # falls back to the document title rather than inventing a location.
    section_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    page_number: Mapped[int | None] = mapped_column(nullable=True)

    # citations (spec F4) reference chunk id + document id + this index.
    # Those stay here, and stay in the AI request record, because an
    # auditor asking "what exactly did the model see" needs the exact
    # chunk — they are simply never shown to a customer, who gets the
    # title/section/page above instead (app.ai.citations).
