from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context
from app.search.schemas import SearchResponse, SearchResultOut
from app.search.service import global_search

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(default="", max_length=200),
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> SearchResponse:
    """Global Search (spec §47): tenant-scoped substring search across
    every module's named records — see app.search.service module
    docstring for the permission-scoping rationale."""
    results = await global_search(db, organization_id=context.organization_id, query=q)
    return SearchResponse(query=q, results=[SearchResultOut.model_validate(r) for r in results])
