"""Tests for the newly-built /settings/roles and /settings/ai-providers
backend endpoints (finding A3 — both pages were previously documented as
at least partially built but did not exist anywhere in the codebase).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Roles Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_list_roles_returns_all_16_system_roles_with_real_permissions(
    client: AsyncClient,
) -> None:
    await _signup(client, "roles1@example.com", "Roles Org 1")
    response = await client.get("/api/v1/organizations/current/roles")
    assert response.status_code == 200
    roles = response.json()
    assert len(roles) == 16
    by_key = {r["key"]: r for r in roles}
    assert "core.tasks.manage" in by_key["org_admin"]["permissions"]
    assert by_key["read_only"]["permissions"] == []


async def test_ai_providers_reports_demo_mode_when_no_key_configured(
    client: AsyncClient,
) -> None:
    await _signup(client, "roles2@example.com", "Roles Org 2")
    response = await client.get("/api/v1/ai/providers")
    assert response.status_code == 200
    providers = response.json()
    by_key = {p["provider_key"]: p for p in providers}
    assert by_key["anthropic"]["has_adapter"] is True
    assert by_key["anthropic"]["configured"] is False
    assert by_key["anthropic"]["active"] is False
    assert by_key["azure_openai"]["has_adapter"] is False
    assert not any(p["active"] for p in providers)


async def test_ai_providers_reports_a_configured_provider_as_active(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key")
    monkeypatch.setattr(settings, "ai_provider", "anthropic")

    await _signup(client, "roles3@example.com", "Roles Org 3")
    response = await client.get("/api/v1/ai/providers")
    assert response.status_code == 200
    by_key = {p["provider_key"]: p for p in response.json()}
    assert by_key["anthropic"]["configured"] is True
    assert by_key["anthropic"]["active"] is True
    assert by_key["openai"]["active"] is False
