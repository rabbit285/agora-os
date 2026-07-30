from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class KnowledgeBaseOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentCreate(BaseModel):
    file_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    knowledge_base_id: uuid.UUID | None = None


class DocumentOut(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    file_id: uuid.UUID
    title: str
    status: str
    error: str | None
    classification: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentChunkOut(BaseModel):
    id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int

    model_config = {"from_attributes": True}


class GraphNodeOut(BaseModel):
    entity_type: str
    id: str
    label: str


class GraphEdgeOut(BaseModel):
    relation: str
    node: GraphNodeOut


class GraphResultOut(BaseModel):
    node: GraphNodeOut
    edges: list[GraphEdgeOut]


class EntityTypeOut(BaseModel):
    entity_types: list[str]
