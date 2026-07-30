"""Tests for the per-framework compliance dashboard (COMP-18): for each
requirement, which of this org's Controls map to it and their status, plus
an overall coverage percentage.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Framework, Requirement


async def _signup(client: AsyncClient, email: str, org_name: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Dashboard Tester",
            "organization_name": org_name,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _seed_framework(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    framework = Framework(key="test-fw", name="Test Framework", description=None)
    db_session.add(framework)
    await db_session.flush()
    req1 = Requirement(framework_id=framework.id, reference_code="TF-1", title="Requirement one")
    req2 = Requirement(framework_id=framework.id, reference_code="TF-2", title="Requirement two")
    db_session.add(req1)
    db_session.add(req2)
    await db_session.flush()
    await db_session.commit()
    return framework.id, req1.id, req2.id


async def test_dashboard_shows_zero_coverage_with_no_controls(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "dashboard1@example.com", "Dashboard Org 1")
    framework_id, _, _ = await _seed_framework(db_session)

    response = await client.get(f"/api/v1/compliance/frameworks/{framework_id}/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["coverage_percent"] == 0.0
    assert len(body["requirements"]) == 2
    assert all(r["controls"] == [] for r in body["requirements"])


async def test_dashboard_reflects_mapped_and_implemented_controls(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "dashboard2@example.com", "Dashboard Org 2")
    framework_id, req1_id, req2_id = await _seed_framework(db_session)

    control = await client.post(
        "/api/v1/compliance/controls",
        json={"title": "Access control policy", "requirement_ids": [str(req1_id)]},
    )
    control_id = control.json()["id"]
    await client.post(
        f"/api/v1/compliance/controls/{control_id}/assessments",
        json={"status": "pass", "notes": "Reviewed"},
    )

    response = await client.get(f"/api/v1/compliance/frameworks/{framework_id}/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["coverage_percent"] == 50.0

    req1_row = next(r for r in body["requirements"] if r["id"] == str(req1_id))
    assert len(req1_row["controls"]) == 1
    assert req1_row["controls"][0]["status"] == "implemented"

    req2_row = next(r for r in body["requirements"] if r["id"] == str(req2_id))
    assert req2_row["controls"] == []


async def test_dashboard_unknown_framework_returns_404(client: AsyncClient) -> None:
    await _signup(client, "dashboard3@example.com", "Dashboard Org 3")
    response = await client.get(f"/api/v1/compliance/frameworks/{uuid.uuid4()}/dashboard")
    assert response.status_code == 404
