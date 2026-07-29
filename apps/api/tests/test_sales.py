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
            "full_name": "Sales Tester",
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


async def test_org_admin_can_create_account(client: AsyncClient) -> None:
    await _signup(client, "account1@example.com", "Account Org")
    response = await client.post("/api/v1/sales/accounts", json={"name": "Acme Robotics"})
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "prospect"


async def test_employee_role_cannot_create_account(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "account2@example.com", "Account Org 2")
    token = await _create_member_with_role(
        db_session, organization_id=org_id, email="employee-sales@example.com", role_key="employee"
    )
    client.cookies.set("agora_session", token)

    response = await client.post("/api/v1/sales/accounts", json={"name": "Should fail"})
    assert response.status_code == 403


async def test_sales_representative_role_can_create_lead(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "lead1@example.com", "Lead Org")
    token = await _create_member_with_role(
        db_session,
        organization_id=org_id,
        email="sales-rep@example.com",
        role_key="sales_representative",
    )
    client.cookies.set("agora_session", token)

    response = await client.post("/api/v1/sales/leads", json={"source": "inbound"})
    assert response.status_code == 201


async def _create_contact(client: AsyncClient, *, email: str, do_not_contact: bool) -> str:
    created = await client.post(
        "/api/v1/sales/contacts",
        json={"full_name": "Test Contact", "email": email},
    )
    contact_id = created.json()["id"]
    if do_not_contact:
        await client.patch(f"/api/v1/sales/contacts/{contact_id}", json={"do_not_contact": True})
    return contact_id


async def test_suppressed_contact_blocks_outreach_send(client: AsyncClient) -> None:
    await _signup(client, "suppress1@example.com", "Suppress Org")
    contact_id = await _create_contact(client, email="suppressed@example.com", do_not_contact=True)

    message = await client.post(
        "/api/v1/sales/outreach", json={"contact_id": contact_id, "body": "Hello there"}
    )
    message_id = message.json()["id"]
    assert message.json()["status"] == "draft"

    sent = await client.post(f"/api/v1/sales/outreach/{message_id}/send")
    assert sent.status_code == 200
    body = sent.json()
    assert body["status"] == "blocked"
    assert (
        "do-not-contact" in body["blocked_reason"].lower()
        or "suppressed" in body["blocked_reason"].lower()
    )
    assert body["sent_at"] is None


async def test_reachable_contact_outreach_sends_successfully(client: AsyncClient) -> None:
    await _signup(client, "reachable1@example.com", "Reachable Org")
    contact_id = await _create_contact(client, email="reachable@example.com", do_not_contact=False)

    message = await client.post(
        "/api/v1/sales/outreach", json={"contact_id": contact_id, "body": "Hello there"}
    )
    message_id = message.json()["id"]

    sent = await client.post(f"/api/v1/sales/outreach/{message_id}/send")
    assert sent.status_code == 200
    body = sent.json()
    assert body["status"] == "sent"
    assert body["blocked_reason"] is None
    assert body["sent_at"] is not None


async def test_cannot_resend_already_sent_message(client: AsyncClient) -> None:
    await _signup(client, "resend1@example.com", "Resend Org")
    contact_id = await _create_contact(client, email="resend@example.com", do_not_contact=False)
    message = await client.post(
        "/api/v1/sales/outreach", json={"contact_id": contact_id, "body": "First send"}
    )
    message_id = message.json()["id"]
    await client.post(f"/api/v1/sales/outreach/{message_id}/send")

    second_attempt = await client.post(f"/api/v1/sales/outreach/{message_id}/send")
    assert second_attempt.status_code == 409


async def test_account_from_other_org_returns_not_found(client: AsyncClient) -> None:
    await _signup(client, "cross-sales1@example.com", "Cross Sales Org 1")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Org 1 account"})
    account_id = account.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    _, other_org_id = await _signup(other_client, "cross-sales2@example.com", "Cross Sales Org 2")

    response = await other_client.get(
        f"/api/v1/sales/accounts/{account_id}", headers={"X-Organization-Id": str(other_org_id)}
    )
    assert response.status_code == 404
    await other_client.aclose()


async def test_opportunity_stage_lifecycle(client: AsyncClient) -> None:
    await _signup(client, "opp1@example.com", "Opp Org")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Opp Account"})
    account_id = account.json()["id"]

    created = await client.post(
        "/api/v1/sales/opportunities", json={"account_id": account_id, "title": "New deal"}
    )
    assert created.status_code == 201
    opportunity_id = created.json()["id"]
    assert created.json()["stage"] == "prospecting"

    updated = await client.patch(
        f"/api/v1/sales/opportunities/{opportunity_id}", json={"stage": "closed_won"}
    )
    assert updated.status_code == 200
    assert updated.json()["stage"] == "closed_won"
