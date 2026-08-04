"""Tests for real, additive pagination (spec §E7 "API Quality":
"pagination; sorting") on a representative set of list endpoints —
app.core.pagination. Omitting limit/offset returns the same bare array
every list endpoint always returned (no frontend caller had to change);
passing them applies a real SQL LIMIT/OFFSET and the true total is
reported via the X-Total-Count response header.
"""

from __future__ import annotations

from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Pagination Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text


async def _create_control(client: AsyncClient, title: str) -> None:
    response = await client.post("/api/v1/compliance/controls", json={"title": title})
    assert response.status_code == 201, response.text


async def test_omitting_limit_returns_every_row_unchanged(client: AsyncClient) -> None:
    await _signup(client, "page1@example.com", "Pagination Org 1")
    for i in range(3):
        await _create_control(client, f"Control {i}")

    response = await client.get("/api/v1/compliance/controls")

    assert response.status_code == 200
    assert len(response.json()) == 3
    assert response.headers["X-Total-Count"] == "3"


async def test_limit_and_offset_apply_a_real_page(client: AsyncClient) -> None:
    await _signup(client, "page2@example.com", "Pagination Org 2")
    for i in range(5):
        await _create_control(client, f"Control {i}")

    first_page = await client.get("/api/v1/compliance/controls?limit=2&offset=0")
    second_page = await client.get("/api/v1/compliance/controls?limit=2&offset=2")
    last_page = await client.get("/api/v1/compliance/controls?limit=2&offset=4")

    assert len(first_page.json()) == 2
    assert len(second_page.json()) == 2
    assert len(last_page.json()) == 1
    assert first_page.headers["X-Total-Count"] == "5"
    assert second_page.headers["X-Total-Count"] == "5"

    first_ids = {c["id"] for c in first_page.json()}
    second_ids = {c["id"] for c in second_page.json()}
    assert first_ids.isdisjoint(second_ids)


async def test_limit_is_capped_at_200(client: AsyncClient) -> None:
    await _signup(client, "page3@example.com", "Pagination Org 3")

    response = await client.get("/api/v1/compliance/controls?limit=500")

    assert response.status_code == 422
