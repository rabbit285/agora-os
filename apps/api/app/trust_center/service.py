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
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import Policy
from app.core.models import File, Task
from app.trust_center.models import EvidenceRequest, TrustCenterItem


class TrustCenterClaimError(Exception):
    """A published claim this system will not record as stated."""


# Statuses that assert a third party's conclusion rather than our own
# work. A buyer can reason about "implemented" from the rest of the page;
# they cannot check "certified" without the certificate, which is exactly
# why it is the one worth faking and the one we refuse to take on trust.
ATTESTED_STATUSES = ("independently_assessed", "certified")


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
    attestation_file_id: uuid.UUID | None = None,
    attestation_note: str | None = None,
) -> TrustCenterItem:
    existing = (
        await db.execute(
            select(TrustCenterItem).where(
                TrustCenterItem.organization_id == organization_id,
                TrustCenterItem.category == category,
            )
        )
    ).scalar_one_or_none()

    if status in ATTESTED_STATUSES:
        # Deliberately not inferable from anything else in the product.
        # Every control being implemented does not make an organization
        # certified; only an auditor does, and the evidence of that is a
        # document with a named person standing behind it.
        if attestation_file_id is None:
            raise TrustCenterClaimError(
                f"'{status}' states that an external party assessed this organization. Attach "
                "the certificate or audit report before publishing that claim — it cannot be "
                "inferred from the controls recorded in Veyntra."
            )
        file_record = await db.get(File, attestation_file_id)
        if file_record is None or file_record.organization_id != organization_id:
            raise TrustCenterClaimError("The attestation document could not be found.")
        if not (attestation_note or "").strip():
            raise TrustCenterClaimError(
                "Record who issued this attestation and what it covers, so a reader can tell a "
                "scoped report from a full certification."
            )

    if is_public and policy_id is not None:
        # A draft policy is by definition not agreed internally, so
        # publishing it externally publishes something nobody has signed
        # off. The public view already hides unpublished policies; this
        # refuses the intent rather than silently doing something else.
        policy = await db.get(Policy, policy_id)
        if policy is None or policy.organization_id != organization_id:
            raise TrustCenterClaimError("The linked policy could not be found.")
        if policy.status != "published":
            raise TrustCenterClaimError(
                f"'{policy.title}' is still a draft. Publish the policy before linking it to a "
                "public Trust Center entry."
            )

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
            attestation_file_id=attestation_file_id,
            attestation_note=attestation_note,
            attested_by=actor_user_id if status in ATTESTED_STATUSES else None,
            attested_at=datetime.now(UTC) if status in ATTESTED_STATUSES else None,
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
        item.attestation_file_id = attestation_file_id
        item.attestation_note = attestation_note
        if status in ATTESTED_STATUSES:
            item.attested_by = actor_user_id
            item.attested_at = datetime.now(UTC)
        else:
            # Dropping back below a certification claim clears its
            # attestation, so a stale certificate cannot linger against a
            # status that no longer asserts one.
            item.attested_by = None
            item.attested_at = None
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
