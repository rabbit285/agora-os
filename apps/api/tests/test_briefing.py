"""Tests for the AI Daily Briefing (spec §88, BIZ-03). Every section
reflects this org's own real rows, never the spec's own literal example
numbers, and the briefing is stable across repeated calls the same day
(generated once, not recomputed on every request).
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
            "full_name": "Briefing Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_briefing_has_all_5_spec_named_sections_with_honest_empty_state(
    client: AsyncClient,
) -> None:
    await _signup(client, "brief1@example.com", "Briefing Org 1")
    response = await client.get("/api/v1/briefing")
    assert response.status_code == 200
    body = response.json()
    keys = {s["key"] for s in body["sections"]}
    assert keys == {"urgent", "revenue", "customers", "risk", "operations"}
    urgent = next(s for s in body["sections"] if s["key"] == "urgent")
    assert "No critical security alerts" in urgent["headline"]
    assert body["ai_suggestion"] is None


async def test_urgent_section_reflects_a_real_critical_alert(client: AsyncClient) -> None:
    await _signup(client, "brief2@example.com", "Briefing Org 2")
    created = await client.post(
        "/api/v1/security/alerts", json={"title": "Live critical alert", "severity": "critical"}
    )
    assert created.status_code == 201, created.text

    response = await client.get("/api/v1/briefing")
    body = response.json()
    urgent = next(s for s in body["sections"] if s["key"] == "urgent")
    assert "1" in urgent["headline"]
    assert urgent["items"] == [{"text": "Live critical alert", "link": "/security"}]


async def test_ai_suggestion_reuses_the_highest_risk_recommendation(client: AsyncClient) -> None:
    await _signup(client, "brief3@example.com", "Briefing Org 3")
    await client.post(
        "/api/v1/security/findings",
        json={"title": "Critical finding", "category": "vulnerability", "severity": "critical"},
    )

    response = await client.get("/api/v1/briefing")
    body = response.json()
    assert body["ai_suggestion"] is not None
    assert "critical" in body["ai_suggestion"].lower() or "security" in body["ai_suggestion"].lower()


async def test_briefing_is_stable_across_repeated_calls_the_same_day(client: AsyncClient) -> None:
    await _signup(client, "brief4@example.com", "Briefing Org 4")
    first = await client.get("/api/v1/briefing")
    first_id = first.json()["id"]

    await client.post(
        "/api/v1/security/alerts", json={"title": "New alert after first briefing", "severity": "critical"}
    )
    second = await client.get("/api/v1/briefing")

    assert second.json()["id"] == first_id
    # Still reflects the state at generation time, not the new alert.
    urgent = next(s for s in second.json()["sections"] if s["key"] == "urgent")
    assert "No critical security alerts" in urgent["headline"]


async def test_briefing_is_tenant_isolated(client: AsyncClient) -> None:
    await _signup(client, "brief5a@example.com", "Briefing Org 5A")
    await client.post(
        "/api/v1/security/alerts", json={"title": "Org A alert", "severity": "critical"}
    )

    await client.post("/api/v1/auth/logout")
    await _signup(client, "brief5b@example.com", "Briefing Org 5B")

    response = await client.get("/api/v1/briefing")
    urgent = next(s for s in response.json()["sections"] if s["key"] == "urgent")
    assert "No critical security alerts" in urgent["headline"]
