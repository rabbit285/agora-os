from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Meeting Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text


async def test_create_and_update_meeting(client: AsyncClient) -> None:
    await _signup(client, "meet1@example.com", "Meeting Org 1")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Meeting Account"})
    account_id = account.json()["id"]

    scheduled_at = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    meeting = await client.post(
        "/api/v1/sales/meetings",
        json={"title": "Discovery call", "account_id": account_id, "scheduled_at": scheduled_at},
    )
    assert meeting.status_code == 201
    assert meeting.json()["status"] == "scheduled"
    meeting_id = meeting.json()["id"]

    updated = await client.patch(
        f"/api/v1/sales/meetings/{meeting_id}", json={"status": "completed"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "completed"


async def test_generate_prep_notes_gives_honest_no_evidence_message_without_kb(
    client: AsyncClient,
) -> None:
    await _signup(client, "meet2@example.com", "Meeting Org 2")
    scheduled_at = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    meeting = await client.post(
        "/api/v1/sales/meetings",
        json={"title": "No KB meeting", "scheduled_at": scheduled_at},
    )
    meeting_id = meeting.json()["id"]

    result = await client.post(f"/api/v1/sales/meetings/{meeting_id}/prep-notes")
    assert result.status_code == 200
    assert result.json()["prep_notes"] is not None
    assert len(result.json()["prep_notes"]) > 0


async def test_sales_intelligence_reflects_real_pipeline(client: AsyncClient) -> None:
    await _signup(client, "intel1@example.com", "Intel Org 1")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Intel Account"})
    account_id = account.json()["id"]

    won = await client.post(
        "/api/v1/sales/opportunities",
        json={"account_id": account_id, "title": "Won Deal", "value": 10000},
    )
    won_id = won.json()["id"]
    await client.patch(f"/api/v1/sales/opportunities/{won_id}", json={"stage": "closed_won"})

    lost = await client.post(
        "/api/v1/sales/opportunities",
        json={"account_id": account_id, "title": "Lost Deal", "value": 5000},
    )
    lost_id = lost.json()["id"]
    await client.patch(f"/api/v1/sales/opportunities/{lost_id}", json={"stage": "closed_lost"})

    intelligence = await client.get("/api/v1/sales/intelligence")
    assert intelligence.status_code == 200
    body = intelligence.json()
    assert body["win_rate_percent"] == 50.0
    assert body["average_deal_size"] == 10000.0
    assert body["pipeline_value_by_stage"]["closed_won"] == 10000.0
    assert body["pipeline_value_by_stage"]["closed_lost"] == 5000.0


async def test_sales_intelligence_is_scoped_per_organization(client: AsyncClient) -> None:
    from httpx import ASGITransport

    from app.main import app

    await _signup(client, "intel2@example.com", "Intel Org 2")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Org 2 Account"})
    await client.post(
        "/api/v1/sales/opportunities",
        json={"account_id": account.json()["id"], "title": "Org 2 Deal", "value": 999},
    )

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    await _signup(other_client, "intel3@example.com", "Intel Org 3")

    intelligence = await other_client.get("/api/v1/sales/intelligence")
    assert intelligence.json()["pipeline_value_by_stage"] == {}
    await other_client.aclose()


async def test_lead_finder_creates_leads_for_unqualified_accounts_without_open_lead(
    client: AsyncClient,
) -> None:
    await _signup(client, "finder1@example.com", "Finder Org 1")
    await client.post("/api/v1/sales/accounts", json={"name": "Finder Account 1"})
    await client.post("/api/v1/sales/accounts", json={"name": "Finder Account 2"})

    result = await client.post("/api/v1/sales/leads/find")
    assert result.status_code == 200
    body = result.json()
    assert body["candidates_considered"] == 2
    assert len(body["created_leads"]) == 2
    assert all(lead["source"] == "lead_finder" for lead in body["created_leads"])


async def test_lead_finder_skips_accounts_with_existing_open_lead(client: AsyncClient) -> None:
    await _signup(client, "finder2@example.com", "Finder Org 2")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Already Has Lead"})
    account_id = account.json()["id"]
    await client.post("/api/v1/sales/leads", json={"account_id": account_id, "source": "manual"})

    result = await client.post("/api/v1/sales/leads/find")
    assert result.json()["created_leads"] == []


async def test_lead_finder_only_matches_icp_when_profile_configured(client: AsyncClient) -> None:
    await _signup(client, "finder3@example.com", "Finder Org 3")
    await client.put(
        "/api/v1/sales/icp-profile",
        json={
            "target_industries": ["fintech"],
            "min_employee_count": None,
            "max_employee_count": None,
        },
    )
    await client.post("/api/v1/sales/accounts", json={"name": "Fintech Fit", "industry": "fintech"})
    await client.post("/api/v1/sales/accounts", json={"name": "Bad Fit", "industry": "retail"})

    result = await client.post("/api/v1/sales/leads/find")
    body = result.json()
    assert len(body["created_leads"]) == 1
