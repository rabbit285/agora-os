from __future__ import annotations

from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Detail Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text


async def test_lead_detail_includes_account_and_contact(client: AsyncClient) -> None:
    await _signup(client, "detail1@example.com", "Detail Org 1")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Lead Account"})
    account_id = account.json()["id"]
    contact = await client.post(
        "/api/v1/sales/contacts",
        json={"full_name": "Lead Contact", "email": "leadcontact@example.com"},
    )
    contact_id = contact.json()["id"]

    lead = await client.post(
        "/api/v1/sales/leads",
        json={"account_id": account_id, "contact_id": contact_id, "source": "manual"},
    )
    lead_id = lead.json()["id"]

    detail = await client.get(f"/api/v1/sales/leads/{lead_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["account"]["id"] == account_id
    assert body["contact"]["id"] == contact_id


async def test_lead_detail_from_other_org_returns_not_found(client: AsyncClient) -> None:
    from httpx import ASGITransport

    from app.main import app

    await _signup(client, "detail2@example.com", "Detail Org 2")
    lead = await client.post("/api/v1/sales/leads", json={"source": "manual"})
    lead_id = lead.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    await _signup(other_client, "detail3@example.com", "Detail Org 3")

    response = await other_client.get(f"/api/v1/sales/leads/{lead_id}")
    assert response.status_code == 404
    await other_client.aclose()


async def test_contact_detail_includes_account_and_outreach_history(client: AsyncClient) -> None:
    await _signup(client, "detail4@example.com", "Detail Org 4")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Contact Account"})
    account_id = account.json()["id"]
    contact = await client.post(
        "/api/v1/sales/contacts",
        json={
            "full_name": "Contact Person",
            "email": "contactperson@example.com",
            "account_id": account_id,
        },
    )
    contact_id = contact.json()["id"]

    message = await client.post(
        "/api/v1/sales/outreach",
        json={"contact_id": contact_id, "body": "Hello there"},
    )
    message_id = message.json()["id"]
    await client.post(f"/api/v1/sales/outreach/{message_id}/send")

    detail = await client.get(f"/api/v1/sales/contacts/{contact_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["account"]["id"] == account_id
    assert len(body["outreach"]) == 1
    assert body["outreach"][0]["status"] == "sent"


async def test_opportunity_detail_includes_account(client: AsyncClient) -> None:
    await _signup(client, "detail5@example.com", "Detail Org 5")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Opportunity Account"})
    account_id = account.json()["id"]
    opportunity = await client.post(
        "/api/v1/sales/opportunities", json={"account_id": account_id, "title": "Big Deal"}
    )
    opportunity_id = opportunity.json()["id"]

    detail = await client.get(f"/api/v1/sales/opportunities/{opportunity_id}")
    assert detail.status_code == 200
    assert detail.json()["account"]["id"] == account_id
