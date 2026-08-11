"""Sales Lead Finder — company/people discovery, saved searches, lists,
and provider status (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md).
Mounted separately from `app.routers.sales` (which owns the pre-existing
Account/Contact/Lead/Opportunity CRUD) so the new provider-neutral
discovery layer reads as its own bounded surface."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.governance import evaluate_outreach_eligibility
from app.core.models import File
from app.core.storage import download_object
from app.db.session import get_db
from app.dependencies import OrgContext, require_permission
from app.sales import (
    csv_import,
    enrichment_job_service,
    import_job_service,
    lead_finder_service,
    linkedin_task_service,
    list_service,
    save_service,
    saved_search_service,
    suppression_service,
)
from app.sales.lead_finder_schemas import (
    CompanyFiltersIn,
    CompanySearchIn,
    CompanySearchOut,
    CreditEstimatePreviewOut,
    CreditUsageSummaryOut,
    DecisionMakerIn,
    EligibilityCheckIn,
    EligibilityCheckOut,
    EnrichIn,
    EnrichmentJobOut,
    ImportJobOut,
    ImportPreviewIn,
    ImportPreviewOut,
    ImportStartIn,
    LinkedInOutreachTaskIn,
    LinkedInOutreachTaskOut,
    ManualCompanyIn,
    ManualPersonIn,
    NormalizedCompanyOut,
    NormalizedPersonOut,
    ParseQueryIn,
    ParseQueryOut,
    PersonFiltersIn,
    PersonSearchIn,
    PersonSearchOut,
    ProvenanceOut,
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
    SuppressionEntryCreate,
    SuppressionEntryOut,
)
from app.sales.list_service import DuplicateListItemError, ListExportDisabledError
from app.sales.models import Contact
from app.sales.nl_filter_parser import parse_query
from app.sales.provider_models import (
    SalesEnrichmentJob,
    SalesImportJob,
    SalesList,
    SalesListItem,
    SalesProviderCreditUsage,
    SalesProviderRecord,
    SalesSavedSearch,
    SalesSuppressionEntry,
)
from app.sales.providers.credentials import get_active_apollo_connection
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
from app.sales.workflow_client import (
    EnrichmentStarter,
    ImportStarter,
    get_enrichment_starter,
    get_import_starter,
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
        db,
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
        db,
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
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> PersonSearchOut:
    response = await lead_finder_service.find_decision_makers(
        db,
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
        provider=(
            "apollo"
            if await is_apollo_configured(db, organization_id=context.organization_id)
            else "demo"
        ),
    )


@router.get("/providers", response_model=list[ProviderStatusOut])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> list[ProviderStatusOut]:
    """Per-organization provider status: "connected" means *this*
    organization has authorized its own Apollo workspace, never that the
    deployment holds a shared key (see
    docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md)."""
    results = []
    for key in list_provider_keys():
        provider = await get_provider(db, organization_id=context.organization_id, provider_key=key)
        caps = provider.capabilities()
        connection = (
            await get_active_apollo_connection(db, organization_id=context.organization_id)
            if key == "apollo"
            else None
        )
        results.append(
            ProviderStatusOut(
                provider_key=key,
                status=(
                    (await apollo_status(db, organization_id=context.organization_id)).value
                    if key == "apollo"
                    else "not_configured"
                ),
                capabilities=ProviderCapabilitiesOut(**caps.__dict__),
                configured=(
                    await is_apollo_configured(db, organization_id=context.organization_id)
                    if key == "apollo"
                    else False
                ),
                connection_id=connection.id if connection is not None else None,
                connected_user_email=connection.provider_user_email if connection else None,
                connected_workspace_name=(
                    connection.provider_workspace_name if connection else None
                ),
                granted_scopes=list(connection.scopes or []) if connection else [],
                can_manage_connection="integrations.apollo.manage" in context.permissions,
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


@router.get("/credit-usage", response_model=list[CreditUsageSummaryOut])
async def credit_usage_dashboard(
    provider: str | None = None,
    operation: str | None = None,
    user_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.providers.manage")),
) -> list[SalesProviderCreditUsage]:
    """Credit-usage dashboard: organization scope is the tenant-isolation
    boundary itself (never a selectable filter — a cross-org selector
    here would be a real tenant-isolation bug, not a feature), plus
    user/provider/operation/date filters and both estimated and actual
    (never fabricated — see app.sales.enrichment_job_service, actual is
    only ever recorded when a provider itself reports a real number)."""
    query = select(SalesProviderCreditUsage).where(
        SalesProviderCreditUsage.organization_id == context.organization_id
    )
    if provider:
        query = query.where(SalesProviderCreditUsage.provider == provider)
    if operation:
        query = query.where(SalesProviderCreditUsage.operation == operation)
    if user_id:
        query = query.where(SalesProviderCreditUsage.requested_by_user_id == user_id)
    if date_from:
        query = query.where(SalesProviderCreditUsage.created_at >= date_from)
    if date_to:
        query = query.where(SalesProviderCreditUsage.created_at <= date_to)
    rows = (
        await db.execute(query.order_by(SalesProviderCreditUsage.created_at.desc()).limit(min(limit, 500)))
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


# ---- Selective / bulk enrichment ----

_SYNC_ENRICHMENT_MAX_RECORDS = 5


@router.post("/enrich/estimate", response_model=CreditEstimatePreviewOut)
async def estimate_enrichment(
    payload: EnrichIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.enrich")),
) -> CreditEstimatePreviewOut:
    estimated = await enrichment_job_service.estimate_enrichment_credits(
        db,
        organization_id=context.organization_id,
        provider_key=payload.provider,
        operation=payload.operation,
        record_count=len(payload.record_ids),
    )
    # Names the customer's own Apollo workspace that will be charged, so
    # the confirmation dialog can never imply Agora Origin supplies the
    # credits (docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md §9).
    connection = await get_active_apollo_connection(db, organization_id=context.organization_id)
    return CreditEstimatePreviewOut(
        provider=payload.provider,
        operation=payload.operation,
        estimated_credits=estimated,
        record_count=len(payload.record_ids),
        connected_workspace_name=(
            connection.provider_workspace_name if connection is not None else None
        ),
        connected_user_email=(
            connection.provider_user_email if connection is not None else None
        ),
    )


@router.post("/enrich", response_model=EnrichmentJobOut, status_code=status.HTTP_201_CREATED)
async def enrich_selected(
    payload: EnrichIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.enrich")),
) -> SalesEnrichmentJob:
    """Synchronous path for small selections (≤5 records) — runs inline
    rather than round-tripping through Temporal for a sub-second job.
    Larger selections must use `/enrich/bulk`."""
    if len(payload.record_ids) > _SYNC_ENRICHMENT_MAX_RECORDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Use /enrich/bulk for more than {_SYNC_ENRICHMENT_MAX_RECORDS} records",
        )
    ip_address, user_agent = _client_meta(request)
    job = await enrichment_job_service.run_enrichment_job(
        db,
        organization_id=context.organization_id,
        provider_key=payload.provider,
        operation=payload.operation,
        requested_by_user_id=context.user.id,
        target_record_ids=payload.record_ids,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/enrich/bulk", response_model=EnrichmentJobOut, status_code=status.HTTP_201_CREATED)
async def enrich_selected_bulk(
    payload: EnrichIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.enrich")),
    start_enrichment: EnrichmentStarter = Depends(get_enrichment_starter),
) -> SalesEnrichmentJob:
    """Durable path via Temporal — the job row is created synchronously so
    `GET /enrichment-jobs/{id}` shows it as `running` immediately; the
    caller polls that endpoint for the running -> succeeded/partial/failed
    transition rather than waiting on this request."""
    ip_address, user_agent = _client_meta(request)
    job = await enrichment_job_service.create_enrichment_job(
        db,
        organization_id=context.organization_id,
        provider_key=payload.provider,
        operation=payload.operation,
        requested_by_user_id=context.user.id,
        target_record_ids=payload.record_ids,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    await db.refresh(job)
    await start_enrichment(job.id)
    return job


@router.get("/enrichment-jobs/{job_id}", response_model=EnrichmentJobOut)
async def get_enrichment_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.enrich")),
) -> SalesEnrichmentJob:
    job = await db.get(SalesEnrichmentJob, job_id)
    if job is None or job.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrichment job not found")
    return job


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
            db,
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
        db,
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


@router.get("/lists/{list_id}/items", response_model=list[SalesListItemOut])
async def get_list_items(
    list_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> list[SalesListItem]:
    await _get_org_list(db, list_id, context.organization_id)
    return await list_service.list_items(db, list_id=list_id)


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


@router.get("/lists/{list_id}/export")
async def export_list(
    list_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.lists.manage")),
) -> Response:
    sales_list = await _get_org_list(db, list_id, context.organization_id)
    ip_address, user_agent = _client_meta(request)
    try:
        csv_text, _row_count = await list_service.export_list_csv(
            db,
            sales_list=sales_list,
            actor_user_id=context.user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except ListExportDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    await db.commit()
    filename = f"{sales_list.name.replace(' ', '_')}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- Outreach eligibility and suppression ----


@router.post("/eligibility/check", response_model=EligibilityCheckOut)
async def check_eligibility(
    payload: EligibilityCheckIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> EligibilityCheckOut:
    """Preview surfaced before enrolling a contact into a Sequence/Campaign
    (spec §23's eligibility panel) — the *authoritative* block still
    happens at send time (`app.sales.service.send_outreach_message`,
    unchanged and already tested), so this is a real, honest preview of
    what will happen, not a separate gate that could drift from it."""
    contact: Contact | None = None
    if payload.contact_id is not None:
        contact = await db.get(Contact, payload.contact_id)
        if contact is None or contact.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

    provider_record: SalesProviderRecord | None = None
    if contact is None and payload.email:
        provider_record = (
            await db.execute(
                select(SalesProviderRecord).where(
                    SalesProviderRecord.organization_id == context.organization_id,
                    SalesProviderRecord.normalized_email == payload.email.lower(),
                )
            )
        ).scalars().first()
        if provider_record is None:
            # No saved record yet — construct a throwaway one just to carry
            # the email through the same evaluation path.
            provider_record = SalesProviderRecord(
                organization_id=context.organization_id,
                provider="unknown",
                record_type="person",
                provider_record_id="preview",
                normalized_email=payload.email.lower(),
                retrieved_at=datetime.now(UTC),
                verification_status="unverified",
            )

    eligibility = await evaluate_outreach_eligibility(
        db, organization_id=context.organization_id, contact=contact, provider_record=provider_record
    )
    return EligibilityCheckOut(status=eligibility.status, reasons=eligibility.reasons)


@router.get("/suppression", response_model=list[SuppressionEntryOut])
async def list_suppression(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.suppression.manage")),
) -> list[SalesSuppressionEntry]:
    return await suppression_service.list_suppression_entries(db, organization_id=context.organization_id)


@router.post("/suppression", response_model=SuppressionEntryOut, status_code=status.HTTP_201_CREATED)
async def add_suppression(
    payload: SuppressionEntryCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.suppression.manage")),
) -> SalesSuppressionEntry:
    ip_address, user_agent = _client_meta(request)
    try:
        entry = await suppression_service.add_suppression_entry(
            db,
            organization_id=context.organization_id,
            created_by_user_id=context.user.id,
            reason=payload.reason,
            email=payload.email,
            domain=payload.domain,
            contact_id=payload.contact_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/suppression/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def remove_suppression(
    entry_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.suppression.manage")),
) -> None:
    entry = await db.get(SalesSuppressionEntry, entry_id)
    if entry is None or entry.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suppression entry not found")
    ip_address, user_agent = _client_meta(request)
    await suppression_service.remove_suppression_entry(
        db, entry=entry, removed_by_user_id=context.user.id, ip_address=ip_address, user_agent=user_agent
    )
    await db.commit()


# ---- CSV import and manual entry ----

_SYNC_IMPORT_MAX_ROWS = 200


@router.post("/import/preview", response_model=ImportPreviewOut)
async def preview_import(
    payload: ImportPreviewIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.import")),
) -> ImportPreviewOut:
    file_record = await db.get(File, payload.file_id)
    if file_record is None or file_record.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    file_bytes = download_object(file_record.storage_key)
    preview = csv_import.parse_preview(file_bytes, record_type=payload.record_type)
    return ImportPreviewOut(
        headers=preview.headers,
        sample_rows=preview.sample_rows,
        suggested_mapping=preview.suggested_mapping,
        total_rows=preview.total_rows,
    )


@router.post("/import", response_model=ImportJobOut, status_code=status.HTTP_201_CREATED)
async def start_import(
    payload: ImportStartIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.import")),
    start_import_job: ImportStarter = Depends(get_import_starter),
) -> SalesImportJob:
    """Small files (<=200 rows) import synchronously so the response
    already reflects the final counts; larger files hand off to
    `SalesCsvImportWorkflow` and the caller polls `GET
    /import-jobs/{id}` for the running -> succeeded/partial/failed
    transition, the same split `/enrich` vs `/enrich/bulk` uses."""
    file_record = await db.get(File, payload.file_id)
    if file_record is None or file_record.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    ip_address, user_agent = _client_meta(request)
    file_bytes = download_object(file_record.storage_key)
    total_rows = len(csv_import.read_all_rows(file_bytes))

    job = await import_job_service.create_import_job(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        record_type=payload.record_type,
        file_id=file_record.id,
        column_mapping=payload.column_mapping,
        total_rows=total_rows,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    if total_rows <= _SYNC_IMPORT_MAX_ROWS:
        job = await import_job_service.execute_import_job(db, job=job)
        await db.commit()
        await db.refresh(job)
        return job

    await db.commit()
    await db.refresh(job)
    await start_import_job(job.id)
    return job


@router.get("/import-jobs/{job_id}", response_model=ImportJobOut)
async def get_import_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.import")),
) -> SalesImportJob:
    job = await db.get(SalesImportJob, job_id)
    if job is None or job.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    return job


@router.post("/manual/company", response_model=SaveCompanyOut, status_code=status.HTTP_201_CREATED)
async def manual_add_company(
    payload: ManualCompanyIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.import")),
) -> SaveCompanyOut:
    """Manually-entered records are source-classified the same way CSV
    imports are (`provider="manual"` -> `verification_status=
    "user_entered"`, see save_service) — never presented as
    provider-verified."""
    ip_address, user_agent = _client_meta(request)
    company = NormalizedCompany(
        provider="manual",
        provider_record_id=f"manual-{uuid.uuid4()}",
        name=payload.name,
        domain=payload.domain,
        website=payload.website,
        industry=payload.industry,
        locations=[payload.location] if payload.location else [],
        employee_count=payload.employee_count,
        employee_range=None,
        revenue_range=None,
        funding_stage=None,
        total_funding_usd=None,
        technologies=[],
        linkedin_url=None,
        source_url=None,
        retrieved_at=datetime.now(UTC),
        raw={},
    )
    account, created = await save_service.save_company_as_account(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        company=company,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return SaveCompanyOut(account_id=account.id, created=created)


@router.post("/manual/person", response_model=SavePersonOut, status_code=status.HTTP_201_CREATED)
async def manual_add_person(
    payload: ManualPersonIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.import")),
) -> SavePersonOut:
    ip_address, user_agent = _client_meta(request)
    person = NormalizedPerson(
        provider="manual",
        provider_record_id=f"manual-{uuid.uuid4()}",
        full_name=payload.full_name,
        title=payload.title,
        seniority=None,
        department=None,
        current_company_name=None,
        current_company_domain=payload.company_domain,
        location=payload.location,
        email=payload.email.lower() if payload.email else None,
        email_status="unverified" if payload.email else "unavailable",
        phone=payload.phone,
        phone_status="unverified" if payload.phone else "unavailable",
        linkedin_url=None,
        source_url=None,
        retrieved_at=datetime.now(UTC),
        raw={},
    )
    contact, created = await save_service.save_person_as_contact(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        person=person,
        account_id=payload.account_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return SavePersonOut(contact_id=contact.id, created=created)


# ---- Provenance ----


@router.get("/provenance/account/{account_id}", response_model=ProvenanceOut)
async def get_account_provenance(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> SalesProviderRecord:
    """How a saved Account was originally found — provider, source URL,
    when it was retrieved/last verified, and whether it's provider-
    verified, user-entered, or still unverified (spec: provenance must be
    visible, never fabricated)."""
    record = (
        await db.execute(
            select(SalesProviderRecord).where(
                SalesProviderRecord.organization_id == context.organization_id,
                SalesProviderRecord.linked_account_id == account_id,
            )
        )
    ).scalars().first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Lead Finder provenance for this account (it wasn't created via search/import/manual entry).",
        )
    return record


@router.get("/provenance/contact/{contact_id}", response_model=ProvenanceOut)
async def get_contact_provenance(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.lead_finder.view")),
) -> SalesProviderRecord:
    record = (
        await db.execute(
            select(SalesProviderRecord).where(
                SalesProviderRecord.organization_id == context.organization_id,
                SalesProviderRecord.linked_contact_id == contact_id,
            )
        )
    ).scalars().first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Lead Finder provenance for this contact (it wasn't created via search/import/manual entry).",
        )
    return record


# ---- Manual LinkedIn outreach (no scraping, no automation — see
# app.sales.linkedin_task_service) ----


@router.post(
    "/contacts/{contact_id}/linkedin-task",
    response_model=LinkedInOutreachTaskOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_linkedin_outreach_task(
    contact_id: uuid.UUID,
    payload: LinkedInOutreachTaskIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("sales.accounts.manage")),
) -> LinkedInOutreachTaskOut:
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    if payload.linkedin_url and not linkedin_task_service.is_plausible_linkedin_url(payload.linkedin_url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="linkedin_url must be a linkedin.com profile URL",
        )
    ip_address, user_agent = _client_meta(request)
    task = await linkedin_task_service.create_linkedin_outreach_task(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        contact=contact,
        linkedin_url=payload.linkedin_url,
        message=payload.message,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return LinkedInOutreachTaskOut(task_id=task.id, linkedin_url=contact.linkedin_url)
