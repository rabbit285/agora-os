from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.memory.models import ENTRY_TYPES


class MemoryEntryCreate(BaseModel):
    entry_type: str
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("entry_type")
    @classmethod
    def _validate_entry_type(cls, value: str) -> str:
        if value not in ENTRY_TYPES:
            raise ValueError(f"Unknown entry_type: {value}")
        return value


class MemoryEntryUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class MemoryEntryOut(BaseModel):
    id: uuid.UUID
    entry_type: str
    content: str
    provenance_type: str
    provenance_id: uuid.UUID | None
    created_by: uuid.UUID | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
