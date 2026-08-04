"""Organization-level data export/deletion execution (spec §B3/§B5:
"support export and deletion" as a real Customer Data Control, not just
DSAR status tracking — see docs/DECISIONS.md for the reasoning).

Deletion is a real, two-step, irreversible action:
1. `request_organization_deletion` — a visible, cancellable, audited
   precursor state (`Organization.deletion_requested_at`).
2. `execute_organization_deletion` — the actual purge. Requires a
   request to already be pending. Every table this org's data lives in
   is deleted in one transaction, using `session_replication_role =
   replica` to disable FK/trigger checks for the duration (a standard,
   safe Postgres technique for exactly this kind of full cascade
   delete) rather than hand-ordering 70+ tables by dependency — this
   also correctly bypasses `audit_events`' own append-only trigger
   (ADR-0042), which is the right behavior here: a genuine
   right-to-erasure deletion must erase that org's audit trail too, not
   leave it permanently un-deletable.

`User` rows are deliberately never deleted here — a login identity is a
separate concept from organization membership throughout this
codebase (Membership is the tenant boundary, not User); a user who was
only ever a member of the deleted organization simply ends up with zero
memberships, which is the correct, honest end state, not a account
deletion this endpoint doesn't claim to perform.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Organization

logger = logging.getLogger("agora.organization_deletion")

# Every table with a direct `organization_id` column, as of this build
# (verified against information_schema — see _verify_table_coverage,
# which fails loudly rather than silently under-deleting if a future
# migration adds a new org-scoped table without updating this list).
_DIRECT_ORG_SCOPED_TABLES: tuple[str, ...] = (
    "ai_assessments",
    "ai_incidents",
    "ai_runs",
    "ai_systems",
    "approvals",
    "audit_events",
    "audit_findings",
    "audits",
    "automation_workflow_runs",
    "automation_workflow_step_runs",
    "automation_workflow_versions",
    "automation_workflows",
    "briefings",
    "business_rules",
    "control_assessments",
    "controls",
    "data_transfers",
    "document_chunks",
    "documents",
    "dpias",
    "dsars",
    "evidence",
    "files",
    "integration_connections",
    "integration_sync_runs",
    "integration_webhook_events",
    "invitations",
    "knowledge_bases",
    "legal_entities",
    "memberships",
    "memory_entries",
    "notification_preferences",
    "notifications",
    "onboarding_profiles",
    "policies",
    "processing_activities",
    "questionnaire_answers",
    "questionnaire_questions",
    "questionnaires",
    "recommendations",
    "reports",
    "risks",
    "roles",
    "sales_accounts",
    "sales_campaigns",
    "sales_contacts",
    "sales_icp_profiles",
    "sales_leads",
    "sales_meetings",
    "sales_opportunities",
    "sales_outreach_messages",
    "sales_sequence_enrollments",
    "sales_sequence_steps",
    "sales_sequences",
    "security_alerts",
    "security_assets",
    "security_findings",
    "security_incident_timeline_entries",
    "security_incidents",
    "security_reviews",
    "sessions",
    "support_ai_agent_configs",
    "support_csat_responses",
    "support_customers",
    "support_knowledge_articles",
    "support_ticket_messages",
    "support_ticket_qa_scores",
    "support_tickets",
    "tasks",
    "teams",
    "trust_center_evidence_requests",
    "trust_center_items",
    "vendor_assessments",
    "vendors",
)

# Tables with no organization_id of their own — scoped via a parent
# table that does. Deleted by subquery, not by dependency order (FK
# checks are disabled for the whole operation).
_CHILD_TABLE_DELETES: tuple[tuple[str, str, str], ...] = (
    ("control_mappings", "control_id", "controls"),
    ("membership_roles", "membership_id", "memberships"),
    ("role_permissions", "role_id", "roles"),
    ("security_incident_assets", "incident_id", "security_incidents"),
)

# `roles`/`role_permissions` deliberately include only organization-
# specific rows (organization_id IS NULL for shared system roles, so
# `WHERE organization_id = :org_id` / the role_id subquery above never
# matches a system role) — this build has no custom per-org roles yet,
# but the column exists for when it does.


async def _verify_table_coverage(db: AsyncSession) -> None:
    """PostgreSQL only — `information_schema` isn't available the same
    way on the test suite's SQLite database, and this is a schema-drift
    safety net (catching a future migration that adds a new org-scoped
    table without updating `_DIRECT_ORG_SCOPED_TABLES`), not core
    deletion logic, so it's skipped rather than faked on SQLite."""
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    result = await db.execute(
        text(
            "SELECT table_name FROM information_schema.columns "
            "WHERE column_name = 'organization_id' AND table_schema = 'public'"
        )
    )
    actual = {row[0] for row in result.all()} - {"organizations"}
    handled = set(_DIRECT_ORG_SCOPED_TABLES)
    missing = actual - handled
    if missing:
        raise RuntimeError(
            "Organization deletion does not yet handle table(s): "
            f"{sorted(missing)}. Add them to _DIRECT_ORG_SCOPED_TABLES in "
            "app.core.organization_deletion before deletion can proceed safely."
        )


