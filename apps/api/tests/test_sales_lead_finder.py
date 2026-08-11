from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import File, Membership, MembershipRole, Organization, Task
from app.core.rbac import get_system_role
from app.core.storage import upload_object
from app.identity.models import User
from app.identity.service import create_session
from app.sales import lead_finder_service
from app.sales.models import Account, Contact
from app.sales.provider_models import SalesProviderRecord
from app.sales.providers.exceptions import ProviderAuthError, ProviderInvalidRequest, ProviderRateLimited
from app.security import hash_password


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Lead Finder Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _create_member_with_role(
    db_session: AsyncSession, *, organization_id: uuid.UUID, email: str, role_key: str
) -> str:
    user = User(email=email, hashed_password=hash_password("irrelevant-password-123"))
    db_session.add(user)
    await db_session.flush()

    membership = Membership(organization_id=organization_id, user_id=user.id, status="active")
    db_session.add(membership)
    await db_session.flush()

    role = await get_system_role(db_session, role_key)
    db_session.add(MembershipRole(membership_id=membership.id, role_id=role.id))

    session = await create_session(
        db_session, user=user, organization_id=organization_id, ip_address=None, user_agent=None
    )
    await db_session.commit()
    return session.raw_token  # type: ignore[attr-defined]


async def test_company_search_returns_demo_labeled_results(client: AsyncClient) -> None:
    await _signup(client, "cs1@example.com", "CS Org 1")
    response = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {"industries": ["B2B SaaS"]}, "page": 1, "page_size": 10},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "demo"
    assert len(body["companies"]) >= 1
    assert all(c["provider"] == "demo" for c in body["companies"])


async def test_company_search_filters_by_employee_count(client: AsyncClient) -> None:
    await _signup(client, "cs2@example.com", "CS Org 2")
    response = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {"min_employee_count": 1000}, "page": 1, "page_size": 10},
    )
    assert response.status_code == 200, response.text
    assert response.json()["companies"] == []


async def test_person_search_returns_demo_labeled_results(client: AsyncClient) -> None:
    await _signup(client, "ps1@example.com", "PS Org 1")
    response = await client.post(
        "/api/v1/sales/lead-finder/people/search",
        json={"filters": {"seniorities": ["c_suite"]}, "page": 1, "page_size": 10},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "demo"
    assert all(p["seniority"] == "c_suite" for p in body["people"])


async def test_find_decision_makers_scopes_to_company_domain(client: AsyncClient) -> None:
    await _signup(client, "dm1@example.com", "DM Org 1")
    response = await client.post(
        "/api/v1/sales/lead-finder/decision-makers",
        json={"company_domain": "northwind-robotics.demo.invalid"},
    )
    assert response.status_code == 200, response.text
    people = response.json()["people"]
    assert len(people) >= 1
    assert all(p["current_company_domain"] == "northwind-robotics.demo.invalid" for p in people)


async def test_parse_query_returns_structured_filters_not_fabricated_records(client: AsyncClient) -> None:
    """The demo AI path must never invent a company/person — it should
    return an honestly-empty, valid, clearly-labeled structure rather than
    crash or fabricate data (spec: "AI must not invent companies/
    people/...")."""
    await _signup(client, "nl1@example.com", "NL Org 1")
    response = await client.post(
        "/api/v1/sales/lead-finder/parse-query",
        json={"query": "Find CEOs of German B2B SaaS companies with 20-200 employees"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "demo"
    assert "company_filters" in body
    assert "person_filters" in body
    assert isinstance(body["unsupported_criteria"], list)


async def test_providers_endpoint_reports_apollo_not_configured(client: AsyncClient) -> None:
    """No Apollo OAuth application is configured in the test environment, so
    no organization is even able to connect one — reported as
    `not_configured` rather than the vaguer `demo` this returned when Apollo
    was a single deployment-wide API key. `configured` stays False, which is
    what the UI keys its demo-data banner off (see
    docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md §11)."""
    await _signup(client, "prov1@example.com", "Prov Org 1")
    response = await client.get("/api/v1/sales/lead-finder/providers")
    assert response.status_code == 200, response.text
    providers = response.json()
    apollo = next(p for p in providers if p["provider_key"] == "apollo")
    assert apollo["configured"] is False
    assert apollo["status"] == "not_configured"
    # Never leaks another tenant's connection, and reports honestly that
    # this organization has connected nothing.
    assert apollo["connection_id"] is None
    assert apollo["connected_user_email"] is None
    assert apollo["granted_scopes"] == []


async def test_save_company_creates_account_and_provenance_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "save1@example.com", "Save Org 1")
    search = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {}, "page": 1, "page_size": 10},
    )
    company = search.json()["companies"][0]

    response = await client.post("/api/v1/sales/lead-finder/companies/save", json=company)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True

    account = await db_session.get(Account, uuid.UUID(body["account_id"]))
    assert account is not None
    assert account.name == company["name"]

    provenance = (
        await db_session.execute(
            SalesProviderRecord.__table__.select().where(
                SalesProviderRecord.linked_account_id == account.id
            )
        )
    ).first()
    assert provenance is not None
    assert provenance.provider == "demo"
    assert provenance.verification_status == "demo"


async def test_save_company_twice_does_not_duplicate_the_account(client: AsyncClient) -> None:
    await _signup(client, "save2@example.com", "Save Org 2")
    search = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {}, "page": 1, "page_size": 10},
    )
    company = search.json()["companies"][0]

    first = await client.post("/api/v1/sales/lead-finder/companies/save", json=company)
    second = await client.post("/api/v1/sales/lead-finder/companies/save", json=company)
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["account_id"] == second.json()["account_id"]


