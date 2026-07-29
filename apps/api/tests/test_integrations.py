from __future__ import annotations

import hashlib
import hmac
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Membership, MembershipRole
from app.core.rbac import get_system_role
from app.identity.models import User
from app.identity.service import create_session
from app.security import hash_password


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


async def _signup(client: AsyncClient, email: str, org_name: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Integrations Tester",
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


async def _create_workflow(client: AsyncClient, *, name: str, trigger_type: str = "manual") -> str:
    response = await client.post(
        "/api/v1/automation/workflows",
        json={
            "name": name,
            "trigger_type": trigger_type,
            "steps": [{"step_type": "create_task", "config": {"title": "Follow up"}}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


async def _activate_workflow(client: AsyncClient, workflow_id: str) -> None:
    response = await client.patch(
        f"/api/v1/automation/workflows/{workflow_id}/status", json={"status": "active"}
    )
    assert response.status_code == 200, response.text


async def test_org_admin_can_create_connection(client: AsyncClient) -> None:
    await _signup(client, "conn1@example.com", "Connection Org")
    response = await client.post("/api/v1/integrations/connections", json={"name": "My Webhook"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["connector_key"] == "webhook"
    assert body["status"] == "active"
    assert len(body["webhook_secret"]) == 64


async def test_employee_role_cannot_create_connection(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "conn2@example.com", "Connection Org 2")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="employee-conn@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)

    response = await client.post("/api/v1/integrations/connections", json={"name": "Should fail"})
    assert response.status_code == 403


async def test_cannot_link_connection_to_non_webhook_workflow(client: AsyncClient) -> None:
    await _signup(client, "conn3@example.com", "Connection Org 3")
    workflow_id = await _create_workflow(client, name="Manual workflow")  # default trigger_type

    connection = await client.post("/api/v1/integrations/connections", json={"name": "Bad link"})
    connection_id = connection.json()["id"]

    response = await client.patch(
        f"/api/v1/integrations/connections/{connection_id}",
        json={"linked_workflow_id": workflow_id},
    )
    assert response.status_code == 422


async def test_verified_webhook_triggers_linked_workflow(client: AsyncClient) -> None:
    await _signup(client, "conn4@example.com", "Connection Org 4")
    workflow_id = await _create_workflow(client, name="Webhook workflow", trigger_type="webhook")
    await _activate_workflow(client, workflow_id)

    connection = await client.post("/api/v1/integrations/connections", json={"name": "Lead intake"})
    connection_id = connection.json()["id"]
    secret = connection.json()["webhook_secret"]

    link = await client.patch(
        f"/api/v1/integrations/connections/{connection_id}",
        json={"linked_workflow_id": workflow_id},
    )
    assert link.status_code == 200
    assert link.json()["linked_workflow_id"] == workflow_id

    body = b'{"lead_name": "Test Lead"}'
    signature = _sign(secret, body)
    received = await client.post(
        f"/api/v1/integrations/webhooks/{connection_id}/receive",
        content=body,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
    )
    assert received.status_code == 202, received.text
    assert received.json() == {"received": True, "verified": True}

    events = await client.get(f"/api/v1/integrations/connections/{connection_id}/events")
    assert events.status_code == 200
    assert len(events.json()) == 1
    event = events.json()[0]
    assert event["verified"] is True
    assert event["triggered_run_id"] is not None

    runs = await client.get("/api/v1/automation/runs")
    assert runs.status_code == 200
    matching_run = next(r for r in runs.json() if r["id"] == event["triggered_run_id"])
    assert matching_run["workflow_id"] == workflow_id
    assert matching_run["status"] == "succeeded"
    assert matching_run["trigger_payload"] == {"lead_name": "Test Lead"}


async def test_invalid_signature_does_not_trigger_workflow(client: AsyncClient) -> None:
    await _signup(client, "conn5@example.com", "Connection Org 5")
    workflow_id = await _create_workflow(client, name="Webhook workflow 2", trigger_type="webhook")
    await _activate_workflow(client, workflow_id)

    connection = await client.post(
        "/api/v1/integrations/connections", json={"name": "Lead intake 2"}
    )
    connection_id = connection.json()["id"]

    await client.patch(
        f"/api/v1/integrations/connections/{connection_id}",
        json={"linked_workflow_id": workflow_id},
    )

    body = b'{"lead_name": "Forged Lead"}'
    received = await client.post(
        f"/api/v1/integrations/webhooks/{connection_id}/receive",
        content=body,
        headers={"X-Webhook-Signature": "not-the-real-signature"},
    )
    assert received.status_code == 202
    assert received.json() == {"received": True, "verified": False}

    events = await client.get(f"/api/v1/integrations/connections/{connection_id}/events")
    event = events.json()[0]
    assert event["verified"] is False
    assert event["triggered_run_id"] is None

    runs = await client.get("/api/v1/automation/runs")
    assert runs.json() == []


async def test_disabled_connection_rejects_valid_signature(client: AsyncClient) -> None:
    await _signup(client, "conn6@example.com", "Connection Org 6")
    connection = await client.post(
        "/api/v1/integrations/connections", json={"name": "Will be disabled"}
    )
    connection_id = connection.json()["id"]
    secret = connection.json()["webhook_secret"]

    disable = await client.patch(
        f"/api/v1/integrations/connections/{connection_id}", json={"status": "disabled"}
    )
    assert disable.status_code == 200
    assert disable.json()["status"] == "disabled"

    body = b'{"lead_name": "Anyone"}'
    received = await client.post(
        f"/api/v1/integrations/webhooks/{connection_id}/receive",
        content=body,
        headers={"X-Webhook-Signature": _sign(secret, body)},
    )
    assert received.status_code == 202
    assert received.json()["verified"] is False


async def test_receive_webhook_for_unknown_connection_returns_not_found(
    client: AsyncClient,
) -> None:
    await _signup(client, "conn7@example.com", "Connection Org 7")
    response = await client.post(
        f"/api/v1/integrations/webhooks/{uuid.uuid4()}/receive",
        content=b"{}",
        headers={"X-Webhook-Signature": "irrelevant"},
    )
    assert response.status_code == 404
