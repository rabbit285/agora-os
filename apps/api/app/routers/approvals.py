from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.models import Approval
from app.core.schemas import ApprovalDecision, ApprovalOut
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Approval]:
    result = await db.execute(
        select(Approval)
        .where(Approval.organization_id == context.organization_id)
        .order_by(Approval.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
async def decide_approval(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("core.approvals.decide")),
) -> Approval:
    approval = await db.get(Approval, approval_id)
    if approval is None or approval.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval already decided")

    approval.status = "approved" if payload.approve else "rejected"
    approval.decided_by = context.user.id
    approval.decided_at = datetime.now(UTC)

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action=f"core.approval.{approval.status}",
        object_type="approval",
        object_id=str(approval.id),
        after_state={"status": approval.status, "reason": payload.reason},
    )
    await db.commit()
    await db.refresh(approval)
    return approval
