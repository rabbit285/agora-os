from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Sequence Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text


async def _create_contact(client: AsyncClient, full_name: str, email: str) -> str:
    response = await client.post(
        "/api/v1/sales/contacts", json={"full_name": full_name, "email": email}
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_create_sequence_and_add_steps(client: AsyncClient) -> None:
    await _signup(client, "seq1@example.com", "Sequence Org 1")
    sequence = await client.post("/api/v1/sales/sequences", json={"name": "Cold Outbound"})
    assert sequence.status_code == 201
    sequence_id = sequence.json()["id"]

    step1 = await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/steps",
        json={"wait_days": 0, "channel": "email", "body_template": "Hi {{first_name}}, ..."},
    )
    assert step1.status_code == 201
    assert step1.json()["order_index"] == 0

    step2 = await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/steps",
        json={"wait_days": 3, "channel": "email", "body_template": "Following up, {{first_name}}"},
    )
    assert step2.json()["order_index"] == 1

    detail = await client.get(f"/api/v1/sales/sequences/{sequence_id}")
    assert len(detail.json()["steps"]) == 2


async def test_enroll_and_advance_due_steps_sends_first_step_immediately(
    client: AsyncClient,
) -> None:
    await _signup(client, "seq2@example.com", "Sequence Org 2")
    sequence = await client.post("/api/v1/sales/sequences", json={"name": "Welcome Sequence"})
    sequence_id = sequence.json()["id"]
    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/steps",
        json={"wait_days": 0, "channel": "email", "body_template": "Hello {{first_name}}"},
    )
    contact_id = await _create_contact(client, "Jane Doe", "jane@example.com")

    enrolled = await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/enroll", json={"contact_ids": [contact_id]}
    )
    assert enrolled.status_code == 200
    assert len(enrolled.json()["enrollments"]) == 1
    assert enrolled.json()["enrollments"][0]["current_step_index"] == 0

    result = await client.post("/api/v1/sales/sequences/process-due-steps")
    assert result.status_code == 200
    assert result.json()["processed"] == 1

    detail = await client.get(f"/api/v1/sales/sequences/{sequence_id}")
    enrollment = detail.json()["enrollments"][0]
    assert enrollment["status"] == "completed"
    assert enrollment["current_step_index"] == 1

    inbox = await client.get("/api/v1/sales/inbox")
    assert inbox.status_code == 200
    assert len(inbox.json()) == 1
    assert inbox.json()[0]["status"] == "sent"
    assert "Jane" in inbox.json()[0]["body"]


async def test_advance_respects_suppression(client: AsyncClient) -> None:
    await _signup(client, "seq3@example.com", "Sequence Org 3")
    sequence = await client.post("/api/v1/sales/sequences", json={"name": "Suppressed Sequence"})
    sequence_id = sequence.json()["id"]
    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/steps",
        json={"wait_days": 0, "channel": "email", "body_template": "Hi {{first_name}}"},
    )
    contact_id = await _create_contact(client, "Suppressed Person", "suppressed@example.com")
    await client.patch(f"/api/v1/sales/contacts/{contact_id}", json={"do_not_contact": True})

    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/enroll", json={"contact_ids": [contact_id]}
    )
    await client.post("/api/v1/sales/sequences/process-due-steps")

    inbox = (await client.get("/api/v1/sales/inbox")).json()
    assert inbox[0]["status"] == "blocked"


async def test_multi_step_sequence_waits_between_steps(client: AsyncClient) -> None:
    await _signup(client, "seq4@example.com", "Sequence Org 4")
    sequence = await client.post("/api/v1/sales/sequences", json={"name": "Multi Step"})
    sequence_id = sequence.json()["id"]
    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/steps",
        json={"wait_days": 0, "channel": "email", "body_template": "Step one"},
    )
    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/steps",
        json={"wait_days": 5, "channel": "email", "body_template": "Step two"},
    )
    contact_id = await _create_contact(client, "Multi Step Person", "multistep@example.com")
    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/enroll", json={"contact_ids": [contact_id]}
    )

    first_run = await client.post("/api/v1/sales/sequences/process-due-steps")
    assert first_run.json()["processed"] == 1

    # Second call immediately after: step 2 isn't due yet (5-day wait).
    second_run = await client.post("/api/v1/sales/sequences/process-due-steps")
    assert second_run.json()["processed"] == 0

    detail = await client.get(f"/api/v1/sales/sequences/{sequence_id}")
    enrollment = detail.json()["enrollments"][0]
    assert enrollment["status"] == "active"
    assert enrollment["current_step_index"] == 1
    raw_due_at = enrollment["next_step_due_at"]
    due_at = datetime.fromisoformat(raw_due_at.replace("Z", "+00:00"))
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=UTC)
    assert due_at > datetime.now(UTC) + timedelta(days=4)


async def test_create_campaign_enrolls_contacts_and_reports_stats(client: AsyncClient) -> None:
    await _signup(client, "camp1@example.com", "Campaign Org 1")
    sequence = await client.post("/api/v1/sales/sequences", json={"name": "Campaign Sequence"})
    sequence_id = sequence.json()["id"]
    await client.post(
        f"/api/v1/sales/sequences/{sequence_id}/steps",
        json={"wait_days": 0, "channel": "email", "body_template": "Campaign message"},
    )
    contact_id = await _create_contact(client, "Campaign Person", "campaign@example.com")

    campaign = await client.post(
        "/api/v1/sales/campaigns",
        json={"name": "Q3 Launch", "sequence_id": sequence_id, "contact_ids": [contact_id]},
    )
    assert campaign.status_code == 201
    assert campaign.json()["status"] == "active"
    campaign_id = campaign.json()["id"]

    await client.post("/api/v1/sales/sequences/process-due-steps")

    detail = await client.get(f"/api/v1/sales/campaigns/{campaign_id}")
    assert detail.status_code == 200
    stats = detail.json()["stats"]
    assert stats["enrolled"] == 1
    assert stats["messages_sent"] == 1
    assert stats["completed"] == 1


async def test_sequence_from_other_org_returns_not_found(client: AsyncClient) -> None:
    from httpx import ASGITransport

    from app.main import app

    await _signup(client, "seq5@example.com", "Sequence Org 5")
    sequence = await client.post("/api/v1/sales/sequences", json={"name": "Org 5 Sequence"})
    sequence_id = sequence.json()["id"]

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    await _signup(other_client, "seq6@example.com", "Sequence Org 6")

    response = await other_client.get(f"/api/v1/sales/sequences/{sequence_id}")
    assert response.status_code == 404
    await other_client.aclose()
