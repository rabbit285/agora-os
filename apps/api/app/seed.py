"""Seed script: demo organization "Acme AI Technologies" (spec section 84).

Run with: docker compose exec api python -m app.seed
Idempotent — safe to run multiple times against the same database.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import ModelGateway
from app.compliance.models import Control, ControlMapping, Evidence, Framework, Requirement, Risk
from app.compliance.service import record_assessment
from app.core.models import File, LegalEntity, Membership, MembershipRole, Organization, Task
from app.core.rbac import ensure_system_roles, get_system_role
from app.core.storage import ensure_bucket, upload_object
from app.db.session import AsyncSessionLocal
from app.identity.models import User
from app.knowledge.models import Document
from app.knowledge.service import get_or_create_default_knowledge_base, ingest_document
from app.sales.models import Account, Contact, Opportunity, OutreachMessage
from app.sales.service import send_outreach_message
from app.secops.models import SecurityAlert, SecurityAsset, SecurityFinding
from app.secops.service import create_incident
from app.security import hash_password
from app.support.models import CSATResponse, Customer, KnowledgeArticle, TicketMessage
from app.support.service import create_ticket

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
        evidence_file_id = None
        if not existing_documents:
            evidence_file_id = await _seed_sample_document(
                db, organization_id=organization.id, uploaded_by=admin.id
            )

        gdpr_requirements = await _ensure_compliance_catalog(db)

        existing_controls = (
            (await db.execute(select(Control).where(Control.organization_id == organization.id)))
            .scalars()
            .all()
        )
        if not existing_controls:
            await _seed_demo_compliance_data(
                db,
                organization_id=organization.id,
                admin_id=admin.id,
                gdpr_requirements=gdpr_requirements,
                evidence_file_id=evidence_file_id,
            )

        existing_assets = (
            (
                await db.execute(
                    select(SecurityAsset).where(SecurityAsset.organization_id == organization.id)
                )
            )
            .scalars()
            .all()
        )
        if not existing_assets:
            await _seed_demo_security_data(db, organization_id=organization.id, admin_id=admin.id)

        existing_accounts = (
            (await db.execute(select(Account).where(Account.organization_id == organization.id)))
            .scalars()
            .all()
        )
        if not existing_accounts:
            await _seed_demo_sales_data(db, organization_id=organization.id, admin_id=admin.id)

        nordwind_account = (
            await db.execute(
                select(Account).where(
                    Account.organization_id == organization.id,
                    Account.name == "Nordwind Robotics GmbH",
                )
            )
        ).scalar_one_or_none()

        existing_customers = (
            (await db.execute(select(Customer).where(Customer.organization_id == organization.id)))
            .scalars()
            .all()
        )
        if not existing_customers:
            await _seed_demo_support_data(
                db,
                organization_id=organization.id,
                admin_id=admin.id,
                sales_account_id=nordwind_account.id if nordwind_account else None,
            )

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
) -> uuid.UUID:
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
    return file_record.id


CATALOG_FRAMEWORKS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "gdpr": (
        "GDPR",
        [
            ("Art. 5", "Principles relating to processing of personal data"),
            ("Art. 30", "Records of processing activities"),
            ("Art. 33", "Notification of a personal data breach"),
            ("Art. 35", "Data protection impact assessment"),
        ],
    ),
    "eu_ai_act": (
        "EU AI Act",
        [
            ("Art. 9", "Risk management system"),
            ("Art. 13", "Transparency and provision of information to users"),
        ],
    ),
    "iso27001": (
        "ISO 27001",
        [
            ("A.5.1", "Policies for information security"),
            ("A.8.1", "Inventory of information and other associated assets"),
        ],
    ),
}


async def _ensure_compliance_catalog(db: AsyncSession) -> dict[str, Requirement]:
    """Idempotently seeds the global framework/requirement catalog (spec
    section 12). Returns the GDPR requirements by reference code, which
    the demo org's controls map to."""
    gdpr_requirements: dict[str, Requirement] = {}

    for key, (name, requirements) in CATALOG_FRAMEWORKS.items():
        framework = (
            await db.execute(select(Framework).where(Framework.key == key))
        ).scalar_one_or_none()
        if framework is None:
            framework = Framework(key=key, name=name)
            db.add(framework)
            await db.flush()

        for reference_code, title in requirements:
            requirement = (
                await db.execute(
                    select(Requirement).where(
                        Requirement.framework_id == framework.id,
                        Requirement.reference_code == reference_code,
                    )
                )
            ).scalar_one_or_none()
            if requirement is None:
                requirement = Requirement(
                    framework_id=framework.id, reference_code=reference_code, title=title
                )
                db.add(requirement)
                await db.flush()
            if key == "gdpr":
                gdpr_requirements[reference_code] = requirement

    await db.commit()
    return gdpr_requirements


