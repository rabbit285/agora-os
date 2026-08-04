"""System role/permission seeding (spec section 54).

Roles are shared across organizations (organization_id is NULL — "system"
roles). Every module grants its own keys in PERMISSIONS and wires them onto
the roles that should hold them; `read_only` is the sole role deliberately
seeded with zero grants (see docs/ACCEPTANCE_TEST_EVIDENCE.md #22).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Permission, Role, RolePermission

# Full default role list from the spec, seeded now so memberships can be
# assigned any of them even before every module grants them permissions.
SYSTEM_ROLE_KEYS: dict[str, str] = {
    "org_admin": "Organization Admin",
    "executive": "Executive",
    "operations_manager": "Operations Manager",
    "compliance_manager": "Compliance Manager",
    "dpo": "DPO",
    "security_manager": "Security Manager",
    "ai_governance_manager": "AI Governance Manager",
    "sales_manager": "Sales Manager",
    "sales_representative": "Sales Representative",
    "support_manager": "Support Manager",
    "support_agent": "Support Agent",
    "automation_manager": "Automation Manager",
    "legal": "Legal",
    "auditor": "Auditor",
    "employee": "Employee",
    "read_only": "Read Only",
}

PERMISSIONS: dict[str, str] = {
    "core.tasks.manage": "Create, assign, and update tasks",
    "core.approvals.decide": "Approve or reject pending approvals",
    "org.settings.manage": "Manage organization profile and settings",
    "org.users.manage": "Invite, suspend, and manage user memberships and roles",
    "org.entities.manage": "Create and archive legal entities and teams",
    "compliance.controls.manage": "Create controls, map requirements, record assessments",
    "compliance.evidence.manage": "Attach and manage evidence",
    "compliance.risks.manage": "Create and update risks",
    "compliance.policies.manage": "Create and publish policies",
    "compliance.ai_systems.manage": "Register AI systems and record AI risk assessments",
    "compliance.privacy.manage": "Manage processing activities, DPIAs, DSARs, and data transfers",
    "compliance.vendors.manage": "Create vendors and record vendor risk assessments",
    "compliance.questionnaires.manage": "Create questionnaires, questions, and answers",
    "compliance.audits.manage": "Create audits and record audit findings",
    "compliance.trust_center.manage": "Manage Trust Center content and evidence requests",
    "compliance.security_reviews.manage": "Start, sync, and clear Enterprise Sales Security Reviews",
    "security.assets.manage": "Create and update the security asset inventory",
    "security.findings.manage": "Create and update security findings",
    "security.alerts.manage": "Triage and update security alerts",
    "security.incidents.manage": "Create and manage security incidents",
    "sales.accounts.manage": "Create and update accounts and contacts",
    "sales.leads.manage": "Create and update leads",
    "sales.opportunities.manage": "Create and update opportunities",
    "sales.outreach.manage": "Draft and send outreach messages",
    "sales.icp.manage": "Configure the Ideal Customer Profile and rescoring",
    "sales.sequences.manage": "Create sequences, campaigns, and enroll contacts",
    "sales.meetings.manage": "Schedule meetings and generate prep notes",
    "support.tickets.manage": "Create and update support tickets and messages",
    "support.knowledge.manage": "Create, edit, and publish knowledge articles",
    "support.ai_agent.manage": "Configure the Support AI Agent's auto-response behavior",
    "support.qa.manage": "Score resolved tickets for quality",
    "automation.workflows.manage": "Create, edit, and publish automation workflows",
    "automation.runs.manage": "Trigger and resume workflow runs",
    "integrations.connections.manage": "Create, edit, and link integration connections",
    "knowledge.documents.manage": "Upload documents and manage knowledge bases",
    "ai.copilot.ask": "Ask the AI Copilot questions grounded in organizational knowledge",
    "reports.generate": "Generate and download reports",
    "business_intelligence.view": "View AI recommendations and the daily business briefing",
    "business_memory.manage": "Create, correct, and delete structured organization memory entries",
    "business_rules.manage": "Configure business rules (condition -> required approval/notification)",
}

COMPLIANCE_PERMISSIONS = [
    "compliance.controls.manage",
    "compliance.evidence.manage",
    "compliance.risks.manage",
    "compliance.policies.manage",
    "compliance.vendors.manage",
    "compliance.questionnaires.manage",
    "compliance.audits.manage",
    "compliance.trust_center.manage",
    "compliance.security_reviews.manage",
]

AI_GOVERNANCE_PERMISSIONS = [
    "compliance.ai_systems.manage",
]

PRIVACY_PERMISSIONS = [
    "compliance.privacy.manage",
]

SECURITY_PERMISSIONS = [
    "security.assets.manage",
    "security.findings.manage",
    "security.alerts.manage",
    "security.incidents.manage",
]

SALES_PERMISSIONS = [
    "sales.accounts.manage",
    "sales.leads.manage",
    "sales.opportunities.manage",
    "sales.outreach.manage",
    "sales.icp.manage",
    "sales.sequences.manage",
    "sales.meetings.manage",
]

SUPPORT_PERMISSIONS = [
    "support.tickets.manage",
    "support.knowledge.manage",
    "support.ai_agent.manage",
    "support.qa.manage",
]

AUTOMATION_PERMISSIONS = [
    "automation.workflows.manage",
    "automation.runs.manage",
]

INTEGRATIONS_PERMISSIONS = [
    "integrations.connections.manage",
]

# Knowledge, the AI Copilot, Reporting, and Business Intelligence
# (Recommendations/Briefing) are cross-cutting capabilities (spec
# §7-11, §55-58, §65, §87-88 — Board/Executive reports and daily
# briefings in particular are meant for leadership across every
# function) used by every specialized role, not owned by one business
# function the way Sales/Security/etc. are — so every role below
# except `read_only` gets all four, in addition to its own module's
# permissions.
KNOWLEDGE_PERMISSIONS = [
    "knowledge.documents.manage",
]
AI_PERMISSIONS = [
    "ai.copilot.ask",
]
REPORTING_PERMISSIONS = [
    "reports.generate",
]
BUSINESS_INTELLIGENCE_PERMISSIONS = [
    "business_intelligence.view",
]
_CROSS_CUTTING_PERMISSIONS = (
    KNOWLEDGE_PERMISSIONS
    + AI_PERMISSIONS
    + REPORTING_PERMISSIONS
    + BUSINESS_INTELLIGENCE_PERMISSIONS
)

# Business AI Memory (spec §89) writes define what the organization
# treats as ground truth — narrower than the cross-cutting set above,
# granted only to governance-adjacent roles rather than every role.
BUSINESS_MEMORY_PERMISSIONS = [
    "business_memory.manage",
]

# Business Rules Engine (spec §90) configuration is likewise narrower
# than the cross-cutting set — a rule can require approval or notify a
# whole role, so only governance/ops-adjacent roles configure them.
BUSINESS_RULES_PERMISSIONS = [
    "business_rules.manage",
]

# Only org_admin gets the full Phase 1 permission set; module-specific
# roles get only their own module's permissions plus the cross-cutting
# Knowledge/Copilot permissions above. `read_only` is deliberately seeded
# with zero permissions (verified RBAC-denial behavior, see
# docs/ACCEPTANCE_TEST_EVIDENCE.md #22) until its owning module defines
# what it should hold.
ROLE_PERMISSION_GRANTS: dict[str, list[str]] = {
    "org_admin": list(PERMISSIONS.keys()),
    "executive": ["core.approvals.decide", *_CROSS_CUTTING_PERMISSIONS],
    "operations_manager": [
        "core.tasks.manage",
        "core.approvals.decide",
        *AUTOMATION_PERMISSIONS,
        *INTEGRATIONS_PERMISSIONS,
        *BUSINESS_RULES_PERMISSIONS,
        *_CROSS_CUTTING_PERMISSIONS,
    ],
    "compliance_manager": (
        COMPLIANCE_PERMISSIONS
        + BUSINESS_MEMORY_PERMISSIONS
        + BUSINESS_RULES_PERMISSIONS
        + _CROSS_CUTTING_PERMISSIONS
    ),
    "dpo": (
        COMPLIANCE_PERMISSIONS
        + AI_GOVERNANCE_PERMISSIONS
        + PRIVACY_PERMISSIONS
        + BUSINESS_MEMORY_PERMISSIONS
        + BUSINESS_RULES_PERMISSIONS
        + _CROSS_CUTTING_PERMISSIONS
    ),
    "security_manager": (
        SECURITY_PERMISSIONS + BUSINESS_RULES_PERMISSIONS + _CROSS_CUTTING_PERMISSIONS
    ),
    "ai_governance_manager": (
        AI_GOVERNANCE_PERMISSIONS
        + BUSINESS_MEMORY_PERMISSIONS
        + BUSINESS_RULES_PERMISSIONS
        + _CROSS_CUTTING_PERMISSIONS
    ),
    "sales_manager": SALES_PERMISSIONS + _CROSS_CUTTING_PERMISSIONS,
    "sales_representative": SALES_PERMISSIONS + _CROSS_CUTTING_PERMISSIONS,
    "support_manager": SUPPORT_PERMISSIONS + _CROSS_CUTTING_PERMISSIONS,
    "support_agent": SUPPORT_PERMISSIONS + _CROSS_CUTTING_PERMISSIONS,
    "automation_manager": (
        AUTOMATION_PERMISSIONS + INTEGRATIONS_PERMISSIONS + _CROSS_CUTTING_PERMISSIONS
    ),
    "legal": PRIVACY_PERMISSIONS + _CROSS_CUTTING_PERMISSIONS,
    "auditor": ["compliance.audits.manage", *_CROSS_CUTTING_PERMISSIONS],
    "employee": ["core.tasks.manage", *_CROSS_CUTTING_PERMISSIONS],
}


async def ensure_system_roles(db: AsyncSession) -> None:
    """Idempotently seed system roles/permissions. Safe to call on every
    startup and from the seed script."""
    permission_rows: dict[str, Permission] = {}
    for key, description in PERMISSIONS.items():
        existing_permission = (
            await db.execute(select(Permission).where(Permission.key == key))
        ).scalar_one_or_none()
        if existing_permission is None:
            existing_permission = Permission(key=key, description=description)
            db.add(existing_permission)
            await db.flush()
        permission_rows[key] = existing_permission

    role_rows: dict[str, Role] = {}
    for key, name in SYSTEM_ROLE_KEYS.items():
        existing_role = (
            await db.execute(select(Role).where(Role.organization_id.is_(None), Role.key == key))
        ).scalar_one_or_none()
        if existing_role is None:
            existing_role = Role(organization_id=None, key=key, name=name, is_system=True)
            db.add(existing_role)
            await db.flush()
        role_rows[key] = existing_role

    for role_key, permission_keys in ROLE_PERMISSION_GRANTS.items():
        role = role_rows[role_key]
        for permission_key in permission_keys:
            permission = permission_rows[permission_key]
            existing_grant = (
                await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == permission.id,
                    )
                )
            ).scalar_one_or_none()
            if existing_grant is None:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))

    await db.commit()


async def get_system_role(db: AsyncSession, key: str) -> Role:
    result = await db.execute(select(Role).where(Role.organization_id.is_(None), Role.key == key))
    role = result.scalar_one_or_none()
    if role is None:
        raise LookupError(f"System role '{key}' has not been seeded — call ensure_system_roles()")
    return role
