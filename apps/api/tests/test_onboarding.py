"""Tests for the Onboarding Experience (spec §68): the 10-step wizard's
backend (company/goals/profile steps, resumable via current_step) and the
live-computed "Business AI Readiness" output (spec §68's final step) —
every dimension and opportunity here must come from real organization
data, never a hardcoded number.
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
            "full_name": "Onboarding Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def test_status_creates_a_profile_starting_at_step_one(client: AsyncClient) -> None:
    await _signup(client, "onboard1@example.com", "Onboard Org 1")
    response = await client.get("/api/v1/onboarding/status")
    assert response.status_code == 200
    body = response.json()
    assert body["current_step"] == 1
    assert body["completed_at"] is None


async def test_steps_advance_current_step_and_persist_data(client: AsyncClient) -> None:
    await _signup(client, "onboard2@example.com", "Onboard Org 2")

    company = await client.put(
        "/api/v1/onboarding/company",
        json={"industry": "Software", "employee_count_range": "11-50"},
    )
    assert company.status_code == 200
    assert company.json()["current_step"] == 2

    goals = await client.put(
        "/api/v1/onboarding/goals",
        json={"selected_goals": ["improve_compliance", "find_more_customers"]},
    )
    assert goals.status_code == 200
    assert goals.json()["current_step"] == 3
    assert goals.json()["selected_goals"] == ["improve_compliance", "find_more_customers"]

    status = await client.get("/api/v1/onboarding/status")
    assert status.json()["industry"] == "Software"


async def test_goals_step_rejects_an_unknown_goal_key(client: AsyncClient) -> None:
    await _signup(client, "onboard3@example.com", "Onboard Org 3")
    response = await client.put(
        "/api/v1/onboarding/goals", json={"selected_goals": ["not_a_real_goal"]}
    )
    assert response.status_code == 422


async def test_full_step_sequence_reaches_step_nine_before_readiness(
    client: AsyncClient,
) -> None:
    await _signup(client, "onboard4b@example.com", "Onboard Org 4b")
    await client.put(
        "/api/v1/onboarding/company", json={"industry": "SaaS", "employee_count_range": "1-10"}
    )
    await client.put("/api/v1/onboarding/goals", json={"selected_goals": ["improve_security"]})
    await client.put(
        "/api/v1/onboarding/compliance-profile", json={"selected_framework_keys": ["gdpr"]}
    )
    await client.put(
        "/api/v1/onboarding/security-profile", json={"primary_cloud_provider": "aws"}
    )
    await client.put("/api/v1/onboarding/sales-profile", json={"sales_focus": "Enterprise"})
    await client.put(
        "/api/v1/onboarding/support-profile", json={"support_channels": ["email"]}
    )
    connect = await client.post("/api/v1/onboarding/advance")
    assert connect.json()["current_step"] == 8
    knowledge = await client.post("/api/v1/onboarding/advance")
    assert knowledge.json()["current_step"] == 9


async def test_complete_sets_completed_at_and_step_ten(client: AsyncClient) -> None:
    await _signup(client, "onboard4@example.com", "Onboard Org 4")
    response = await client.post("/api/v1/onboarding/complete")
    assert response.status_code == 200
    body = response.json()
    assert body["completed_at"] is not None
    assert body["current_step"] == 10


async def test_readiness_is_honestly_zero_for_a_brand_new_organization(
    client: AsyncClient,
) -> None:
    await _signup(client, "onboard5@example.com", "Onboard Org 5")
    response = await client.get("/api/v1/onboarding/readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["compliance"]["percent"] == 0.0
    assert body["security"]["percent"] == 100.0  # no findings/alerts yet -> nothing to deduct
    assert body["sales_automation"]["percent"] == 0.0
    assert body["support_automation"]["percent"] == 0.0


async def test_readiness_compliance_percent_reflects_implemented_controls(
    client: AsyncClient,
) -> None:
    await _signup(client, "onboard6@example.com", "Onboard Org 6")

    created = await client.post(
        "/api/v1/compliance/controls", json={"title": "Access reviews"}
    )
    assert created.status_code == 201, created.text
    control_id = created.json()["id"]

    before = await client.get("/api/v1/onboarding/readiness")
    assert before.json()["compliance"]["percent"] == 0.0
    assert any("compliance control gap" in o["title"] for o in before.json()["opportunities"])

    assessed = await client.post(
        f"/api/v1/compliance/controls/{control_id}/assessments", json={"status": "pass"}
    )
    assert assessed.status_code == 201, assessed.text

    after = await client.get("/api/v1/onboarding/readiness")
    assert after.json()["compliance"]["percent"] == 100.0


async def test_readiness_flags_admins_without_mfa(client: AsyncClient) -> None:
    await _signup(client, "onboard7@example.com", "Onboard Org 7")
    response = await client.get("/api/v1/onboarding/readiness")
    titles = [o["title"] for o in response.json()["opportunities"]]
    assert any("Enable MFA" in t for t in titles)
