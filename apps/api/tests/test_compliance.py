from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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


async def test_employee_role_cannot_register_ai_system(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "ai-emp1@example.com", "AI System Employee Org")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="employee-ai@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Should fail", "purpose": "irrelevant"},
    )
    assert response.status_code == 403


async def test_ai_governance_manager_role_can_register_ai_system(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "ai-gov1@example.com", "AI Governance Org")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="ai-governance-manager@example.com",
        role_key="ai_governance_manager",
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Manager-registered system", "purpose": "Testing RBAC"},
    )
    assert response.status_code == 201


async def test_registering_high_risk_ai_system_creates_pending_approval(
    client: AsyncClient,
) -> None:
    await _signup(client, "ai1@example.com", "AI System Org")
    response = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Resume Screening AI",
            "vendor": "Some Vendor Inc",
            "purpose": "Ranks job applicants",
            "risk_classification": "high",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "in_review"
    approval_id = body["approval_id"]
    assert approval_id is not None

    approvals = await client.get("/api/v1/approvals")
    matching = next(a for a in approvals.json() if a["id"] == approval_id)
    assert matching["status"] == "pending"
    assert matching["risk_class"] == "high"


async def test_unacceptable_risk_ai_system_requests_critical_approval(
    client: AsyncClient,
) -> None:
    await _signup(client, "ai2@example.com", "AI System Org 2")
    response = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Social Scoring Tool",
            "purpose": "Scores citizens",
            "risk_classification": "unacceptable",
        },
    )
    assert response.status_code == 201
    approval_id = response.json()["approval_id"]

    approvals = await client.get("/api/v1/approvals")
    matching = next(a for a in approvals.json() if a["id"] == approval_id)
    assert matching["risk_class"] == "critical"


async def test_minimal_risk_ai_system_has_no_approval_and_can_be_approved_directly(
    client: AsyncClient,
) -> None:
    await _signup(client, "ai3@example.com", "AI System Org 3")
    created = await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Notes Summarizer", "purpose": "Summarizes meeting notes"},
    )
    assert created.json()["risk_classification"] == "minimal"
    assert created.json()["approval_id"] is None
    system_id = created.json()["id"]

    approved = await client.patch(
        f"/api/v1/compliance/ai-systems/{system_id}/status", json={"status": "approved"}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


async def test_cannot_approve_high_risk_system_before_approval_granted(
    client: AsyncClient,
) -> None:
    await _signup(client, "ai4@example.com", "AI System Org 4")
    created = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Fraud Detection AI",
            "purpose": "Flags suspicious transactions",
            "risk_classification": "high",
        },
    )
    system_id = created.json()["id"]

    blocked = await client.patch(
        f"/api/v1/compliance/ai-systems/{system_id}/status", json={"status": "approved"}
    )
    assert blocked.status_code == 422


async def test_can_approve_high_risk_system_after_approval_granted(
    client: AsyncClient,
) -> None:
    await _signup(client, "ai5@example.com", "AI System Org 5")
    created = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Hiring Ranking AI",
            "purpose": "Ranks candidates",
            "risk_classification": "high",
        },
    )
    system_id = created.json()["id"]
    approval_id = created.json()["approval_id"]

    decision = await client.post(f"/api/v1/approvals/{approval_id}/decide", json={"approve": True})
    assert decision.status_code == 200

    approved = await client.patch(
        f"/api/v1/compliance/ai-systems/{system_id}/status", json={"status": "approved"}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


async def test_ai_system_detail_includes_assessments(client: AsyncClient) -> None:
    await _signup(client, "ai6@example.com", "AI System Org 6")
    created = await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Support Chatbot", "purpose": "Answers customer questions"},
    )
    system_id = created.json()["id"]

    await client.post(
        f"/api/v1/compliance/ai-systems/{system_id}/assessments",
        json={"status": "pass", "notes": "No PII processed."},
    )

    detail = await client.get(f"/api/v1/compliance/ai-systems/{system_id}")
    assert detail.status_code == 200
    assessments = detail.json()["assessments"]
    assert len(assessments) == 1
    assert assessments[0]["status"] == "pass"


