from __future__ import annotations

from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "AI Agent Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text


async def _create_ticket(client: AsyncClient) -> str:
    customer = await client.post(
        "/api/v1/support/customers", json={"name": "AI Co", "email": "aico@example.com"}
    )
    customer_id = customer.json()["id"]
    ticket = await client.post(
        "/api/v1/support/tickets",
        json={"customer_id": customer_id, "subject": "Can't log in", "description": "Help!"},
    )
    return ticket.json()["id"]


async def test_draft_reply_creates_pending_ai_draft_without_agent_config(
    client: AsyncClient,
) -> None:
    await _signup(client, "aiagent1@example.com", "AI Agent Org 1")
    ticket_id = await _create_ticket(client)

    draft = await client.post(f"/api/v1/support/tickets/{ticket_id}/draft-reply")
    assert draft.status_code == 200
    body = draft.json()
    assert body["sender_type"] == "ai"
    assert body["status"] == "draft"
    assert len(body["body"]) > 0


async def test_agent_can_send_a_pending_ai_draft(client: AsyncClient) -> None:
    await _signup(client, "aiagent2@example.com", "AI Agent Org 2")
    ticket_id = await _create_ticket(client)

    draft = await client.post(f"/api/v1/support/tickets/{ticket_id}/draft-reply")
    message_id = draft.json()["id"]

    sent = await client.post(f"/api/v1/support/tickets/{ticket_id}/messages/{message_id}/send")
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"

    already_sent = await client.post(
        f"/api/v1/support/tickets/{ticket_id}/messages/{message_id}/send"
    )
    assert already_sent.status_code == 409


async def test_ai_agent_config_defaults_to_none(client: AsyncClient) -> None:
    await _signup(client, "aiagent3@example.com", "AI Agent Org 3")
    config = await client.get("/api/v1/support/ai-agent-config")
    assert config.status_code == 200
    assert config.json() is None


async def test_saving_ai_agent_config_with_auto_send_still_drafts_ungrounded_replies(
    client: AsyncClient,
) -> None:
    await _signup(client, "aiagent4@example.com", "AI Agent Org 4")
    saved = await client.put(
        "/api/v1/support/ai-agent-config",
        json={"enabled": True, "auto_send_grounded_replies": True},
    )
    assert saved.status_code == 200
    assert saved.json()["enabled"] is True

    ticket_id = await _create_ticket(client)
    draft = await client.post(f"/api/v1/support/tickets/{ticket_id}/draft-reply")
    # No knowledge base documents exist in this org, so the Copilot's
    # honest "no evidence" answer is never grounded — even with
    # auto-send enabled, this must stay a pending draft, not be
    # auto-sent as if it were a confident answer.
    assert draft.json()["status"] == "draft"


async def test_qa_score_lifecycle(client: AsyncClient) -> None:
    await _signup(client, "qa1@example.com", "QA Org 1")
    ticket_id = await _create_ticket(client)

    created = await client.post(
        f"/api/v1/support/tickets/{ticket_id}/qa-score",
        json={"score": 4, "notes": "Good tone, slightly slow to resolve."},
    )
    assert created.status_code == 201
    assert created.json()["score"] == 4

    scores = await client.get(f"/api/v1/support/tickets/{ticket_id}/qa-scores")
    assert scores.status_code == 200
    assert len(scores.json()) == 1


async def test_support_analytics_reflects_real_data(client: AsyncClient) -> None:
    await _signup(client, "analytics1@example.com", "Analytics Org 1")
    ticket_id = await _create_ticket(client)

    await client.post(
        "/api/v1/support/csat", json={"ticket_id": ticket_id, "score": 5, "comment": "Great!"}
    )
    await client.post(f"/api/v1/support/tickets/{ticket_id}/qa-score", json={"score": 3})
    await client.patch(f"/api/v1/support/tickets/{ticket_id}", json={"status": "resolved"})

    analytics = await client.get("/api/v1/support/analytics")
    assert analytics.status_code == 200
    body = analytics.json()
    assert body["total_tickets"] == 1
    assert body["open_tickets"] == 0
    assert body["tickets_by_status"]["resolved"] == 1
    assert body["average_csat"] == 5.0
    assert body["csat_response_count"] == 1
    assert body["average_qa_score"] == 3.0
    assert body["qa_score_count"] == 1


async def test_support_analytics_is_scoped_per_organization(client: AsyncClient) -> None:
    from httpx import ASGITransport

    from app.main import app

    await _signup(client, "analytics2@example.com", "Analytics Org 2")
    await _create_ticket(client)

    transport = ASGITransport(app=app)
    other_client = AsyncClient(transport=transport, base_url="http://test")
    await _signup(other_client, "analytics3@example.com", "Analytics Org 3")

    analytics = await other_client.get("/api/v1/support/analytics")
    assert analytics.json()["total_tickets"] == 0
    await other_client.aclose()
