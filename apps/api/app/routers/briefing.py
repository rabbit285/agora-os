from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.briefing.models import Briefing
from app.briefing.schemas import BriefingOut
from app.briefing.service import get_or_create_daily_briefing
from app.db.session import get_db
from app.dependencies import OrgContext, require_permission

router = APIRouter(prefix="/api/v1/briefing", tags=["briefing"])


@router.get("", response_model=BriefingOut)
async def get_daily_briefing(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("business_intelligence.view")),
) -> Briefing:
    """spec §88 — one real briefing per organization per calendar day,
    generated on first request and held stable for the rest of the day
    rather than recomputed on every visit."""
    return await get_or_create_daily_briefing(db, organization_id=context.organization_id)
