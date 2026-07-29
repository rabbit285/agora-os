"""Seed script: demo organization "Acme AI Technologies" (spec section 84).

Run with: docker compose exec api python -m app.seed
Idempotent — safe to run multiple times against the same database.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.core.models import File, LegalEntity, Membership, MembershipRole, Organization, Task
from app.core.rbac import ensure_system_roles, get_system_role
from app.core.storage import ensure_bucket, upload_object
from app.db.session import AsyncSessionLocal
from app.identity.models import User
from app.knowledge.models import Document
from app.knowledge.service import get_or_create_default_knowledge_base, ingest_document
from app.security import hash_password

logger = logging.getLogger("agora.seed")
logging.basicConfig(level=logging.INFO)

DEMO_ORG_SLUG = "acme-ai-technologies"
DEMO_ADMIN_EMAIL = "admin@acme-ai.example"
DEMO_ADMIN_PASSWORD = "ChangeMe123456!"


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        await ensure_system_roles(db)

        organization = (
            await db.execute(select(Organization).where(Organization.slug == DEMO_ORG_SLUG))
        ).scalar_one_or_none()
        if organization is None:
            organization = Organization(name="Acme AI Technologies", slug=DEMO_ORG_SLUG)
            db.add(organization)
            await db.flush()
            db.add(
                LegalEntity(
                    organization_id=organization.id,
                    name="Acme AI Technologies",
                    country="DE",
                    is_default=True,
                )
            )
            logger.info("Created organization %s", organization.id)
        else:
            logger.info("Organization already seeded (%s)", organization.id)

        admin = (
            await db.execute(select(User).where(User.email == DEMO_ADMIN_EMAIL))
        ).scalar_one_or_none()
        if admin is None:
            admin = User(
                email=DEMO_ADMIN_EMAIL,
                hashed_password=hash_password(DEMO_ADMIN_PASSWORD),
                full_name="Acme Admin",
            )
            db.add(admin)
            await db.flush()
            logger.info("Created admin user %s", admin.email)

        membership = (
            await db.execute(
                select(Membership).where(
                    Membership.organization_id == organization.id,
                    Membership.user_id == admin.id,
                )
            )
        ).scalar_one_or_none()
        if membership is None:
            membership = Membership(
                organization_id=organization.id, user_id=admin.id, status="active"
            )
            db.add(membership)
            await db.flush()
            org_admin_role = await get_system_role(db, "org_admin")
            db.add(MembershipRole(membership_id=membership.id, role_id=org_admin_role.id))
            logger.info("Granted org_admin membership")

        existing_tasks = (
            (await db.execute(select(Task).where(Task.organization_id == organization.id)))
            .scalars()
            .all()
        )
        if not existing_tasks:
            sample_tasks = [
                ("Review Q3 GDPR evidence gaps", "compliance", "high"),
                ("Investigate elevated login failures", "security", "urgent"),
                ("Follow up with 3 stalled enterprise opportunities", "sales", "normal"),
                ("Clear support backlog from weekend", "support", "high"),
                ("Approve vendor onboarding workflow draft", "automation", "normal"),
            ]
            for title, module, priority in sample_tasks:
                db.add(
                    Task(
                        organization_id=organization.id,
                        title=title,
                        module=module,
                        priority=priority,
                        status="open",
                    )
                )
            logger.info("Seeded %d sample tasks", len(sample_tasks))

        await db.commit()

        existing_documents = (
            (await db.execute(select(Document).where(Document.organization_id == organization.id)))
            .scalars()
            .all()
        )
        if not existing_documents:
            await _seed_sample_document(db, organization_id=organization.id, uploaded_by=admin.id)

        logger.info(
            "Seed complete. Log in as %s / %s (org: %s)",
            DEMO_ADMIN_EMAIL,
            DEMO_ADMIN_PASSWORD,
            organization.slug,
        )


SAMPLE_DOCUMENT_TEXT = """\
Acme AI Technologies — GDPR Compliance Overview

Acme AI Technologies processes personal data of EU customers and
employees in connection with its B2B SaaS platform. This overview
summarizes the company's current data protection posture.

Data categories processed include: account contact details, usage
analytics, and support ticket content. Special category data is not
intentionally collected.

Acme relies on legitimate interest and contractual necessity as the
primary legal bases for processing customer data, and consent for
marketing communications. Data subject access requests are handled
within the statutory 30-day window.

Data is retained for the duration of the customer relationship plus 24
months, after which it is deleted unless a legal hold applies. Acme uses
sub-processors for cloud hosting and email delivery; a current list is
maintained in the vendor register.
"""


async def _seed_sample_document(
    db: AsyncSession, *, organization_id: uuid.UUID, uploaded_by: uuid.UUID
) -> None:
    """Uploads and fully ingests one real sample document so the Knowledge
    module has honest, non-empty demo data (spec section 84) rather than a
    fabricated "ready" status with no underlying file."""
    ensure_bucket()

    data = SAMPLE_DOCUMENT_TEXT.encode("utf-8")
    storage_key = f"org/{organization_id}/seed/gdpr-overview.txt"
    upload_object(storage_key, data, "text/plain")

    file_record = File(
        organization_id=organization_id,
        storage_key=storage_key,
        original_filename="gdpr-overview.txt",
        content_type="text/plain",
        size_bytes=len(data),
        classification="internal",
        uploaded_by=uploaded_by,
    )
    db.add(file_record)
    await db.flush()

    knowledge_base = await get_or_create_default_knowledge_base(db, organization_id)

    document = Document(
        organization_id=organization_id,
        knowledge_base_id=knowledge_base.id,
        file_id=file_record.id,
        title="GDPR Compliance Overview",
        classification="internal",
        created_by=uploaded_by,
    )
    db.add(document)
    await db.flush()

    status = await ingest_document(
        db, document_id=document.id, file_bytes=data, gateway=ModelGateway()
    )
    logger.info("Seeded sample document %s (status=%s)", document.id, status)


if __name__ == "__main__":
    asyncio.run(seed())
