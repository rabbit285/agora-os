"""Suppression list independent of `Contact.do_not_contact` (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §12) — a person can be
suppressed before they're ever saved as a Contact, e.g. a search result
the user recognizes and never wants contacted."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.sales.provider_models import SalesSuppressionEntry


def _normalize_domain(website_or_domain: str) -> str:
    return (
        website_or_domain.replace("https://", "")
        .replace("http://", "")
        .split("/")[0]
        .removeprefix("www.")
        .lower()
    )


async def list_suppression_entries(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[SalesSuppressionEntry]:
    rows = (
        await db.execute(
            select(SalesSuppressionEntry)
            .where(SalesSuppressionEntry.organization_id == organization_id)
            .order_by(SalesSuppressionEntry.created_at.desc())
        )
    ).scalars()
    return list(rows)


async def add_suppression_entry(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    reason: str,
    email: str | None = None,
    domain: str | None = None,
    contact_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SalesSuppressionEntry:
    if not email and not domain and not contact_id:
        raise ValueError("At least one of email, domain, or contact_id is required")
    entry = SalesSuppressionEntry(
        organization_id=organization_id,
        email=email.lower() if email else None,
        domain=_normalize_domain(domain) if domain else None,
        contact_id=contact_id,
        reason=reason,
        created_by_user_id=created_by_user_id,
    )
    db.add(entry)
    await db.flush()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=created_by_user_id,
        action="sales.suppression.added",
        object_type="sales_suppression_entry",
        object_id=str(entry.id),
        after_state={"email": entry.email, "domain": entry.domain, "reason": reason},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return entry


async def remove_suppression_entry(
    db: AsyncSession,
    *,
    entry: SalesSuppressionEntry,
    removed_by_user_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    entry_id = str(entry.id)
    organization_id = entry.organization_id
    await db.delete(entry)
    await db.flush()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=removed_by_user_id,
        action="sales.suppression.removed",
        object_type="sales_suppression_entry",
        object_id=entry_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


async def find_matching_suppression(
    db: AsyncSession, *, organization_id: uuid.UUID, email: str | None
) -> SalesSuppressionEntry | None:
    """Matches by exact email, or by the email's domain against any
    domain-level suppression entry."""
    if not email:
        return None
    email = email.lower()
    domain = email.split("@")[-1] if "@" in email else None

    by_email = (
        await db.execute(
            select(SalesSuppressionEntry).where(
                SalesSuppressionEntry.organization_id == organization_id,
                SalesSuppressionEntry.email == email,
            )
        )
    ).scalar_one_or_none()
    if by_email is not None:
        return by_email

    if domain:
        by_domain = (
            await db.execute(
                select(SalesSuppressionEntry).where(
                    SalesSuppressionEntry.organization_id == organization_id,
                    SalesSuppressionEntry.domain == domain,
                )
            )
        ).scalar_one_or_none()
        if by_domain is not None:
            return by_domain
    return None