async def test_save_person_creates_contact(client: AsyncClient, db_session: AsyncSession) -> None:
    await _signup(client, "save3@example.com", "Save Org 3")
    search = await client.post(
        "/api/v1/sales/lead-finder/people/search",
        json={"filters": {}, "page": 1, "page_size": 10},
    )
    people = search.json()["people"]
    person = next(p for p in people if p["email"])

    response = await client.post("/api/v1/sales/lead-finder/people/save", json=person)
    assert response.status_code == 201, response.text
    contact = await db_session.get(Contact, uuid.UUID(response.json()["contact_id"]))
    assert contact is not None
    assert contact.email == person["email"].lower()


async def test_dedupe_check_reflects_previously_saved_company(client: AsyncClient) -> None:
    await _signup(client, "dedupe1@example.com", "Dedupe Org 1")
    search = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {}, "page": 1, "page_size": 10},
    )
    company = search.json()["companies"][0]
    assert company["dedupe_status"] == "new"

    await client.post("/api/v1/sales/lead-finder/companies/save", json=company)

    second_search = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {}, "page": 1, "page_size": 10, "refresh": True},
    )
    same_company = next(
        c for c in second_search.json()["companies"] if c["provider_record_id"] == company["provider_record_id"]
    )
    assert same_company["dedupe_status"] == "existing"
    assert same_company["existing_account_id"] is not None


