"""Tests for spec §53's "Support:" multi-tenancy tier — real LegalEntity/
Team CRUD (PLAT-16). The "Future:" tier of that same spec section (parent
organization / subsidiaries / agency-consultant multi-client mode) remains
genuinely unbuilt, disclosed in docs/KNOWN_LIMITATIONS.md — these tests
only cover what's actually implemented.
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
            "full_name": "Entities Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_signup_creates_exactly_one_default_legal_entity(client: AsyncClient) -> None:
    await _signup(client, "entities1@example.com", "Entities Org 1")
    response = await client.get("/api/v1/organizations/current/legal-entities")
    assert response.status_code == 200
    entities = response.json()
    assert len(entities) == 1
    assert entities[0]["is_default"] is True
    assert entities[0]["is_active"] is True


async def test_org_admin_can_create_and_update_a_legal_entity(client: AsyncClient) -> None:
    await _signup(client, "entities2@example.com", "Entities Org 2")

    created = await client.post(
        "/api/v1/organizations/current/legal-entities",
        json={"name": "Agora GmbH", "country": "DE"},
    )
    assert created.status_code == 201, created.text
    entity_id = created.json()["id"]
    assert created.json()["is_default"] is False

    updated = await client.patch(
        f"/api/v1/organizations/current/legal-entities/{entity_id}",
        json={"country": "AT"},
    )
    assert updated.status_code == 200
    assert updated.json()["country"] == "AT"


async def test_setting_a_new_default_demotes_the_previous_one(client: AsyncClient) -> None:
    await _signup(client, "entities3@example.com", "Entities Org 3")
    entities = (await client.get("/api/v1/organizations/current/legal-entities")).json()
    original_default_id = entities[0]["id"]

    created = await client.post(
        "/api/v1/organizations/current/legal-entities", json={"name": "Second Entity"}
    )
    new_id = created.json()["id"]

    promoted = await client.patch(
        f"/api/v1/organizations/current/legal-entities/{new_id}", json={"is_default": True}
    )
    assert promoted.json()["is_default"] is True

    entities_after = (await client.get("/api/v1/organizations/current/legal-entities")).json()
    by_id = {e["id"]: e for e in entities_after}
    assert by_id[new_id]["is_default"] is True
    assert by_id[original_default_id]["is_default"] is False


async def test_cannot_archive_the_default_legal_entity(client: AsyncClient) -> None:
    await _signup(client, "entities4@example.com", "Entities Org 4")
    entities = (await client.get("/api/v1/organizations/current/legal-entities")).json()
    default_id = entities[0]["id"]

    response = await client.delete(f"/api/v1/organizations/current/legal-entities/{default_id}")
    assert response.status_code == 409


async def test_archiving_a_non_default_legal_entity_sets_it_inactive(client: AsyncClient) -> None:
    await _signup(client, "entities5@example.com", "Entities Org 5")
    created = await client.post(
        "/api/v1/organizations/current/legal-entities", json={"name": "To Archive"}
    )
    entity_id = created.json()["id"]

    response = await client.delete(f"/api/v1/organizations/current/legal-entities/{entity_id}")
    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_team_can_be_created_and_linked_to_a_legal_entity(client: AsyncClient) -> None:
    await _signup(client, "entities6@example.com", "Entities Org 6")
    entities = (await client.get("/api/v1/organizations/current/legal-entities")).json()
    default_entity_id = entities[0]["id"]

    created = await client.post(
        "/api/v1/organizations/current/teams",
        json={"name": "Platform Team", "legal_entity_id": default_entity_id},
    )
    assert created.status_code == 201, created.text
    assert created.json()["legal_entity_id"] == default_entity_id
    assert created.json()["is_active"] is True

    listed = await client.get("/api/v1/organizations/current/teams")
    assert len(listed.json()) == 1


async def test_team_cannot_link_to_a_legal_entity_from_another_organization(
    client: AsyncClient,
) -> None:
    await _signup(client, "entities7@example.com", "Entities Org 7")

    # A separate org's legal entity id — real signup, different session cookie.
    other_client_response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "entities7b@example.com",
            "password": "correct-horse-battery",
            "full_name": "Other Org Admin",
            "organization_name": "Entities Org 7 Other",
        },
    )
    assert other_client_response.status_code == 200

    # Now we're logged into the second org (signup logs the new session in) —
    # capture its default legal entity, then create a fresh org and confirm
    # cross-tenant linking is rejected.
    other_org_entities = (await client.get("/api/v1/organizations/current/legal-entities")).json()
    other_entity_id = other_org_entities[0]["id"]

    await _signup(client, "entities7c@example.com", "Entities Org 7 Third")
    response = await client.post(
        "/api/v1/organizations/current/teams",
        json={"name": "Cross-tenant Team", "legal_entity_id": other_entity_id},
    )
    assert response.status_code == 404


async def test_archive_team_sets_it_inactive(client: AsyncClient) -> None:
    await _signup(client, "entities8@example.com", "Entities Org 8")
    created = await client.post("/api/v1/organizations/current/teams", json={"name": "Temp Team"})
    team_id = created.json()["id"]

    response = await client.delete(f"/api/v1/organizations/current/teams/{team_id}")
    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_employee_cannot_manage_legal_entities(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await _signup(client, "entities9@example.com", "Entities Org 9")

    with caplog.at_level("INFO", logger="agora.invitations"):
        created = await client.post(
            "/api/v1/organizations/current/invitations",
            json={"email": "employee9@example.com", "role_key": "employee"},
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
        json={"token": token, "full_name": "Employee Nine", "password": "correct-horse-battery"},
    )
    assert accept.status_code == 200, accept.text

    response = await client.get("/api/v1/organizations/current/legal-entities")
    assert response.status_code == 403
