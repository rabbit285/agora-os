"""Global Search (spec §47 Unified Search): a real, tenant-scoped
case-insensitive substring search across every module's named records.

Deliberately a simple `ILIKE` scan per entity type, not a separate search
index (Elasticsearch/OpenSearch) — real and correct at the record volumes
a single organization reaches, the same trade-off already made and
disclosed for Knowledge retrieval's cosine-similarity scan (see
docs/DECISIONS.md ADR-0012). "All retrieval must respect permissions"
(spec §11): every query below is scoped to `organization_id` exactly like
every other query in the app, so cross-tenant leakage is structurally
impossible; there is currently no per-module *read* permission distinct
from tenant membership anywhere else in the app (only writes are
permission-gated — see app.core.rbac), so global search doesn't invent one
either — it is exactly as permission-scoped as clicking into each module
individually already is.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import Workflow
from app.compliance.models import DPIA, AIIncident, AISystem, Audit, Control, Questionnaire, Vendor
from app.knowledge.models import Document
from app.sales.models import Account, Contact, Lead, Opportunity
from app.secops.models import SecurityIncident
from app.support.models import Customer, Ticket

DEFAULT_LIMIT_PER_TYPE = 5


@dataclass
class SearchResult:
    entity_type: str
    id: str
    label: str
    module: str


# (entity_type, model, [text columns to match], label column, module label)
_SEARCH_TARGETS: list[tuple[str, type[Any], list[str], str, str]] = [
    ("sales_account", Account, ["name", "industry"], "name", "Sales"),
    ("sales_contact", Contact, ["full_name", "email"], "full_name", "Sales"),
    ("sales_lead", Lead, ["source"], "source", "Sales"),
    ("sales_opportunity", Opportunity, ["title"], "title", "Sales"),
    ("support_customer", Customer, ["name", "email"], "name", "Support"),
    ("support_ticket", Ticket, ["subject", "description"], "subject", "Support"),
    ("vendor", Vendor, ["name", "description"], "name", "Compliance"),
    ("control", Control, ["title", "description"], "title", "Compliance"),
    ("audit", Audit, ["title"], "title", "Compliance"),
    ("ai_system", AISystem, ["name", "purpose"], "name", "Compliance"),
    ("dpia", DPIA, ["title"], "title", "Compliance"),
    ("ai_incident", AIIncident, ["title", "description"], "title", "Compliance"),
    ("questionnaire", Questionnaire, ["title"], "title", "Compliance"),
    ("security_incident", SecurityIncident, ["title", "description"], "title", "Security"),
    ("automation_workflow", Workflow, ["name", "description"], "name", "Automation"),
    ("knowledge_document", Document, ["title"], "title", "Knowledge"),
]


async def global_search(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    query: str,
    limit_per_type: int = DEFAULT_LIMIT_PER_TYPE,
) -> list[SearchResult]:
    normalized = query.strip()
    if not normalized:
        return []
    pattern = f"%{normalized}%"

    results: list[SearchResult] = []
    for entity_type, model, columns, label_column, module in _SEARCH_TARGETS:
        conditions = [cast(getattr(model, col), String).ilike(pattern) for col in columns]
        stmt = (
            select(model)
            .where(getattr(model, "organization_id") == organization_id, or_(*conditions))  # noqa: B009
            .order_by(getattr(model, "created_at").desc())  # noqa: B009
            .limit(limit_per_type)
        )
        rows = (await db.execute(stmt)).scalars().all()
        for row in rows:
            label = getattr(row, label_column, None) or str(row.id)
            results.append(
                SearchResult(
                    entity_type=entity_type, id=str(row.id), label=str(label), module=module
                )
            )
    return results
