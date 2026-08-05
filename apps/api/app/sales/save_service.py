"""Turning a provider search result into a real, permanent Account/Contact
(see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §7, §10). Writes a
`SalesProviderRecord` for provenance and links it to the new/existing
row — this is the one and only place a search result is ever persisted."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.sales.icp import compute_icp_score, get_icp_profile
from app.sales.models import Account, Contact
from app.sales.provider_models import SalesProviderRecord
from app.sales.providers.schemas import NormalizedCompany, NormalizedPerson

_EMAIL_STATUS_TO_VERIFICATION_STATUS = {
    "verified": "verified",
    "unverified": "unverified",
    "catch_all": "unverified",
    "unavailable": "unavailable",
}

# CSV-imported and manually-entered records are never presented as
# provider-verified (spec: "guessed contact details presented as verified"
# is a hard prohibition) — both map to the same honest "user_entered"
# status regardless of what the row happened to contain.
_NON_PROVIDER_SOURCE_VERIFICATION_STATUS = {
    "demo": "demo",
    "csv": "user_entered",
    "manual": "user_entered",
}


def _normalize_domain(website_or_domain: str) -> str:
    return (
        website_or_domain.replace("https://", "")
        .replace("http://", "")
        .split("/")[0]
        .removeprefix("www.")
        .lower()
    )


async def save_company_as_account(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    company: NormalizedCompany,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[Account, bool]:
    """Returns (account, created) — `created=False` when an existing
    Account already matched (never a silent duplicate, spec §10)."""
    existing: Account | None = None
    if company.domain:
        domain = _normalize_domain(company.domain)
        candidates = (
            await db.execute(
                select(Account).where(
                    Account.organization_id == organization_id, Account.website.isnot(None)
                )
            )
        ).scalars()
        for candidate in candidates:
            if candidate.website and _normalize_domain(candidate.website) == domain:
                existing = candidate
                break

    if existing is not None:
        account = existing
        created = False
    else:
        account = Account(
            organization_id=organization_id,
            name=company.name,
            industry=company.industry,
            website=company.website or (f"https://{company.domain}" if company.domain else None),
            employee_count=company.employee_count,
        )
        db.add(account)
        await db.flush()
        profile = await get_icp_profile(db, organization_id=organization_id)
        if profile is not None:
            account.icp_score = compute_icp_score(account, profile)
        created = True

    provider_record = SalesProviderRecord(
        organization_id=organization_id,
        provider=company.provider,
        record_type="company",
        provider_record_id=company.provider_record_id,
        normalized_domain=_normalize_domain(company.domain) if company.domain else None,
        source_url=company.source_url,
        retrieved_at=company.retrieved_at,
        last_verified_at=datetime.now(UTC),
        verification_status=_NON_PROVIDER_SOURCE_VERIFICATION_STATUS.get(
            company.provider, "provider_supplied"
        ),
        raw_payload=company.raw,
        linked_account_id=account.id,
        imported_by_user_id=actor_user_id,
    )
    db.add(provider_record)
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="sales.lead_finder.company.saved",
        object_type="sales_account",
        object_id=str(account.id),
        after_state={"name": account.name, "provider": company.provider, "created": created},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return account, created


async def save_person_as_contact(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    person: NormalizedPerson,
    account_id: uuid.UUID | None,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[Contact, bool]:
    existing: Contact | None = None
    if person.email:
        existing = (
            await db.execute(
                select(Contact).where(
                    Contact.organization_id == organization_id,
                    Contact.email == person.email.lower(),
                )
            )
        ).scalar_one_or_none()

    if existing is not None:
        contact = existing
        created = False
    else:
        contact = Contact(
            organization_id=organization_id,
            full_name=person.full_name,
            email=(person.email or f"unknown-{uuid.uuid4().hex[:8]}@no-email.invalid").lower(),
            job_title=person.title,
            account_id=account_id,
        )
        db.add(contact)
        await db.flush()
        created = True

    provider_record = SalesProviderRecord(
        organization_id=organization_id,
        provider=person.provider,
        record_type="person",
        provider_record_id=person.provider_record_id,
        normalized_email=person.email.lower() if person.email else None,
        source_url=person.source_url,
        retrieved_at=person.retrieved_at,
        last_verified_at=datetime.now(UTC),
        verification_status=_NON_PROVIDER_SOURCE_VERIFICATION_STATUS.get(
            person.provider,
            _EMAIL_STATUS_TO_VERIFICATION_STATUS.get(person.email_status, "unverified"),
        ),
        raw_payload=person.raw,
        linked_contact_id=contact.id,
        imported_by_user_id=actor_user_id,
    )
    db.add(provider_record)
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="sales.lead_finder.person.saved",
        object_type="sales_contact",
        object_id=str(contact.id),
        after_state={"full_name": contact.full_name, "provider": person.provider, "created": created},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return contact, created
