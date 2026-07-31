"""Tests for spec §72's Global Create button backend support (PLAT-22):
GET /organizations/current/my-permissions exposes the current membership's
resolved permission keys so the frontend can filter its options to what the
user can actually create — the same set require_permission() already
enforces server-side on every write, not a second, possibly-drifting
source of truth.
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
            "full_name": "Global Create Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_org_admin_gets_every_permission_key(client: AsyncClient) -> None:
    await _signup(client, "gcreate1@example.com", "Global Create Org 1")
    response = await client.get("/api/v1/organizations/current/my-permissions")
    assert response.status_code == 200
    permissions = response.json()
    assert "core.tasks.manage" in permissions
    assert "sales.leads.manage" in permissions
    assert "org.entities.manage" in permissions


async def test_read_only_style_employee_gets_a_narrow_permission_set(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await _signup(client, "gcreate2@example.com", "Global Create Org 2")

    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": "employee-gcreate@example.com", "role_key": "employee"},
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
        json={
            "token": token,
            "full_name": "Employee GCreate",
            "password": "correct-horse-battery",
        },
    )
    assert accept.status_code == 200, accept.text

    response = await client.get("/api/v1/organizations/current/my-permissions")
    assert response.status_code == 200
    permissions = response.json()
    assert "core.tasks.manage" in permissions
    # employee never gets sales/compliance/security management permissions.
    assert "sales.leads.manage" not in permissions
    assert "compliance.risks.manage" not in permissions
    assert "org.entities.manage" not in permissions