async def _seed_demo_compliance_data(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    admin_id: uuid.UUID,
    gdpr_requirements: dict[str, Requirement],
    evidence_file_id: uuid.UUID | None,
) -> None:
    """Seeds a few controls (one mapped to GDPR Art. 30, one to Art. 33),
    an assessment for each — one pass, one fail so the cross-module
    Task-creation hook (app.compliance.service.record_assessment) has
    something real to demonstrate — plus one risk and, if the sample
    document was seeded, an evidence link to it."""
    ropa_control = Control(
        organization_id=organization_id,
        title="Maintain Records of Processing Activities",
        description="Keep an up-to-date RoPA covering all processing activities.",
        owner_id=admin_id,
        status="implemented",
    )
    breach_control = Control(
        organization_id=organization_id,
        title="Breach Notification Runbook",
        description="Documented process to notify the supervisory authority within 72 hours.",
        owner_id=admin_id,
    )
    db.add_all([ropa_control, breach_control])
    await db.flush()

    if "Art. 30" in gdpr_requirements:
        db.add(
            ControlMapping(
                control_id=ropa_control.id, requirement_id=gdpr_requirements["Art. 30"].id
            )
        )
    if "Art. 33" in gdpr_requirements:
        db.add(
            ControlMapping(
                control_id=breach_control.id, requirement_id=gdpr_requirements["Art. 33"].id
            )
        )
    await db.flush()

    await record_assessment(
        db,
        organization_id=organization_id,
        control=ropa_control,
        status="pass",
        notes="RoPA reviewed and current as of this quarter.",
        assessed_by=admin_id,
    )
    await record_assessment(
        db,
        organization_id=organization_id,
        control=breach_control,
        status="fail",
        notes="Runbook exists but has not been tested with a tabletop exercise.",
        assessed_by=admin_id,
    )

    if evidence_file_id is not None:
        db.add(
            Evidence(
                organization_id=organization_id,
                control_id=ropa_control.id,
                file_id=evidence_file_id,
                title="GDPR Compliance Overview",
                created_by=admin_id,
            )
        )

    db.add(
        Risk(
            organization_id=organization_id,
            title="Vendor sub-processor list not reviewed in 12 months",
            description="Annual sub-processor risk review is overdue.",
            category="privacy",
            likelihood="medium",
            impact="medium",
            control_id=ropa_control.id,
            owner_id=admin_id,
        )
    )

    await db.commit()
    logger.info("Seeded demo compliance data (2 controls, 2 assessments, 1 risk)")


async def _seed_demo_security_data(
    db: AsyncSession, *, organization_id: uuid.UUID, admin_id: uuid.UUID
) -> None:
    """Seeds a couple of assets, one resolved and one open finding, one
    alert, and one critical incident — the critical incident exercises
    the cross-module hook that links it to a Compliance Risk (spec
    section 19)."""
    prod_cluster = SecurityAsset(
        organization_id=organization_id,
        name="prod-api-cluster",
        asset_type="cloud_account",
        provider="aws",
        criticality="critical",
        internet_exposed=True,
        owner_id=admin_id,
    )
    laptop_fleet = SecurityAsset(
        organization_id=organization_id,
        name="Employee laptop fleet",
        asset_type="endpoint",
        provider="google_workspace",
        criticality="medium",
        owner_id=admin_id,
    )
    db.add_all([prod_cluster, laptop_fleet])
    await db.flush()

    db.add(
        SecurityFinding(
            organization_id=organization_id,
            asset_id=prod_cluster.id,
            category="cloud_misconfiguration",
            title="S3 bucket allows public read access",
            description="customer-exports bucket has public-read ACL enabled.",
            severity="critical",
            status="open",
            owner_id=admin_id,
        )
    )
    db.add(
        SecurityFinding(
            organization_id=organization_id,
            asset_id=laptop_fleet.id,
            category="identity",
            title="2 administrators without MFA",
            severity="high",
            status="resolved",
            owner_id=admin_id,
        )
    )
    db.add(
        SecurityAlert(
            organization_id=organization_id,
            title="Unusual login location for admin@acme-ai.example",
            severity="medium",
            status="investigating",
        )
    )
    await db.flush()

    await create_incident(
        db,
        organization_id=organization_id,
        title="Public S3 bucket exposed customer export data",
        description="Discovered via routine cloud configuration scan; bucket made private immediately.",
        severity="critical",
        owner_id=admin_id,
        actor_user_id=admin_id,
    )

    await db.commit()
    logger.info("Seeded demo security data (2 assets, 2 findings, 1 alert, 1 critical incident)")