async def test_saved_search_crud_and_run(client: AsyncClient) -> None:
    await _signup(client, "svsearch1@example.com", "SvSearch Org 1")
    create = await client.post(
        "/api/v1/sales/lead-finder/saved-searches",
        json={
            "name": "My saved search",
            "search_type": "company",
            "filters": {"industries": ["B2B SaaS"]},
        },
    )
    assert create.status_code == 201, create.text
    saved_search_id = create.json()["id"]
    assert create.json()["last_executed_at"] is None

    listed = await client.get("/api/v1/sales/lead-finder/saved-searches")
    assert any(s["id"] == saved_search_id for s in listed.json())

    run = await client.post(f"/api/v1/sales/lead-finder/saved-searches/{saved_search_id}/run")
    assert run.status_code == 200, run.text

    updated = await client.patch(
        f"/api/v1/sales/lead-finder/saved-searches/{saved_search_id}", json={"name": "Renamed"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"

    deleted = await client.delete(f"/api/v1/sales/lead-finder/saved-searches/{saved_search_id}")
    assert deleted.status_code == 204

    listed_again = await client.get("/api/v1/sales/lead-finder/saved-searches")
    assert all(s["id"] != saved_search_id for s in listed_again.json())


async def test_list_create_add_item_and_prevent_duplicate(client: AsyncClient) -> None:
    await _signup(client, "list1@example.com", "List Org 1")
    create_account = await client.post(
        "/api/v1/sales/lead-finder/companies/search", json={"filters": {}, "page": 1, "page_size": 10}
    )
    company = create_account.json()["companies"][0]
    saved = await client.post("/api/v1/sales/lead-finder/companies/save", json=company)
    account_id = saved.json()["account_id"]

    create_list = await client.post(
        "/api/v1/sales/lead-finder/lists", json={"name": "Targets", "list_type": "company"}
    )
    assert create_list.status_code == 201, create_list.text
    list_id = create_list.json()["id"]

    add = await client.post(
        f"/api/v1/sales/lead-finder/lists/{list_id}/items", json={"account_id": account_id}
    )
    assert add.status_code == 201, add.text
    item_id = add.json()["id"]

    duplicate = await client.post(
        f"/api/v1/sales/lead-finder/lists/{list_id}/items", json={"account_id": account_id}
    )
    assert duplicate.status_code == 409

    removed = await client.delete(f"/api/v1/sales/lead-finder/lists/{list_id}/items/{item_id}")
    assert removed.status_code == 204

    # Regression: the delete must actually persist, not just return 204
    # while leaving the row in place (a real bug caught here — the
    # endpoint was missing its db.commit()).
    items = await client.get(f"/api/v1/sales/lead-finder/lists/{list_id}/items")
    assert items.status_code == 200
    assert items.json() == []

    re_add = await client.post(
        f"/api/v1/sales/lead-finder/lists/{list_id}/items", json={"account_id": account_id}
    )
    assert re_add.status_code == 201, re_add.text


async def test_lead_finder_view_requires_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "rbac-owner@example.com", "RBAC Org 1")
    # employee role has no sales.* permissions at all (see core/rbac.py)
    token = await _create_member_with_role(
        db_session, organization_id=organization_id, email="rbac-employee@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)
    response = await client.post(
        "/api/v1/sales/lead-finder/companies/search", json={"filters": {}, "page": 1, "page_size": 10}
    )
    assert response.status_code == 403


async def test_company_search_maps_apollo_auth_error_to_clean_403(
    client: AsyncClient, monkeypatch
) -> None:
    """Regression: an unhandled ProviderAuthError previously propagated
    past CORSMiddleware as a raw 500 (browsers report that as a CORS
    failure and the frontend sees a generic "Failed to fetch") instead of
    the honest, sanitized 403 app.main's SalesProviderError handler now
    returns — see docs/SALES_DATA_PROVIDER_ARCHITECTURE.md §3."""
    await _signup(client, "provider-403@example.com", "Provider 403 Org")

    class _FailingProvider:
        provider_key = "apollo"

        async def search_companies(self, request):  # noqa: ANN001
            raise ProviderAuthError("Apollo rejected the configured API key (HTTP 403)", status_code=403)

    async def _fake_get_provider(db, *, organization_id, provider_key="apollo"):  # noqa: ANN001
        return _FailingProvider()

    monkeypatch.setattr(lead_finder_service, "get_provider", _fake_get_provider)

    response = await client.post(
        "/api/v1/sales/lead-finder/companies/search", json={"filters": {}, "page": 1, "page_size": 1}
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["message"] == "Your Apollo account or API key does not have access to this feature."
    # Never echoes the raw provider error code/response back to the client.
    assert "API_INACCESSIBLE" not in response.text


async def test_people_search_maps_apollo_rate_limit_to_clean_429(
    client: AsyncClient, monkeypatch
) -> None:
    await _signup(client, "provider-429@example.com", "Provider 429 Org")

    class _RateLimitedProvider:
        provider_key = "apollo"

        async def search_people(self, request):  # noqa: ANN001
            raise ProviderRateLimited("Apollo rate limit exceeded", retry_after_seconds=30)

    async def _fake_get_provider(db, *, organization_id, provider_key="apollo"):  # noqa: ANN001
        return _RateLimitedProvider()

    monkeypatch.setattr(lead_finder_service, "get_provider", _fake_get_provider)

    response = await client.post(
        "/api/v1/sales/lead-finder/people/search", json={"filters": {}, "page": 1, "page_size": 1}
    )
    assert response.status_code == 429
    assert response.json()["error"]["message"] == "Apollo rate limit reached. Please try again later."
    assert response.headers.get("Retry-After") == "30"


async def test_company_search_maps_apollo_invalid_request_to_clean_422(
    client: AsyncClient, monkeypatch
) -> None:
    await _signup(client, "provider-422@example.com", "Provider 422 Org")

    class _InvalidRequestProvider:
        provider_key = "apollo"

        async def search_companies(self, request):  # noqa: ANN001
            raise ProviderInvalidRequest("Apollo rejected the request as invalid (HTTP 422)")

    async def _fake_get_provider(db, *, organization_id, provider_key="apollo"):  # noqa: ANN001
        return _InvalidRequestProvider()

    monkeypatch.setattr(lead_finder_service, "get_provider", _fake_get_provider)

    response = await client.post(
        "/api/v1/sales/lead-finder/companies/search", json={"filters": {}, "page": 1, "page_size": 1}
    )
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "One or more search filters are not supported by Apollo."


async def test_enrich_estimate_reports_zero_for_demo(client: AsyncClient) -> None:
    await _signup(client, "enrich-est1@example.com", "Enrich Est Org 1")
    response = await client.post(
        "/api/v1/sales/lead-finder/enrich/estimate",
        json={"operation": "enrich_company", "record_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["estimated_credits"] == 0


async def test_enrich_selective_enriches_saved_company(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "enrich1@example.com", "Enrich Org 1")
    search = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {"name": "Northwind"}, "page": 1, "page_size": 10},
    )
    company = search.json()["companies"][0]
    saved = await client.post("/api/v1/sales/lead-finder/companies/save", json=company)
    account_id = saved.json()["account_id"]

    response = await client.post(
        "/api/v1/sales/lead-finder/enrich",
        json={"operation": "enrich_company", "record_ids": [account_id]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["succeeded_count"] == 1
    assert body["failed_count"] == 0

    account = await db_session.get(Account, uuid.UUID(account_id))
    assert account is not None
    assert account.industry == "Industrial Automation"


async def test_enrich_selective_rejects_more_than_five_records(client: AsyncClient) -> None:
    await _signup(client, "enrich2@example.com", "Enrich Org 2")
    response = await client.post(
        "/api/v1/sales/lead-finder/enrich",
        json={"operation": "enrich_company", "record_ids": [str(uuid.uuid4()) for _ in range(6)]},
    )
    assert response.status_code == 422


async def test_enrich_selective_reports_partial_failure_for_unknown_record(
    client: AsyncClient,
) -> None:
    await _signup(client, "enrich3@example.com", "Enrich Org 3")
    response = await client.post(
        "/api/v1/sales/lead-finder/enrich",
        json={"operation": "enrich_company", "record_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["failed_count"] == 1
    assert len(body["error_records"]) == 1


async def test_enrich_bulk_creates_running_job_and_can_be_polled(client: AsyncClient) -> None:
    await _signup(client, "enrich4@example.com", "Enrich Org 4")
    search = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {}, "page": 1, "page_size": 10},
    )
    company = search.json()["companies"][0]
    saved = await client.post("/api/v1/sales/lead-finder/companies/save", json=company)
    account_id = saved.json()["account_id"]

    response = await client.post(
        "/api/v1/sales/lead-finder/enrich/bulk",
        json={"operation": "enrich_company", "record_ids": [account_id]},
    )
    assert response.status_code == 201, response.text
    job_id = response.json()["id"]
    # The Temporal starter is a no-op in tests (see conftest.py), so the
    # job stays "running" — this confirms the row is created synchronously
    # and pollable, not that the workflow itself executed.
    assert response.json()["status"] == "running"

    poll = await client.get(f"/api/v1/sales/lead-finder/enrichment-jobs/{job_id}")
    assert poll.status_code == 200
    assert poll.json()["id"] == job_id


async def test_enrich_requires_permission(client: AsyncClient, db_session: AsyncSession) -> None:
    organization_id = await _signup(client, "enrich-rbac@example.com", "Enrich RBAC Org")
    token = await _create_member_with_role(
        db_session,
        organization_id=organization_id,
        email="enrich-rbac-employee@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)
    response = await client.post(
        "/api/v1/sales/lead-finder/enrich",
        json={"operation": "enrich_company", "record_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 403


async def test_credit_usage_dashboard_filters_by_provider_operation_user_and_date(
    client: AsyncClient,
) -> None:
    await _signup(client, "credit1@example.com", "Credit Org 1")
    search = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {"name": "Northwind"}, "page": 1, "page_size": 10},
    )
    company = search.json()["companies"][0]
    saved = await client.post("/api/v1/sales/lead-finder/companies/save", json=company)
    account_id = saved.json()["account_id"]
    await client.post(
        "/api/v1/sales/lead-finder/enrich",
        json={"operation": "enrich_company", "record_ids": [account_id]},
    )

    all_usage = await client.get("/api/v1/sales/lead-finder/credit-usage")
    assert all_usage.status_code == 200
    rows = all_usage.json()
    assert len(rows) == 1
    row = rows[0]
    # EnrichIn.provider defaults to "apollo" — the requested provider key
    # is what's recorded regardless of whether it internally fell back to
    # demo data (Apollo isn't configured in this test environment; see
    # test_company_search_returns_demo_labeled_results for where the
    # demo/apollo distinction actually surfaces to the caller instead).
    assert row["provider"] == "apollo"
    assert row["operation"] == "enrich_company"
    assert row["requested_by_user_id"] is not None
    assert "estimated_credits" in row
    assert "actual_credits" in row

    by_provider = await client.get("/api/v1/sales/lead-finder/credit-usage?provider=apollo")
    assert len(by_provider.json()) == 1
    by_wrong_provider = await client.get("/api/v1/sales/lead-finder/credit-usage?provider=hubspot")
    assert by_wrong_provider.json() == []

    by_operation = await client.get(
        "/api/v1/sales/lead-finder/credit-usage?operation=enrich_company"
    )
    assert len(by_operation.json()) == 1
    by_wrong_operation = await client.get(
        "/api/v1/sales/lead-finder/credit-usage?operation=enrich_person"
    )
    assert by_wrong_operation.json() == []

    by_user = await client.get(f"/api/v1/sales/lead-finder/credit-usage?user_id={row['requested_by_user_id']}")
    assert len(by_user.json()) == 1
    by_wrong_user = await client.get(f"/api/v1/sales/lead-finder/credit-usage?user_id={uuid.uuid4()}")
    assert by_wrong_user.json() == []

    future = await client.get(
        "/api/v1/sales/lead-finder/credit-usage?date_from=2999-01-01T00:00:00Z"
    )
    assert future.json() == []
    past = await client.get(
        "/api/v1/sales/lead-finder/credit-usage?date_from=2000-01-01T00:00:00Z"
    )
    assert len(past.json()) == 1


async def test_credit_usage_dashboard_requires_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "credit2a@example.com", "Credit Org 2a")

    # sales_representative doesn't get sales.lead_finder.providers.manage (manager-only)
    token = await _create_member_with_role(
        db_session,
        organization_id=organization_id,
        email="credit2a-rep@example.com",
        role_key="sales_representative",
    )
    client.cookies.set("agora_session", token)
    denied = await client.get("/api/v1/sales/lead-finder/credit-usage")
    assert denied.status_code == 403


async def test_credit_usage_dashboard_isolated_per_organization(client: AsyncClient) -> None:
    await _signup(client, "credit3a@example.com", "Credit Org 3a")
    search = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {"name": "Northwind"}, "page": 1, "page_size": 10},
    )
    company = search.json()["companies"][0]
    saved = await client.post("/api/v1/sales/lead-finder/companies/save", json=company)
    await client.post(
        "/api/v1/sales/lead-finder/enrich",
        json={"operation": "enrich_company", "record_ids": [saved.json()["account_id"]]},
    )

    await _signup(client, "credit3b@example.com", "Credit Org 3b")
    other_org = await client.get("/api/v1/sales/lead-finder/credit-usage")
    assert other_org.status_code == 200
    assert other_org.json() == []


async def test_saved_search_is_isolated_per_organization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "tenant-a@example.com", "Tenant Org A")
    create = await client.post(
        "/api/v1/sales/lead-finder/saved-searches",
        json={"name": "Org A search", "search_type": "company", "filters": {}},
    )
    saved_search_id = create.json()["id"]

    other_org_id = await _signup(client, "tenant-b@example.com", "Tenant Org B")
    token = await _create_member_with_role(
        db_session, organization_id=other_org_id, email="tenant-b-member@example.com", role_key="sales_manager"
    )
    client.cookies.set("agora_session", token)

    response = await client.get(f"/api/v1/sales/lead-finder/saved-searches/{saved_search_id}/run")
    assert response.status_code in (404, 405)  # GET not allowed; confirms no cross-tenant leak via other verbs
    response = await client.delete(f"/api/v1/sales/lead-finder/saved-searches/{saved_search_id}")
    assert response.status_code == 404


async def _create_contact(client: AsyncClient, full_name: str, email: str) -> str:
    response = await client.post(
        "/api/v1/sales/contacts", json={"full_name": full_name, "email": email}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_eligibility_check_eligible_contact(client: AsyncClient) -> None:
    await _signup(client, "elig1@example.com", "Elig Org 1")
    contact_id = await _create_contact(client, "Jane Reachable", "jane.reachable@example.com")

    response = await client.post(
        "/api/v1/sales/lead-finder/eligibility/check", json={"contact_id": contact_id}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "eligible"


async def test_eligibility_check_blocked_for_do_not_contact(client: AsyncClient) -> None:
    await _signup(client, "elig2@example.com", "Elig Org 2")
    contact_id = await _create_contact(client, "Suppressed Person", "suppressed-elig@example.com")
    await client.patch(f"/api/v1/sales/contacts/{contact_id}", json={"do_not_contact": True})

    response = await client.post(
        "/api/v1/sales/lead-finder/eligibility/check", json={"contact_id": contact_id}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert "do-not-contact" in body["reasons"][0]


async def test_eligibility_check_unknown_with_no_contact_or_email(client: AsyncClient) -> None:
    await _signup(client, "elig3@example.com", "Elig Org 3")
    response = await client.post("/api/v1/sales/lead-finder/eligibility/check", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "unknown"


async def test_suppression_entry_blocks_eligibility_before_contact_is_saved(
    client: AsyncClient,
) -> None:
    await _signup(client, "elig4@example.com", "Elig Org 4")
    add = await client.post(
        "/api/v1/sales/lead-finder/suppression",
        json={"email": "blocklisted@example.com", "reason": "Requested no contact via LinkedIn"},
    )
    assert add.status_code == 201, add.text

    response = await client.post(
        "/api/v1/sales/lead-finder/eligibility/check", json={"email": "blocklisted@example.com"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "blocked"
    assert "Requested no contact" in body["reasons"][0]


async def test_suppression_blocks_a_saved_contact_even_without_do_not_contact_flag(
    client: AsyncClient,
) -> None:
    await _signup(client, "elig5@example.com", "Elig Org 5")
    contact_id = await _create_contact(client, "Domain Suppressed", "person@blocked-domain.example")
    await client.post(
        "/api/v1/sales/lead-finder/suppression",
        json={"domain": "blocked-domain.example", "reason": "Competitor domain — never contact"},
    )

    response = await client.post(
        "/api/v1/sales/lead-finder/eligibility/check", json={"contact_id": contact_id}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


async def test_suppression_list_blocks_sequence_send_without_do_not_contact_flag(
    client: AsyncClient,
) -> None:
    """The suppression list must also gate the real send path (spec §23),
    not just the preview panel — extends
    test_advance_respects_suppression's existing do_not_contact coverage
    to the new, independent suppression-list mechanism."""
    await _signup(client, "elig6@example.com", "Elig Org 6")
    sequence = await client.post("/api/v1/sales/sequences", json={"name": "Suppression List Sequence"})
    sequence_id = sequence.json()["id"]
    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/steps",
        json={"wait_days": 0, "channel": "email", "body_template": "Hi {{first_name}}"},
    )
    contact_id = await _create_contact(client, "List Suppressed", "list-suppressed@example.com")
    await client.post(
        "/api/v1/sales/lead-finder/suppression",
        json={"email": "list-suppressed@example.com", "reason": "Manually flagged do-not-contact"},
    )

    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/enroll", json={"contact_ids": [contact_id]}
    )
    await client.post("/api/v1/sales/sequences/process-due-steps")

    inbox = (await client.get("/api/v1/sales/inbox")).json()
    assert inbox[0]["status"] == "blocked"
    assert "Suppressed" in inbox[0]["blocked_reason"]


async def test_suppression_crud_and_permission(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "supp1@example.com", "Supp Org 1")

    add = await client.post(
        "/api/v1/sales/lead-finder/suppression",
        json={"email": "toremove@example.com", "reason": "Test entry"},
    )
    assert add.status_code == 201, add.text
    entry_id = add.json()["id"]

    listed = await client.get("/api/v1/sales/lead-finder/suppression")
    assert any(e["id"] == entry_id for e in listed.json())

    removed = await client.delete(f"/api/v1/sales/lead-finder/suppression/{entry_id}")
    assert removed.status_code == 204

    listed_again = await client.get("/api/v1/sales/lead-finder/suppression")
    assert all(e["id"] != entry_id for e in listed_again.json())

    # sales_representative doesn't get sales.suppression.manage (manager-only, see core/rbac.py)
    token = await _create_member_with_role(
        db_session,
        organization_id=organization_id,
        email="supp-rep@example.com",
        role_key="sales_representative",
    )
    client.cookies.set("agora_session", token)
    denied = await client.get("/api/v1/sales/lead-finder/suppression")
    assert denied.status_code == 403


async def test_suppression_by_contact_id_alone_blocks_eligibility_and_send(
    client: AsyncClient,
) -> None:
    """Regression: a suppression entry created with only a contact_id (no
    email/domain) must actually block that contact — find_matching_
    suppression used to only ever match by email/domain, so a contact_id-
    only entry was silently never found (caught by
    e2e/sales-lead-finder.spec.ts's "campaign compliance block" journey)."""
    await _signup(client, "supp-contact1@example.com", "Supp Contact Org 1")
    contact_id = await _create_contact(client, "Contact ID Suppressed", "contact-id-suppressed@example.com")

    add = await client.post(
        "/api/v1/sales/lead-finder/suppression",
        json={"contact_id": contact_id, "reason": "Suppressed by contact_id only"},
    )
    assert add.status_code == 201, add.text

    eligibility = await client.post(
        "/api/v1/sales/lead-finder/eligibility/check", json={"contact_id": contact_id}
    )
    assert eligibility.status_code == 200
    body = eligibility.json()
    assert body["status"] == "blocked"
    assert "Suppressed by contact_id only" in body["reasons"][0]

    sequence = await client.post(
        "/api/v1/sales/sequences", json={"name": "Contact-ID Suppression Sequence"}
    )
    sequence_id = sequence.json()["id"]
    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/steps",
        json={"wait_days": 0, "channel": "email", "body_template": "Hi {{first_name}}"},
    )
    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/enroll", json={"contact_ids": [contact_id]}
    )
    await client.post("/api/v1/sales/sequences/process-due-steps")

    inbox = (await client.get("/api/v1/sales/inbox")).json()
    assert inbox[0]["status"] == "blocked"
    assert "Suppressed by contact_id only" in inbox[0]["blocked_reason"]


# ---- CSV import and manual entry ----


async def _upload_csv(
    client: AsyncClient, db_session: AsyncSession, *, organization_id, email: str, content: str
) -> str:
    """Writes real bytes to object storage (the same discipline
    test_reporting.py uses for report downloads) rather than mocking
    storage, so these tests exercise the real download/parse pipeline —
    not just the row-mapping logic in isolation."""
    user_id = (await db_session.execute(select(User.id).where(User.email == email))).scalar_one()
    storage_key = f"org/{organization_id}/{uuid.uuid4()}/import.csv"
    upload_object(storage_key, content.encode("utf-8"), "text/csv")
    file_record = File(
        organization_id=organization_id,
        storage_key=storage_key,
        original_filename="import.csv",
        content_type="text/csv",
        size_bytes=len(content),
        uploaded_by=user_id,
    )
    db_session.add(file_record)
    await db_session.flush()
    await db_session.commit()
    return str(file_record.id)


async def test_import_preview_suggests_column_mapping(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "import1@example.com", "Import Org 1")
    file_id = await _upload_csv(
        client,
        db_session,
        organization_id=organization_id,
        email="import1@example.com",
        content="Company Name,Website,Employees\nAcme Robotics,acme-robotics.example,120\n",
    )
    response = await client.post(
        "/api/v1/sales/lead-finder/import/preview",
        json={"file_id": file_id, "record_type": "company"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_rows"] == 1
    assert body["suggested_mapping"]["name"] == "Company Name"
    assert body["suggested_mapping"]["website"] == "Website"
    assert body["sample_rows"][0]["Company Name"] == "Acme Robotics"


async def test_import_small_file_runs_synchronously_and_creates_accounts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "import2@example.com", "Import Org 2")
    file_id = await _upload_csv(
        client,
        db_session,
        organization_id=organization_id,
        email="import2@example.com",
        content=(
            "Company Name,Website\n"
            "Acme Robotics,acme-robotics.example\n"
            "Bolt Logistics,bolt-logistics.example\n"
        ),
    )
    response = await client.post(
        "/api/v1/sales/lead-finder/import",
        json={
            "file_id": file_id,
            "record_type": "company",
            "column_mapping": {"name": "Company Name", "website": "Website"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["total_rows"] == 2
    assert body["imported_rows"] == 2
    assert body["skipped_rows"] == 0

    accounts = (
        await db_session.execute(
            select(Account).where(Account.organization_id == organization_id)
        )
    ).scalars().all()
    assert {a.name for a in accounts} == {"Acme Robotics", "Bolt Logistics"}

    provider_records = (
        await db_session.execute(
            select(SalesProviderRecord).where(
                SalesProviderRecord.organization_id == organization_id,
                SalesProviderRecord.provider == "csv",
            )
        )
    ).scalars().all()
    assert len(provider_records) == 2
    # CSV-imported records are never presented as provider-verified (spec
    # prohibition on "guessed contact details presented as verified").
    assert all(r.verification_status == "user_entered" for r in provider_records)

    poll = await client.get(f"/api/v1/sales/lead-finder/import-jobs/{body['id']}")
    assert poll.status_code == 200
    assert poll.json()["status"] == "succeeded"


async def test_import_reports_row_errors_without_failing_the_whole_file(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "import3@example.com", "Import Org 3")
    file_id = await _upload_csv(
        client,
        db_session,
        organization_id=organization_id,
        email="import3@example.com",
        content="Full Name,Email\nJane Doe,jane@example.com\n,missing-name@example.com\nBad Email,not-an-email\n",
    )
    response = await client.post(
        "/api/v1/sales/lead-finder/import",
        json={
            "file_id": file_id,
            "record_type": "person",
            "column_mapping": {"full_name": "Full Name", "email": "Email"},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "partial"
    assert body["total_rows"] == 3
    assert body["imported_rows"] == 1
    assert body["skipped_rows"] == 2
    assert len(body["error_rows"]) == 2
    assert any("name" in e["error"].lower() for e in body["error_rows"])
    assert any("email" in e["error"].lower() for e in body["error_rows"])


async def test_import_dedupes_against_an_existing_saved_account(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "import4@example.com", "Import Org 4")
    search = await client.post(
        "/api/v1/sales/lead-finder/companies/search",
        json={"filters": {"name": "Northwind"}, "page": 1, "page_size": 10},
    )
    company = search.json()["companies"][0]
    saved = await client.post("/api/v1/sales/lead-finder/companies/save", json=company)
    existing_account_id = saved.json()["account_id"]

    file_id = await _upload_csv(
        client,
        db_session,
        organization_id=organization_id,
        email="import4@example.com",
        content=f"Company Name,Website\nNorthwind,{company['domain']}\n",
    )
    response = await client.post(
        "/api/v1/sales/lead-finder/import",
        json={
            "file_id": file_id,
            "record_type": "company",
            "column_mapping": {"name": "Company Name", "website": "Website"},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["imported_rows"] == 1

    accounts = (
        await db_session.execute(
            select(Account).where(Account.organization_id == organization_id)
        )
    ).scalars().all()
    # The CSV row matched the existing account by domain rather than
    # creating a duplicate (see save_service.save_company_as_account) — its
    # name is untouched by the CSV row's ("Northwind") differing label.
    assert len(accounts) == 1
    assert str(accounts[0].id) == existing_account_id
    assert accounts[0].name == company["name"]


async def test_import_requires_permission(client: AsyncClient, db_session: AsyncSession) -> None:
    organization_id = await _signup(client, "import-rbac@example.com", "Import RBAC Org")
    token = await _create_member_with_role(
        db_session,
        organization_id=organization_id,
        email="import-rbac-employee@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)
    response = await client.post(
        "/api/v1/sales/lead-finder/import",
        json={"file_id": str(uuid.uuid4()), "record_type": "company", "column_mapping": {}},
    )
    assert response.status_code == 403


async def test_import_rejects_file_from_another_organization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_a = await _signup(client, "import-tenant-a@example.com", "Import Tenant A")
    file_id = await _upload_csv(
        client,
        db_session,
        organization_id=org_a,
        email="import-tenant-a@example.com",
        content="Company Name\nAcme\n",
    )

    await _signup(client, "import-tenant-b@example.com", "Import Tenant B")
    response = await client.post(
        "/api/v1/sales/lead-finder/import/preview",
        json={"file_id": file_id, "record_type": "company"},
    )
    assert response.status_code == 404


async def test_manual_add_company_creates_account_with_user_entered_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "manual1@example.com", "Manual Org 1")
    response = await client.post(
        "/api/v1/sales/lead-finder/manual/company",
        json={"name": "Handwritten Co", "domain": "handwritten.example", "employee_count": 12},
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["account_id"]
    assert response.json()["created"] is True

    account = await db_session.get(Account, uuid.UUID(account_id))
    assert account is not None
    assert account.name == "Handwritten Co"

    provider_record = (
        await db_session.execute(
            select(SalesProviderRecord).where(
                SalesProviderRecord.organization_id == organization_id,
                SalesProviderRecord.provider == "manual",
            )
        )
    ).scalar_one()
    assert provider_record.verification_status == "user_entered"


async def test_manual_add_person_creates_contact_with_user_entered_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "manual2@example.com", "Manual Org 2")
    response = await client.post(
        "/api/v1/sales/lead-finder/manual/person",
        json={"full_name": "Pat Rivera", "email": "pat.rivera@example.com", "title": "VP Sales"},
    )
    assert response.status_code == 201, response.text
    contact_id = response.json()["contact_id"]

    contact = await db_session.get(Contact, uuid.UUID(contact_id))
    assert contact is not None
    assert contact.full_name == "Pat Rivera"
    assert contact.job_title == "VP Sales"

    provider_record = (
        await db_session.execute(
            select(SalesProviderRecord).where(SalesProviderRecord.linked_contact_id == contact.id)
        )
    ).scalar_one()
    assert provider_record.verification_status == "user_entered"


async def test_manual_add_requires_permission(client: AsyncClient, db_session: AsyncSession) -> None:
    organization_id = await _signup(client, "manual-rbac@example.com", "Manual RBAC Org")
    token = await _create_member_with_role(
        db_session,
        organization_id=organization_id,
        email="manual-rbac-employee@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)
    response = await client.post(
        "/api/v1/sales/lead-finder/manual/company", json={"name": "Should Be Blocked"}
    )
    assert response.status_code == 403


# ---- Provenance ----


async def test_account_provenance_reflects_how_it_was_found(client: AsyncClient) -> None:
    await _signup(client, "provenance1@example.com", "Provenance Org 1")
    manual = await client.post(
        "/api/v1/sales/lead-finder/manual/company", json={"name": "Provenance Test Co"}
    )
    account_id = manual.json()["account_id"]

    response = await client.get(f"/api/v1/sales/lead-finder/provenance/account/{account_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider"] == "manual"
    assert body["verification_status"] == "user_entered"


async def test_account_provenance_404_when_not_from_lead_finder(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "provenance2@example.com", "Provenance Org 2")
    created = await client.post("/api/v1/sales/accounts", json={"name": "Old-school account"})
    account_id = created.json()["id"]

    response = await client.get(f"/api/v1/sales/lead-finder/provenance/account/{account_id}")
    assert response.status_code == 404


async def test_contact_provenance_isolated_per_organization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "provenance3@example.com", "Provenance Org 3")
    manual = await client.post(
        "/api/v1/sales/lead-finder/manual/person", json={"full_name": "Provenance Person"}
    )
    contact_id = manual.json()["contact_id"]

    own_org = await client.get(f"/api/v1/sales/lead-finder/provenance/contact/{contact_id}")
    assert own_org.status_code == 200
    assert own_org.json()["provider"] == "manual"

    await _signup(client, "provenance3b@example.com", "Provenance Org 3b")
    other_org = await client.get(f"/api/v1/sales/lead-finder/provenance/contact/{contact_id}")
    assert other_org.status_code == 404


# ---- Manual LinkedIn outreach ----


async def test_linkedin_task_creates_task_and_stores_profile_url(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "linkedin1@example.com", "LinkedIn Org 1")
    contact_id = await _create_contact(client, "LinkedIn Target", "linkedin-target@example.com")

    response = await client.post(
        f"/api/v1/sales/lead-finder/contacts/{contact_id}/linkedin-task",
        json={
            "linkedin_url": "https://www.linkedin.com/in/linkedin-target",
            "message": "Hi — following up after our conversation at the conference.",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["linkedin_url"] == "https://www.linkedin.com/in/linkedin-target"

    contact = await db_session.get(Contact, uuid.UUID(contact_id))
    assert contact is not None
    assert contact.linkedin_url == "https://www.linkedin.com/in/linkedin-target"

    task = await db_session.get(Task, uuid.UUID(body["task_id"]))
    assert task is not None
    assert task.module == "sales"
    assert task.entity_type == "sales_contact"
    assert task.entity_id == contact_id
    assert "conference" in (task.description or "")


async def test_linkedin_task_rejects_a_non_linkedin_url(client: AsyncClient) -> None:
    await _signup(client, "linkedin2@example.com", "LinkedIn Org 2")
    contact_id = await _create_contact(client, "Bad URL Target", "bad-url-target@example.com")

    response = await client.post(
        f"/api/v1/sales/lead-finder/contacts/{contact_id}/linkedin-task",
        json={"linkedin_url": "https://evil.example.com/scrape", "message": "hi"},
    )
    assert response.status_code == 422


async def test_linkedin_task_requires_permission(client: AsyncClient, db_session: AsyncSession) -> None:
    organization_id = await _signup(client, "linkedin3@example.com", "LinkedIn Org 3")
    contact_id = await _create_contact(client, "Perm Target", "perm-target@example.com")
    token = await _create_member_with_role(
        db_session,
        organization_id=organization_id,
        email="linkedin-employee@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)
    response = await client.post(
        f"/api/v1/sales/lead-finder/contacts/{contact_id}/linkedin-task",
        json={"message": "hi"},
    )
    assert response.status_code == 403


async def test_linkedin_task_404_for_contact_in_another_organization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "linkedin4a@example.com", "LinkedIn Org 4a")
    contact_id = await _create_contact(client, "Cross Tenant Target", "cross-tenant-target@example.com")

    await _signup(client, "linkedin4b@example.com", "LinkedIn Org 4b")
    response = await client.post(
        f"/api/v1/sales/lead-finder/contacts/{contact_id}/linkedin-task",
        json={"message": "hi"},
    )
    assert response.status_code == 404


# ---- Saved-list CSV export ----


async def _create_company_list_with_one_item(client: AsyncClient) -> tuple[str, str]:
    manual = await client.post(
        "/api/v1/sales/lead-finder/manual/company",
        json={"name": "Export Target Co", "domain": "export-target.example", "employee_count": 42},
    )
    assert manual.status_code == 201, manual.text
    account_id = manual.json()["account_id"]

    create_list = await client.post(
        "/api/v1/sales/lead-finder/lists", json={"name": "Export List", "list_type": "company"}
    )
    assert create_list.status_code == 201, create_list.text
    list_id = create_list.json()["id"]

    add = await client.post(
        f"/api/v1/sales/lead-finder/lists/{list_id}/items", json={"account_id": account_id}
    )
    assert add.status_code == 201, add.text
    return list_id, account_id


async def test_export_company_list_returns_csv_with_expected_rows(client: AsyncClient) -> None:
    await _signup(client, "export1@example.com", "Export Org 1")
    list_id, account_id = await _create_company_list_with_one_item(client)

    response = await client.get(f"/api/v1/sales/lead-finder/lists/{list_id}/export")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    lines = response.text.strip("\r\n").split("\r\n")
    header = lines[0].split(",")
    assert header == [
        "name",
        "industry",
        "website",
        "employee_count",
        "icp_score",
        "status",
        "account_id",
        "added_at",
    ]
    assert len(lines) == 2
    row = lines[1].split(",")
    assert row[0] == "Export Target Co"
    assert row[3] == "42"
    assert row[6] == account_id


async def test_export_person_list_returns_csv_with_expected_rows(client: AsyncClient) -> None:
    await _signup(client, "export2@example.com", "Export Org 2")
    manual = await client.post(
        "/api/v1/sales/lead-finder/manual/person",
        json={"full_name": "Export Target Person", "email": "export-target-person@example.com"},
    )
    assert manual.status_code == 201, manual.text
    contact_id = manual.json()["contact_id"]

    create_list = await client.post(
        "/api/v1/sales/lead-finder/lists", json={"name": "Export People", "list_type": "person"}
    )
    list_id = create_list.json()["id"]
    add = await client.post(
        f"/api/v1/sales/lead-finder/lists/{list_id}/items", json={"contact_id": contact_id}
    )
    assert add.status_code == 201, add.text

    response = await client.get(f"/api/v1/sales/lead-finder/lists/{list_id}/export")
    assert response.status_code == 200, response.text
    lines = response.text.strip("\r\n").split("\r\n")
    header = lines[0].split(",")
    assert header == ["full_name", "email", "job_title", "do_not_contact", "contact_id", "added_at"]
    row = lines[1].split(",")
    assert row[0] == "Export Target Person"
    assert row[1] == "export-target-person@example.com"
    assert row[4] == contact_id


async def test_export_list_requires_permission(client: AsyncClient, db_session: AsyncSession) -> None:
    organization_id = await _signup(client, "export-rbac@example.com", "Export RBAC Org")
    list_id, _account_id = await _create_company_list_with_one_item(client)

    token = await _create_member_with_role(
        db_session, organization_id=organization_id, email="export-employee@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)
    response = await client.get(f"/api/v1/sales/lead-finder/lists/{list_id}/export")
    assert response.status_code == 403


async def test_export_list_blocked_when_organization_disables_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    organization_id = await _signup(client, "export-disabled@example.com", "Export Disabled Org")
    list_id, _account_id = await _create_company_list_with_one_item(client)

    organization = await db_session.get(Organization, organization_id)
    assert organization is not None
    organization.allow_list_export = False
    await db_session.commit()

    response = await client.get(f"/api/v1/sales/lead-finder/lists/{list_id}/export")
    assert response.status_code == 403
    assert "disabled" in response.json()["error"]["message"].lower()


async def test_export_list_records_audit_event_with_row_count(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "export-audit@example.com", "Export Audit Org")
    list_id, _account_id = await _create_company_list_with_one_item(client)

    response = await client.get(f"/api/v1/sales/lead-finder/lists/{list_id}/export")
    assert response.status_code == 200, response.text

    from app.audit.models import AuditEvent

    event = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "sales.lead_finder.list.exported",
                AuditEvent.object_id == list_id,
            )
        )
    ).scalar_one()
    assert event.after_state["row_count"] == 1


async def test_export_list_404_for_list_in_another_organization(client: AsyncClient) -> None:
    await _signup(client, "export-tenant-a@example.com", "Export Tenant A")
    list_id, _account_id = await _create_company_list_with_one_item(client)

    await _signup(client, "export-tenant-b@example.com", "Export Tenant B")
    response = await client.get(f"/api/v1/sales/lead-finder/lists/{list_id}/export")
    assert response.status_code == 404
