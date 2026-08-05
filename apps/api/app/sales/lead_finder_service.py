"""Sales Lead Finder search/discovery service (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md). Provider dispatch + short-TTL
result caching + existing-record dedupe-check composition. Search results
themselves are never persisted (see architecture doc §7) — only an
explicit user action (save/enrich/list) writes a `SalesProviderRecord`.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sales.models import Account, Contact
from app.sales.provider_models import SalesProviderRecord
from app.sales.providers import cache
from app.sales.providers.registry import get_provider
from app.sales.providers.schemas import (
    CompanyFilters,
    CompanySearchRequest,
    CompanySearchResponse,
    DecisionMakerRequest,
    NormalizedCompany,
    NormalizedPerson,
    PersonFilters,
    PersonSearchRequest,
    PersonSearchResponse,
    SortSpec,
)


def _company_to_dict(company: NormalizedCompany) -> dict[str, Any]:
    payload = asdict(company)
    payload["retrieved_at"] = company.retrieved_at.isoformat()
    return payload


def _company_from_dict(payload: dict[str, Any]) -> NormalizedCompany:
    payload = dict(payload)
    payload["retrieved_at"] = datetime.fromisoformat(payload["retrieved_at"])
    return NormalizedCompany(**payload)


def _person_to_dict(person: NormalizedPerson) -> dict[str, Any]:
    payload = asdict(person)
    payload["retrieved_at"] = person.retrieved_at.isoformat()
    return payload


def _person_from_dict(payload: dict[str, Any]) -> NormalizedPerson:
    payload = dict(payload)
    payload["retrieved_at"] = datetime.fromisoformat(payload["retrieved_at"])
    return NormalizedPerson(**payload)


async def search_companies(
    *,
    organization_id: uuid.UUID,
    filters: CompanyFilters,
    page: int = 1,
    page_size: int = 25,
    sort: SortSpec | None = None,
    provider_key: str = "apollo",
    refresh: bool = False,
) -> CompanySearchResponse:
    provider = get_provider(provider_key)
    cache_key = cache.build_cache_key(
        organization_id=organization_id,
        provider=provider.provider_key,
        record_type="company",
        filters=filters,
        page=page,
        sort_key=f"{sort.field}:{sort.direction}" if sort else None,
    )
    if not refresh:
        cached = await cache.get_cached(cache_key)
        if cached is not None:
            return CompanySearchResponse(
                provider=cached["provider"],
                companies=[_company_from_dict(c) for c in cached["companies"]],
                total_available=cached["total_available"],
                page=cached["page"],
                page_size=cached["page_size"],
                credits_used=cached.get("credits_used"),
            )

    request = CompanySearchRequest(
        organization_id=organization_id, filters=filters, page=page, page_size=page_size, sort=sort
    )
    response = await provider.search_companies(request)

    await cache.set_cached(
        cache_key,
        {
            "provider": response.provider,
            "companies": [_company_to_dict(c) for c in response.companies],
            "total_available": response.total_available,
            "page": response.page,
            "page_size": response.page_size,
            "credits_used": response.credits_used,
        },
    )
    return response


async def search_people(
    *,
    organization_id: uuid.UUID,
    filters: PersonFilters,
    page: int = 1,
    page_size: int = 25,
    sort: SortSpec | None = None,
    provider_key: str = "apollo",
    refresh: bool = False,
) -> PersonSearchResponse:
    provider = get_provider(provider_key)
    cache_key = cache.build_cache_key(
        organization_id=organization_id,
        provider=provider.provider_key,
        record_type="person",
        filters=filters,
        page=page,
        sort_key=f"{sort.field}:{sort.direction}" if sort else None,
    )
    if not refresh:
        cached = await cache.get_cached(cache_key)
        if cached is not None:
            return PersonSearchResponse(
                provider=cached["provider"],
                people=[_person_from_dict(p) for p in cached["people"]],
                total_available=cached["total_available"],
                page=cached["page"],
                page_size=cached["page_size"],
                credits_used=cached.get("credits_used"),
            )

    request = PersonSearchRequest(
        organization_id=organization_id, filters=filters, page=page, page_size=page_size, sort=sort
    )
    response = await provider.search_people(request)

    await cache.set_cached(
        cache_key,
        {
            "provider": response.provider,
            "people": [_person_to_dict(p) for p in response.people],
            "total_available": response.total_available,
            "page": response.page,
            "page_size": response.page_size,
            "credits_used": response.credits_used,
        },
    )
    return response


async def find_decision_makers(
    *, organization_id: uuid.UUID, company_domain: str, provider_key: str = "apollo"
) -> PersonSearchResponse:
    provider = get_provider(provider_key)
    request = DecisionMakerRequest(organization_id=organization_id, company_domain=company_domain)
    return await provider.find_decision_makers(request)


def _normalize_domain(website_or_domain: str) -> str:
    return (
        website_or_domain.replace("https://", "")
        .replace("http://", "")
        .split("/")[0]
        .removeprefix("www.")
        .lower()
    )


async def dedupe_check_companies(
    db: AsyncSession, *, organization_id: uuid.UUID, companies: list[NormalizedCompany]
) -> dict[str, dict[str, Any]]:
    """Batched — one query per lookup dimension across the whole page,
    not N+1 (see architecture doc §10)."""
    provider_ids = [c.provider_record_id for c in companies]
    domains = [_normalize_domain(c.domain) for c in companies if c.domain]

    existing_by_provider_id: dict[str, uuid.UUID] = {}
    if provider_ids:
        rows = (
            await db.execute(
                select(SalesProviderRecord.provider_record_id, SalesProviderRecord.linked_account_id).where(
                    SalesProviderRecord.organization_id == organization_id,
                    SalesProviderRecord.record_type == "company",
                    SalesProviderRecord.provider_record_id.in_(provider_ids),
                    SalesProviderRecord.linked_account_id.isnot(None),
                )
            )
        ).all()
        existing_by_provider_id = {r[0]: r[1] for r in rows}

    existing_by_domain: dict[str, uuid.UUID] = {}
    if domains:
        account_rows = (
            await db.execute(
                select(Account.id, Account.website).where(
                    Account.organization_id == organization_id, Account.website.isnot(None)
                )
            )
        ).all()
        for account_id, website in account_rows:
            existing_by_domain[_normalize_domain(website)] = account_id

    results: dict[str, dict[str, Any]] = {}
    for company in companies:
        domain = _normalize_domain(company.domain) if company.domain else None
        if company.provider_record_id in existing_by_provider_id:
            results[company.provider_record_id] = {
                "status": "existing",
                "existing_account_id": str(existing_by_provider_id[company.provider_record_id]),
            }
        elif domain and domain in existing_by_domain:
            results[company.provider_record_id] = {
                "status": "existing",
                "existing_account_id": str(existing_by_domain[domain]),
            }
        else:
            results[company.provider_record_id] = {"status": "new", "existing_account_id": None}
    return results


async def dedupe_check_people(
    db: AsyncSession, *, organization_id: uuid.UUID, people: list[NormalizedPerson]
) -> dict[str, dict[str, Any]]:
    provider_ids = [p.provider_record_id for p in people]
    emails = [p.email.lower() for p in people if p.email]

    existing_by_provider_id: dict[str, uuid.UUID] = {}
    if provider_ids:
        provider_rows = (
            await db.execute(
                select(SalesProviderRecord.provider_record_id, SalesProviderRecord.linked_contact_id).where(
                    SalesProviderRecord.organization_id == organization_id,
                    SalesProviderRecord.record_type == "person",
                    SalesProviderRecord.provider_record_id.in_(provider_ids),
                    SalesProviderRecord.linked_contact_id.isnot(None),
                )
            )
        ).all()
        existing_by_provider_id = {r[0]: r[1] for r in provider_rows}

    existing_by_email: dict[str, uuid.UUID] = {}
    if emails:
        contact_rows = (
            await db.execute(
                select(Contact.id, Contact.email).where(
                    Contact.organization_id == organization_id,
                    func.lower(Contact.email).in_(emails),
                )
            )
        ).all()
        existing_by_email = {email.lower(): contact_id for contact_id, email in contact_rows}

    results: dict[str, dict[str, Any]] = {}
    for person in people:
        email = person.email.lower() if person.email else None
        if person.provider_record_id in existing_by_provider_id:
            results[person.provider_record_id] = {
                "status": "existing",
                "existing_contact_id": str(existing_by_provider_id[person.provider_record_id]),
            }
        elif email and email in existing_by_email:
            results[person.provider_record_id] = {
                "status": "existing",
                "existing_contact_id": str(existing_by_email[email]),
            }
        else:
            results[person.provider_record_id] = {"status": "new", "existing_contact_id": None}
    return results