async def _seed_demo_sales_data(
    db: AsyncSession, *, organization_id: uuid.UUID, admin_id: uuid.UUID
) -> None:
    """Seeds one account with two contacts (one reachable, one suppressed),
    an opportunity, and two outreach messages — one to each contact — so
    the suppression cross-module hook (spec section 91) has a real,
    non-trivial demonstration: one message sends, one is blocked."""
    account = Account(
        organization_id=organization_id,
        name="Nordwind Robotics GmbH",
        industry="Industrial Automation",
        website="https://nordwind-robotics.example",
        employee_count=180,
        icp_score=87.5,
        status="prospect",
        owner_id=admin_id,
    )
    db.add(account)
    await db.flush()

    reachable_contact = Contact(
        organization_id=organization_id,
        account_id=account.id,
        full_name="Lena Voigt",
        email="l.voigt@nordwind-robotics.example",
        job_title="VP Engineering",
        do_not_contact=False,
    )
    suppressed_contact = Contact(
        organization_id=organization_id,
        account_id=account.id,
        full_name="Jonas Weber",
        email="j.weber@nordwind-robotics.example",
        job_title="Procurement Lead",
        do_not_contact=True,
    )
    db.add_all([reachable_contact, suppressed_contact])
    await db.flush()

    db.add(
        Opportunity(
            organization_id=organization_id,
            account_id=account.id,
            title="Nordwind Robotics — Platform expansion",
            stage="qualification",
            value=42000,
            probability=40,
            owner_id=admin_id,
        )
    )

    for contact in (reachable_contact, suppressed_contact):
        message = OutreachMessage(
            organization_id=organization_id,
            contact_id=contact.id,
            channel="email",
            subject="Following up on your compliance automation needs",
            body=(
                f"Hi {contact.full_name.split()[0]}, following up on our conversation about "
                "automating your GDPR compliance workflows. Would you be open to a quick call?"
            ),
            created_by=admin_id,
        )
        db.add(message)
        await db.flush()
        await send_outreach_message(
            db,
            organization_id=organization_id,
            message=message,
            contact=contact,
            actor_user_id=admin_id,
        )

    await db.commit()
    logger.info(
        "Seeded demo sales data (1 account, 2 contacts, 1 opportunity, "
        "2 outreach attempts: 1 sent, 1 blocked by suppression)"
    )


async def _seed_demo_support_data(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    admin_id: uuid.UUID,
    sales_account_id: uuid.UUID | None,
) -> None:
    """Seeds one customer (linked to the Nordwind Robotics sales account —
    spec section 69 "New Customer"), a resolved billing ticket with a CSAT
    response, and a ticket categorized "security" so the Support -> Security
    cross-module hook (spec section 35) has a real demonstration: creating
    it auto-creates a linked SecurityAlert. Also seeds one published
    knowledge article."""
    customer = Customer(
        organization_id=organization_id,
        sales_account_id=sales_account_id,
        name="Nordwind Robotics GmbH",
        email="support@nordwind-robotics.example",
        plan="Growth",
        status="active",
    )
    db.add(customer)
    await db.flush()

    billing_ticket = await create_ticket(
        db,
        organization_id=organization_id,
        customer_id=customer.id,
        subject="Question about our latest invoice",
        description="We were charged twice for the March subscription period.",
        channel="email",
        category="billing",
        priority="medium",
        actor_user_id=admin_id,
    )
    db.add(
        TicketMessage(
            organization_id=organization_id,
            ticket_id=billing_ticket.id,
            sender_type="customer",
            body="We were charged twice for the March subscription period.",
        )
    )
    db.add(
        TicketMessage(
            organization_id=organization_id,
            ticket_id=billing_ticket.id,
            sender_type="agent",
            author_id=admin_id,
            body=(
                "Thanks for flagging this - I can see the duplicate charge and have "
                "issued a refund for the extra charge."
            ),
        )
    )
    billing_ticket.status = "resolved"
    billing_ticket.resolved_at = datetime.now(UTC)
    db.add(
        CSATResponse(
            organization_id=organization_id,
            ticket_id=billing_ticket.id,
            score=5,
            comment="Fast and clear resolution, thank you.",
        )
    )

    security_ticket = await create_ticket(
        db,
        organization_id=organization_id,
        customer_id=customer.id,
        subject="Possible unauthorized access to our account",
        description="One of our engineers noticed a login from an unrecognized location.",
        channel="email",
        category="security",
        priority="high",
        actor_user_id=admin_id,
    )
    db.add(
        TicketMessage(
            organization_id=organization_id,
            ticket_id=security_ticket.id,
            sender_type="customer",
            body="One of our engineers noticed a login from an unrecognized location this morning.",
        )
    )

    db.add(
        KnowledgeArticle(
            organization_id=organization_id,
            title="How to reset your password",
            body="Go to Settings, then Security, then Reset Password and follow the emailed link.",
            category="account",
            published=True,
        )
    )

    await db.commit()
    logger.info(
        "Seeded demo support data (1 customer, 2 tickets - 1 resolved with CSAT, "
        "1 security-flagged ticket that auto-created a SecurityAlert, 1 knowledge article)"
    )


if __name__ == "__main__":
    asyncio.run(seed())
