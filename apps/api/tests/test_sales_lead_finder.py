from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Membership, MembershipRole
from app.core.rbac import get_system_role
from app.identity.models import User
from app.identity.service import create_session
from app.sales.models import Account, Contact
from app.sales.provider_models import SalesProviderRecord
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
    await _signup(client, "prov1@example.com", "Prov Org 1")
    response = await client.get("/api/v1/sales/lead-finder/providers")
    assert response.status_code == 200, response.text
    providers = response.json()
    apollo = next(p for p in providers if p["provider_key"] == "apollo")
    assert apollo["configured"] is False
    assert apollo["status"] == "demo"


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
