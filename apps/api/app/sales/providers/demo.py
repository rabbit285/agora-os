"""Deterministic demo Sales data provider — the automatic fallback
whenever `APOLLO_API_KEY` is unset (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §4), the same "unset key ->
clearly-labeled demo output" behavior `app.ai.gateway.DemoAdapter` already
has for AI features. Every record's `provider` is the literal string
"demo"; the frontend renders a "Demo data" badge whenever it sees that
value, mirroring how `/copilot` already does this.

Not a per-organization toggle — there is no organization-level "demo
mode" concept anywhere else in this codebase (AI providers, Clearbit
enrichment, and every OAuth integration all fall back to a demo/mock
adapter purely on missing credentials), so this doesn't invent one.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from app.sales.providers.schemas import (
    CompanyEnrichRequest,
    CompanyEnrichResponse,
    CompanySearchRequest,
    CompanySearchResponse,
    CreditEstimate,
    CreditEstimateRequest,
    DecisionMakerRequest,
    NormalizedCompany,
    NormalizedPerson,
    PersonEnrichRequest,
    PersonEnrichResponse,
    PersonSearchRequest,
    PersonSearchResponse,
    ProviderCapabilities,
    ProviderHealth,
)

# Deliberately fictional — no real company or person names, `.invalid`
# email domains (reserved by RFC 2606, guaranteed never to resolve).
_DEMO_COMPANIES: list[dict[str, Any]] = [
    {
        "id": "demo-co-1",
        "name": "Northwind Robotics (Demo)",
        "domain": "northwind-robotics.demo.invalid",
        "industry": "Industrial Automation",
        "locations": ["Berlin, Germany"],
        "employee_count": 85,
        "employee_range": "51-200",
        "revenue_range": "$10M-$25M",
        "funding_stage": "Series B",
        "total_funding_usd": 18_000_000,
        "technologies": ["AWS", "Salesforce", "Python"],
    },
    {
        "id": "demo-co-2",
        "name": "Fjordline Analytics (Demo)",
        "domain": "fjordline-analytics.demo.invalid",
        "industry": "B2B SaaS",
        "locations": ["Stockholm, Sweden"],
        "employee_count": 42,
        "employee_range": "11-50",
        "revenue_range": "$1M-$10M",
        "funding_stage": "Seed",
        "total_funding_usd": 3_500_000,
        "technologies": ["GCP", "HubSpot"],
    },
    {
        "id": "demo-co-3",
        "name": "Cobalt Compliance Group (Demo)",
        "domain": "cobalt-compliance.demo.invalid",
        "industry": "Compliance Software",
        "locations": ["Amsterdam, Netherlands"],
        "employee_count": 160,
        "employee_range": "51-200",
        "revenue_range": "$25M-$50M",
        "funding_stage": "Series C",
        "total_funding_usd": 42_000_000,
        "technologies": ["Azure", "Workday"],
    },
    {
        "id": "demo-co-4",
        "name": "Redwing Logistics (Demo)",
        "domain": "redwing-logistics.demo.invalid",
        "industry": "Logistics",
        "locations": ["Lyon, France"],
        "employee_count": 12,
        "employee_range": "1-10",
        "revenue_range": None,
        "funding_stage": None,
        "total_funding_usd": None,
        "technologies": [],
    },
]

_DEMO_PEOPLE: list[dict[str, Any]] = [
    {
        "id": "demo-person-1",
        "full_name": "Elena Marsh (Demo)",
        "title": "Chief Executive Officer",
        "seniority": "c_suite",
        "department": "Executive",
        "company_domain": "northwind-robotics.demo.invalid",
        "company_name": "Northwind Robotics (Demo)",
        "location": "Berlin, Germany",
        "email": "elena.marsh@northwind-robotics.demo.invalid",
        "email_status": "unverified",
        "phone": None,
        "linkedin_url": "https://www.linkedin.com/in/example-demo-profile-1",
    },
    {
        "id": "demo-person-2",
        "full_name": "Jonas Berg (Demo)",
        "title": "VP of Engineering",
        "seniority": "vp",
        "department": "Engineering",
        "company_domain": "fjordline-analytics.demo.invalid",
        "company_name": "Fjordline Analytics (Demo)",
        "location": "Stockholm, Sweden",
        "email": None,
        "email_status": "unavailable",
        "phone": None,
        "linkedin_url": "https://www.linkedin.com/in/example-demo-profile-2",
    },
    {
        "id": "demo-person-3",
        "full_name": "Priya Chandra (Demo)",
        "title": "Head of Compliance",
        "seniority": "director",
        "department": "Legal & Compliance",
        "company_domain": "cobalt-compliance.demo.invalid",
        "company_name": "Cobalt Compliance Group (Demo)",
        "location": "Amsterdam, Netherlands",
        "email": "priya.chandra@cobalt-compliance.demo.invalid",
        "email_status": "unverified",
        "phone": None,
        "linkedin_url": None,
    },
]

def _matches_company(company: dict[str, Any], request: CompanySearchRequest) -> bool:
    filters = request.filters
    employee_count = company["employee_count"] or 0
    checks = [
        not filters.min_employee_count or employee_count >= filters.min_employee_count,
        not filters.max_employee_count or employee_count <= filters.max_employee_count,
        not filters.industries or company["industry"] in filters.industries,
        not filters.name or filters.name.lower() in company["name"].lower(),
    ]
    return all(checks)


def _matches_person(person: dict[str, Any], request: PersonSearchRequest) -> bool:
    filters = request.filters
    checks = [
        not filters.current_company_domain
        or person["company_domain"] == filters.current_company_domain,
        not filters.seniorities or person["seniority"] in filters.seniorities,
        not filters.title_keywords
        or any(k.lower() in (person["title"] or "").lower() for k in filters.title_keywords),
    ]
    return all(checks)


class DemoSalesDataProvider:
    provider_key = "demo"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            company_search=True,
            people_search=True,
            company_enrichment=True,
            person_enrichment=True,
            decision_makers=True,
            credit_estimation=True,
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(status="healthy", detail="Demo data — no provider configured")

    def normalize_company(self, raw: dict[str, Any]) -> NormalizedCompany:
        return NormalizedCompany(
            provider=self.provider_key,
            provider_record_id=raw["id"],
            name=raw["name"],
            domain=raw["domain"],
            website=f"https://{raw['domain']}",
            industry=raw["industry"],
            locations=raw["locations"],
            employee_count=raw["employee_count"],
            employee_range=raw["employee_range"],
            revenue_range=raw["revenue_range"],
            funding_stage=raw["funding_stage"],
            total_funding_usd=raw["total_funding_usd"],
            technologies=raw["technologies"],
            linkedin_url=None,
            source_url=None,
            retrieved_at=datetime.now(UTC),
            raw=raw,
        )

    def normalize_person(self, raw: dict[str, Any]) -> NormalizedPerson:
        return NormalizedPerson(
            provider=self.provider_key,
            provider_record_id=raw["id"],
            full_name=raw["full_name"],
            title=raw["title"],
            seniority=raw["seniority"],
            department=raw["department"],
            current_company_name=raw["company_name"],
            current_company_domain=raw["company_domain"],
            location=raw["location"],
            email=raw["email"],
            email_status=raw["email_status"],
            phone=raw["phone"],
            phone_status="unavailable",
            linkedin_url=raw["linkedin_url"],
            source_url=None,
            retrieved_at=datetime.now(UTC),
            raw=raw,
        )

    async def search_companies(self, request: CompanySearchRequest) -> CompanySearchResponse:
        matches = [c for c in _DEMO_COMPANIES if _matches_company(c, request)]
        start = (request.page - 1) * request.page_size
        page_rows = matches[start : start + request.page_size]
        return CompanySearchResponse(
            provider=self.provider_key,
            companies=[self.normalize_company(c) for c in page_rows],
            total_available=len(matches),
            page=request.page,
            page_size=request.page_size,
            credits_used=0,
        )

    async def search_people(self, request: PersonSearchRequest) -> PersonSearchResponse:
        matches = [p for p in _DEMO_PEOPLE if _matches_person(p, request)]
        start = (request.page - 1) * request.page_size
        page_rows = matches[start : start + request.page_size]
        return PersonSearchResponse(
            provider=self.provider_key,
            people=[self.normalize_person(p) for p in page_rows],
            total_available=len(matches),
            page=request.page,
            page_size=request.page_size,
            credits_used=0,
        )

    async def find_decision_makers(self, request: DecisionMakerRequest) -> PersonSearchResponse:
        matches = [
            p
            for p in _DEMO_PEOPLE
            if p["company_domain"] == request.company_domain and p["seniority"] in request.seniorities
        ]
        return PersonSearchResponse(
            provider=self.provider_key,
            people=[self.normalize_person(p) for p in matches[: request.page_size]],
            total_available=len(matches),
            page=1,
            page_size=request.page_size,
            credits_used=0,
        )

    async def enrich_company(self, request: CompanyEnrichRequest) -> CompanyEnrichResponse:
        found = next(
            (
                c
                for c in _DEMO_COMPANIES
                if c["domain"] == request.domain or c["id"] == request.provider_record_id
            ),
            None,
        )
        return CompanyEnrichResponse(
            provider=self.provider_key,
            company=self.normalize_company(found) if found else None,
            credits_used=0,
        )

    async def enrich_person(self, request: PersonEnrichRequest) -> PersonEnrichResponse:
        found = next(
            (
                p
                for p in _DEMO_PEOPLE
                if p["email"] == request.email or p["id"] == request.provider_record_id
            ),
            None,
        )
        return PersonEnrichResponse(
            provider=self.provider_key,
            person=self.normalize_person(found) if found else None,
            credits_used=0,
        )

    async def estimate_credit_usage(self, request: CreditEstimateRequest) -> CreditEstimate:
        # Demo data never spends a real credit, regardless of operation.
        return CreditEstimate(
            provider=self.provider_key,
            operation=request.operation,
            estimated_credits=0,
            is_estimate=True,
        )


def _stable_hash(*parts: str) -> str:
    """Not used for record selection (the demo catalog is small and
    filtered directly) — kept for parity with other Demo adapters in this
    codebase that key deterministic output off a request hash, and
    available to tests that want a stable reference id."""
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:8]
