from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.db.session import get_db
from app.marketing.models import DemoRequest
from app.marketing.schemas import DemoRequestIn, DemoRequestOut

router = APIRouter(prefix="/api/v1/marketing", tags=["marketing"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None, request.headers.get("user-agent"))


@router.post("/demo-requests", response_model=DemoRequestOut, status_code=status.HTTP_201_CREATED)
async def submit_demo_request(
    payload: DemoRequestIn, request: Request, db: AsyncSession = Depends(get_db)
) -> DemoRequest:
    """Genuinely public — no session, no organization, exactly like
    GET /billing/plans already is. Protected against abuse by the
    existing global, IP-keyed RateLimitMiddleware (app.core.rate_limit),
    which already wraps every route including this one at no extra cost.
    Never silently discards a submission: the row is durable, and a
    platform-level audit event is recorded (organization_id=None — the
    same "platform event, no org yet" shape auth.signup itself uses
    before an organization exists) so a submission is traceable even
    with no real email provider to notify anyone about it (see
    docs/PUBLIC_SITE_DESIGN.md §6 for why there is deliberately no
    list-by-org_admin endpoint here)."""
    demo_request = DemoRequest(
        full_name=payload.full_name,
        work_email=payload.work_email.lower(),
        company_name=payload.company_name,
        company_size=payload.company_size,
        country=payload.country,
        primary_interest=payload.primary_interest,
        message=payload.message,
    )
    db.add(demo_request)
    await db.flush()

    ip_address, user_agent = _client_meta(request)
    await record_event(
        db,
        organization_id=None,
        actor_user_id=None,
        action="marketing.demo_request.created",
        object_type="demo_request",
        object_id=str(demo_request.id),
        after_state={"company_name": demo_request.company_name, "primary_interest": demo_request.primary_interest},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return demo_request
