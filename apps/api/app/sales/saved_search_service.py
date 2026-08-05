"""Saved Lead Finder searches (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md
§11). Tenant-scoped CRUD, audited — same shape as every other domain
service in this codebase."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.sales.provider_models import SalesSavedSearch


async def list_saved_searches(
    db: AsyncSession, *, organization_id: uuid.UUID, search_type: str | None = None
) -> list[SalesSavedSearch]:
    query = select(SalesSavedSearch).where(SalesSavedSearch.organization_id == organization_id)
    if search_type:
        query = query.where(SalesSavedSearch.search_type == search_type)
    return list((await db.execute(query.order_by(SalesSavedSearch.updated_at.desc()))).scalars().all())


async def create_saved_search(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    name: str,
    search_type: str,
    filters: Any,
    provider: str,
    columns: list[str],
    sort: dict[str, Any] | None,
    density: str,
    is_shared: bool,
    ip_address: str | None,
    user_agent: str | None,
) -> SalesSavedSearch:
    saved_search = SalesSavedSearch(
        organization_id=organization_id,
        owner_user_id=owner_user_id,
        name=name,
        search_type=search_type,
        filters=asdict(filters) if not isinstance(filters, dict) else filters,
        provider=provider,
        columns=columns,
        sort=sort,
        density=density,
        is_shared=is_shared,
    )
    db.add(saved_search)
    await db.flush()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=owner_user_id,
        action="sales.lead_finder.saved_search.created",
        object_type="sales_saved_search",
        object_id=str(saved_search.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return saved_search


async def update_saved_search(
    db: AsyncSession,
    *,
    saved_search: SalesSavedSearch,
    actor_user_id: uuid.UUID,
    updates: dict[str, Any],
    ip_address: str | None,
    user_agent: str | None,
) -> SalesSavedSearch:
    before_state = {"name": saved_search.name, "filters": saved_search.filters}
    for key, value in updates.items():
        setattr(saved_search, key, value)
    await db.flush()
    await record_event(
        db,
        organization_id=saved_search.organization_id,
        actor_user_id=actor_user_id,
        action="sales.lead_finder.saved_search.updated",
        object_type="sales_saved_search",
        object_id=str(saved_search.id),
        before_state=before_state,
        after_state={"name": saved_search.name, "filters": saved_search.filters},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return saved_search


async def delete_saved_search(
    db: AsyncSession,
    *,
    saved_search: SalesSavedSearch,
    actor_user_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    saved_search_id = str(saved_search.id)
    organization_id = saved_search.organization_id
    await db.delete(saved_search)
    await db.flush()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="sales.lead_finder.saved_search.deleted",
        object_type="sales_saved_search",
        object_id=saved_search_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def mark_executed(db: AsyncSession, *, saved_search: SalesSavedSearch, result_count: int) -> None:
    saved_search.last_executed_at = datetime.now(UTC)
    saved_search.last_result_count = result_count
    await db.flush()
