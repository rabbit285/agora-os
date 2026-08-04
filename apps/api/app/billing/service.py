"""Real entitlement service (spec §64: "Use entitlement service. Do not
hard-code plan checks across UI."). Every caller — API routers, other
services — resolves what an organization's current plan allows through
`get_entitlements`/`check_boolean_entitlement`/`check_numeric_limit`, never
by reading `Organization.plan_key` directly and branching on it inline.

Plan assignment itself is real (`set_organization_plan`, an org_admin
self-service action) but there is no payment collection behind it — spec
§64's own "Plans architecture" qualifier means this build honestly stops
at "real plans, really enforced," not "real billing transactions." See
docs/KNOWN_LIMITATIONS.md.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.models import Plan
from app.core.models import Membership, Organization

# spec §64's exact "Potential entitlements" list. `int` values are
# monthly/total limits (None means "unlimited" at that tier); `bool`
# values are feature flags.
ENTITLEMENT_KEYS = frozenset(
    {
        "max_users",
        "max_ai_usage_monthly",
        "max_documents",
        "max_storage_gb",
        "max_frameworks",
        "max_ai_systems",
        "max_security_connectors",
        "max_sales_leads",
        "max_outreach_volume_monthly",
        "max_support_conversations_monthly",
        "max_automation_runs_monthly",
        "max_integrations",
        "sso_enabled",
        "scim_enabled",
        "api_enabled",
        "custom_frameworks_enabled",
        "trust_center_enabled",
        "advanced_reporting_enabled",
        "data_residency_enabled",
    }
)

# spec §64's four named plans, seeded once (mirrors
# app.compliance.models.Framework's seeded-catalog pattern). Numeric
# limits step up per tier; boolean features unlock at the tier spec's own
# ordering implies (SSO/API at Growth+, SCIM/advanced reporting/data
# residency at Enterprise only — a defensible, disclosed judgment call
# since spec doesn't spell out the exact per-tier cutoffs).
PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "starter": {
        "name": "Starter",
        "entitlements": {
            "max_users": 5,
            "max_ai_usage_monthly": 100,
            "max_documents": 100,
            "max_storage_gb": 5,
            "max_frameworks": 1,
            "max_ai_systems": 5,
            "max_security_connectors": 1,
            "max_sales_leads": 100,
            "max_outreach_volume_monthly": 200,
            "max_support_conversations_monthly": 100,
            "max_automation_runs_monthly": 100,
            "max_integrations": 2,
            "sso_enabled": False,
            "scim_enabled": False,
            "api_enabled": False,
            "custom_frameworks_enabled": False,
            "trust_center_enabled": False,
            "advanced_reporting_enabled": False,
            "data_residency_enabled": False,
        },
    },
    "growth": {
        "name": "Growth",
        "entitlements": {
            "max_users": 25,
            "max_ai_usage_monthly": 1000,
            "max_documents": 1000,
            "max_storage_gb": 50,
            "max_frameworks": 3,
            "max_ai_systems": 25,
            "max_security_connectors": 3,
            "max_sales_leads": 1000,
            "max_outreach_volume_monthly": 2000,
            "max_support_conversations_monthly": 1000,
            "max_automation_runs_monthly": 1000,
            "max_integrations": 5,
            "sso_enabled": True,
            "scim_enabled": False,
            "api_enabled": True,
            "custom_frameworks_enabled": False,
            "trust_center_enabled": True,
            "advanced_reporting_enabled": False,
            "data_residency_enabled": False,
        },
    },
    "business": {
        "name": "Business",
        "entitlements": {
            "max_users": 100,
            "max_ai_usage_monthly": 10000,
            "max_documents": 10000,
            "max_storage_gb": 500,
            "max_frameworks": 8,
            "max_ai_systems": 100,
            "max_security_connectors": 7,
            "max_sales_leads": 10000,
            "max_outreach_volume_monthly": 20000,
            "max_support_conversations_monthly": 10000,
            "max_automation_runs_monthly": 10000,
            "max_integrations": 7,
            "sso_enabled": True,
            "scim_enabled": True,
            "api_enabled": True,
            "custom_frameworks_enabled": True,
            "trust_center_enabled": True,
            "advanced_reporting_enabled": True,
            "data_residency_enabled": False,
        },
    },
    "enterprise": {
        "name": "Enterprise",
        "entitlements": {
            "max_users": None,
            "max_ai_usage_monthly": None,
            "max_documents": None,
            "max_storage_gb": None,
            "max_frameworks": None,
            "max_ai_systems": None,
            "max_security_connectors": None,
            "max_sales_leads": None,
            "max_outreach_volume_monthly": None,
            "max_support_conversations_monthly": None,
            "max_automation_runs_monthly": None,
            "max_integrations": None,
            "sso_enabled": True,
            "scim_enabled": True,
            "api_enabled": True,
            "custom_frameworks_enabled": True,
            "trust_center_enabled": True,
            "advanced_reporting_enabled": True,
            "data_residency_enabled": True,
        },
    },
}


async def ensure_plan_catalog(db: AsyncSession) -> None:
    """Idempotently seed the 4 plans — safe to call on every startup, the
    same convention `app.core.rbac.ensure_system_roles` established."""
    for key, spec in PLAN_CATALOG.items():
        existing = (await db.execute(select(Plan).where(Plan.key == key))).scalar_one_or_none()
        if existing is None:
            db.add(Plan(key=key, name=spec["name"], entitlements=spec["entitlements"]))
        else:
            # Keep seeded entitlement values in sync with this catalog on
            # every boot — the same "additive/refreshing" idempotency
            # ensure_system_roles uses, so a later change to
            # PLAN_CATALOG reaches already-seeded plans without a
            # migration.
            existing.name = spec["name"]
            existing.entitlements = spec["entitlements"]
    await db.commit()


async def get_plan(db: AsyncSession, plan_key: str) -> Plan:
    plan = (await db.execute(select(Plan).where(Plan.key == plan_key))).scalar_one_or_none()
    if plan is None:
        raise LookupError(f"Plan '{plan_key}' has not been seeded — call ensure_plan_catalog()")
    return plan


async def get_entitlements(db: AsyncSession, *, organization_id: uuid.UUID) -> dict[str, Any]:
    organization = await db.get(Organization, organization_id)
    assert organization is not None
    plan = await get_plan(db, organization.plan_key)
    return dict(plan.entitlements)


async def check_boolean_entitlement(
    db: AsyncSession, *, organization_id: uuid.UUID, key: str
) -> bool:
    entitlements = await get_entitlements(db, organization_id=organization_id)
    return bool(entitlements.get(key, False))


async def require_boolean_entitlement(
    db: AsyncSession, *, organization_id: uuid.UUID, key: str, feature_name: str
) -> None:
    if not await check_boolean_entitlement(db, organization_id=organization_id, key=key):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{feature_name} is not included in this organization's current plan",
        )


async def require_numeric_capacity(
    db: AsyncSession, *, organization_id: uuid.UUID, key: str, current_usage: int, feature_name: str
) -> None:
    """`limit is None` means unlimited at this tier (Enterprise)."""
    entitlements = await get_entitlements(db, organization_id=organization_id)
    limit = entitlements.get(key)
    if limit is not None and current_usage >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"{feature_name} limit reached for this organization's current plan "
            f"({current_usage}/{limit})",
        )


async def count_active_members(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(
            select(Membership.id)
            .where(Membership.organization_id == organization_id, Membership.status == "active")
            .subquery()
        )
    )
    return int(result.scalar_one())


async def set_organization_plan(
    db: AsyncSession, *, organization_id: uuid.UUID, plan_key: str
) -> Organization:
    if plan_key not in PLAN_CATALOG:
        raise ValueError(f"Unknown plan: {plan_key}")
    organization = await db.get(Organization, organization_id)
    assert organization is not None
    organization.plan_key = plan_key
    return organization
