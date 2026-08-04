from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.memory.models import MemoryEntry
from app.memory.schemas import MemoryEntryCreate, MemoryEntryOut, MemoryEntryUpdate
from app.memory.service import (
    correct_memory_entry,
    create_memory_entry,
    delete_memory_entry,
    get_org_memory_entry,
    list_memory_entries,
)

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


@router.get("", response_model=list[MemoryEntryOut])
async def list_organization_memory(
    entry_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[MemoryEntry]:
    """Any org member can view organizational memory (spec §89) — it is
    meant to ground answers broadly; only creating/correcting/deleting
    entries is permission-gated."""
    return await list_memory_entries(db, organization_id=context.organization_id, entry_type=entry_type)


@router.post("", response_model=MemoryEntryOut, status_code=status.HTTP_201_CREATED)
async def create_organization_memory(
    payload: MemoryEntryCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("business_memory.manage")),
) -> MemoryEntry:
    entry = await create_memory_entry(
        db,
        organization_id=context.organization_id,
        entry_type=payload.entry_type,
        content=payload.content,
        provenance_type="manual",
        provenance_id=None,
        created_by=context.user.id,
    )
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="memory.entry.created",
        object_type="memory_entry",
        object_id=str(entry.id),
        after_state={"entry_type": entry.entry_type, "content": entry.content},
    )
    await db.commit()
    return entry


@router.patch("/{entry_id}", response_model=MemoryEntryOut)
async def correct_organization_memory(
    entry_id: uuid.UUID,
    payload: MemoryEntryUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("business_memory.manage")),
) -> MemoryEntry:
    before = await get_org_memory_entry(db, organization_id=context.organization_id, entry_id=entry_id)
    if before is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory entry not found")
    before_content = before.content

    existing = await correct_memory_entry(
        db, organization_id=context.organization_id, entry_id=entry_id, content=payload.content
    )
    assert existing is not None
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="memory.entry.corrected",
        object_type="memory_entry",
        object_id=str(existing.id),
        before_state={"content": before_content},
        after_state={"content": payload.content},
    )
    await db.commit()
    return existing


@router.delete("/{entry_id}", response_model=MemoryEntryOut)
async def delete_organization_memory(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("business_memory.manage")),
) -> MemoryEntry:
    existing = await delete_memory_entry(db, organization_id=context.organization_id, entry_id=entry_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory entry not found")
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="memory.entry.deleted",
        object_type="memory_entry",
        object_id=str(existing.id),
        after_state={"status": "deleted"},
    )
    await db.commit()
    return existing
