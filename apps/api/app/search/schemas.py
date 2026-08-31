from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel


@dataclass
class SearchResult:
    entity_type: str
    id: str
    label: str
    # Which part of the product this belongs to, in the words the
    # navigation uses — so a reader can tell a Control hit from a
    # Requirement hit at a glance.
    module: str
    # Where to open it. Computed server-side: a client-side lookup table
    # drifts the moment a route changes, and the failure mode is a result
    # that looks real and lands on a 404.
    href: str


class SearchResultOut(BaseModel):
    entity_type: str
    id: str
    label: str
    module: str
    href: str

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultOut]
