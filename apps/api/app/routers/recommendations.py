from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.db.session import get_db
from app.dependencies import OrgContext, require_permission
from app.recommendations.models import Recommendation
from app.recommendations.schemas import RecommendationOut
from app.recommendations.service import (
    list_recommendations,
    refresh_recommendations,
    set_recommendation_status,
)

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])


@router.get("", response_model=list[RecommendationOut])
async def get_recommendations(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("business_intelligence.view")),
) -> list[Recommendation]:
    """Recomputes every generator (spec §87) against this org's own live
    data before listing — recommendations are never stale, and a
    dismissed/actioned one is never resurrected (see
    app.recommendations.service.refresh_recommendations)."""
    await refresh_recommendations(db, organization_id=context.organization_id)
    return await list_recommendations(db, organization_id=context.organization_id)


async def _set_status(
    recommendation_id: uuid.UUID, status_value: str, db: AsyncSession, context: OrgContext
) -> Recommendation:
    recommendation = await set_recommendation_status(
        db,
        organization_id=context.organization_id,
        recommendation_id=recommendation_id,
        status=status_value,
    )
    if recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action=f"recommendation.{status_value}",
        object_type="recommendation",
        object_id=str(recommendation.id),
        after_state={"status": status_value},
    )
    await db.commit()
    return recommendation


@router.post("/{recommendation_id}/dismiss", response_model=RecommendationOut)
async def dismiss_recommendation(
    recommendation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("business_intelligence.view")),
) -> Recommendation:
    return await _set_status(recommendation_id, "dismissed", db, context)


@router.post("/{recommendation_id}/action", response_model=RecommendationOut)
async def action_recommendation(
    recommendation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("business_intelligence.view")),
) -> Recommendation:
    """Marks the recommendation as acted on. Does not itself perform the
    suggested action (e.g. creating a Workflow draft) — the frontend
    deep-links each category's suggested action into the module that
    already owns real creation for it (Automation, Sales, etc.), the
    same pattern spec §72's Global Create button uses, rather than a
    second miniature action-executor living here."""
    return await _set_status(recommendation_id, "actioned", db, context)
