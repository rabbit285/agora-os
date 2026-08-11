"""Real Apollo.io adapter (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §3
and docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md).

**Customer-connected**: this adapter holds no credential of its own. It is
constructed with a `credential_resolver` bound to one organization and asks
it for that customer's Apollo access token immediately before each call, so
every search and enrichment runs against the customer's own Apollo account,
permissions, rate limits, and credits — never a shared platform key.

Requests authenticate with `Authorization: Bearer <customer_access_token>`.
The legacy `x-api-key` header is used only in the isolated
`APOLLO_AUTH_MODE=api_key` development/test mode, which the startup guard in
`app.config` refuses to run in production.

Apollo has no single "decision makers" endpoint — `find_decision_makers`
is an honest, documented composition of `search_people` scoped to a
company domain with a seniority filter, not a fabricated capability (see
architecture doc §3's endpoint-mapping table).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.config import settings
from app.sales.providers.credentials import ApolloCredential
from app.sales.providers.exceptions import (
    ProviderAuthError,
    ProviderInvalidRequest,
    ProviderRateLimited,
    ProviderUnavailable,
)
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

REQUEST_TIMEOUT_SECONDS = 20.0


class ApolloCredentialResolver(Protocol):
    """The organization-bound credential source this adapter reads from —
    `app.sales.providers.credentials.OrganizationApolloCredentialResolver`
    in production. A Protocol so tests can supply a stub without a database
    or a real connection row."""

    async def resolve(self, *, capability: str) -> ApolloCredential: ...

    async def record_success(self) -> None: ...

    async def refresh_after_unauthorized(self) -> ApolloCredential | None: ...

    async def mark_reauthorization_required(self, *, detail: str) -> None: ...

# Apollo's own per-call credit cost varies by record type/enrichment depth
# and is only authoritative in Apollo's own response. These are
# conservative, documented per-record constants used only to show a
# labeled *estimate* before the call — never presented as a guarantee
# (spec: "never fabricate credit values when the provider does not expose
# them").
ESTIMATED_CREDITS_PER_COMPANY = 1
ESTIMATED_CREDITS_PER_PERSON = 1
ESTIMATED_CREDITS_PER_ENRICHMENT = 1


def _domain(website: str | None) -> str | None:
    if not website:
        return None
    return (
        website.replace("https://", "")
        .replace("http://", "")
        .split("/")[0]
        .removeprefix("www.")
        or None
    )


class ApolloDataProvider:
    provider_key = "apollo"

    def __init__(self, *, credential_resolver: ApolloCredentialResolver) -> None:
        self._credentials = credential_resolver

    @staticmethod
    def _headers(credential: ApolloCredential) -> dict[str, str]:
        if credential.is_legacy_api_key:
            # Development/test only (APOLLO_AUTH_MODE=api_key). Production
            # is Bearer-only — see app.config's startup guard.
            return {"x-api-key": credential.access_token, "Content-Type": "application/json"}
        return {
            "Authorization": f"Bearer {credential.access_token}",
            "Content-Type": "application/json",
        }

    async def _send(
        self, path: str, body: dict[str, Any], credential: ApolloCredential
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            try:
                return await client.post(
                    f"{settings.apollo_api_base_url}{path}",
                    json=body,
                    headers=self._headers(credential),
                )
            except httpx.TimeoutException as exc:
                raise ProviderUnavailable(f"Apollo request to {path} timed out") from exc
            except httpx.RequestError as exc:
                raise ProviderUnavailable(f"Apollo request to {path} failed: {exc}") from exc

    async def _post(self, path: str, body: dict[str, Any], *, capability: str) -> dict[str, Any]:
        credential = await self._credentials.resolve(capability=capability)
        response = await self._send(path, body, credential)

        # Exactly one refresh-and-retry on 401 (architecture §10): an
        # access token can expire between the freshness check and the call.
        # A second 401 means the grant itself is no longer usable, so the
        # connection is marked as needing reauthorization rather than
        # retried again.
        if response.status_code == 401 and not credential.is_legacy_api_key:
            refreshed = await self._credentials.refresh_after_unauthorized()
            if refreshed is None:
                await self._credentials.mark_reauthorization_required(
                    detail="Apollo rejected the stored credential and it could not be refreshed"
                )
                raise ProviderAuthError(
                    "Apollo rejected the stored credential (HTTP 401)", status_code=401
                )
            response = await self._send(path, body, refreshed)
            if response.status_code == 401:
                await self._credentials.mark_reauthorization_required(
                    detail="Apollo rejected the refreshed credential"
                )
                raise ProviderAuthError(
                    "Apollo rejected the stored credential (HTTP 401)", status_code=401
                )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise ProviderRateLimited(
                "Apollo rate limit exceeded",
                retry_after_seconds=int(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"Apollo rejected the request (HTTP {response.status_code})",
                status_code=response.status_code,
            )
        if response.status_code == 422:
            raise ProviderInvalidRequest(f"Apollo rejected the request as invalid (HTTP 422) for {path}")
        if response.status_code >= 500:
            raise ProviderUnavailable(f"Apollo returned HTTP {response.status_code}")
        if response.status_code >= 400:
            # Any other 4xx this adapter doesn't specifically interpret —
            # still routed through the same normalized-error path instead
            # of falling through to a raw, unmapped httpx.HTTPStatusError
            # (see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §3: callers
            # must only ever see SalesProviderError subclasses).
            raise ProviderUnavailable(f"Apollo returned HTTP {response.status_code} for {path}")

        await self._credentials.record_success()
        result: dict[str, Any] = response.json()
        return result

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
        # Apollo has no dedicated zero-cost health endpoint. This build
        # uses a minimal `search_people` call (page_size=1, no filters) —
        # documented here rather than hidden — as the least-cost real call
        # that proves the credential is valid and the API is reachable.
        try:
            await self._post(
                "/mixed_people/search", {"page": 1, "per_page": 1}, capability="search_people"
            )
        except ProviderRateLimited as exc:
            return ProviderHealth(
                status="rate_limited",
                detail="Apollo rate limit reached",
                retry_after_seconds=exc.retry_after_seconds,
            )
        except ProviderAuthError as exc:
            return ProviderHealth(status="failed", detail=str(exc))
        except ProviderUnavailable as exc:
            return ProviderHealth(status="degraded", detail=str(exc))
        return ProviderHealth(status="healthy", detail="Connected")

    def normalize_company(self, raw: dict[str, Any]) -> NormalizedCompany:
        return NormalizedCompany(
            provider=self.provider_key,
            provider_record_id=str(raw.get("id", "")),
            name=raw.get("name") or "",
            domain=raw.get("primary_domain") or _domain(raw.get("website_url")),
            website=raw.get("website_url"),
            industry=raw.get("industry"),
            locations=[loc for loc in [raw.get("city"), raw.get("state"), raw.get("country")] if loc],
            employee_count=raw.get("estimated_num_employees"),
            employee_range=None,
            revenue_range=None,
            funding_stage=None,
            total_funding_usd=raw.get("total_funding"),
            technologies=raw.get("technology_names") or raw.get("technologies") or [],
            linkedin_url=raw.get("linkedin_url"),
            source_url=raw.get("linkedin_url") or raw.get("website_url"),
            retrieved_at=datetime.now(UTC),
            raw=raw,
        )

    def normalize_person(self, raw: dict[str, Any]) -> NormalizedPerson:
        org = raw.get("organization") or {}
        email = raw.get("email")
        # Apollo returns a locked placeholder like "email_not_unlocked@domain.com"
        # for people search results that haven't been enriched yet — never
        # treat that as a real, deliverable email address.
        email_status: str
        if not email:
            email_status = "unavailable"
        elif "email_not_unlocked" in email or "not_unlocked" in email:
            email = None
            email_status = "unavailable"
        else:
            email_status = "verified" if raw.get("email_status") == "verified" else "unverified"
        return NormalizedPerson(
            provider=self.provider_key,
            provider_record_id=str(raw.get("id", "")),
            full_name=raw.get("name") or f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip(),
            title=raw.get("title"),
            seniority=raw.get("seniority"),
            department=(raw.get("departments") or [None])[0],
            current_company_name=org.get("name"),
            current_company_domain=org.get("primary_domain") or _domain(org.get("website_url")),
            location=", ".join(loc for loc in [raw.get("city"), raw.get("state"), raw.get("country")] if loc)
            or None,
            email=email,
            email_status=email_status,  # type: ignore[arg-type]
            phone=raw.get("sanitized_phone") or raw.get("phone_number"),
            phone_status="unverified" if (raw.get("sanitized_phone") or raw.get("phone_number")) else "unavailable",
            linkedin_url=raw.get("linkedin_url"),
            source_url=raw.get("linkedin_url"),
            retrieved_at=datetime.now(UTC),
            raw=raw,
        )

    async def search_companies(self, request: CompanySearchRequest) -> CompanySearchResponse:
        filters = request.filters
        body: dict[str, Any] = {"page": request.page, "per_page": request.page_size}
        if filters.domain:
            body["q_organization_domains"] = filters.domain
        if filters.name:
            body["q_organization_name"] = filters.name
        if filters.locations:
            body["organization_locations"] = filters.locations
        if filters.min_employee_count or filters.max_employee_count:
            lo = filters.min_employee_count or 0
            hi = filters.max_employee_count or 1_000_000
            body["organization_num_employees_ranges"] = [f"{lo},{hi}"]
        if filters.keywords:
            body["q_keywords"] = " ".join(filters.keywords)
        if filters.technologies:
            body["technologies"] = filters.technologies

        payload = await self._post(
            "/mixed_companies/search", body, capability="search_companies"
        )
        organizations = payload.get("organizations", [])
        pagination = payload.get("pagination", {})
        return CompanySearchResponse(
            provider=self.provider_key,
            companies=[self.normalize_company(o) for o in organizations],
            total_available=pagination.get("total_entries"),
            page=request.page,
            page_size=request.page_size,
            credits_used=payload.get("credits_consumed"),
        )

    async def search_people(self, request: PersonSearchRequest) -> PersonSearchResponse:
        filters = request.filters
        body: dict[str, Any] = {"page": request.page, "per_page": request.page_size}
        if filters.current_company_domain:
            body["q_organization_domains"] = filters.current_company_domain
        if filters.titles:
            body["person_titles"] = filters.titles
        if filters.title_keywords:
            body["q_keywords"] = " ".join(filters.title_keywords)
        if filters.seniorities:
            body["person_seniorities"] = filters.seniorities
        if filters.departments:
            body["person_departments"] = filters.departments
        if filters.locations:
            body["person_locations"] = filters.locations

        payload = await self._post("/mixed_people/search", body, capability="search_people")
        people = payload.get("people", [])
        if filters.require_verified_email:
            people = [p for p in people if p.get("email_status") == "verified"]
        pagination = payload.get("pagination", {})
        return PersonSearchResponse(
            provider=self.provider_key,
            people=[self.normalize_person(p) for p in people],
            total_available=pagination.get("total_entries"),
            page=request.page,
            page_size=request.page_size,
            credits_used=payload.get("credits_consumed"),
        )

    async def find_decision_makers(self, request: DecisionMakerRequest) -> PersonSearchResponse:
        payload = await self._post(
            "/mixed_people/search",
            {
                "q_organization_domains": request.company_domain,
                "person_seniorities": request.seniorities,
                "page": 1,
                "per_page": request.page_size,
            },
            capability="find_decision_makers",
        )
        people = payload.get("people", [])
        pagination = payload.get("pagination", {})
        return PersonSearchResponse(
            provider=self.provider_key,
            people=[self.normalize_person(p) for p in people],
            total_available=pagination.get("total_entries"),
            page=1,
            page_size=request.page_size,
            credits_used=payload.get("credits_consumed"),
        )

    async def enrich_company(self, request: CompanyEnrichRequest) -> CompanyEnrichResponse:
        body: dict[str, Any] = {}
        if request.domain:
            body["domain"] = request.domain
        payload = await self._post("/organizations/enrich", body, capability="enrich_company")
        org = payload.get("organization")
        return CompanyEnrichResponse(
            provider=self.provider_key,
            company=self.normalize_company(org) if org else None,
            credits_used=payload.get("credits_consumed"),
        )

    async def enrich_person(self, request: PersonEnrichRequest) -> PersonEnrichResponse:
        body: dict[str, Any] = {}
        if request.email:
            body["email"] = request.email
        if request.full_name:
            body["name"] = request.full_name
        if request.company_domain:
            body["domain"] = request.company_domain
        payload = await self._post("/people/match", body, capability="enrich_person")
        person = payload.get("person")
        return PersonEnrichResponse(
            provider=self.provider_key,
            person=self.normalize_person(person) if person else None,
            credits_used=payload.get("credits_consumed"),
        )

    async def estimate_credit_usage(self, request: CreditEstimateRequest) -> CreditEstimate:
        per_record = {
            "search_companies": ESTIMATED_CREDITS_PER_COMPANY,
            "search_people": ESTIMATED_CREDITS_PER_PERSON,
            "enrich_company": ESTIMATED_CREDITS_PER_ENRICHMENT,
            "enrich_person": ESTIMATED_CREDITS_PER_ENRICHMENT,
            "find_decision_makers": ESTIMATED_CREDITS_PER_PERSON,
        }[request.operation]
        return CreditEstimate(
            provider=self.provider_key,
            operation=request.operation,
            estimated_credits=per_record * request.record_count,
            is_estimate=True,
        )
