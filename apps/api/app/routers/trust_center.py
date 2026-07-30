from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Policy
from app.core.models import Organization
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.trust_center.models import EvidenceRequest, TrustCenterItem
from app.trust_center.schemas import (
    EvidenceRequestCreate,
    EvidenceRequestOut,
    EvidenceRequestStatusUpdate,
    TrustCenterItemOut,
    TrustCenterItemUpsert,
    TrustCenterPublicItemOut,
    TrustCenterPublicOut,
    TrustCenterPublicPolicyOut,
)
from app.trust_center.service import (
    create_evidence_request,
    fulfill_evidence_request,
    upsert_trust_center_item,
)

router = APIRouter(prefix="/api/v1/trust-center", tags=["trust-center"])


@router.get("/public/{org_slug}", response_model=TrustCenterPublicOut)
async def get_public_trust_center(
    org_slug: str, db: AsyncSession = Depends(get_db)
) -> TrustCenterPublicOut:
    """No session/OrgContext dependency — this is the genuinely public
    trust page (spec B4), reachable by anyone with the org's slug. The
    security boundary is simply "only is_public rows, and only for a
    published Policy," not RBAC."""
    organization = (
        await db.execute(select(Organization).where(Organization.slug == org_slug))
    ).scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    items_result = await db.execute(
        select(TrustCenterItem).where(
            TrustCenterItem.organization_id == organization.id,
            TrustCenterItem.is_public.is_(True),
        )
    )
    public_items = []
    for item in items_result.scalars().all():
        policy_out = None
        if item.policy_id is not None:
            policy = await db.get(Policy, item.policy_id)
            if policy is not None and policy.status == "published":
                policy_out = TrustCenterPublicPolicyOut(id=policy.id, title=policy.title)
        public_items.append(
            TrustCenterPublicItemOut(
                category=item.category,
                title=item.title,
                content=item.content,
                status=item.status,
                policy=policy_out,
            )
        )

    return TrustCenterPublicOut(organization_name=organization.name, items=public_items)


@router.post(
    "/public/{org_slug}/evidence-requests",
    response_model=EvidenceRequestOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_evidence_request(
    org_slug: str,
    payload: EvidenceRequestCreate,
    db: AsyncSession = Depends(get_db),
) -> EvidenceRequest:
    """Also public — no session/OrgContext dependency. Always creates a
    linked core.Task so the org sees it in its normal task queue."""
    organization = (
        await db.execute(select(Organization).where(Organization.slug == org_slug))
    ).scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    request = await create_evidence_request(
        db,
        organization_id=organization.id,
        requester_name=payload.requester_name,
        requester_email=payload.requester_email,
        company_name=payload.company_name,
        message=payload.message,
    )
    await db.commit()
    await db.refresh(request)
    return request


@router.get("/items", response_model=list[TrustCenterItemOut])
async def list_trust_center_items(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[TrustCenterItem]:
    result = await db.execute(
        select(TrustCenterItem)
        .where(TrustCenterItem.organization_id == context.organization_id)
        .order_by(TrustCenterItem.category)
    )
    return list(result.scalars().all())


@router.post("/items", response_model=TrustCenterItemOut, status_code=status.HTTP_201_CREATED)
async def set_trust_center_item(
    payload: TrustCenterItemUpsert,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.trust_center.manage")),
) -> TrustCenterItem:
    if payload.policy_id is not None:
        policy = await db.get(Policy, payload.policy_id)
        if policy is None or policy.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    item = await upsert_trust_center_item(
        db,
        organization_id=context.organization_id,
        category=payload.category,
        title=payload.title,
        content=payload.content,
        status=payload.status,
        is_public=payload.is_public,
        policy_id=payload.policy_id,
        owner_id=payload.owner_id,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/evidence-requests", response_model=list[EvidenceRequestOut])
async def list_evidence_requests(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[EvidenceRequest]:
    result = await db.execute(
        select(EvidenceRequest)
        .where(EvidenceRequest.organization_id == context.organization_id)
        .order_by(EvidenceRequest.created_at.desc())
    )
    return list(result.scalars().all())


@router.patch("/evidence-requests/{request_id}/status", response_model=EvidenceRequestOut)
async def update_evidence_request_status(
    request_id: uuid.UUID,
    payload: EvidenceRequestStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.trust_center.manage")),
) -> EvidenceRequest:
    evidence_request = await db.get(EvidenceRequest, request_id)
    if evidence_request is None or evidence_request.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if payload.status == "fulfilled":
        evidence_request = await fulfill_evidence_request(
            db, evidence_request=evidence_request, actor_user_id=context.user.id
        )
    await db.commit()
    await db.refresh(evidence_request)
    return evidence_request