async def test_ai_system_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross-ai1@example.com", "Cross AI Org 1")
    created = await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Org 1 AI system", "purpose": "internal"},
    )
    system_id = created.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(other_client, "cross-ai2@example.com", "Cross AI Org 2")

    response = await other_client.get(
        f"/api/v1/compliance/ai-systems/{system_id}",
        headers={"X-Organization-Id": str(other_org_id)},
    )
    assert response.status_code == 404
    await other_client.aclose()


# --- Privacy: ProcessingActivity (RoPA), DPIA, DSAR ---


async def test_employee_role_cannot_create_processing_activity(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "privacy-emp1@example.com", "Privacy Employee Org")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="employee-privacy@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/compliance/processing-activities",
        json={
            "name": "Should fail",
            "purpose": "irrelevant",
            "legal_basis": "consent",
            "data_subjects": "customers",
            "retention_period": "1 year",
        },
    )
    assert response.status_code == 403


async def test_dpo_role_can_create_processing_activity(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "privacy-dpo1@example.com", "Privacy DPO Org")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="dpo1@example.com", role_key="dpo"
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/compliance/processing-activities",
        json={
            "name": "Customer support ticket data",
            "purpose": "Resolve support requests",
            "legal_basis": "contract",
            "data_categories": ["contact_info", "usage_data"],
            "data_subjects": "customers",
            "retention_period": "3 years post-relationship",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["legal_basis"] == "contract"
    assert body["data_categories"] == ["contact_info", "usage_data"]
    assert body["status"] == "active"


async def test_legal_role_can_create_dsar_but_not_control(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`legal` is activated for the first time by this Privacy slice — it
    should get privacy permissions but nothing else (still zero broader
    compliance permissions), same "only what the module grants" discipline
    ai_governance_manager's first activation followed (ADR-0027)."""
    _, org_id = await _signup(client, "privacy-legal1@example.com", "Privacy Legal Org")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="legal1@example.com", role_key="legal"
    )
    client.cookies.set("agora_session", token)

    dsar = await client.post(
        "/api/v1/compliance/dsars",
        json={
            "requester_name": "Jane Doe",
            "requester_email": "jane@example.com",
            "request_type": "access",
        },
    )
    assert dsar.status_code == 201, dsar.text

    forbidden = await client.post(
        "/api/v1/compliance/controls", json={"title": "Should still be forbidden"}
    )
    assert forbidden.status_code == 403


async def test_dsar_creation_sets_a_thirty_day_due_date(client: AsyncClient) -> None:
    await _signup(client, "dsar1@example.com", "DSAR Org 1")
    created_at_floor = datetime.now(UTC)
    response = await client.post(
        "/api/v1/compliance/dsars",
        json={
            "requester_name": "John Smith",
            "requester_email": "john@example.com",
            "request_type": "deletion",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "received"
    assert body["fulfilled_at"] is None

    due_at = datetime.fromisoformat(body["due_at"].replace("Z", "+00:00"))
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=UTC)
    delta = due_at - created_at_floor
    assert timedelta(days=29) < delta < timedelta(days=31)


async def test_dsar_status_lifecycle_sets_fulfilled_at(client: AsyncClient) -> None:
    await _signup(client, "dsar2@example.com", "DSAR Org 2")
    created = await client.post(
        "/api/v1/compliance/dsars",
        json={
            "requester_name": "Requester Two",
            "requester_email": "requester2@example.com",
            "request_type": "access",
        },
    )
    dsar_id = created.json()["id"]

    in_progress = await client.patch(
        f"/api/v1/compliance/dsars/{dsar_id}/status",
        json={"status": "in_progress", "notes": "Gathering records"},
    )
    assert in_progress.status_code == 200
    assert in_progress.json()["fulfilled_at"] is None
    assert in_progress.json()["notes"] == "Gathering records"

    fulfilled = await client.patch(
        f"/api/v1/compliance/dsars/{dsar_id}/status", json={"status": "fulfilled"}
    )
    assert fulfilled.status_code == 200
    assert fulfilled.json()["status"] == "fulfilled"
    assert fulfilled.json()["fulfilled_at"] is not None


async def test_dsar_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross-dsar1@example.com", "Cross DSAR Org 1")
    created = await client.post(
        "/api/v1/compliance/dsars",
        json={
            "requester_name": "Org 1 requester",
            "requester_email": "org1@example.com",
            "request_type": "access",
        },
    )
    dsar_id = created.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(other_client, "cross-dsar2@example.com", "Cross DSAR Org 2")

    response = await other_client.get(
        f"/api/v1/compliance/dsars/{dsar_id}",
        headers={"X-Organization-Id": str(other_org_id)},
    )
    assert response.status_code == 404
    await other_client.aclose()


async def test_high_risk_dpia_created_directly_requires_its_own_approval(
    client: AsyncClient,
) -> None:
    await _signup(client, "dpia1@example.com", "DPIA Org 1")
    created = await client.post(
        "/api/v1/compliance/dpias",
        json={"title": "New marketing analytics pipeline", "risk_level": "high"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    approval_id = body["approval_id"]
    assert approval_id is not None

    blocked = await client.patch(
        f"/api/v1/compliance/dpias/{body['id']}/status", json={"status": "approved"}
    )
    assert blocked.status_code == 422

    decided = await client.post(f"/api/v1/approvals/{approval_id}/decide", json={"approve": True})
    assert decided.status_code == 200

    approved = await client.patch(
        f"/api/v1/compliance/dpias/{body['id']}/status", json={"status": "approved"}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


async def test_low_risk_dpia_has_no_approval_and_approves_directly(client: AsyncClient) -> None:
    await _signup(client, "dpia2@example.com", "DPIA Org 2")
    created = await client.post(
        "/api/v1/compliance/dpias",
        json={"title": "Internal newsletter list", "risk_level": "low"},
    )
    assert created.json()["approval_id"] is None
    dpia_id = created.json()["id"]

    approved = await client.patch(
        f"/api/v1/compliance/dpias/{dpia_id}/status",
        json={"status": "approved", "findings": "No significant risk identified."},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["findings"] == "No significant risk identified."


async def test_dpia_can_link_to_a_processing_activity(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "dpia3@example.com", "DPIA Org 3")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="dpo3@example.com", role_key="dpo"
    )
    client.cookies.set("agora_session", token)

    activity = await client.post(
        "/api/v1/compliance/processing-activities",
        json={
            "name": "Employee background checks",
            "purpose": "Pre-employment screening",
            "legal_basis": "legal_obligation",
            "data_subjects": "job applicants",
            "retention_period": "6 months",
        },
    )
    activity_id = activity.json()["id"]

    dpia = await client.post(
        "/api/v1/compliance/dpias",
        json={
            "title": "Background check vendor DPIA",
            "processing_activity_id": activity_id,
            "risk_level": "medium",
        },
    )
    assert dpia.status_code == 201
    assert dpia.json()["processing_activity_id"] == activity_id
    assert dpia.json()["ai_system_id"] is None


async def test_dpia_rejects_processing_activity_from_another_org(client: AsyncClient) -> None:
    await _signup(client, "dpia4@example.com", "DPIA Org 4")
    response = await client.post(
        "/api/v1/compliance/dpias",
        json={
            "title": "Should fail",
            "processing_activity_id": str(uuid.uuid4()),
            "risk_level": "low",
        },
    )
    assert response.status_code == 404


async def test_registering_high_risk_ai_system_auto_creates_linked_dpia(
    client: AsyncClient,
) -> None:
    """Extends the "New AI Tool Adoption" hook a second time (ADR-0029):
    the same registration that creates an Approval (ADR-0027) also
    creates the chain's "Privacy assessment" step as a real DPIA linked
    via ai_system_id, sharing the AI system's Approval rather than
    duplicating it."""
    await _signup(client, "ai-dpia1@example.com", "AI DPIA Org 1")
    created = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Candidate Scoring Model",
            "purpose": "Scores job candidates automatically",
            "risk_classification": "high",
        },
    )
    assert created.status_code == 201
    system_id = created.json()["id"]

    dpias = await client.get("/api/v1/compliance/dpias")
    assert dpias.status_code == 200
    matching = [d for d in dpias.json() if d["ai_system_id"] == system_id]
    assert len(matching) == 1
    assert matching[0]["status"] == "draft"
    assert matching[0]["risk_level"] == "high"
    assert matching[0]["approval_id"] is None


async def test_minimal_risk_ai_system_does_not_create_a_dpia(client: AsyncClient) -> None:
    await _signup(client, "ai-dpia2@example.com", "AI DPIA Org 2")
    created = await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Internal notes tool", "purpose": "Summarizes meeting notes"},
    )
    system_id = created.json()["id"]

    dpias = await client.get("/api/v1/compliance/dpias")
    matching = [d for d in dpias.json() if d["ai_system_id"] == system_id]
    assert matching == []


# --- AI Incidents ---


async def _register_ai_system(client: AsyncClient, name: str) -> str:
    response = await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": name, "purpose": "Testing AI incidents"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


async def test_employee_role_cannot_create_ai_incident(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "ai-incident-emp1@example.com", "AI Incident Employee Org")
    system_id = await _register_ai_system(client, "Employee-visible system")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="employee-ai-incident@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/compliance/ai-incidents",
        json={"ai_system_id": system_id, "title": "Should fail", "severity": "low"},
    )
    assert response.status_code == 403


async def test_critical_ai_incident_creates_linked_risk(client: AsyncClient) -> None:
    await _signup(client, "ai-incident1@example.com", "AI Incident Org 1")
    system_id = await _register_ai_system(client, "Recommendation Engine")

    response = await client.post(
        "/api/v1/compliance/ai-incidents",
        json={
            "ai_system_id": system_id,
            "title": "Model produced discriminatory recommendations",
            "severity": "critical",
        },
    )
    assert response.status_code == 201, response.text
    incident = response.json()
    assert incident["related_risk_id"] is not None

    risks = await client.get("/api/v1/compliance/risks")
    risk_titles = [r["title"] for r in risks.json()]
    assert any("Model produced discriminatory recommendations" in t for t in risk_titles)


async def test_critical_ai_incident_creates_response_task(client: AsyncClient) -> None:
    await _signup(client, "ai-incident-task1@example.com", "AI Incident Task Org")
    system_id = await _register_ai_system(client, "Fraud Model")

    response = await client.post(
        "/api/v1/compliance/ai-incidents",
        json={
            "ai_system_id": system_id,
            "title": "Model outage during peak hours",
            "severity": "critical",
        },
    )
    assert response.status_code == 201
    incident = response.json()
    assert incident["related_task_id"] is not None

    tasks = await client.get("/api/v1/tasks")
    matching = next(t for t in tasks.json() if t["id"] == incident["related_task_id"])
    assert "Model outage during peak hours" in matching["title"]
    assert matching["module"] == "compliance"
    assert matching["priority"] == "urgent"


async def test_critical_ai_incident_with_owner_notifies_owner(client: AsyncClient) -> None:
    user_id, _ = await _signup(client, "ai-incident-owner1@example.com", "AI Incident Owner Org")
    system_id = await _register_ai_system(client, "Chatbot")

    response = await client.post(
        "/api/v1/compliance/ai-incidents",
        json={
            "ai_system_id": system_id,
            "title": "Chatbot leaked another customer's data",
            "severity": "critical",
            "owner_id": str(user_id),
        },
    )
    assert response.status_code == 201

    notifications = await client.get("/api/v1/notifications")
    assert notifications.status_code == 200
    assert any("Chatbot leaked another customer's data" in n["body"] for n in notifications.json())


async def test_high_severity_ai_incident_does_not_create_risk_or_task(
    client: AsyncClient,
) -> None:
    await _signup(client, "ai-incident2@example.com", "AI Incident Org 2")
    system_id = await _register_ai_system(client, "Support Assistant")

    response = await client.post(
        "/api/v1/compliance/ai-incidents",
        json={
            "ai_system_id": system_id,
            "title": "Occasional hallucinated citation",
            "severity": "high",
        },
    )
    assert response.status_code == 201
    incident = response.json()
    assert incident["related_risk_id"] is None
    assert incident["related_task_id"] is None


async def test_ai_incident_status_lifecycle(client: AsyncClient) -> None:
    await _signup(client, "ai-incident3@example.com", "AI Incident Org 3")
    system_id = await _register_ai_system(client, "Scoring Model")

    created = await client.post(
        "/api/v1/compliance/ai-incidents",
        json={"ai_system_id": system_id, "title": "Minor drift detected", "severity": "low"},
    )
    incident_id = created.json()["id"]
    assert created.json()["status"] == "open"

    updated = await client.patch(
        f"/api/v1/compliance/ai-incidents/{incident_id}/status",
        json={"status": "investigating"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "investigating"

    resolved = await client.patch(
        f"/api/v1/compliance/ai-incidents/{incident_id}/status", json={"status": "resolved"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


async def test_ai_incident_rejects_ai_system_from_another_org(client: AsyncClient) -> None:
    await _signup(client, "ai-incident4@example.com", "AI Incident Org 4")
    response = await client.post(
        "/api/v1/compliance/ai-incidents",
        json={"ai_system_id": str(uuid.uuid4()), "title": "Should fail", "severity": "low"},
    )
    assert response.status_code == 404


async def test_ai_incident_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross-ai-incident1@example.com", "Cross AI Incident Org 1")
    system_id = await _register_ai_system(client, "Org 1 system")
    created = await client.post(
        "/api/v1/compliance/ai-incidents",
        json={"ai_system_id": system_id, "title": "Org 1 incident", "severity": "low"},
    )
    incident_id = created.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(
        other_client, "cross-ai-incident2@example.com", "Cross AI Incident Org 2"
    )

    response = await other_client.get(
        f"/api/v1/compliance/ai-incidents/{incident_id}",
        headers={"X-Organization-Id": str(other_org_id)},
    )
    assert response.status_code == 404
    await other_client.aclose()


# --- Vendor Risk ---


async def test_employee_role_cannot_create_vendor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "vendor-emp1@example.com", "Vendor Employee Org")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="employee-vendor@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)

    response = await client.post("/api/v1/compliance/vendors", json={"name": "Should fail"})
    assert response.status_code == 403


async def test_compliance_manager_can_create_vendor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "vendor-cm1@example.com", "Vendor CM Org")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="cm-vendor@example.com",
        role_key="compliance_manager",
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/compliance/vendors",
        json={"name": "Acme Cloud Storage Inc", "category": "cloud_infrastructure"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["risk_tier"] == "low"
    assert body["status"] == "active"


async def test_critical_vendor_assessment_creates_linked_risk(client: AsyncClient) -> None:
    await _signup(client, "vendor1@example.com", "Vendor Org 1")
    vendor = await client.post("/api/v1/compliance/vendors", json={"name": "Sketchy Analytics LLC"})
    vendor_id = vendor.json()["id"]

    response = await client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/assessments",
        json={"risk_conclusion": "critical", "notes": "No SOC 2 report, data stored unencrypted."},
    )
    assert response.status_code == 201, response.text
    assert response.json()["related_risk_id"] is not None

    risks = await client.get("/api/v1/compliance/risks")
    risk_titles = [r["title"] for r in risks.json()]
    assert any("Sketchy Analytics LLC" in t for t in risk_titles)

    vendor_detail = await client.get(f"/api/v1/compliance/vendors/{vendor_id}")
    assert vendor_detail.json()["risk_tier"] == "critical"
    assert len(vendor_detail.json()["assessments"]) == 1


async def test_low_risk_vendor_assessment_does_not_create_a_risk(client: AsyncClient) -> None:
    await _signup(client, "vendor2@example.com", "Vendor Org 2")
    vendor = await client.post("/api/v1/compliance/vendors", json={"name": "Reliable Vendor Co"})
    vendor_id = vendor.json()["id"]

    response = await client.post(
        f"/api/v1/compliance/vendors/{vendor_id}/assessments",
        json={"risk_conclusion": "low"},
    )
    assert response.status_code == 201
    assert response.json()["related_risk_id"] is None


async def test_vendor_status_lifecycle(client: AsyncClient) -> None:
    await _signup(client, "vendor3@example.com", "Vendor Org 3")
    vendor = await client.post("/api/v1/compliance/vendors", json={"name": "Transitioning Vendor"})
    vendor_id = vendor.json()["id"]

    updated = await client.patch(
        f"/api/v1/compliance/vendors/{vendor_id}/status", json={"status": "under_review"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "under_review"

    offboarded = await client.patch(
        f"/api/v1/compliance/vendors/{vendor_id}/status", json={"status": "offboarded"}
    )
    assert offboarded.status_code == 200
    assert offboarded.json()["status"] == "offboarded"


async def test_evidence_can_attach_to_a_vendor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.core.models import File

    _, org_id = await _signup(client, "vendor-evidence1@example.com", "Vendor Evidence Org")
    vendor = await client.post("/api/v1/compliance/vendors", json={"name": "Documented Vendor Inc"})
    vendor_id = vendor.json()["id"]

    file_record = File(
        organization_id=org_id,
        storage_key="org/vendor/soc2.pdf",
        original_filename="soc2.pdf",
        content_type="application/pdf",
        size_bytes=100,
        uploaded_by=uuid.uuid4(),
    )
    db_session.add(file_record)
    await db_session.commit()

    response = await client.post(
        "/api/v1/compliance/evidence",
        json={
            "file_id": str(file_record.id),
            "title": "SOC 2 Type II report",
            "vendor_id": vendor_id,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["vendor_id"] == vendor_id

    vendor_detail = await client.get(f"/api/v1/compliance/vendors/{vendor_id}")
    assert len(vendor_detail.json()["evidence"]) == 1
    assert vendor_detail.json()["evidence"][0]["title"] == "SOC 2 Type II report"


async def test_vendor_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross-vendor1@example.com", "Cross Vendor Org 1")
    vendor = await client.post("/api/v1/compliance/vendors", json={"name": "Org 1 vendor"})
    vendor_id = vendor.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(other_client, "cross-vendor2@example.com", "Cross Vendor Org 2")

    response = await other_client.get(
        f"/api/v1/compliance/vendors/{vendor_id}",
        headers={"X-Organization-Id": str(other_org_id)},
    )
    assert response.status_code == 404
    await other_client.aclose()


# --- Security Questionnaires ---


async def _create_questionnaire(client: AsyncClient, title: str) -> str:
    response = await client.post("/api/v1/compliance/questionnaires", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


async def test_employee_role_cannot_create_questionnaire(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "quest-emp1@example.com", "Questionnaire Employee Org")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="employee-quest@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)

    response = await client.post("/api/v1/compliance/questionnaires", json={"title": "Should fail"})
    assert response.status_code == 403


async def test_compliance_manager_can_create_questionnaire_and_add_question(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "quest-cm1@example.com", "Questionnaire CM Org")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="cm-quest@example.com",
        role_key="compliance_manager",
    )
    client.cookies.set("agora_session", token)

    questionnaire = await client.post(
        "/api/v1/compliance/questionnaires",
        json={"title": "Acme Corp security questionnaire", "source": "customer_provided"},
    )
    assert questionnaire.status_code == 201, questionnaire.text
    questionnaire_id = questionnaire.json()["id"]

    question = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire_id}/questions",
        json={"text": "Do you encrypt data at rest?", "category": "security"},
    )
    assert question.status_code == 201, question.text

    detail = await client.get(f"/api/v1/compliance/questionnaires/{questionnaire_id}")
    assert detail.status_code == 200
    assert len(detail.json()["questions"]) == 1
    assert detail.json()["questions"][0]["answer"]["status"] == "missing"


async def test_suggest_answer_without_knowledge_returns_honest_no_evidence_message(
    client: AsyncClient,
) -> None:
    """No documents are indexed for this fresh org, so the real AI Copilot
    call (not mocked) honestly reports it has no evidence rather than
    fabricating an answer (spec §82)."""
    await _signup(client, "quest1@example.com", "Questionnaire Org 1")
    questionnaire_id = await _create_questionnaire(client, "Vendor security review")
    question = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire_id}/questions",
        json={"text": "Do you have a SOC 2 report?", "category": "security"},
    )
    question_id = question.json()["id"]

    suggested = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire_id}/questions/{question_id}/suggest-answer"
    )
    assert suggested.status_code == 200, suggested.text
    body = suggested.json()
    assert body["source_type"] == "ai_suggested"
    assert body["status"] == "draft"
    assert "don't have any indexed documents" in body["answer_text"]


async def test_manual_answer_approval_lets_a_later_identical_question_reuse_it(
    client: AsyncClient,
) -> None:
    await _signup(client, "quest2@example.com", "Questionnaire Org 2")

    first_questionnaire_id = await _create_questionnaire(client, "First customer review")
    first_question = await client.post(
        f"/api/v1/compliance/questionnaires/{first_questionnaire_id}/questions",
        json={"text": "Where is customer data hosted?", "category": "compliance"},
    )
    first_question_id = first_question.json()["id"]

    manual_answer = await client.patch(
        f"/api/v1/compliance/questionnaires/{first_questionnaire_id}/questions/{first_question_id}/answer",
        json={
            "answer_text": "All customer data is hosted in AWS eu-central-1.",
            "status": "approved",
        },
    )
    assert manual_answer.status_code == 200, manual_answer.text

    second_questionnaire_id = await _create_questionnaire(client, "Second customer review")
    second_question = await client.post(
        f"/api/v1/compliance/questionnaires/{second_questionnaire_id}/questions",
        json={"text": "Where is customer data hosted?", "category": "compliance"},
    )
    second_question_id = second_question.json()["id"]

    suggested = await client.post(
        f"/api/v1/compliance/questionnaires/{second_questionnaire_id}/questions/{second_question_id}/suggest-answer"
    )
    assert suggested.status_code == 200, suggested.text
    body = suggested.json()
    assert body["source_type"] == "reused_from_library"
    assert body["status"] == "draft"
    assert body["answer_text"] == "All customer data is hosted in AWS eu-central-1."


async def test_questionnaire_status_lifecycle(client: AsyncClient) -> None:
    await _signup(client, "quest3@example.com", "Questionnaire Org 3")
    questionnaire_id = await _create_questionnaire(client, "Status lifecycle test")

    updated = await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire_id}/status",
        json={"status": "in_progress"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "in_progress"

    completed = await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire_id}/status",
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


async def test_questionnaire_rejects_opportunity_from_another_org(client: AsyncClient) -> None:
    await _signup(client, "quest4@example.com", "Questionnaire Org 4")
    response = await client.post(
        "/api/v1/compliance/questionnaires",
        json={"title": "Should fail", "opportunity_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


async def test_questionnaire_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross-quest1@example.com", "Cross Questionnaire Org 1")
    questionnaire_id = await _create_questionnaire(client, "Org 1 questionnaire")

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(
        other_client, "cross-quest2@example.com", "Cross Questionnaire Org 2"
    )

    response = await other_client.get(
        f"/api/v1/compliance/questionnaires/{questionnaire_id}",
        headers={"X-Organization-Id": str(other_org_id)},
    )
    assert response.status_code == 404
    await other_client.aclose()
