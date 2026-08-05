"""Sales Lead Finder lists (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md
§11). Adding a raw search result to a list implicitly saves it as an
Account/Contact first if it isn't already — surfaced to the caller as one
action, not a silent second write the user didn't ask for."""

from __future__ import annotations

import csv
import io
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.core.models import Organization
from app.sales.models import Account, Contact
from app.sales.provider_models import SalesList, SalesListItem


class DuplicateListItemError(Exception):
    """Raised when the account/contact is already in this list."""


class ListExportDisabledError(Exception):
    """Raised when the organization's own policy has export turned off
    (Organization.allow_list_export) — independent of the exporting
    user's own RBAC permission."""


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


_COMPANY_EXPORT_COLUMNS = [
    "name",
    "industry",
    "website",
    "employee_count",
    "icp_score",
    "status",
    "account_id",
    "added_at",
]
_PERSON_EXPORT_COLUMNS = [
    "full_name",
    "email",
    "job_title",
    "do_not_contact",
    "contact_id",
    "added_at",
]


async def export_list_csv(
    db: AsyncSession,
    *,
    sales_list: SalesList,
    actor_user_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, int]:
    """Returns (csv_text, row_count). Organization policy
    (Organization.allow_list_export) is enforced here, independent of the
    exporting user's own RBAC permission — an org_admin can turn export
    off entirely for the whole organization. Every export is audited
    with the real row count, whether or not the list was empty."""
    organization = await db.get(Organization, sales_list.organization_id)
    if organization is None or not organization.allow_list_export:
        raise ListExportDisabledError(
            "List export is disabled for this organization. Ask an admin to enable it in "
            "organization settings."
        )

    items = await list_items(db, list_id=sales_list.id)
    buffer = io.StringIO()

    if sales_list.list_type == "company":
        writer = csv.DictWriter(buffer, fieldnames=_COMPANY_EXPORT_COLUMNS)
        writer.writeheader()
        account_ids = [item.account_id for item in items if item.account_id]
        accounts_by_id: dict[uuid.UUID, Account] = {}
        if account_ids:
            rows = (await db.execute(select(Account).where(Account.id.in_(account_ids)))).scalars()
            accounts_by_id = {a.id: a for a in rows}
        for item in items:
            account = accounts_by_id.get(item.account_id) if item.account_id else None
            if account is None:
                continue
            writer.writerow(
                {
                    "name": account.name,
                    "industry": account.industry or "",
                    "website": account.website or "",
                    "employee_count": account.employee_count if account.employee_count is not None else "",
                    "icp_score": account.icp_score if account.icp_score is not None else "",
                    "status": account.status,
                    "account_id": str(account.id),
                    "added_at": item.created_at.isoformat(),
                }
            )
    else:
        writer = csv.DictWriter(buffer, fieldnames=_PERSON_EXPORT_COLUMNS)
        writer.writeheader()
        contact_ids = [item.contact_id for item in items if item.contact_id]
        contacts_by_id: dict[uuid.UUID, Contact] = {}
        if contact_ids:
            contact_rows = (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars()
            contacts_by_id = {c.id: c for c in contact_rows}
        for item in items:
            contact = contacts_by_id.get(item.contact_id) if item.contact_id else None
            if contact is None:
                continue
            writer.writerow(
                {
                    "full_name": contact.full_name,
                    "email": contact.email,
                    "job_title": contact.job_title or "",
                    "do_not_contact": contact.do_not_contact,
                    "contact_id": str(contact.id),
                    "added_at": item.created_at.isoformat(),
                }
            )

    csv_text = buffer.getvalue()
    row_count = csv_text.count("\n") - 1  # header line doesn't count as a data row

    await record_event(
        db,
        organization_id=sales_list.organization_id,
        actor_user_id=actor_user_id,
        action="sales.lead_finder.list.exported",
        object_type="sales_list",
        object_id=str(sales_list.id),
        after_state={"row_count": row_count},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return csv_text, row_count
