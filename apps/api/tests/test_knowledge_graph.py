"""Tests for the Organization Knowledge Graph (spec §10) — a read-only
traversal over real, already-existing foreign keys across modules, not a
duplicated graph store. See app.knowledge.graph's module docstring.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.graph import UnknownEntityTypeError, get_entity_graph


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Graph Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_unknown_entity_type_raises(db_session: AsyncSession) -> None:
    try:
        await get_entity_graph(
            db_session,
            organization_id=uuid.uuid4(),
            entity_type="not_a_real_type",
            entity_id=uuid.uuid4(),
        )
        raise AssertionError("expected UnknownEntityTypeError")
    except UnknownEntityTypeError:
        pass


async def test_graph_endpoint_lists_entity_types(client: AsyncClient) -> None:
    await _signup(client, "graph-types@example.com", "Graph Types Org")
    response = await client.get("/api/v1/knowledge/graph/entity-types")
    assert response.status_code == 200
    assert "sales_account" in response.json()["entity_types"]
    assert "security_incident" in response.json()["entity_types"]


async def test_graph_missing_entity_returns_404(client: AsyncClient) -> None:
    await _signup(client, "graph-404@example.com", "Graph 404 Org")
    response = await client.get(f"/api/v1/knowledge/graph/sales_account/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_graph_traverses_account_to_contact_opportunity_and_customer(
    client: AsyncClient,
) -> None:
    await _signup(client, "graph1@example.com", "Graph Org 1")

    account = await client.post("/api/v1/sales/accounts", json={"name": "Graph Test Co"})
    account_id = account.json()["id"]

    contact = await client.post(
        "/api/v1/sales/contacts",
        json={
            "full_name": "Graph Contact",
            "email": "contact@graph-test.example",
            "account_id": account_id,
        },
    )
    assert contact.status_code == 201

    opportunity = await client.post(
        "/api/v1/sales/opportunities", json={"account_id": account_id, "title": "Graph Deal"}
    )
    opportunity_id = opportunity.json()["id"]

    won = await client.patch(
        f"/api/v1/sales/opportunities/{opportunity_id}", json={"stage": "closed_won"}
    )
    customer_id = won.json()["onboarding_customer_id"]
    assert customer_id is not None

    graph = await client.get(f"/api/v1/knowledge/graph/sales_account/{account_id}")
    assert graph.status_code == 200
    body = graph.json()
    assert body["node"]["entity_type"] == "sales_account"
    assert body["node"]["label"] == "Graph Test Co"

    relations = {(e["relation"], e["node"]["entity_type"]) for e in body["edges"]}
    assert ("contact", "sales_contact") in relations
    assert ("opportunity", "sales_opportunity") in relations
    assert ("support_customer", "support_customer") in relations

    customer_ids = {
        e["node"]["id"] for e in body["edges"] if e["node"]["entity_type"] == "support_customer"
    }
    assert customer_id in customer_ids


async def test_graph_traverses_ticket_to_security_alert(client: AsyncClient) -> None:
    await _signup(client, "graph2@example.com", "Graph Org 2")

    customer = await client.post(
        "/api/v1/support/customers", json={"name": "Graph Customer", "email": "c@graph.example"}
    )
    customer_id = customer.json()["id"]

    ticket = await client.post(
        "/api/v1/support/tickets",
        json={
            "customer_id": customer_id,
            "subject": "Possible breach",
            "channel": "email",
            "category": "security",
            "priority": "high",
        },
    )
    assert ticket.status_code == 201
    ticket_id = ticket.json()["id"]
    related_alert_id = ticket.json()["related_alert_id"]
    assert related_alert_id is not None

    graph = await client.get(f"/api/v1/knowledge/graph/support_ticket/{ticket_id}")
    assert graph.status_code == 200
    body = graph.json()
    relations = {(e["relation"], e["node"]["id"]) for e in body["edges"]}
    assert ("security_alert", related_alert_id) in relations
    assert ("support_customer", customer_id) in relations


async def test_graph_is_tenant_scoped(client: AsyncClient) -> None:
    await _signup(client, "graph3a@example.com", "Graph Org 3A")
    account = await client.post("/api/v1/sales/accounts", json={"name": "Org3A Account"})
    account_id = account.json()["id"]

    await _signup(client, "graph3b@example.com", "Graph Org 3B")
    response = await client.get(f"/api/v1/knowledge/graph/sales_account/{account_id}")
    assert response.status_code == 404
