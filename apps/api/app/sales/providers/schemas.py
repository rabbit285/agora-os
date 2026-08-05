"""Typed, versioned request/response schemas for the Sales Lead Finder's
provider-neutral discovery/enrichment layer (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §2). `schema_version` guards
against a future breaking provider-schema change silently corrupting
anything cached or persisted from an older shape.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

SCHEMA_VERSION = 1


@dataclass
class SortSpec:
    field: str
    direction: Literal["asc", "desc"] = "asc"


@dataclass
class CompanyFilters:
    name: str | None = None
    domain: str | None = None
    locations: list[str] = field(default_factory=list)
    min_employee_count: int | None = None
    max_employee_count: int | None = None
    industries: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    min_revenue: int | None = None
    max_revenue: int | None = None
    funding_stages: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)


@dataclass
class PersonFilters:
    name: str | None = None
    current_company_domain: str | None = None
    titles: list[str] = field(default_factory=list)
    title_keywords: list[str] = field(default_factory=list)
    seniorities: list[str] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    require_verified_email: bool = False


@dataclass
class CompanySearchRequest:
    organization_id: uuid.UUID
    filters: CompanyFilters
    page: int = 1
    page_size: int = 25
    sort: SortSpec | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass
class PersonSearchRequest:
    organization_id: uuid.UUID
    filters: PersonFilters
    page: int = 1
    page_size: int = 25
    sort: SortSpec | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass
class DecisionMakerRequest:
    organization_id: uuid.UUID
    company_domain: str
    seniorities: list[str] = field(
        default_factory=lambda: ["owner", "founder", "c_suite", "vp", "director"]
    )
    page_size: int = 10
    schema_version: int = SCHEMA_VERSION


@dataclass
class NormalizedCompany:
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
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedPerson:
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
    email_status: Literal["verified", "unverified", "catch_all", "unavailable"]
    phone: str | None
    phone_status: Literal["verified", "unverified", "unavailable"]
    linkedin_url: str | None
    source_url: str | None
    retrieved_at: datetime
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompanySearchResponse:
    provider: str
    companies: list[NormalizedCompany]
    total_available: int | None
    page: int
    page_size: int
    credits_used: int | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass
class PersonSearchResponse:
    provider: str
    people: list[NormalizedPerson]
    total_available: int | None
    page: int
    page_size: int
    credits_used: int | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass
class CompanyEnrichRequest:
    organization_id: uuid.UUID
    domain: str | None = None
    provider_record_id: str | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass
class CompanyEnrichResponse:
    provider: str
    company: NormalizedCompany | None
    credits_used: int | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass
class PersonEnrichRequest:
    organization_id: uuid.UUID
    email: str | None = None
    provider_record_id: str | None = None
    full_name: str | None = None
    company_domain: str | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass
class PersonEnrichResponse:
    provider: str
    person: NormalizedPerson | None
    credits_used: int | None = None
    schema_version: int = SCHEMA_VERSION


@dataclass
class CreditEstimateRequest:
    operation: Literal[
        "search_companies", "search_people", "enrich_company", "enrich_person", "find_decision_makers"
    ]
    record_count: int
    schema_version: int = SCHEMA_VERSION


@dataclass
class CreditEstimate:
    provider: str
    operation: str
    estimated_credits: int
    is_estimate: bool = True


@dataclass
class ProviderCapabilities:
    company_search: bool
    people_search: bool
    company_enrichment: bool
    person_enrichment: bool
    decision_makers: bool
    credit_estimation: bool


@dataclass
class ProviderHealth:
    status: Literal["healthy", "degraded", "rate_limited", "failed"]
    detail: str
    retry_after_seconds: int | None = None
