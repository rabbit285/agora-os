from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.main import app


async def _signup_new_client(email: str, org_name: str) -> tuple[AsyncClient, str]:
    """Each org needs its own cookie jar, so tests use independent clients
    sharing the same ASGI app/db rather than the shared `client` fixture."""
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    signup = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Test User",
            "organization_name": org_name,
        },
    )
    assert signup.status_code == 200, signup.text
    organization_id = signup.json()["organization"]["id"]
    return client, organization_id


async def test_user_cannot_access_another_organization_via_header(client: AsyncClient) -> None:
    # `client` fixture already wires up the shared in-memory DB; reuse its
    # app instance for a second, independent session.
    client_a, org_a_id = await _signup_new_client("alice@example.com", "Org A")
    client_b, org_b_id = await _signup_new_client("bob@example.com", "Org B")

    task_in_a = await client_a.post("/api/v1/tasks", json={"title": "Org A secret task"})
    assert task_in_a.status_code == 201

    # Bob tries to read Org A's tasks by spoofing the header — must be
    # rejected, not silently scoped, and not leak whether org_a_id exists.
    spoofed = await client_b.get("/api/v1/tasks", headers={"X-Organization-Id": org_a_id})
    assert spoofed.status_code == 403

    # Bob's own org has no tasks.
    own = await client_b.get("/api/v1/tasks", headers={"X-Organization-Id": org_b_id})
    assert own.status_code == 200
    assert own.json() == []

    await client_a.aclose()
    await client_b.aclose()


async def test_task_update_across_tenants_returns_not_found(client: AsyncClient) -> None:
    client_a, _ = await _signup_new_client("carol@example.com", "Org C")
    client_b, org_b_id = await _signup_new_client("dave@example.com", "Org D")

    created = await client_a.post("/api/v1/tasks", json={"title": "Org C task"})
    task_id = created.json()["id"]

    # Dave (Org D) cannot update a task belonging to Org C, even scoped to
    # his own valid organization header — the task lookup itself must not
    # cross the tenant boundary.
    response = await client_b.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
        headers={"X-Organization-Id": org_b_id},
    )
    assert response.status_code == 404

    await client_a.aclose()
    await client_b.aclose()
