from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.models import MemoryEntry


async def create_memory_entry(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    entry_type: str,
    content: str,
    provenance_type: str,
    provenance_id: uuid.UUID | None,
    created_by: uuid.UUID | None,
) -> MemoryEntry:
    entry = MemoryEntry(
        organization_id=organization_id,
        entry_type=entry_type,
        content=content,
        provenance_type=provenance_type,
        provenance_id=provenance_id,
        created_by=created_by,
    )
    db.add(entry)
    await db.flush()
    return entry


async def list_memory_entries(
    db: AsyncSession, *, organization_id: uuid.UUID, entry_type: str | None = None
) -> list[MemoryEntry]:
    stmt = select(MemoryEntry).where(
        MemoryEntry.organization_id == organization_id, MemoryEntry.status == "active"
    )
    if entry_type is not None:
        stmt = stmt.where(MemoryEntry.entry_type == entry_type)
    result = await db.execute(stmt.order_by(MemoryEntry.created_at.desc()))
    return list(result.scalars().all())


async def get_org_memory_entry(
    db: AsyncSession, *, organization_id: uuid.UUID, entry_id: uuid.UUID
) -> MemoryEntry | None:
    entry = await db.get(MemoryEntry, entry_id)
    if entry is None or entry.organization_id != organization_id:
        return None
    return entry


async def correct_memory_entry(
    db: AsyncSession, *, organization_id: uuid.UUID, entry_id: uuid.UUID, content: str
) -> MemoryEntry | None:
    entry = await get_org_memory_entry(db, organization_id=organization_id, entry_id=entry_id)
    if entry is None:
        return None
    entry.content = content
    await db.flush()
    return entry


async def delete_memory_entry(
    db: AsyncSession, *, organization_id: uuid.UUID, entry_id: uuid.UUID
) -> MemoryEntry | None:
    """Soft delete — flips `status`, never removes the row, so an
    administrator's deletion action itself remains part of the record
    (spec §89: "Allow administrators to correct/delete memory")."""
    entry = await get_org_memory_entry(db, organization_id=organization_id, entry_id=entry_id)
    if entry is None:
        return None
    entry.status = "deleted"
    await db.flush()
    return entry


async def record_policy_published_memory(
    db: AsyncSession, *, organization_id: uuid.UUID, policy_id: uuid.UUID, policy_title: str
) -> None:
    """The one real automatic provenance hook (spec §89's "Policies"
    category) — fired from app.routers.compliance.update_policy_status
    when a Policy transitions to "published". Deliberately not fired for
    every workflow run/decision/answer: spec's own "Create organization
    memory carefully" cautions against indiscriminate automatic capture,
    so every other category is administrator-curated via
    create_memory_entry instead."""
    await create_memory_entry(
        db,
        organization_id=organization_id,
        entry_type="policy",
        content=f'Policy published: "{policy_title}"',
        provenance_type="policy",
        provenance_id=policy_id,
        created_by=None,
    )
