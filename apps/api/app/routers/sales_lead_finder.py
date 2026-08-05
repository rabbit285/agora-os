"""Sales Lead Finder — company/people discovery, saved searches, lists,
and provider status (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md).
Mounted separately from `app.routers.sales` (which owns the pre-existing
Account/Contact/Lead/Opportunity CRUD) so the new provider-neutral
discovery layer reads as its own bounded surface."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import OrgContext, require_permission
from app.sales import lead_finder_service, list_service, save_service, saved_search_service
from app.sales.lead_finder_schemas import (
    CompanyFiltersIn,
    CompanySearchIn,
    CompanySearchOut,
    CreditUsageSummaryOut,
    DecisionMakerIn,
    NormalizedCompanyOut,
    NormalizedPersonOut,
    ParseQueryIn,
    ParseQueryOut,
    PersonFiltersIn,
    PersonSearchIn,
    PersonSearchOut,
    ProviderCapabilitiesOut,
    ProviderStatusOut,
    SalesListCreate,
    SalesListItemCreate,
    SalesListItemOut,
    SalesListOut,
    SaveCompanyOut,
    SavedSearchCreate,
    SavedSearchOut,
    SavedSearchUpdate,
    SavePersonOut,
    SortSpecIn,
)
from app.sales.list_service import DuplicateListItemError
from app.sales.nl_filter_parser import parse_query
from app.sales.provider_models import (
    SalesList,
    SalesListItem,
    SalesProviderCreditUsage,
    SalesSavedSearch,
)
from app.sales.providers.registry import (
    apollo_status,
    get_provider,
    is_apollo_configured,
    list_provider_keys,
)
from app.sales.providers.schemas import (
    CompanyFilters,
    NormalizedCompany,
    NormalizedPerson,
    PersonFilters,
    SortSpec,
)

router = APIRouter(prefix="/api/v1/sales/lead-finder", tags=["sales-lead-finder"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None, request.headers.get("user-agent"))


def _to_domain_company_filters(filters: CompanyFiltersIn) -> CompanyFilters:
    return CompanyFilters(**filters.model_dump())


def _to_domain_person_filters(filters: PersonFiltersIn) -> PersonFilters:
    return PersonFilters(**filters.model_dump())


def _to_domain_sort(sort: SortSpecIn | None) -> SortSpec | None:
    return SortSpec(field=sort.field, direction=sort.direction) if sort else None


@router.post("/companies/search", response_model=CompanySearchOut)
async def search_companies(
    payload: CompanySearchIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> CompanySearchOut:
    response = await lead_finder_service.search_companies(
        organization_id=context.organization_id,
        filters=_to_domain_company_filters(payload.filters),
        page=payload.page,
        page_size=payload.page_size,
        sort=_to_domain_sort(payload.sort),
        provider_key=payload.provider,
        refresh=payload.refresh,
    )
    dedupe = await lead_finder_service.dedupe_check_companies(
        db, organization_id=context.organization_id, companies=response.companies
    )
    return CompanySearchOut(
        provider=response.provider,
        companies=[
            NormalizedCompanyOut.from_normalized(c, dedupe.get(c.provider_record_id))
            for c in response.companies
        ],
        total_available=response.total_available,
        page=response.page,
        page_size=response.page_size,
        credits_used=response.credits_used,
    )


@router.post("/people/search", response_model=PersonSearchOut)
async def search_people(
    payload: PersonSearchIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> PersonSearchOut:
    response = await lead_finder_service.search_people(
        organization_id=context.organization_id,
        filters=_to_domain_person_filters(payload.filters),
        page=payload.page,
        page_size=payload.page_size,
        sort=_to_domain_sort(payload.sort),
        provider_key=payload.provider,
        refresh=payload.refresh,
    )
    dedupe = await lead_finder_service.dedupe_check_people(
        db, organization_id=context.organization_id, people=response.people
    )
    return PersonSearchOut(
        provider=response.provider,
        people=[
            NormalizedPersonOut.from_normalized(p, dedupe.get(p.provider_record_id))
            for p in response.people
        ],
        total_available=response.total_available,
        page=response.page,
        page_size=response.page_size,
        credits_used=response.credits_used,
    )


@router.post("/decision-makers", response_model=PersonSearchOut)
async def find_decision_makers(
    payload: DecisionMakerIn,
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> PersonSearchOut:
    response = await lead_finder_service.find_decision_makers(
        organization_id=context.organization_id,
        company_domain=payload.company_domain,
        provider_key=payload.provider,
    )
    return PersonSearchOut(
        provider=response.provider,
        people=[NormalizedPersonOut.from_normalized(p) for p in response.people],
        total_available=response.total_available,
        page=response.page,
        page_size=response.page_size,
        credits_used=response.credits_used,
    )


@router.post("/parse-query", response_model=ParseQueryOut)
async def parse_natural_language_query(
    payload: ParseQueryIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> ParseQueryOut:
    parsed = await parse_query(
        db, organization_id=context.organization_id, requested_by=context.user.id, query=payload.query
    )
    await db.commit()
    return ParseQueryOut(
        company_filters=CompanyFiltersIn(**parsed.company_filters.model_dump()),
        person_filters=PersonFiltersIn(**parsed.person_filters.model_dump()),
        unsupported_criteria=parsed.unsupported_criteria,
        provider="demo" if not is_apollo_configured() else "apollo",
    )


@router.get("/providers", response_model=list[ProviderStatusOut])
async def list_providers(
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> list[ProviderStatusOut]:
    results = []
    for key in list_provider_keys():
        provider = get_provider(key)
        caps = provider.capabilities()
        results.append(
            ProviderStatusOut(
                provider_key=key,
                status=apollo_status().value if key == "apollo" else "not_configured",
                capabilities=ProviderCapabilitiesOut(**caps.__dict__),
                configured=is_apollo_configured() if key == "apollo" else False,
            )
        )
    return results


@router.get("/providers/{provider_key}/usage", response_model=list[CreditUsageSummaryOut])
async def provider_usage(
    provider_key: str,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.providers.manage")),
) -> list[SalesProviderCreditUsage]:
    rows = (
        await db.execute(
            select(SalesProviderCreditUsage)
            .where(
                SalesProviderCreditUsage.organization_id == context.organization_id,
                SalesProviderCreditUsage.provider == provider_key,
            )
            .order_by(SalesProviderCreditUsage.created_at.desc())
            .limit(200)
        )
    ).scalars()
    return list(rows)


# ---- Save as Account / Contact ----


@router.post("/companies/save", response_model=SaveCompanyOut, status_code=status.HTTP_201_CREATED)
async def save_company(
    payload: NormalizedCompanyOut,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.accounts.manage")),
) -> SaveCompanyOut:
    ip_address, user_agent = _client_meta(request)
    normalized = NormalizedCompany(**payload.model_dump(exclude={"dedupe_status", "existing_account_id"}))
    account, created = await save_service.save_company_as_account(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        company=normalized,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return SaveCompanyOut(account_id=account.id, created=created)


@router.post("/people/save", response_model=SavePersonOut, status_code=status.HTTP_201_CREATED)
async def save_person(
    payload: NormalizedPersonOut,
    request: Request,
    account_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.accounts.manage")),
) -> SavePersonOut:
    ip_address, user_agent = _client_meta(request)
    normalized = NormalizedPerson(**payload.model_dump(exclude={"dedupe_status", "existing_contact_id"}))
    contact, created = await save_service.save_person_as_contact(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        person=normalized,
        account_id=account_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return SavePersonOut(contact_id=contact.id, created=created)


# ---- Saved searches ----


@router.get("/saved-searches", response_model=list[SavedSearchOut])
async def list_saved_searches(
    search_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> list[SalesSavedSearch]:
    return await saved_search_service.list_saved_searches(
        db, organization_id=context.organization_id, search_type=search_type
    )


@router.post("/saved-searches", response_model=SavedSearchOut, status_code=status.HTTP_201_CREATED)
async def create_saved_search(
    payload: SavedSearchCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.saved_searches.manage")),
) -> SalesSavedSearch:
    ip_address, user_agent = _client_meta(request)
    saved_search = await saved_search_service.create_saved_search(
        db,
        organization_id=context.organization_id,
        owner_user_id=context.user.id,
        name=payload.name,
        search_type=payload.search_type,
        filters=payload.filters,
        provider=payload.provider,
        columns=payload.columns,
        sort=payload.sort,
        density=payload.density,
        is_shared=payload.is_shared,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    await db.refresh(saved_search)
    return saved_search


async def _get_org_saved_search(
    db: AsyncSession, saved_search_id: uuid.UUID, organization_id: uuid.UUID
) -> SalesSavedSearch:
    saved_search = await db.get(SalesSavedSearch, saved_search_id)
    if saved_search is None or saved_search.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved search not found")
    return saved_search


@router.patch("/saved-searches/{saved_search_id}", response_model=SavedSearchOut)
async def update_saved_search(
    saved_search_id: uuid.UUID,
    payload: SavedSearchUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.saved_searches.manage")),
) -> SalesSavedSearch:
    saved_search = await _get_org_saved_search(db, saved_search_id, context.organization_id)
    ip_address, user_agent = _client_meta(request)
    updates = payload.model_dump(exclude_unset=True)
    saved_search = await saved_search_service.update_saved_search(
        db,
        saved_search=saved_search,
        actor_user_id=context.user.id,
        updates=updates,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    await db.refresh(saved_search)
    return saved_search


@router.delete(
    "/saved-searches/{saved_search_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_saved_search(
    saved_search_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.saved_searches.manage")),
) -> None:
    saved_search = await _get_org_saved_search(db, saved_search_id, context.organization_id)
    ip_address, user_agent = _client_meta(request)
    await saved_search_service.delete_saved_search(
        db,
        saved_search=saved_search,
        actor_user_id=context.user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()


@router.post("/saved-searches/{saved_search_id}/run", response_model=CompanySearchOut | PersonSearchOut)
async def run_saved_search(
    saved_search_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> CompanySearchOut | PersonSearchOut:
    saved_search = await _get_org_saved_search(db, saved_search_id, context.organization_id)
    if saved_search.search_type == "company":
        company_response = await lead_finder_service.search_companies(
            organization_id=context.organization_id,
            filters=CompanyFilters(**saved_search.filters),
            provider_key=saved_search.provider,
        )
        await saved_search_service.mark_executed(
            db, saved_search=saved_search, result_count=len(company_response.companies)
        )
        company_dedupe = await lead_finder_service.dedupe_check_companies(
            db, organization_id=context.organization_id, companies=company_response.companies
        )
        await db.commit()
        return CompanySearchOut(
            provider=company_response.provider,
            companies=[
                NormalizedCompanyOut.from_normalized(c, company_dedupe.get(c.provider_record_id))
                for c in company_response.companies
            ],
            total_available=company_response.total_available,
            page=company_response.page,
            page_size=company_response.page_size,
            credits_used=company_response.credits_used,
        )

    person_response = await lead_finder_service.search_people(
        organization_id=context.organization_id,
        filters=PersonFilters(**saved_search.filters),
        provider_key=saved_search.provider,
    )
    await saved_search_service.mark_executed(
        db, saved_search=saved_search, result_count=len(person_response.people)
    )
    person_dedupe = await lead_finder_service.dedupe_check_people(
        db, organization_id=context.organization_id, people=person_response.people
    )
    await db.commit()
    return PersonSearchOut(
        provider=person_response.provider,
        people=[
            NormalizedPersonOut.from_normalized(p, person_dedupe.get(p.provider_record_id))
            for p in person_response.people
        ],
        total_available=person_response.total_available,
        page=person_response.page,
        page_size=person_response.page_size,
        credits_used=person_response.credits_used,
    )


# ---- Lists ----


@router.get("/lists", response_model=list[SalesListOut])
async def list_lists(
    list_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> list[SalesList]:
    return await list_service.list_lists(db, organization_id=context.organization_id, list_type=list_type)


@router.post("/lists", response_model=SalesListOut, status_code=status.HTTP_201_CREATED)
async def create_list(
    payload: SalesListCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.lists.manage")),
) -> SalesList:
    ip_address, user_agent = _client_meta(request)
    sales_list = await list_service.create_list(
        db,
        organization_id=context.organization_id,
        owner_user_id=context.user.id,
        name=payload.name,
        list_type=payload.list_type,
        description=payload.description,
        tags=payload.tags,
        is_shared=payload.is_shared,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    await db.refresh(sales_list)
    return sales_list


async def _get_org_list(db: AsyncSession, list_id: uuid.UUID, organization_id: uuid.UUID) -> SalesList:
    sales_list = await db.get(SalesList, list_id)
    if sales_list is None or sales_list.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List not found")
    return sales_list


@router.post("/lists/{list_id}/items", response_model=SalesListItemOut, status_code=status.HTTP_201_CREATED)
async def add_list_item(
    list_id: uuid.UUID,
    payload: SalesListItemCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.lists.manage")),
) -> SalesListItem:
    sales_list = await _get_org_list(db, list_id, context.organization_id)
    if not payload.account_id and not payload.contact_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either account_id or contact_id is required",
        )
    ip_address, user_agent = _client_meta(request)
    try:
        item = await list_service.add_item(
            db,
            sales_list=sales_list,
            account_id=payload.account_id,
            contact_id=payload.contact_id,
            added_by_user_id=context.user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except DuplicateListItemError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(item)
    return item


@router.delete(
    "/lists/{list_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def remove_list_item(
    list_id: uuid.UUID,
    item_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.lists.manage")),
) -> None:
    sales_list = await _get_org_list(db, list_id, context.organization_id)
    item = await db.get(SalesListItem, item_id)
    if item is None or item.list_id != sales_list.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="List item not found")
    ip_address, user_agent = _client_meta(request)
    await list_service.remove_item(
        db,
        sales_list=sales_list,
        item=item,
        removed_by_user_id=context.user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
