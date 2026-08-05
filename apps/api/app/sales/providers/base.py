"""Provider-neutral Sales data-provider Protocol (see
docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §1). Mirrors the
`ModelAdapter`/`DemoAdapter` shape in `app.ai.gateway` and the
`OAuthConnectorAdapter` shape in `app.integrations.adapters.base` — a
`Protocol` every real provider implements, plus a Demo adapter that is
never presented to end users as a live result. This is a **sibling** of
`OAuthConnectorAdapter`, not a reuse of it: the capability surface here is
search/enrich, not an OAuth token lifecycle plus generic CRM-object sync.
"""

from __future__ import annotations

from typing import Any, Protocol

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


class SalesDataProvider(Protocol):
    provider_key: str

    def capabilities(self) -> ProviderCapabilities: ...

    async def health(self) -> ProviderHealth: ...

    async def search_companies(self, request: CompanySearchRequest) -> CompanySearchResponse: ...

    async def search_people(self, request: PersonSearchRequest) -> PersonSearchResponse: ...

    async def enrich_company(self, request: CompanyEnrichRequest) -> CompanyEnrichResponse: ...

    async def enrich_person(self, request: PersonEnrichRequest) -> PersonEnrichResponse: ...

    async def find_decision_makers(self, request: DecisionMakerRequest) -> PersonSearchResponse: ...

    async def estimate_credit_usage(self, request: CreditEstimateRequest) -> CreditEstimate: ...

    def normalize_company(self, raw: dict[str, Any]) -> NormalizedCompany: ...

    def normalize_person(self, raw: dict[str, Any]) -> NormalizedPerson: ...
