from __future__ import annotations

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Policy
from app.core.models import Membership, MembershipRole
from app.core.rbac import get_system_role
from app.identity.models import User
from app.identity.service import create_session
from app.main import app
from app.security import hash_password


async def _signup(
    client: AsyncClient, email: str, org_name: str
) -> tuple[uuid.UUID, uuid.UUID, str]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Trust Center Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return (
        uuid.UUID(body["user"]["id"]),
        uuid.UUID(body["organization"]["id"]),
        body["organization"]["slug"],
    )


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


async def test_employee_role_cannot_set_trust_center_item(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id, _ = await _signup(client, "trust-emp1@example.com", "Trust Employee Org")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="employee-trust@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/trust-center/items",
        json={"category": "security_overview", "title": "Should fail"},
    )
    assert response.status_code == 403


async def test_compliance_manager_can_set_and_update_trust_center_item(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id, _ = await _signup(client, "trust-cm1@example.com", "Trust CM Org")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="cm-trust@example.com",
        role_key="compliance_manager",
    )
    client.cookies.set("agora_session", token)

    created = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "security_overview",
            "title": "Security Overview",
            "content": "We take security seriously.",
            "status": "implemented",
            "is_public": True,
        },
    )
    assert created.status_code == 201, created.text

    # Updating in place: same category, so the same row is rewritten
    # rather than a second one appearing.
    updated = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "security_overview",
            "title": "Security Overview",
            "content": "Updated content.",
            "status": "in_progress",
            "is_public": True,
        },
    )
    assert updated.status_code == 201, updated.text
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["status"] == "in_progress"

    # But an attested status is not a status the product will take on
    # trust. This test previously asserted that 'certified' could be set
    # freely; the attestation guard now refuses it, and the guard is
    # right — being certified is something an auditor does, not something
    # implemented controls imply.
    claimed = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "security_overview",
            "title": "Security Overview",
            "content": "Updated content.",
            "status": "certified",
            "is_public": True,
        },
    )
    assert claimed.status_code == 422
    assert "attach" in claimed.json()["error"]["message"].lower()

    listed = await client.get("/api/v1/trust-center/items")
    assert len(listed.json()) == 1
    assert listed.json()[0]["status"] == "in_progress"


async def test_public_endpoint_returns_only_public_items(client: AsyncClient) -> None:
    _, _, org_slug = await _signup(client, "trust-pub1@example.com", "Trust Public Org")

    await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "security_overview",
            "title": "Public item",
            "content": "Visible.",
            "is_public": True,
        },
    )
    await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "availability",
            "title": "Private item",
            "content": "Hidden.",
            "is_public": False,
        },
    )

    transport = ASGITransport(app=app)
    anonymous_client = AsyncClient(transport=transport, base_url="http://test")
    response = await anonymous_client.get(f"/api/v1/trust-center/public/{org_slug}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["organization_name"] == "Trust Public Org"
    categories = [item["category"] for item in body["items"]]
    assert categories == ["security_overview"]
    await anonymous_client.aclose()


async def test_public_endpoint_only_surfaces_a_published_linked_policy(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id, org_slug = await _signup(client, "trust-policy1@example.com", "Trust Policy Org")

    draft_policy = Policy(organization_id=org_id, title="Draft DPA template", status="draft")
    published_policy = Policy(
        organization_id=org_id, title="Published Security Policy", status="published"
    )
    db_session.add_all([draft_policy, published_policy])
    await db_session.commit()

    await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "dpa_availability",
            "title": "DPA availability",
            "is_public": True,
            "policy_id": str(draft_policy.id),
        },
    )
    await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "security_overview",
            "title": "Security overview",
            "is_public": True,
            "policy_id": str(published_policy.id),
        },
    )

    transport = ASGITransport(app=app)
    anonymous_client = AsyncClient(transport=transport, base_url="http://test")
    response = await anonymous_client.get(f"/api/v1/trust-center/public/{org_slug}")
    assert response.status_code == 200
    items_by_category = {item["category"]: item for item in response.json()["items"]}
    assert items_by_category["dpa_availability"]["policy"] is None
    assert items_by_category["security_overview"]["policy"]["title"] == "Published Security Policy"
    await anonymous_client.aclose()


