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
from app.seed import _ensure_compliance_catalog


async def _signup(client: AsyncClient, email: str, org_name: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Compliance Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


async def test_catalog_frameworks_are_listable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _ensure_compliance_catalog(db_session)
    await _signup(client, "framework1@example.com", "Framework Org")

    response = await client.get("/api/v1/compliance/frameworks")
    assert response.status_code == 200
    names = {f["name"] for f in response.json()}
    assert {"GDPR", "EU AI Act", "ISO 27001"} <= names


async def test_org_admin_can_create_control(client: AsyncClient) -> None:
    await _signup(client, "control1@example.com", "Control Org")
    response = await client.post("/api/v1/compliance/controls", json={"title": "Access review"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "not_started"


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


async def test_employee_role_cannot_create_control(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "control2@example.com", "Control Org 2")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="employee2@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/compliance/controls", json={"title": "Should be forbidden"}
    )
    assert response.status_code == 403


async def test_compliance_manager_role_can_create_control(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "control3@example.com", "Control Org 3")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="compliance-manager@example.com",
        role_key="compliance_manager",
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/compliance/controls", json={"title": "Vendor security review"}
    )
    assert response.status_code == 201


async def test_failed_assessment_creates_remediation_task(client: AsyncClient) -> None:
    await _signup(client, "assess1@example.com", "Assessment Org")
    control = await client.post(
        "/api/v1/compliance/controls", json={"title": "Backup restore test"}
    )
    control_id = control.json()["id"]

    response = await client.post(
        f"/api/v1/compliance/controls/{control_id}/assessments",
        json={"status": "fail", "notes": "Restore test failed."},
    )
    assert response.status_code == 201

    tasks = await client.get("/api/v1/tasks")
    compliance_tasks = [t for t in tasks.json() if t["module"] == "compliance"]
    assert any("Backup restore test" in t["title"] for t in compliance_tasks)

    control_detail = await client.get(f"/api/v1/compliance/controls/{control_id}")
    assert control_detail.json()["status"] == "needs_review"


async def test_passed_assessment_does_not_create_task(client: AsyncClient) -> None:
    await _signup(client, "assess2@example.com", "Assessment Org 2")
    control = await client.post("/api/v1/compliance/controls", json={"title": "MFA enforcement"})
    control_id = control.json()["id"]

    await client.post(
        f"/api/v1/compliance/controls/{control_id}/assessments", json={"status": "pass"}
    )

    tasks = await client.get("/api/v1/tasks")
    compliance_tasks = [t for t in tasks.json() if t["module"] == "compliance"]
    assert compliance_tasks == []

    control_detail = await client.get(f"/api/v1/compliance/controls/{control_id}")
    assert control_detail.json()["status"] == "implemented"


async def test_control_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross1@example.com", "Cross Org 1")
    control = await client.post("/api/v1/compliance/controls", json={"title": "Org 1 control"})
    control_id = control.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(other_client, "cross2@example.com", "Cross Org 2")

    response = await other_client.get(
        f"/api/v1/compliance/controls/{control_id}",
        headers={"X-Organization-Id": str(other_org_id)},
    )
    assert response.status_code == 404
    await other_client.aclose()


async def test_evidence_rejects_file_from_another_org(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.core.models import File

    _, org_id = await _signup(client, "evidence1@example.com", "Evidence Org")

    other_org_file = File(
        organization_id=uuid.uuid4(),
        storage_key="org/other/secret.txt",
        original_filename="secret.txt",
        content_type="text/plain",
        size_bytes=10,
        uploaded_by=uuid.uuid4(),
    )
    db_session.add(other_org_file)
    await db_session.flush()

    response = await client.post(
        "/api/v1/compliance/evidence",
        json={"file_id": str(other_org_file.id), "title": "Should be rejected"},
    )
    assert response.status_code == 404


async def test_risk_lifecycle(client: AsyncClient) -> None:
    await _signup(client, "risk1@example.com", "Risk Org")
    created = await client.post(
        "/api/v1/compliance/risks",
        json={"title": "Unpatched CVE", "likelihood": "high", "impact": "high"},
    )
    assert created.status_code == 201
    risk_id = created.json()["id"]
    assert created.json()["status"] == "open"

    updated = await client.patch(
        f"/api/v1/compliance/risks/{risk_id}", json={"status": "mitigated"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "mitigated"