async def request_organization_deletion(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> Organization:
    organization = await db.get(Organization, organization_id)
    assert organization is not None
    organization.deletion_requested_at = datetime.now(UTC)
    await db.flush()
    return organization


async def cancel_organization_deletion(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> Organization:
    organization = await db.get(Organization, organization_id)
    assert organization is not None
    organization.deletion_requested_at = None
    await db.flush()
    return organization


async def execute_organization_deletion(
    db: AsyncSession, *, organization_id: uuid.UUID, executed_by: uuid.UUID
) -> None:
    """The actual, irreversible purge. Caller must have already verified
    `Organization.deletion_requested_at is not None` (the two-step
    confirmation gate lives in the router, not here, so this function
    stays a pure "do the deletion" primitive)."""
    await _verify_table_coverage(db)

    organization = await db.get(Organization, organization_id)
    assert organization is not None
    organization_name = organization.name

    # PostgreSQL only: disables FK/trigger checks for this transaction so
    # 70+ tables can be deleted without hand-ordering them by dependency
    # (and correctly bypasses audit_events' own append-only trigger, see
    # this module's docstring). The test suite's SQLite database has no
    # FK enforcement enabled at all (no PRAGMA foreign_keys=ON anywhere
    # in this codebase), so the equivalent statement is both invalid
    # SQLite syntax and unnecessary there.
    is_postgres = db.bind is not None and db.bind.dialect.name == "postgresql"
    # SQLAlchemy's Uuid type stores rows as 32-char hex with no dashes on
    # a non-native backend (SQLite) — a raw text() query must match that
    # exact stored form, not str(uuid) (which has dashes) and not the raw
    # UUID object (SQLite's driver can't bind it at all). Postgres's
    # native uuid column accepts either hex form through asyncpg, so
    # .hex works for both dialects.
    org_id_param = organization_id.hex
    if is_postgres:
        await db.execute(text("SET session_replication_role = replica"))
    try:
        for table, fk_column, parent_table in _CHILD_TABLE_DELETES:
            await db.execute(
                text(
                    f"DELETE FROM {table} WHERE {fk_column} IN "  # noqa: S608 - table/column names are a hardcoded constant list, never request input
                    f"(SELECT id FROM {parent_table} WHERE organization_id = :org_id)"
                ),
                {"org_id": org_id_param},
            )
        for table in _DIRECT_ORG_SCOPED_TABLES:
            await db.execute(
                text(f"DELETE FROM {table} WHERE organization_id = :org_id"),  # noqa: S608
                {"org_id": org_id_param},
            )
        await db.execute(
            text("DELETE FROM organizations WHERE id = :org_id"), {"org_id": org_id_param}
        )
    finally:
        if is_postgres:
            await db.execute(text("SET session_replication_role = DEFAULT"))
    await db.commit()
    # Raw text() DELETEs don't touch the ORM identity map the way
    # session.delete(obj) would, and this session factory disables
    # expire_on_commit (AsyncSessionLocal in app.db.session) — without
    # this, a later db.get(Organization, organization_id) in the same
    # session could still return the pre-deletion cached instance
    # instead of None.
    db.expire_all()

    # The organization's own audit_events row are deleted along with
    # everything else above — a genuine erasure needs no tenant-visible
    # trail — so this one system-level, non-tenant-scoped log line is
    # the only durable record the deletion happened at all.
    logger.info(
        "Organization deleted: id=%s name=%r executed_by=%s",
        organization_id,
        organization_name,
        executed_by,
    )
