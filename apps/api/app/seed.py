"""Seed script: demo organization "Acme AI Technologies" (spec section 84).

Run with: docker compose exec api python -m app.seed
Idempotent — safe to run multiple times against the same database.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.models import LegalEntity, Membership, MembershipRole, Organization, Task
from app.core.rbac import ensure_system_roles, get_system_role
from app.db.session import AsyncSessionLocal
from app.identity.models import User
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
        logger.info(
            "Seed complete. Log in as %s / %s (org: %s)",
            DEMO_ADMIN_EMAIL,
            DEMO_ADMIN_PASSWORD,
            organization.slug,
        )


if __name__ == "__main__":
    asyncio.run(seed())
