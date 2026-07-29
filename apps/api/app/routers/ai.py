from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot import ask_copilot
from app.ai.schemas import CitationOut, CopilotAskRequest, CopilotAskResponse
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.post("/copilot/ask", response_model=CopilotAskResponse)
async def copilot_ask(
    payload: CopilotAskRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> CopilotAskResponse:
    """Retrieval-grounded Copilot (spec section 9): embeds the question,
    searches the organization's own document chunks, and answers using
    only what was retrieved — citations reflect what was actually fetched,
    not anything the model asserts about itself (docs/AI_ARCHITECTURE.md)."""
    answer = await ask_copilot(
        db,
        organization_id=context.organization_id,
        requested_by=context.user.id,
        question=payload.prompt,
    )
    await db.commit()
    return CopilotAskResponse(
        text=answer.text,
        provider=answer.provider,
        model=answer.model,
        grounded=answer.grounded,
        citations=[
            CitationOut(
                document_id=c.document_id,
                chunk_id=c.chunk_id,
                chunk_index=c.chunk_index,
                score=c.score,
            )
            for c in answer.citations
        ],
    )
