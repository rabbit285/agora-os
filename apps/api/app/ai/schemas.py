from __future__ import annotations

import uuid

from pydantic import BaseModel


class CitationOut(BaseModel):
    document_id: uuid.UUID
    chunk_id: uuid.UUID
    chunk_index: int
    score: float


class CopilotAskRequest(BaseModel):
    prompt: str


class CopilotAskResponse(BaseModel):
    text: str
    provider: str
    model: str
    grounded: bool
    citations: list[CitationOut]
