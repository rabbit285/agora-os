from __future__ import annotations

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Membership, MembershipRole
from app.core.rbac import get_system_role
from app.identity.models import User
from app.identity.service import create_session
from app.main import app
from app.secops.models import SecurityAsset
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


async def test_critical_incident_gets_an_ai_summary(client: AsyncClient) -> None:
    """spec §69 "Security Incident" chain step "Security AI summarizes" —
    a real AI call (DemoAdapter's honest fallback text in this test
    environment, same as every other uncredentialed AI call)."""
    await _signup(client, "incident-ai1@example.com", "Incident AI Org")
    response = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Unusual outbound traffic", "severity": "critical"},
    )
    assert response.status_code == 201
    assert response.json()["ai_summary"]


async def test_critical_incident_auto_links_at_risk_assets_and_flags_personal_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Chain steps "Finds affected assets" and "Checks personal-data
    impact" — every asset already flagged at_risk/compromised elsewhere
    in the inventory is auto-linked; personal_data_impact is true only
    because one of them is classified confidential/restricted."""
    await _signup(client, "incident-assets1@example.com", "Incident Assets Org")

    healthy_asset = await client.post(
        "/api/v1/security/assets",
        json={"name": "Healthy DB", "asset_type": "database", "data_classification": "internal"},
    )
    at_risk_asset = await client.post(
        "/api/v1/security/assets",
        json={
            "name": "Customer DB",
            "asset_type": "database",
            "data_classification": "confidential",
        },
    )
    assert healthy_asset.status_code == 201
    assert at_risk_asset.status_code == 201
    at_risk_asset_id = at_risk_asset.json()["id"]

    # No endpoint flips asset.status (only a real scan/manual triage
    # would) — set it directly, the same real column a scan would write.
    asset_row = await db_session.get(SecurityAsset, uuid.UUID(at_risk_asset_id))
    assert asset_row is not None
    asset_row.status = "at_risk"
    await db_session.commit()

    response = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Breach affecting customer DB", "severity": "critical"},
    )
    assert response.status_code == 201
    incident = response.json()
    assert incident["personal_data_impact"] is True

    detail = await client.get(f"/api/v1/security/incidents/{incident['id']}")
    linked_asset_ids = {a["id"] for a in detail.json()["affected_assets"]}
    assert linked_asset_ids == {at_risk_asset_id}


async def test_critical_incident_generates_a_communication_draft_and_evidence(
    client: AsyncClient,
) -> None:
    """Chain steps "Generates draft communications" and "Preserves
    evidence" — a real timeline entry (entry_type="communication") and a
    real Evidence row pointing at an uploaded point-in-time snapshot."""
    await _signup(client, "incident-comms1@example.com", "Incident Comms Org")
    created = await client.post(
        "/api/v1/security/incidents",
        json={"title": "Ransomware on payments service", "severity": "critical"},
    )
    incident_id = created.json()["id"]

    detail = await client.get(f"/api/v1/security/incidents/{incident_id}")
    timeline = detail.json()["timeline"]
    communications = [e for e in timeline if e["entry_type"] == "communication"]
    assert len(communications) == 1
    assert communications[0]["body"]

    evidence = await client.get("/api/v1/compliance/evidence")
    matching = [e for e in evidence.json() if e.get("incident_id") == incident_id]
    assert len(matching) == 1
    assert matching[0]["title"] == "Point-in-time snapshot: Ransomware on payments service"


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
