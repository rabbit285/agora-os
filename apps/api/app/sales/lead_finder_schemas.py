"""Pydantic request/response schemas for `/api/v1/sales/lead-finder/*`
(see app.routers.sales_lead_finder). Separate from the dataclass-based
provider-layer schemas in `app.sales.providers.schemas` — these are the
HTTP contract; the provider layer's dataclasses are the internal,
provider-neutral shape those HTTP schemas convert to/from."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.sales.providers.schemas import NormalizedCompany, NormalizedPerson


class SortSpecIn(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class CompanyFiltersIn(BaseModel):
    name: str | None = None
    domain: str | None = None
    locations: list[str] = Field(default_factory=list)
    min_employee_count: int | None = None
    max_employee_count: int | None = None
    industries: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    min_revenue: int | None = None
    max_revenue: int | None = None
    funding_stages: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)


class PersonFiltersIn(BaseModel):
    name: str | None = None
    current_company_domain: str | None = None
    titles: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(default_factory=list)
    seniorities: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    require_verified_email: bool = False


class CompanySearchIn(BaseModel):
    filters: CompanyFiltersIn
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)
    sort: SortSpecIn | None = None
    provider: str = "apollo"
    refresh: bool = False


class PersonSearchIn(BaseModel):
    filters: PersonFiltersIn
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)
    sort: SortSpecIn | None = None
    provider: str = "apollo"
    refresh: bool = False


class DecisionMakerIn(BaseModel):
    company_domain: str
    provider: str = "apollo"


class NormalizedCompanyOut(BaseModel):
    provider: str
    provider_record_id: str
    name: str
    domain: str | None
    website: str | None
    industry: str | None
    locations: list[str]
    employee_count: int | None
    employee_range: str | None
    revenue_range: str | None
    funding_stage: str | None
    total_funding_usd: int | None
    technologies: list[str]
    linkedin_url: str | None
    source_url: str | None
    retrieved_at: datetime
    dedupe_status: Literal["new", "existing"] = "new"
    existing_account_id: uuid.UUID | None = None

    @classmethod
    def from_normalized(
        cls, company: NormalizedCompany, dedupe: dict[str, Any] | None = None
    ) -> NormalizedCompanyOut:
        dedupe = dedupe or {"status": "new", "existing_account_id": None}
        return cls(
            provider=company.provider,
            provider_record_id=company.provider_record_id,
            name=company.name,
            domain=company.domain,
            website=company.website,
            industry=company.industry,
            locations=company.locations,
            employee_count=company.employee_count,
            employee_range=company.employee_range,
            revenue_range=company.revenue_range,
            funding_stage=company.funding_stage,
            total_funding_usd=company.total_funding_usd,
            technologies=company.technologies,
            linkedin_url=company.linkedin_url,
            source_url=company.source_url,
            retrieved_at=company.retrieved_at,
            dedupe_status=dedupe["status"],
            existing_account_id=dedupe.get("existing_account_id"),
        )


class NormalizedPersonOut(BaseModel):
    provider: str
    provider_record_id: str
    full_name: str
    title: str | None
    seniority: str | None
    department: str | None
    current_company_name: str | None
    current_company_domain: str | None
    location: str | None
    email: str | None
    email_status: str
    phone: str | None
    phone_status: str
    linkedin_url: str | None
    source_url: str | None
    retrieved_at: datetime
    dedupe_status: Literal["new", "existing"] = "new"
    existing_contact_id: uuid.UUID | None = None

    @classmethod
    def from_normalized(
        cls, person: NormalizedPerson, dedupe: dict[str, Any] | None = None
    ) -> NormalizedPersonOut:
        dedupe = dedupe or {"status": "new", "existing_contact_id": None}
        return cls(
            provider=person.provider,
            provider_record_id=person.provider_record_id,
            full_name=person.full_name,
            title=person.title,
            seniority=person.seniority,
            department=person.department,
            current_company_name=person.current_company_name,
            current_company_domain=person.current_company_domain,
            location=person.location,
            email=person.email,
            email_status=person.email_status,
            phone=person.phone,
            phone_status=person.phone_status,
            linkedin_url=person.linkedin_url,
            source_url=person.source_url,
            retrieved_at=person.retrieved_at,
            dedupe_status=dedupe["status"],
            existing_contact_id=dedupe.get("existing_contact_id"),
        )


class CompanySearchOut(BaseModel):
    provider: str
    companies: list[NormalizedCompanyOut]
    total_available: int | None
    page: int
    page_size: int
    credits_used: int | None


class PersonSearchOut(BaseModel):
    provider: str
    people: list[NormalizedPersonOut]
    total_available: int | None
    page: int
    page_size: int
    credits_used: int | None


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    search_type: Literal["company", "person"]
    filters: dict[str, Any]
    provider: str = "apollo"
    columns: list[str] = Field(default_factory=list)
    sort: dict[str, Any] | None = None
    density: Literal["comfortable", "compact"] = "comfortable"
    is_shared: bool = False


class SavedSearchUpdate(BaseModel):
    name: str | None = None
    filters: dict[str, Any] | None = None
    columns: list[str] | None = None
    sort: dict[str, Any] | None = None
    density: Literal["comfortable", "compact"] | None = None
    is_shared: bool | None = None


class SavedSearchOut(BaseModel):
    id: uuid.UUID
    name: str
    search_type: str
    filters: dict[str, Any]
    provider: str
    columns: list[str]
    sort: dict[str, Any] | None
    density: str
    is_shared: bool
    owner_user_id: uuid.UUID
    last_executed_at: datetime | None
    last_result_count: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SalesListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    list_type: Literal["company", "person"]
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_shared: bool = False


class SalesListOut(BaseModel):
    id: uuid.UUID
    name: str
    list_type: str
    description: str | None
    tags: list[str]
    is_shared: bool
    owner_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SalesListItemCreate(BaseModel):
    account_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None


class SalesListItemOut(BaseModel):
    id: uuid.UUID
    list_id: uuid.UUID
    account_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    added_by_user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ProviderCapabilitiesOut(BaseModel):
    company_search: bool
    people_search: bool
    company_enrichment: bool
    person_enrichment: bool
    decision_makers: bool
    credit_estimation: bool


class ProviderStatusOut(BaseModel):
    provider_key: str
    status: str
    capabilities: ProviderCapabilitiesOut
    configured: bool


class CreditUsageSummaryOut(BaseModel):
    provider: str
    operation: str
    estimated_credits: int
    actual_credits: int | None
    succeeded: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SuppressionEntryCreate(BaseModel):
    email: str | None = None
    domain: str | None = None
    contact_id: uuid.UUID | None = None
    reason: str = Field(min_length=1, max_length=500)


class SuppressionEntryOut(BaseModel):
    id: uuid.UUID
    email: str | None
    domain: str | None
    contact_id: uuid.UUID | None
    reason: str
    created_by_user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class EligibilityCheckIn(BaseModel):
    contact_id: uuid.UUID | None = None
    email: str | None = None


class EligibilityCheckOut(BaseModel):
    status: Literal["eligible", "requires_review", "blocked", "unknown"]
    reasons: list[str]


class ParseQueryIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


class ParseQueryOut(BaseModel):
    company_filters: CompanyFiltersIn
    person_filters: PersonFiltersIn
    unsupported_criteria: list[str]
    provider: str


class EnrichIn(BaseModel):
    operation: Literal["enrich_company", "enrich_person"]
    record_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    provider: str = "apollo"


class EnrichmentJobOut(BaseModel):
    id: uuid.UUID
    provider: str
    operation: str
    status: str
    estimated_credits: int
    actual_credits: int | None
    succeeded_count: int
    failed_count: int
    error_records: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreditEstimatePreviewOut(BaseModel):
    provider: str
    operation: str
    estimated_credits: int
    record_count: int


class SaveCompanyOut(BaseModel):
    account_id: uuid.UUID
    created: bool


class SavePersonOut(BaseModel):
    contact_id: uuid.UUID
    created: bool
