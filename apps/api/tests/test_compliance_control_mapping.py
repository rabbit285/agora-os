"""Mapping controls to requirements after the control already exists.

Guide step A6. Mapping was previously only possible at creation, so the
only way to answer a second requirement with an existing measure was to
create a second control — which then splits its evidence and assessment
history in two, and quietly inflates coverage by counting the same work
twice.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.seed import _ensure_compliance_catalog


@pytest.fixture(autouse=True)
async def _catalog(db_session: AsyncSession) -> None:
    await _ensure_compliance_catalog(db_session)


async def _signup(client: AsyncClient, email: str) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Compliance Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _gdpr(client: AsyncClient) -> tuple[str, dict[str, str]]:
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    framework_id = next(f["id"] for f in frameworks if f["key"] == "gdpr")
    requirements = (
        await client.get(f"/api/v1/compliance/frameworks/{framework_id}/requirements")
    ).json()
    return framework_id, {r["reference_code"]: r["id"] for r in requirements}


async def test_control_carries_category_priority_and_owner(client: AsyncClient) -> None:
    """A6 asks for all three. They were absent, so the only place to put
    "who cares about this and how urgent is it" was the description."""
    await _signup(client, "map-fields@example.com")
    _, requirements = await _gdpr(client)

    response = await client.post(
        "/api/v1/compliance/controls",
        json={
            "title": "Maintain Record of Processing Activities",
            "description": "The organization maintains an up-to-date RoPA.",
            "category": "Privacy / Data Governance",
            "priority": "high",
            "requirement_ids": [requirements["Art. 30"]],
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["category"] == "Privacy / Data Governance"
    assert body["priority"] == "high"
    # A new control is never born "implemented" — whether it is evidenced
    # is derived from what is attached, not asserted at creation.
    assert body["status"] == "not_started"


async def test_existing_control_can_be_mapped_to_another_requirement(
    client: AsyncClient,
) -> None:
    """The case that forced duplicates: one breach procedure answers GDPR
    Article 33 and, in a real programme, several others."""
    await _signup(client, "map-existing@example.com")
    framework_id, requirements = await _gdpr(client)

    control_id = (
        await client.post(
            "/api/v1/compliance/controls",
            json={
                "title": "Personal Data Breach Detection and Notification",
                "requirement_ids": [requirements["Art. 33"]],
            },
        )
    ).json()["id"]

    response = await client.post(
        f"/api/v1/compliance/controls/{control_id}/requirements",
        json={"requirement_ids": [requirements["Art. 5"]]},
    )
    assert response.status_code == 201, response.text
    codes = {r["reference_code"] for r in response.json()["requirements"]}
    assert codes == {"Art. 33", "Art. 5"}

    # And the framework dashboard reflects it without a second control.
    dashboard = (
        await client.get(f"/api/v1/compliance/frameworks/{framework_id}/dashboard")
    ).json()
    by_code = {r["reference_code"]: r for r in dashboard["requirements"]}
    assert len(by_code["Art. 5"]["controls"]) == 1
    assert by_code["Art. 5"]["controls"][0]["id"] == control_id


async def test_mapping_the_same_requirement_twice_is_a_no_op(client: AsyncClient) -> None:
    """The button has to be safe to press twice — a duplicate mapping row
    would double-count the control on the dashboard."""
    await _signup(client, "map-twice@example.com")
    framework_id, requirements = await _gdpr(client)
    control_id = (
        await client.post(
            "/api/v1/compliance/controls",
            json={"title": "RoPA", "requirement_ids": [requirements["Art. 30"]]},
        )
    ).json()["id"]

    again = await client.post(
        f"/api/v1/compliance/controls/{control_id}/requirements",
        json={"requirement_ids": [requirements["Art. 30"]]},
    )
    assert again.status_code == 201
    assert len(again.json()["requirements"]) == 1

    dashboard = (
        await client.get(f"/api/v1/compliance/frameworks/{framework_id}/dashboard")
    ).json()
    by_code = {r["reference_code"]: r for r in dashboard["requirements"]}
    assert len(by_code["Art. 30"]["controls"]) == 1


async def test_unmapping_keeps_the_control(client: AsyncClient) -> None:
    """Removing a mapping must not remove the control — it may answer
    other requirements, and deleting it would take its evidence and
    assessment history with it."""
    await _signup(client, "map-remove@example.com")
    _, requirements = await _gdpr(client)
    control_id = (
        await client.post(
            "/api/v1/compliance/controls",
            json={
                "title": "Shared control",
                "requirement_ids": [requirements["Art. 30"], requirements["Art. 5"]],
            },
        )
    ).json()["id"]

    removed = await client.delete(
        f"/api/v1/compliance/controls/{control_id}/requirements/{requirements['Art. 5']}"
    )
    assert removed.status_code == 204

    detail = (await client.get(f"/api/v1/compliance/controls/{control_id}")).json()
    assert [r["reference_code"] for r in detail["requirements"]] == ["Art. 30"]


async def test_mapping_another_organizations_control_is_refused(
    client: AsyncClient,
) -> None:
    await _signup(client, "map-iso-a@example.com")
    _, requirements = await _gdpr(client)
    control_id = (
        await client.post(
            "/api/v1/compliance/controls",
            json={"title": "Org A control", "requirement_ids": [requirements["Art. 30"]]},
        )
    ).json()["id"]
    await client.post("/api/v1/auth/logout")

    await _signup(client, "map-iso-b@example.com")
    response = await client.post(
        f"/api/v1/compliance/controls/{control_id}/requirements",
        json={"requirement_ids": [requirements["Art. 5"]]},
    )
    assert response.status_code == 404


async def test_a6_end_state_is_four_mapped_requirements_without_evidence(
    client: AsyncClient,
) -> None:
    """The state A6 is meant to leave behind: every requirement has a
    control, and the assessment reports evidence missing rather than
    treating a mapped control as satisfaction."""
    await _signup(client, "map-a6@example.com")
    framework_id, requirements = await _gdpr(client)

    for code, title in (
        ("Art. 30", "Maintain Record of Processing Activities"),
        ("Art. 33", "Personal Data Breach Detection and Notification"),
        ("Art. 35", "DPIA Screening and Assessment Process"),
        ("Art. 5", "Personal Data Processing Principles"),
    ):
        created = await client.post(
            "/api/v1/compliance/controls",
            json={
                "title": title,
                "category": "Privacy / Data Governance",
                "priority": "high",
                "requirement_ids": [requirements[code]],
            },
        )
        assert created.status_code == 201, created.text

    dashboard = (
        await client.get(f"/api/v1/compliance/frameworks/{framework_id}/dashboard")
    ).json()
    for row in dashboard["requirements"]:
        assert len(row["controls"]) == 1, f"{row['reference_code']} has no mapped control"

    result = (await client.post(f"/api/v1/compliance/frameworks/{framework_id}/assess")).json()
    statuses = {r["reference_code"]: r["status"] for r in result["requirements"]}
    # Mapped but unevidenced — not "not_assessed" (no control) and
    # certainly not satisfied.
    assert set(statuses.values()) == {"evidence_missing"}
    assert result["satisfied_count"] == 0
    assert result["gap_count"] == 4


async def test_mapping_is_audited(client: AsyncClient) -> None:
    await _signup(client, "map-audit@example.com")
    _, requirements = await _gdpr(client)
    control_id = (
        await client.post(
            "/api/v1/compliance/controls",
            json={"title": "RoPA", "requirement_ids": [requirements["Art. 30"]]},
        )
    ).json()["id"]
    await client.post(
        f"/api/v1/compliance/controls/{control_id}/requirements",
        json={"requirement_ids": [requirements["Art. 5"]]},
    )

    events = (
        await client.get("/api/v1/audit-events?action_prefix=compliance.control&limit=20")
    ).json()
    assert "compliance.control.mapped" in {e["action"] for e in events}
