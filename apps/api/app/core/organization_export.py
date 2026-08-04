"""Organization data export (spec §B3/§B5 "Customer Data Control":
export; deletion — see app.core.organization_deletion for the deletion
half). Reuses app.reporting's own `ReportSection`/`ReportContent`
dataclasses and its 4 real renderers outright, rather than a second
export/rendering implementation — the shape (a title plus named
sections of real rows) is exactly what a data-portability bundle needs
too.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import Workflow
from app.compliance.models import DPIA, DSAR, Control, Policy, Risk, Vendor
from app.core.models import LegalEntity, Membership, Team
from app.identity.models import User
from app.knowledge.models import Document
from app.memory.models import MemoryEntry
from app.reporting.content import ReportContent, ReportSection
from app.rules_engine.models import BusinessRule
from app.sales.models import Account, Contact, Opportunity
from app.secops.models import SecurityAsset, SecurityFinding, SecurityIncident
from app.support.models import Customer, Ticket


async def build_organization_export(db: AsyncSession, organization_id: uuid.UUID) -> ReportContent:
    members_result = await db.execute(
        select(User.email, User.full_name, Membership.status)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == organization_id)
    )
    members = [
        {"Email": email, "Name": full_name or "", "Status": status}
        for email, full_name, status in members_result.all()
    ]

    legal_entities = list(
        (
            await db.execute(select(LegalEntity).where(LegalEntity.organization_id == organization_id))
        )
        .scalars()
        .all()
    )
    teams = list(
        (await db.execute(select(Team).where(Team.organization_id == organization_id))).scalars().all()
    )
    controls = list(
        (await db.execute(select(Control).where(Control.organization_id == organization_id)))
        .scalars()
        .all()
    )
    risks = list(
        (await db.execute(select(Risk).where(Risk.organization_id == organization_id))).scalars().all()
    )
    vendors = list(
        (await db.execute(select(Vendor).where(Vendor.organization_id == organization_id)))
        .scalars()
        .all()
    )
    policies = list(
        (await db.execute(select(Policy).where(Policy.organization_id == organization_id)))
        .scalars()
        .all()
    )
    dpias = list(
        (await db.execute(select(DPIA).where(DPIA.organization_id == organization_id))).scalars().all()
    )
    dsars = list(
        (await db.execute(select(DSAR).where(DSAR.organization_id == organization_id))).scalars().all()
    )
    assets = list(
        (
            await db.execute(select(SecurityAsset).where(SecurityAsset.organization_id == organization_id))
        )
        .scalars()
        .all()
    )
    findings = list(
        (
            await db.execute(
                select(SecurityFinding).where(SecurityFinding.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    incidents = list(
        (
            await db.execute(
                select(SecurityIncident).where(SecurityIncident.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    accounts = list(
        (await db.execute(select(Account).where(Account.organization_id == organization_id)))
        .scalars()
        .all()
    )
    contacts = list(
        (await db.execute(select(Contact).where(Contact.organization_id == organization_id)))
        .scalars()
        .all()
    )
    opportunities = list(
        (await db.execute(select(Opportunity).where(Opportunity.organization_id == organization_id)))
        .scalars()
        .all()
    )
    customers = list(
        (await db.execute(select(Customer).where(Customer.organization_id == organization_id)))
        .scalars()
        .all()
    )
    tickets = list(
        (await db.execute(select(Ticket).where(Ticket.organization_id == organization_id)))
        .scalars()
        .all()
    )
    documents = list(
        (await db.execute(select(Document).where(Document.organization_id == organization_id)))
        .scalars()
        .all()
    )
    workflows = list(
        (await db.execute(select(Workflow).where(Workflow.organization_id == organization_id)))
        .scalars()
        .all()
    )
    memory_entries = list(
        (
            await db.execute(
                select(MemoryEntry).where(
                    MemoryEntry.organization_id == organization_id, MemoryEntry.status == "active"
                )
            )
        )
        .scalars()
        .all()
    )
    business_rules = list(
        (await db.execute(select(BusinessRule).where(BusinessRule.organization_id == organization_id)))
        .scalars()
        .all()
    )

    return ReportContent(
        title="Organization Data Export",
        generated_at=datetime.now(UTC),
        sections=[
            ReportSection("Members", members),
            ReportSection(
                "Legal Entities", [{"Name": e.name, "Country": e.country or ""} for e in legal_entities]
            ),
            ReportSection("Teams", [{"Name": t.name} for t in teams]),
            ReportSection(
                "Compliance Controls",
                [{"Title": c.title, "Status": c.status} for c in controls],
            ),
            ReportSection(
                "Risks",
                [{"Title": r.title, "Likelihood": r.likelihood, "Impact": r.impact, "Status": r.status} for r in risks],
            ),
            ReportSection(
                "Vendors", [{"Name": v.name, "Risk Tier": v.risk_tier, "Status": v.status} for v in vendors]
            ),
            ReportSection("Policies", [{"Title": p.title, "Status": p.status} for p in policies]),
            ReportSection(
                "DPIAs", [{"Title": d.title, "Risk Level": d.risk_level, "Status": d.status} for d in dpias]
            ),
            ReportSection(
                "DSARs",
                [
                    {"Requester": d.requester_name, "Type": d.request_type, "Status": d.status}
                    for d in dsars
                ],
            ),
            ReportSection(
                "Security Assets", [{"Name": a.name, "Type": a.asset_type} for a in assets]
            ),
            ReportSection(
                "Security Findings",
                [{"Title": f.title, "Severity": f.severity, "Status": f.status} for f in findings],
            ),
            ReportSection(
                "Security Incidents",
                [{"Title": i.title, "Status": i.status} for i in incidents],
            ),
            ReportSection(
                "Sales Accounts", [{"Name": a.name, "Status": a.status} for a in accounts]
            ),
            ReportSection(
                "Sales Contacts", [{"Name": c.full_name, "Email": c.email} for c in contacts]
            ),
            ReportSection(
                "Sales Opportunities",
                [{"Title": o.title, "Stage": o.stage, "Value": float(o.value) if o.value else None} for o in opportunities],
            ),
            ReportSection(
                "Support Customers", [{"Name": c.name} for c in customers]
            ),
            ReportSection(
                "Support Tickets",
                [{"Subject": t.subject, "Status": t.status, "Priority": t.priority} for t in tickets],
            ),
            ReportSection(
                "Knowledge Documents", [{"Title": d.title, "Status": d.status} for d in documents]
            ),
            ReportSection(
                "Automation Workflows",
                [{"Name": w.name, "Trigger Type": w.trigger_type, "Status": w.status} for w in workflows],
            ),
            ReportSection(
                "Business Memory",
                [{"Type": m.entry_type, "Content": m.content} for m in memory_entries],
            ),
            ReportSection(
                "Business Rules",
                [{"Name": r.name, "Trigger": r.trigger_type, "Action": r.action_type} for r in business_rules],
            ),
        ],
    )
