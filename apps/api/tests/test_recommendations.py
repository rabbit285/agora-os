"""Tests for the AI Recommendation Engine (spec §87, BIZ-02). Each
recommendation is computed from real rows this org actually has —
these tests create the underlying data and assert the recommendation's
content (counts, source references) reflects it exactly, not a
canned/example string from the spec text.
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
            "full_name": "Recommendations Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_no_recommendations_for_a_brand_new_organization(client: AsyncClient) -> None:
    await _signup(client, "reco1@example.com", "Recommendations Org 1")
    response = await client.get("/api/v1/recommendations")
    assert response.status_code == 200
    assert response.json() == []


async def test_compliance_gap_recommendation_reflects_real_control_count(
    client: AsyncClient,
) -> None:
    await _signup(client, "reco2@example.com", "Recommendations Org 2")
    for i in range(3):
        created = await client.post("/api/v1/compliance/controls", json={"title": f"Control {i}"})
        assert created.status_code == 201

    response = await client.get("/api/v1/recommendations")
    assert response.status_code == 200
    body = response.json()
    compliance_recs = [r for r in body if r["category"] == "compliance"]
    assert len(compliance_recs) == 1
    rec = compliance_recs[0]
    assert "3" in rec["title"]
    assert len(rec["sources"]) == 3
    assert all(s.startswith("control:") for s in rec["sources"])
    assert rec["confidence"] in ("low", "medium", "high")
    assert rec["status"] == "new"


async def test_security_recommendation_reflects_real_finding_count(client: AsyncClient) -> None:
    await _signup(client, "reco3@example.com", "Recommendations Org 3")
    for i in range(2):
        created = await client.post(
            "/api/v1/security/findings",
            json={
                "title": f"Finding {i}",
                "category": "vulnerability",
                "severity": "critical",
            },
        )
        assert created.status_code == 201

    response = await client.get("/api/v1/recommendations")
    security_recs = [r for r in response.json() if r["category"] == "security"]
    assert len(security_recs) == 1
    assert "2" in security_recs[0]["title"]


async def test_dismissing_a_recommendation_removes_it_and_it_is_not_resurrected(
    client: AsyncClient,
) -> None:
    await _signup(client, "reco4@example.com", "Recommendations Org 4")
    await client.post("/api/v1/compliance/controls", json={"title": "Control A"})

    first = await client.get("/api/v1/recommendations")
    rec_id = first.json()[0]["id"]

    dismissed = await client.post(f"/api/v1/recommendations/{rec_id}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    # The underlying condition (1 not-started control) still holds, but a
    # dismissed recommendation must not be resurrected by the next refresh.
    second = await client.get("/api/v1/recommendations")
    assert second.json() == []


async def test_actioning_a_recommendation_marks_it_actioned(client: AsyncClient) -> None:
    await _signup(client, "reco5@example.com", "Recommendations Org 5")
    await client.post("/api/v1/compliance/controls", json={"title": "Control A"})

    first = await client.get("/api/v1/recommendations")
    rec_id = first.json()[0]["id"]

    actioned = await client.post(f"/api/v1/recommendations/{rec_id}/action")
    assert actioned.status_code == 200
    assert actioned.json()["status"] == "actioned"

    second = await client.get("/api/v1/recommendations")
    assert second.json() == []


async def test_recommendations_are_tenant_isolated(client: AsyncClient) -> None:
    await _signup(client, "reco6a@example.com", "Recommendations Org 6A")
    await client.post("/api/v1/compliance/controls", json={"title": "Org A Control"})

    await client.post("/api/v1/auth/logout")
    await _signup(client, "reco6b@example.com", "Recommendations Org 6B")

    response = await client.get("/api/v1/recommendations")
    assert response.json() == []