async def test_public_endpoint_returns_404_for_unknown_org_slug(client: AsyncClient) -> None:
    transport = ASGITransport(app=app)
    anonymous_client = AsyncClient(transport=transport, base_url="http://test")
    response = await anonymous_client.get("/api/v1/trust-center/public/no-such-org")
    assert response.status_code == 404
    await anonymous_client.aclose()


async def test_submit_evidence_request_creates_task_with_no_auth(client: AsyncClient) -> None:
    _, org_id, org_slug = await _signup(client, "trust-evidence1@example.com", "Trust Evidence Org")

    transport = ASGITransport(app=app)
    anonymous_client = AsyncClient(transport=transport, base_url="http://test")
    response = await anonymous_client.post(
        f"/api/v1/trust-center/public/{org_slug}/evidence-requests",
        json={
            "requester_name": "Priya Nandakumar",
            "requester_email": "priya@prospect.example",
            "company_name": "Prospect Robotics",
            "message": "Please share your latest SOC 2 report.",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "open"
    assert body["related_task_id"] is not None
    await anonymous_client.aclose()

    tasks = await client.get("/api/v1/tasks")
    matching = next(t for t in tasks.json() if t["id"] == body["related_task_id"])
    assert "Priya Nandakumar" in matching["title"]
    assert matching["module"] == "compliance"


async def test_evidence_request_status_lifecycle(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id, org_slug = await _signup(
        client, "trust-evidence2@example.com", "Trust Evidence Org 2"
    )

    transport = ASGITransport(app=app)
    anonymous_client = AsyncClient(transport=transport, base_url="http://test")
    created = await anonymous_client.post(
        f"/api/v1/trust-center/public/{org_slug}/evidence-requests",
        json={"requester_name": "Someone", "requester_email": "someone@example.com"},
    )
    await anonymous_client.aclose()
    request_id = created.json()["id"]

    fulfilled = await client.patch(
        f"/api/v1/trust-center/evidence-requests/{request_id}/status",
        json={"status": "fulfilled"},
    )
    assert fulfilled.status_code == 200
    assert fulfilled.json()["status"] == "fulfilled"

    listed = await client.get("/api/v1/trust-center/evidence-requests")
    assert len(listed.json()) == 1


async def test_employee_role_cannot_fulfill_evidence_request(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id, org_slug = await _signup(
        client, "trust-evidence3@example.com", "Trust Evidence Org 3"
    )

    transport = ASGITransport(app=app)
    anonymous_client = AsyncClient(transport=transport, base_url="http://test")
    created = await anonymous_client.post(
        f"/api/v1/trust-center/public/{org_slug}/evidence-requests",
        json={"requester_name": "Someone", "requester_email": "someone@example.com"},
    )
    await anonymous_client.aclose()
    request_id = created.json()["id"]

    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="employee-evidence@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)

    response = await client.patch(
        f"/api/v1/trust-center/evidence-requests/{request_id}/status",
        json={"status": "fulfilled"},
    )
    assert response.status_code == 403


async def test_trust_center_item_rejects_unknown_category(client: AsyncClient) -> None:
    await _signup(client, "trust-bad-category@example.com", "Trust Bad Category Org")

    response = await client.post(
        "/api/v1/trust-center/items",
        json={"category": "not_a_real_category", "title": "Should fail"},
    )
    assert response.status_code == 422


async def test_trust_center_item_rejects_policy_from_another_org(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, _ = await _signup(client, "trust-cross1@example.com", "Trust Cross Org 1")

    other_org_policy = Policy(
        organization_id=uuid.uuid4(), title="Someone else's policy", status="published"
    )
    db_session.add(other_org_policy)
    await db_session.commit()

    response = await client.post(
        "/api/v1/trust-center/items",
        json={
            "category": "security_overview",
            "title": "Should fail",
            "policy_id": str(other_org_policy.id),
        },
    )
    assert response.status_code == 404
