from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Membership, MembershipRole
from app.core.rbac import get_system_role
from app.identity.models import User
from app.sales.icp import compute_icp_score
from app.sales.models import Account, ICPProfile
from app.security import hash_password


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "ICP Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _create_member_with_role(
    db_session: AsyncSession, *, organization_id: uuid.UUID, email: str, role_key: str
) -> str:
    from app.identity.service import create_session

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


def test_compute_icp_score_full_match() -> None:
    profile = ICPProfile(
        target_industries=["fintech"], min_employee_count=50, max_employee_count=500
    )
    account = Account(name="Acme", industry="fintech", employee_count=200)
    assert compute_icp_score(account, profile) == 100.0


def test_compute_icp_score_no_industry_match_and_out_of_range() -> None:
    profile = ICPProfile(
        target_industries=["fintech"], min_employee_count=50, max_employee_count=500
    )
    account = Account(name="Acme", industry="retail", employee_count=5000)
    score = compute_icp_score(account, profile)
    assert score == 0.0


def test_compute_icp_score_empty_profile_gives_full_credit() -> None:
    profile = ICPProfile(target_industries=[], min_employee_count=None, max_employee_count=None)
    account = Account(name="Acme", industry="anything", employee_count=1)
    assert compute_icp_score(account, profile) == 100.0


def test_compute_icp_score_missing_account_data_scores_zero_on_that_axis() -> None:
    profile = ICPProfile(
        target_industries=["fintech"], min_employee_count=50, max_employee_count=500
    )
    account = Account(name="Acme", industry=None, employee_count=None)
    assert compute_icp_score(account, profile) == 0.0


async def test_no_profile_leaves_icp_score_none(client: AsyncClient) -> None:
    await _signup(client, "icp1@example.com", "ICP Org 1")
    account = await client.post(
        "/api/v1/sales/accounts", json={"name": "No Profile Co", "industry": "fintech"}
    )
    assert account.status_code == 201
    assert account.json()["icp_score"] is None

    profile = await client.get("/api/v1/sales/icp-profile")
    assert profile.status_code == 200
    assert profile.json() is None


async def test_saving_profile_rescores_existing_accounts(client: AsyncClient) -> None:
    await _signup(client, "icp2@example.com", "ICP Org 2")
    await client.post(
        "/api/v1/sales/accounts",
        json={"name": "Fintech Co", "industry": "fintech", "employee_count": 100},
    )
    await client.post(
        "/api/v1/sales/accounts",
        json={"name": "Retail Co", "industry": "retail", "employee_count": 100},
    )

    saved = await client.put(
        "/api/v1/sales/icp-profile",
        json={
            "target_industries": ["fintech"],
            "min_employee_count": 50,
            "max_employee_count": 500,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["target_industries"] == ["fintech"]

    accounts = (await client.get("/api/v1/sales/accounts")).json()
    fintech = next(a for a in accounts if a["name"] == "Fintech Co")
    retail = next(a for a in accounts if a["name"] == "Retail Co")
    assert fintech["icp_score"] == 100.0
    assert retail["icp_score"] == 50.0


async def test_new_account_created_after_profile_is_scored_immediately(client: AsyncClient) -> None:
    await _signup(client, "icp3@example.com", "ICP Org 3")
    await client.put(
        "/api/v1/sales/icp-profile",
        json={
            "target_industries": ["saas"],
            "min_employee_count": None,
            "max_employee_count": None,
        },
    )

    account = await client.post(
        "/api/v1/sales/accounts", json={"name": "SaaS Co", "industry": "saas"}
    )
    assert account.status_code == 201
    assert account.json()["icp_score"] == 100.0


async def test_employee_role_cannot_save_icp_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "icp4@example.com", "ICP Org 4")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="employee-icp@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)

    response = await client.put(
        "/api/v1/sales/icp-profile",
        json={"target_industries": [], "min_employee_count": None, "max_employee_count": None},
    )
    assert response.status_code == 403


async def test_enrichment_reports_not_configured_without_clearbit_key(client: AsyncClient) -> None:
    await _signup(client, "enrich1@example.com", "Enrich Org 1")
    account = await client.post(
        "/api/v1/sales/accounts", json={"name": "Enrich Co", "website": "https://example.com"}
    )
    account_id = account.json()["id"]

    result = await client.post(f"/api/v1/sales/accounts/{account_id}/enrich")
    assert result.status_code == 200
    assert result.json() == {"configured": False, "updated_fields": []}
