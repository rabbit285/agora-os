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
            "full_name": "Automation Tester",
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


async def _create_workflow(client: AsyncClient, *, name: str, steps: list[dict]) -> str:
    response = await client.post(
        "/api/v1/automation/workflows", json={"name": name, "steps": steps}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


async def _activate(client: AsyncClient, workflow_id: str) -> None:
    response = await client.patch(
        f"/api/v1/automation/workflows/{workflow_id}/status", json={"status": "active"}
    )
    assert response.status_code == 200, response.text


async def test_org_admin_can_create_workflow(client: AsyncClient) -> None:
    await _signup(client, "wf1@example.com", "Workflow Org")
    workflow_id = await _create_workflow(
        client,
        name="Simple task workflow",
        steps=[{"step_type": "create_task", "config": {"title": "Do a thing"}}],
    )
    assert workflow_id


async def test_employee_role_cannot_create_workflow(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "wf2@example.com", "Workflow Org 2")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="employee-wf@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/automation/workflows",
        json={"name": "Should fail", "steps": [{"step_type": "create_task", "config": {}}]},
    )
    assert response.status_code == 403


async def test_automation_manager_role_can_create_workflow(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "wf3@example.com", "Workflow Org 3")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="automation-manager@example.com",
        role_key="automation_manager",
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/automation/workflows",
        json={"name": "Manager workflow", "steps": [{"step_type": "create_task", "config": {}}]},
    )
    assert response.status_code == 201


async def test_steps_cannot_be_edited_once_active(client: AsyncClient) -> None:
    await _signup(client, "wf4@example.com", "Workflow Org 4")
    workflow_id = await _create_workflow(
        client, name="Gate test", steps=[{"step_type": "create_task", "config": {}}]
    )
    await _activate(client, workflow_id)

    response = await client.patch(
        f"/api/v1/automation/workflows/{workflow_id}/steps",
        json={"steps": [{"step_type": "send_notification", "config": {}}]},
    )
    assert response.status_code == 409


async def test_only_active_workflows_can_run(client: AsyncClient) -> None:
    await _signup(client, "wf5@example.com", "Workflow Org 5")
    workflow_id = await _create_workflow(
        client, name="Still draft", steps=[{"step_type": "create_task", "config": {}}]
    )

    response = await client.post(f"/api/v1/automation/workflows/{workflow_id}/run", json={})
    assert response.status_code == 409


async def test_run_with_no_approval_step_succeeds_immediately(client: AsyncClient) -> None:
    await _signup(client, "wf6@example.com", "Workflow Org 6")
    workflow_id = await _create_workflow(
        client,
        name="Happy path",
        steps=[
            {"step_type": "create_task", "config": {"title": "Task one"}},
            {"step_type": "send_notification", "config": {"title": "Done", "body": "All set"}},
        ],
    )
    await _activate(client, workflow_id)

    run = await client.post(f"/api/v1/automation/workflows/{workflow_id}/run", json={})
    assert run.status_code == 201, run.text
    assert run.json()["status"] == "succeeded"

    detail = await client.get(f"/api/v1/automation/runs/{run.json()['id']}")
    assert detail.status_code == 200
    step_runs = detail.json()["step_runs"]
    assert len(step_runs) == 2
    assert all(s["status"] == "succeeded" for s in step_runs)


async def test_human_approval_step_creates_approval_and_pauses_run(client: AsyncClient) -> None:
    await _signup(client, "wf7@example.com", "Workflow Org 7")
    workflow_id = await _create_workflow(
        client,
        name="Needs approval",
        steps=[
            {"step_type": "create_task", "config": {"title": "Prep"}},
            {
                "step_type": "human_approval",
                "config": {"action_type": "Approve the thing", "risk_class": "high"},
            },
            {"step_type": "create_task", "config": {"title": "Finalize"}},
        ],
    )
    await _activate(client, workflow_id)

    run = await client.post(f"/api/v1/automation/workflows/{workflow_id}/run", json={})
    assert run.status_code == 201
    run_id = run.json()["id"]
    assert run.json()["status"] == "awaiting_approval"

    detail = await client.get(f"/api/v1/automation/runs/{run_id}")
    step_runs = detail.json()["step_runs"]
    assert len(step_runs) == 2  # first task step + the paused approval step
    assert step_runs[0]["status"] == "succeeded"
    assert step_runs[1]["status"] == "awaiting_approval"
    approval_id = step_runs[1]["approval_id"]
    assert approval_id is not None

    approvals = await client.get("/api/v1/approvals")
    assert any(a["id"] == approval_id for a in approvals.json())

    # resuming before a decision is a no-op, still awaiting approval
    resumed = await client.post(f"/api/v1/automation/runs/{run_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "awaiting_approval"

    decision = await client.post(f"/api/v1/approvals/{approval_id}/decide", json={"approve": True})
    assert decision.status_code == 200

    resumed_after_approval = await client.post(f"/api/v1/automation/runs/{run_id}/resume")
    assert resumed_after_approval.status_code == 200
    assert resumed_after_approval.json()["status"] == "succeeded"

    final_detail = await client.get(f"/api/v1/automation/runs/{run_id}")
    assert len(final_detail.json()["step_runs"]) == 3


async def test_rejected_approval_fails_the_run(client: AsyncClient) -> None:
    await _signup(client, "wf8@example.com", "Workflow Org 8")
    workflow_id = await _create_workflow(
        client,
        name="Will be rejected",
        steps=[{"step_type": "human_approval", "config": {"action_type": "Risky action"}}],
    )
    await _activate(client, workflow_id)

    run = await client.post(f"/api/v1/automation/workflows/{workflow_id}/run", json={})
    run_id = run.json()["id"]
    step_runs = (await client.get(f"/api/v1/automation/runs/{run_id}")).json()["step_runs"]
    approval_id = step_runs[0]["approval_id"]

    await client.post(f"/api/v1/approvals/{approval_id}/decide", json={"approve": False})
    resumed = await client.post(f"/api/v1/automation/runs/{run_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "failed"


async def test_workflow_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross-wf1@example.com", "Cross Workflow Org 1")
    workflow_id = await _create_workflow(
        client, name="Org 1 workflow", steps=[{"step_type": "create_task", "config": {}}]
    )

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(other_client, "cross-wf2@example.com", "Cross Workflow Org 2")

    response = await other_client.get(
        f"/api/v1/automation/workflows/{workflow_id}",
        headers={"X-Organization-Id": str(other_org_id)},
    )
    assert response.status_code == 404
    await other_client.aclose()
