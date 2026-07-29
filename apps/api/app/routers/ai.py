from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import GenerateRequest, ModelGateway
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

_gateway = ModelGateway()


class CopilotAskRequest(BaseModel):
    prompt: str


class CopilotAskResponse(BaseModel):
    text: str
    provider: str
    model: str


@router.post("/copilot/ask", response_model=CopilotAskResponse)
async def copilot_ask(
    payload: CopilotAskRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> CopilotAskResponse:
    """Minimal Copilot entry point for Phase 1 — exercises the Model Gateway
    end to end (request -> AiRun log -> response). The full intent
    router / context builder / citation pipeline (spec section 9) is a
    Phase 2 deliverable once the Knowledge module exists."""
    result = await _gateway.generate(
        db,
        organization_id=context.organization_id,
        requested_by=context.user.id,
        request=GenerateRequest(task_type="copilot.ask", prompt=payload.prompt),
    )
    await db.commit()
    return CopilotAskResponse(text=result.text, provider=result.provider, model=result.model)
