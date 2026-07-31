from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.copilot import ask_copilot
from app.ai.schemas import AIProviderStatusOut, CitationOut, CopilotAskRequest, CopilotAskResponse
from app.config import settings
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

# spec §57 Model Gateway: OpenAI/Anthropic are real, live adapters
# (`app.ai.adapters`); Azure OpenAI has no "architecture" qualifier in the
# spec text but has zero adapter code here — disclosed as MISSING, not
# stubbed as configured (see docs/KNOWN_LIMITATIONS.md). Google carries an
# explicit "architecture" qualifier in the spec itself; "Local/private" is
# explicitly "future". No API key is ever stored in the database for any
# provider — every one is environment-variable-only, the same convention
# every OAuth integration in this build follows (see .env.example) — this
# endpoint is a real-time status view, not a secrets-writing configuration
# API.
_AI_PROVIDER_CATALOG = [
    {"provider_key": "anthropic", "name": "Anthropic", "status": "available"},
    {"provider_key": "openai", "name": "OpenAI", "status": "available"},
    {"provider_key": "azure_openai", "name": "Azure OpenAI", "status": "not_built"},
    {"provider_key": "google", "name": "Google", "status": "not_built"},
]


@router.get("/providers", response_model=list[AIProviderStatusOut])
async def list_ai_providers(
    context: OrgContext = Depends(get_org_context),
) -> list[AIProviderStatusOut]:
    """Real-time status of every named spec §57 provider — which is
    actually configured (has a real, live adapter and a real API key set
    via environment variable), which has an adapter but no key, and which
    has no adapter built at all. `active` marks the one provider
    `AI_PROVIDER` actually routes calls to right now (`build_adapter()`);
    every other configured-but-not-active provider has real code but
    isn't the one currently selected."""
    configured_keys = {
        "anthropic": bool(settings.anthropic_api_key),
        "openai": bool(settings.openai_api_key),
    }
    out: list[AIProviderStatusOut] = []
    for entry in _AI_PROVIDER_CATALOG:
        key = entry["provider_key"]
        has_adapter = entry["status"] == "available"
        configured = configured_keys.get(key, False) if has_adapter else False
        out.append(
            AIProviderStatusOut(
                provider_key=key,
                name=entry["name"],
                has_adapter=has_adapter,
                configured=configured,
                active=configured and settings.ai_provider == key,
            )
        )
    return out


@router.post("/copilot/ask", response_model=CopilotAskResponse)
async def copilot_ask(
    payload: CopilotAskRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("ai.copilot.ask")),
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
