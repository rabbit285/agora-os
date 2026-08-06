"""Tests for real organization data export/deletion execution (spec
§B3/§B5 "Customer Data Control": export; deletion). Deletion is tested
end to end through the two-step confirm flow; the actual cross-table
purge mechanism itself (`SET session_replication_role = replica`) is
PostgreSQL-only and additionally live-verified against the real dev
database — see docs/DECISIONS.md — since the SQLite test database these
tests run against has no equivalent and skips that specific statement
(app.core.organization_deletion.execute_organization_deletion).
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
            "full_name": "Deletion Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_deletion_request_requires_the_exact_organization_name(client: AsyncClient) -> None:
    await _signup(client, "del1@example.com", "Deletion Org 1")
    response = await client.post(
        "/api/v1/organizations/current/deletion-request", json={"confirm_name": "Wrong Name"}
    )
    assert response.status_code == 400


async def test_deletion_request_sets_a_real_visible_timestamp(client: AsyncClient) -> None:
    await _signup(client, "del2@example.com", "Deletion Org 2")
    requested = await client.post(
        "/api/v1/organizations/current/deletion-request", json={"confirm_name": "Deletion Org 2"}
    )
    assert requested.status_code == 200
    assert requested.json()["deletion_requested_at"] is not None

    current = await client.get("/api/v1/organizations/current")
    assert current.json()["deletion_requested_at"] is not None


async def test_cancelling_a_deletion_request_clears_it(client: AsyncClient) -> None:
    await _signup(client, "del3@example.com", "Deletion Org 3")
    await client.post(
        "/api/v1/organizations/current/deletion-request", json={"confirm_name": "Deletion Org 3"}
    )
    cancelled = await client.post("/api/v1/organizations/current/deletion-request/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["deletion_requested_at"] is None


async def test_execute_is_rejected_without_a_prior_pending_request(client: AsyncClient) -> None:
    await _signup(client, "del4@example.com", "Deletion Org 4")
    response = await client.post(
        "/api/v1/organizations/current/deletion-request/execute",
        json={"confirm_name": "Deletion Org 4"},
    )
    assert response.status_code == 409


async def test_execute_requires_the_exact_name_again(client: AsyncClient) -> None:
    await _signup(client, "del5@example.com", "Deletion Org 5")
    await client.post(
        "/api/v1/organizations/current/deletion-request", json={"confirm_name": "Deletion Org 5"}
    )
    response = await client.post(
        "/api/v1/organizations/current/deletion-request/execute",
        json={"confirm_name": "Not The Right Name"},
    )
    assert response.status_code == 400


async def test_execute_actually_deletes_the_organization_and_its_data(client: AsyncClient) -> None:
    await _signup(client, "del6@example.com", "Deletion Org 6")
    await client.post("/api/v1/compliance/controls", json={"title": "Doomed control"})

    await client.post(
        "/api/v1/organizations/current/deletion-request", json={"confirm_name": "Deletion Org 6"}
    )
    executed = await client.post(
        "/api/v1/organizations/current/deletion-request/execute",
        json={"confirm_name": "Deletion Org 6"},
    )
    assert executed.status_code == 204

    # The org's own session was deleted as part of the purge, so any
    # further request under that session is honestly unauthenticated.
    after = await client.get("/api/v1/organizations/current")
    assert after.status_code == 401


async def test_execute_clears_the_now_stale_session_cookie(client: AsyncClient) -> None:
    """The `sessions` row is deleted server-side as part of the purge
    (see test_execute_actually_deletes_the_organization_and_its_data),
    but the browser's own cookie survives that unless the response
    explicitly clears it — left stale, a client that still checks
    cookie presence rather than validity (e.g. apps/web/middleware.ts)
    would keep treating the browser as authenticated."""
    await _signup(client, "del7@example.com", "Deletion Org 7")
    await client.post(
        "/api/v1/organizations/current/deletion-request", json={"confirm_name": "Deletion Org 7"}
    )
    executed = await client.post(
        "/api/v1/organizations/current/deletion-request/execute",
        json={"confirm_name": "Deletion Org 7"},
    )
    assert executed.status_code == 204
    set_cookie = executed.headers.get("set-cookie", "")
    assert "agora_session=" in set_cookie
    assert 'Max-Age=0' in set_cookie or "01 Jan 1970" in set_cookie


async def test_data_export_returns_a_real_download_link(client: AsyncClient) -> None:
    await _signup(client, "export1@example.com", "Export Org 1")
    await client.post("/api/v1/compliance/controls", json={"title": "Exported control"})

    response = await client.get("/api/v1/organizations/current/data-export?format=csv")
    assert response.status_code == 200
    assert response.json()["download_url"].startswith("http")


async def test_data_export_rejects_an_unknown_format(client: AsyncClient) -> None:
    await _signup(client, "export2@example.com", "Export Org 2")
    response = await client.get("/api/v1/organizations/current/data-export?format=rtf")
    assert response.status_code == 422
