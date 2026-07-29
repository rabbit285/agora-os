from __future__ import annotations

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Membership, MembershipRole
from app.core.rbac import get_system_role
from app.identity.models import User
from app.identity.service import create_session
from app.main import app
from app.security import hash_password


async def _signup(client: AsyncClient, email: str, org_name: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Security Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


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


async def test_org_admin_can_create_asset(client: AsyncClient) -> None:
    await _signup(client, "asset1@example.com", "Asset Org")
    response = await client.post(
        "/api/v1/security/assets", json={"name": "prod-db", "asset_type": "database"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "healthy"


async def test_employee_role_cannot_create_asset(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "asset2@example.com", "Asset Org 2")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="employee-sec@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/security/assets", json={"name": "should-fail", "asset_type": "server"}
    )
    assert response.status_code == 403


async def test_security_manager_role_can_create_finding(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "finding1@example.com", "Finding Org")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="security-manager@example.com",
        role_key="security_manager",
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/security/findings",
        json={"title": "Exposed port 22", "category": "cloud_misconfiguration", "severity": "high"},
    )
    assert response.status_code == 201


async def test_critical_incident_creates_linked_compliance_risk(client: AsyncClient) -> None:
    await _signup(client, "incident1@example.com", "Incident Org")

    response = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Ransomware detected on file server", "severity": "critical"},
    )
    assert response.status_code == 201
    incident = response.json()
    assert incident["related_risk_id"] is not None

    risks = await client.get("/api/v1/compliance/risks")
    risk_titles = [r["title"] for r in risks.json()]
    assert any("Ransomware detected on file server" in t for t in risk_titles)


async def test_critical_incident_creates_response_task(client: AsyncClient) -> None:
    await _signup(client, "incident-task1@example.com", "Incident Task Org")

    response = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Data exfiltration suspected", "severity": "critical"},
    )
    assert response.status_code == 201
    incident = response.json()
    assert incident["related_task_id"] is not None

    tasks = await client.get("/api/v1/tasks")
    matching = next(t for t in tasks.json() if t["id"] == incident["related_task_id"])
    assert "Data exfiltration suspected" in matching["title"]
    assert matching["module"] == "security"
    assert matching["priority"] == "urgent"


async def test_critical_incident_with_owner_notifies_owner(client: AsyncClient) -> None:
    user_id, _ = await _signup(client, "incident-owner1@example.com", "Incident Owner Org")

    response = await client.post(
        "/api/v1/security/incidents",
        json={
            "title": "Credential stuffing attack",
            "severity": "critical",
            "owner_id": str(user_id),
        },
    )
    assert response.status_code == 201

    notifications = await client.get("/api/v1/notifications")
    assert notifications.status_code == 200
    assert any("Credential stuffing attack" in n["body"] for n in notifications.json())


async def test_high_severity_incident_does_not_create_risk_or_task(client: AsyncClient) -> None:
    await _signup(client, "incident2@example.com", "Incident Org 2")

    response = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Suspicious login attempt", "severity": "high"},
    )
    assert response.status_code == 201
    assert response.json()["related_risk_id"] is None
    assert response.json()["related_task_id"] is None

    risks = await client.get("/api/v1/compliance/risks")
    assert risks.json() == []


async def test_incident_status_workflow(client: AsyncClient) -> None:
    await _signup(client, "incident3@example.com", "Incident Org 3")
    created = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Phishing email reported", "severity": "medium"},
    )
    incident_id = created.json()["id"]
    assert created.json()["status"] == "detected"

    updated = await client.patch(
        f"/api/v1/security/incidents/{incident_id}", json={"status": "triage"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "triage"

    closed = await client.patch(
        f"/api/v1/security/incidents/{incident_id}", json={"status": "closed"}
    )
    assert closed.json()["closed_at"] is not None


async def test_incident_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross-sec1@example.com", "Cross Sec Org 1")
    incident = await client.post(
        "/api/v1/security/incidents", json={"title": "Org 1 incident", "severity": "low"}
    )
    incident_id = incident.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(other_client, "cross-sec2@example.com", "Cross Sec Org 2")

    response = await other_client.get(
        f"/api/v1/security/incidents/{incident_id}",
        headers={"X-Organization-Id": str(other_org_id)},
    )
    assert response.status_code == 404
    await other_client.aclose()


async def test_finding_status_lifecycle(client: AsyncClient) -> None:
    await _signup(client, "finding2@example.com", "Finding Org 2")
    created = await client.post(
        "/api/v1/security/findings",
        json={"title": "Outdated TLS version", "category": "vulnerability", "severity": "medium"},
    )
    finding_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/security/findings/{finding_id}", json={"status": "resolved"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"
