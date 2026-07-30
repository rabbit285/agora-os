"""Tests for Global Search (spec §47) — a real, tenant-scoped substring
search across every module's named records. See app.search.service's
module docstring for why this is ILIKE-based rather than a separate search
index, and for the permission-scoping rationale.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Search Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_search_finds_matching_records_across_modules(client: AsyncClient) -> None:
    await _signup(client, "search1@example.com", "Search Org 1")

    await client.post("/api/v1/sales/accounts", json={"name": "Nordwind Robotics GmbH"})
    await client.post(
        "/api/v1/support/customers",
        json={"name": "Nordwind Support Customer", "email": "billing@nordwind.example"},
    )

    response = await client.get("/api/v1/search", params={"q": "Nordwind"})
    assert response.status_code == 200
    body = response.json()
    entity_types = {r["entity_type"] for r in body["results"]}
    assert "sales_account" in entity_types
    assert "support_customer" in entity_types


async def test_search_is_case_insensitive(client: AsyncClient) -> None:
    await _signup(client, "search2@example.com", "Search Org 2")
    await client.post("/api/v1/sales/accounts", json={"name": "Acme Robotics"})

    response = await client.get("/api/v1/search", params={"q": "acme robotics".upper()})
    assert response.status_code == 200
    assert any(r["label"] == "Acme Robotics" for r in response.json()["results"])


async def test_search_empty_query_returns_no_results(client: AsyncClient) -> None:
    await _signup(client, "search3@example.com", "Search Org 3")
    await client.post("/api/v1/sales/accounts", json={"name": "Should Not Appear"})

    response = await client.get("/api/v1/search", params={"q": ""})
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_no_match_returns_empty_list(client: AsyncClient) -> None:
    await _signup(client, "search4@example.com", "Search Org 4")
    response = await client.get("/api/v1/search", params={"q": "nonexistent-xyz-123"})
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_never_crosses_tenant_boundary(client: AsyncClient) -> None:
    await _signup(client, "search5a@example.com", "Search Org 5A")
    await client.post("/api/v1/sales/accounts", json={"name": "Org5A Confidential Deal"})

    await _signup(client, "search5b@example.com", "Search Org 5B")
    response = await client.get("/api/v1/search", params={"q": "Confidential"})
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_search_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/search", params={"q": "anything"})
    assert response.status_code == 401
