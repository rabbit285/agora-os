from __future__ import annotations

from pydantic import BaseModel


class SearchResultOut(BaseModel):
    entity_type: str
    id: str
    label: str
    module: str

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultOut]
