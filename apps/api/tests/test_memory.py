"""Tests for Business AI Memory (spec §89, BIZ-04): structured entries
with real provenance, administrator correct/delete, and one real
automatic provenance hook (a published Policy).
"""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Memory Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_create_and_list_a_manual_memory_entry(client: AsyncClient) -> None:
    await _signup(client, "mem1@example.com", "Memory Org 1")
    created = await client.post(
        "/api/v1/memory", json={"entry_type": "business_rule", "content": "Refunds over €500 require Finance approval."}
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["provenance_type"] == "manual"
    assert body["created_by"] is not None
    assert body["status"] == "active"

    listed = await client.get("/api/v1/memory")
    assert listed.status_code == 200
    assert any(e["id"] == body["id"] for e in listed.json())


async def test_unknown_entry_type_is_rejected(client: AsyncClient) -> None:
    await _signup(client, "mem2@example.com", "Memory Org 2")
    response = await client.post(
        "/api/v1/memory", json={"entry_type": "not_a_real_type", "content": "..."}
    )
    assert response.status_code == 422


async def test_correcting_a_memory_entry_changes_its_content(client: AsyncClient) -> None:
    await _signup(client, "mem3@example.com", "Memory Org 3")
    created = await client.post(
        "/api/v1/memory", json={"entry_type": "approved_fact", "content": "Original wording."}
    )
    entry_id = created.json()["id"]

    corrected = await client.patch(f"/api/v1/memory/{entry_id}", json={"content": "Corrected wording."})
    assert corrected.status_code == 200
    assert corrected.json()["content"] == "Corrected wording."


async def test_deleting_a_memory_entry_is_a_soft_delete_excluded_from_listing(
    client: AsyncClient,
) -> None:
    await _signup(client, "mem4@example.com", "Memory Org 4")
    created = await client.post(
        "/api/v1/memory", json={"entry_type": "preference", "content": "Always use formal tone."}
    )
    entry_id = created.json()["id"]

    deleted = await client.delete(f"/api/v1/memory/{entry_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    listed = await client.get("/api/v1/memory")
    assert all(e["id"] != entry_id for e in listed.json())


async def test_publishing_a_policy_creates_a_real_memory_entry(client: AsyncClient) -> None:
    await _signup(client, "mem5@example.com", "Memory Org 5")
    policy = await client.post("/api/v1/compliance/policies", json={"title": "Data Retention Policy"})
    assert policy.status_code == 201, policy.text
    policy_id = policy.json()["id"]

    published = await client.patch(
        f"/api/v1/compliance/policies/{policy_id}/status", json={"status": "published"}
    )
    assert published.status_code == 200

    listed = await client.get("/api/v1/memory", params={"entry_type": "policy"})
    entries = listed.json()
    assert len(entries) == 1
    assert entries[0]["provenance_type"] == "policy"
    assert entries[0]["provenance_id"] == policy_id
    assert "Data Retention Policy" in entries[0]["content"]


async def test_publishing_the_same_policy_twice_does_not_duplicate_the_memory_entry(
    client: AsyncClient,
) -> None:
    await _signup(client, "mem6@example.com", "Memory Org 6")
    policy = await client.post("/api/v1/compliance/policies", json={"title": "Second Policy"})
    policy_id = policy.json()["id"]

    await client.patch(f"/api/v1/compliance/policies/{policy_id}/status", json={"status": "draft"})
    await client.patch(f"/api/v1/compliance/policies/{policy_id}/status", json={"status": "published"})
    await client.patch(f"/api/v1/compliance/policies/{policy_id}/status", json={"status": "published"})

    listed = await client.get("/api/v1/memory", params={"entry_type": "policy"})
    assert len(listed.json()) == 1


async def test_a_narrow_permission_role_cannot_write_memory(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await _signup(client, "mem7@example.com", "Memory Org 7")

    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": "employee-mem@example.com", "role_key": "employee"},
        )
    assert created.status_code == 201
    token = None
    for record in caplog.records:
        match = re.search(r"/invite/([A-Za-z0-9_-]+)", record.message)
        if match:
            token = match.group(1)
            break
    assert token is not None

    await client.post("/api/v1/auth/logout")
    accept = await client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": token, "full_name": "Employee Mem", "password": "correct-horse-battery"},
    )
    assert accept.status_code == 200, accept.text

    # An employee can still view memory (it grounds AI broadly)...
    view = await client.get("/api/v1/memory")
    assert view.status_code == 200
    # ...but cannot write to it.
    write = await client.post(
        "/api/v1/memory", json={"entry_type": "approved_fact", "content": "Should be blocked."}
    )
    assert write.status_code == 403
