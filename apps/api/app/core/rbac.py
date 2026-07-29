"""System role/permission seeding (spec section 54).

Roles are shared across organizations (organization_id is NULL — "system"
roles). Only the permission keys relevant to Phase 1 primitives are granted
today; each later module adds its own keys to PERMISSIONS and wires them
onto the roles that should hold them when that module ships.
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
    "compliance.controls.manage": "Create controls, map requirements, record assessments",
    "compliance.evidence.manage": "Attach and manage evidence",
    "compliance.risks.manage": "Create and update risks",
    "compliance.policies.manage": "Create and publish policies",
}

COMPLIANCE_PERMISSIONS = [
    "compliance.controls.manage",
    "compliance.evidence.manage",
    "compliance.risks.manage",
    "compliance.policies.manage",
]

# Only org_admin gets the full Phase 1 permission set; module-specific
# roles get only their own module's permissions. Every other role is
# seeded with zero permissions until its owning module defines what it
# should hold.
ROLE_PERMISSION_GRANTS: dict[str, list[str]] = {
    "org_admin": list(PERMISSIONS.keys()),
    "compliance_manager": COMPLIANCE_PERMISSIONS,
    "dpo": COMPLIANCE_PERMISSIONS,
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
