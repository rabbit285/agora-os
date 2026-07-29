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
            "full_name": "Support Tester",
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


async def _create_customer(client: AsyncClient, *, email: str) -> str:
    response = await client.post(
        "/api/v1/support/customers", json={"name": "Test Customer", "email": email}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]  # type: ignore[no-any-return]


async def test_org_admin_can_create_customer(client: AsyncClient) -> None:
    await _signup(client, "customer1@example.com", "Customer Org")
    response = await client.post(
        "/api/v1/support/customers", json={"name": "Acme Corp", "email": "billing@acme.example"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "active"


async def test_employee_role_cannot_create_ticket(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "customer2@example.com", "Customer Org 2")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="employee-support@example.com",
        role_key="employee",
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/support/tickets",
        json={"customer_id": str(uuid.uuid4()), "subject": "Should fail"},
    )
    assert response.status_code == 403


async def test_support_agent_role_can_create_ticket(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "customer3@example.com", "Customer Org 3")
    customer_id = await _create_customer(client, email="agent-test@example.com")

    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="support-agent@example.com",
        role_key="support_agent",
    )
    client.cookies.set("agora_session", token)

    response = await client.post(
        "/api/v1/support/tickets",
        json={"customer_id": customer_id, "subject": "Cannot log in"},
    )
    assert response.status_code == 201


async def test_security_category_ticket_creates_linked_alert(client: AsyncClient) -> None:
    await _signup(client, "seccat1@example.com", "SecCat Org")
    customer_id = await _create_customer(client, email="seccat@example.com")

    ticket = await client.post(
        "/api/v1/support/tickets",
        json={
            "customer_id": customer_id,
            "subject": "Suspicious login on our account",
            "category": "security",
            "priority": "medium",
        },
    )
    assert ticket.status_code == 201, ticket.text
    body = ticket.json()
    assert body["related_alert_id"] is not None
    # category=security auto-escalates priority regardless of what was requested
    assert body["priority"] == "urgent"

    alerts = await client.get("/api/v1/security/alerts")
    assert alerts.status_code == 200
    alert_ids = {a["id"] for a in alerts.json()}
    assert body["related_alert_id"] in alert_ids


async def test_general_category_ticket_has_no_linked_alert(client: AsyncClient) -> None:
    await _signup(client, "gencat1@example.com", "GenCat Org")
    customer_id = await _create_customer(client, email="gencat@example.com")

    ticket = await client.post(
        "/api/v1/support/tickets",
        json={"customer_id": customer_id, "subject": "How do I export my data?"},
    )
    assert ticket.status_code == 201
    assert ticket.json()["related_alert_id"] is None


async def test_ticket_detail_includes_messages(client: AsyncClient) -> None:
    await _signup(client, "msg1@example.com", "Msg Org")
    customer_id = await _create_customer(client, email="msg@example.com")

    ticket = await client.post(
        "/api/v1/support/tickets",
        json={"customer_id": customer_id, "subject": "Billing question"},
    )
    ticket_id = ticket.json()["id"]

    await client.post(
        f"/api/v1/support/tickets/{ticket_id}/messages",
        json={"sender_type": "customer", "body": "Why was I charged twice?"},
    )
    await client.post(
        f"/api/v1/support/tickets/{ticket_id}/messages",
        json={"sender_type": "agent", "body": "Refunded the duplicate charge."},
    )

    detail = await client.get(f"/api/v1/support/tickets/{ticket_id}")
    assert detail.status_code == 200
    messages = detail.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["body"] == "Why was I charged twice?"


async def test_ticket_status_transition_sets_resolved_at(client: AsyncClient) -> None:
    await _signup(client, "resolve1@example.com", "Resolve Org")
    customer_id = await _create_customer(client, email="resolve@example.com")

    ticket = await client.post(
        "/api/v1/support/tickets",
        json={"customer_id": customer_id, "subject": "Feature request"},
    )
    ticket_id = ticket.json()["id"]
    assert ticket.json()["resolved_at"] is None

    updated = await client.patch(
        f"/api/v1/support/tickets/{ticket_id}", json={"status": "resolved"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "resolved"
    assert updated.json()["resolved_at"] is not None


async def test_ticket_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross-support1@example.com", "Cross Support Org 1")
    customer_id = await _create_customer(client, email="cross1@example.com")
    ticket = await client.post(
        "/api/v1/support/tickets",
        json={"customer_id": customer_id, "subject": "Org 1 ticket"},
    )
    ticket_id = ticket.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(
        other_client, "cross-support2@example.com", "Cross Support Org 2"
    )

    response = await other_client.get(
        f"/api/v1/support/tickets/{ticket_id}", headers={"X-Organization-Id": str(other_org_id)}
    )
    assert response.status_code == 404
    await other_client.aclose()


async def test_csat_response_requires_valid_ticket(client: AsyncClient) -> None:
    await _signup(client, "csat1@example.com", "CSAT Org")
    customer_id = await _create_customer(client, email="csat@example.com")
    ticket = await client.post(
        "/api/v1/support/tickets",
        json={"customer_id": customer_id, "subject": "Resolved issue"},
    )
    ticket_id = ticket.json()["id"]

    response = await client.post(
        "/api/v1/support/csat", json={"ticket_id": ticket_id, "score": 5, "comment": "Great!"}
    )
    assert response.status_code == 201
    assert response.json()["score"] == 5


async def test_knowledge_article_publish_toggle(client: AsyncClient) -> None:
    await _signup(client, "kb1@example.com", "KB Org")
    created = await client.post(
        "/api/v1/support/knowledge-articles",
        json={"title": "Resetting your password", "body": "Go to Settings > Security."},
    )
    assert created.status_code == 201
    assert created.json()["published"] is False
    article_id = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/support/knowledge-articles/{article_id}", json={"published": True}
    )
    assert updated.status_code == 200
    assert updated.json()["published"] is True
