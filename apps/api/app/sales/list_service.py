"""Sales Lead Finder lists (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md
§11). Adding a raw search result to a list implicitly saves it as an
Account/Contact first if it isn't already — surfaced to the caller as one
action, not a silent second write the user didn't ask for."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.sales.provider_models import SalesList, SalesListItem


class DuplicateListItemError(Exception):
    """Raised when the account/contact is already in this list."""


async def list_lists(
    db: AsyncSession, *, organization_id: uuid.UUID, list_type: str | None = None
) -> list[SalesList]:
    query = select(SalesList).where(SalesList.organization_id == organization_id)
    if list_type:
        query = query.where(SalesList.list_type == list_type)
    return list((await db.execute(query.order_by(SalesList.updated_at.desc()))).scalars().all())


async def list_items(db: AsyncSession, *, list_id: uuid.UUID) -> list[SalesListItem]:
    rows = (
        await db.execute(
            select(SalesListItem)
            .where(SalesListItem.list_id == list_id)
            .order_by(SalesListItem.created_at.desc())
        )
    ).scalars()
    return list(rows)


async def create_list(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    name: str,
    list_type: str,
    description: str | None,
    tags: list[str],
    is_shared: bool,
    ip_address: str | None,
    user_agent: str | None,
) -> SalesList:
    sales_list = SalesList(
        organization_id=organization_id,
        owner_user_id=owner_user_id,
        name=name,
        list_type=list_type,
        description=description,
        tags=tags,
        is_shared=is_shared,
    )
    db.add(sales_list)
    await db.flush()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=owner_user_id,
        action="sales.lead_finder.list.created",
        object_type="sales_list",
        object_id=str(sales_list.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return sales_list


async def add_item(
    db: AsyncSession,
    *,
    sales_list: SalesList,
    account_id: uuid.UUID | None,
    contact_id: uuid.UUID | None,
    added_by_user_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
) -> SalesListItem:
    item = SalesListItem(
        list_id=sales_list.id,
        account_id=account_id,
        contact_id=contact_id,
        added_by_user_id=added_by_user_id,
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateListItemError("This record is already in the list.") from exc
    await record_event(
        db,
        organization_id=sales_list.organization_id,
        actor_user_id=added_by_user_id,
        action="sales.lead_finder.list.item_added",
        object_type="sales_list_item",
        object_id=str(item.id),
        after_state={"list_id": str(sales_list.id), "account_id": str(account_id) if account_id else None,
                     "contact_id": str(contact_id) if contact_id else None},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return item


async def remove_item(
    db: AsyncSession,
    *,
    sales_list: SalesList,
    item: SalesListItem,
    removed_by_user_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    item_id = str(item.id)
    await db.delete(item)
    await db.flush()
    await record_event(
        db,
        organization_id=sales_list.organization_id,
        actor_user_id=removed_by_user_id,
        action="sales.lead_finder.list.item_removed",
        object_type="sales_list_item",
        object_id=item_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
