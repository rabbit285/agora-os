"""Trust Center domain services.

`upsert_trust_center_item` treats each (organization, category) pair as a
single row (spec B4's fixed 14-category list, enforced by
`uq_trust_center_item_org_category`) rather than an open-ended list —
setting a category's content/status/visibility again updates the same
row instead of accumulating duplicates.

`create_evidence_request` ships this build's now-familiar "creates a
tracked consequence" hook shape (spec §80) with no authenticated actor:
a public evidence request always creates a linked `core.Task`, the same
primitive every other module's hook reuses, so the org sees it in its
normal task queue rather than a separate inbox.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.models import Task
from app.trust_center.models import EvidenceRequest, TrustCenterItem


async def upsert_trust_center_item(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    category: str,
    title: str,
    content: str | None,
    status: str,
    is_public: bool,
    policy_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
) -> TrustCenterItem:
    existing = (
        await db.execute(
            select(TrustCenterItem).where(
                TrustCenterItem.organization_id == organization_id,
                TrustCenterItem.category == category,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        item = TrustCenterItem(
            organization_id=organization_id,
            category=category,
            title=title,
            content=content,
            status=status,
            is_public=is_public,
            policy_id=policy_id,
            owner_id=owner_id,
        )
        db.add(item)
        before_state = None
    else:
        item = existing
        before_state = {"status": item.status, "is_public": item.is_public}
        item.title = title
        item.content = content
        item.status = status
        item.is_public = is_public
        item.policy_id = policy_id
        item.owner_id = owner_id
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="trust_center.item.upserted",
        object_type="trust_center_item",
        object_id=str(item.id),
        before_state=before_state,
        after_state={"status": status, "is_public": is_public},
    )
    return item


async def create_evidence_request(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    requester_name: str,
    requester_email: str,
    company_name: str | None,
    message: str | None,
) -> EvidenceRequest:
    request = EvidenceRequest(
        organization_id=organization_id,
        requester_name=requester_name,
        requester_email=requester_email,
        company_name=company_name,
        message=message,
    )
    db.add(request)
    await db.flush()

    task = Task(
        organization_id=organization_id,
        title=f"Evidence request from {requester_name}"
        + (f" ({company_name})" if company_name else ""),
        description=message,
        module="compliance",
        priority="normal",
    )
    db.add(task)
    await db.flush()
    request.related_task_id = task.id

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=None,
        action="trust_center.evidence_request.created",
        object_type="trust_center_evidence_request",
        object_id=str(request.id),
        after_state={"requester_email": requester_email, "related_task_id": str(task.id)},
    )
    return request


async def fulfill_evidence_request(
    db: AsyncSession,
    *,
    evidence_request: EvidenceRequest,
    actor_user_id: uuid.UUID | None,
) -> EvidenceRequest:
    before_status = evidence_request.status
    evidence_request.status = "fulfilled"
    await record_event(
        db,
        organization_id=evidence_request.organization_id,
        actor_user_id=actor_user_id,
        action="trust_center.evidence_request.status_changed",
        object_type="trust_center_evidence_request",
        object_id=str(evidence_request.id),
        before_state={"status": before_status},
        after_state={"status": "fulfilled"},
    )
    return evidence_request
