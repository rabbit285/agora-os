"""Global compliance search.

Searches the things a compliance team actually looks for by name, and
returns each hit with the route that opens it. The href is computed here
rather than in the browser deliberately: a client-side lookup table
drifts the moment a route changes, and the failure mode is a result that
looks real and lands on a 404 — which is worse than not finding it.

Nothing outside compliance is searchable. Sales, support, automation and
knowledge records still exist in the database (DSAR discovery reads the
first two on purpose), but those modules were withdrawn from the product
and a result linking into one advertises a screen the customer was told
they do not have.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    DPIA,
    AIIncident,
    AISystem,
    Audit,
    ComplianceGap,
    Control,
    Evidence,
    Framework,
    FrameworkActivation,
    Policy,
    Questionnaire,
    Requirement,
    Risk,
    Vendor,
)
from app.core.models import File
from app.knowledge.documents import hrefs_for_files
from app.search.schemas import SearchResult

DEFAULT_LIMIT_PER_TYPE = 5


@dataclass(frozen=True)
class _Target:
    entity_type: str
    model: type[Any]
    columns: list[str]
    label_column: str
    module: str
    # How to open it. `None` means the entity has no detail page of its
    # own and the hit routes to the screen that lists it.
    href: str


# (entity_type, model, searched columns, label column, module, href
# template). Every href here resolves to a page that exists — checked by
# `test_search_results_all_route_somewhere_real`.
_TARGETS: tuple[_Target, ...] = (
    _Target("control", Control, ["title", "description"], "title", "Controls", "/compliance/controls/{id}"),
    _Target("evidence", Evidence, ["title"], "title", "Evidence", "/documents"),
    _Target("document", File, ["original_filename"], "original_filename", "Documents", "/documents"),
    _Target("ai_system", AISystem, ["name", "purpose"], "name", "AI Systems", "/compliance/ai-systems/{id}"),
    _Target("risk", Risk, ["title", "description"], "title", "Risk", "/compliance#controls"),
    _Target("gap", ComplianceGap, ["summary", "recommendation"], "summary", "Gaps", "/compliance"),
    _Target("policy", Policy, ["title"], "title", "Policies", "/compliance#controls"),
    _Target("vendor", Vendor, ["name", "description"], "name", "Vendors", "/compliance/vendors/{id}"),
    _Target("dpia", DPIA, ["title"], "title", "Privacy", "/compliance/dpias/{id}"),
    _Target("audit", Audit, ["title"], "title", "Assessments", "/compliance/audits/{id}"),
    _Target("questionnaire", Questionnaire, ["title"], "title", "Assessments", "/compliance/questionnaires/{id}"),
    _Target("ai_incident", AIIncident, ["title", "description"], "title", "AI Systems", "/compliance/ai-incidents/{id}"),
)


async def _search_frameworks(
    db: AsyncSession, *, organization_id: uuid.UUID, pattern: str, limit: int
) -> list[SearchResult]:
    """Frameworks are catalog data, so they are not organization-scoped
    the way everything else is: the global rows are visible to everyone,
    plus any custom framework this organization defined."""
    rows = list(
        (
            await db.execute(
                select(Framework)
                .where(
                    or_(
                        Framework.organization_id.is_(None),
                        Framework.organization_id == organization_id,
                    ),
                    or_(
                        cast(Framework.name, String).ilike(pattern),
                        cast(Framework.key, String).ilike(pattern),
                    ),
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        SearchResult(
            entity_type="framework",
            id=str(row.id),
            label=row.name,
            module="Frameworks",
            href=f"/compliance/frameworks/{row.id}",
        )
        for row in rows
    ]


async def _search_requirements(
    db: AsyncSession, *, organization_id: uuid.UUID, pattern: str, limit: int
) -> list[SearchResult]:
    """Requirements are global too, but scoped here to the frameworks this
    organization has actually adopted.

    Searching "human oversight" should not surface DORA articles at a
    company that never adopted DORA — the hit would be real and useless,
    and it pushes the results that matter off the list.
    """
    rows = list(
        (
            await db.execute(
                select(Requirement, Framework)
                .join(Framework, Framework.id == Requirement.framework_id)
                .join(FrameworkActivation, FrameworkActivation.framework_id == Framework.id)
                .where(
                    FrameworkActivation.organization_id == organization_id,
                    FrameworkActivation.status == "active",
                    or_(
                        cast(Requirement.title, String).ilike(pattern),
                        cast(Requirement.reference_code, String).ilike(pattern),
                        cast(Requirement.description, String).ilike(pattern),
                    ),
                )
                .limit(limit)
            )
        ).all()
    )
    return [
        SearchResult(
            entity_type="requirement",
            id=str(requirement.id),
            # The framework is part of the identity: "Article 26" alone
            # does not tell the reader which regulation they are looking at.
            label=f"{framework.name} · {requirement.reference_code} {requirement.title}",
            module="Requirements",
            href=f"/compliance/frameworks/{framework.id}",
        )
        for requirement, framework in rows
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

    for target in _TARGETS:
        conditions = [
            cast(getattr(target.model, column), String).ilike(pattern)
            for column in target.columns
        ]
        rows = (
            (
                await db.execute(
                    select(target.model)
                    .where(
                        target.model.organization_id == organization_id,
                        or_(*conditions),
                    )
                    .order_by(target.model.created_at.desc())
                    .limit(limit_per_type)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            label = getattr(row, target.label_column, None) or str(row.id)
            results.append(
                SearchResult(
                    entity_type=target.entity_type,
                    id=str(row.id),
                    # Trimmed: a gap summary is a paragraph, and a result
                    # row is one line.
                    label=str(label)[:160],
                    module=target.module,
                    href=target.href.format(id=row.id),
                )
            )

    # A document hit opens the document, not the list it sits in. The
    # target template cannot express this on its own: search matches a
    # File, and the Document Detail route is addressed by the indexed
    # document made from it. Resolved in one query, and a file with no
    # indexed document keeps the list href rather than gaining a link to
    # a page that does not exist.
    document_hits = [result for result in results if result.entity_type == "document"]
    if document_hits:
        hrefs = await hrefs_for_files(
            db,
            organization_id=organization_id,
            file_ids=[uuid.UUID(hit.id) for hit in document_hits],
        )
        for hit in document_hits:
            href = hrefs.get(uuid.UUID(hit.id))
            if href:
                hit.href = href

    results += await _search_frameworks(
        db, organization_id=organization_id, pattern=pattern, limit=limit_per_type
    )
    results += await _search_requirements(
        db, organization_id=organization_id, pattern=pattern, limit=limit_per_type
    )

    return results


__all__ = ["DEFAULT_LIMIT_PER_TYPE", "global_search"]
