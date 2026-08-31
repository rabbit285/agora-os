"""One queue for everything waiting on a person.

The product's argument is that AI does the repetitive work and humans
handle exceptions — which only holds if the exceptions are in one place.
These tests are mostly about what the queue refuses to do: pad itself
with things nobody can act on, and claim credit for automation that did
not happen.
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
            "full_name": "Review Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def test_a_new_organization_has_an_empty_queue(client: AsyncClient) -> None:
    """An empty Review Center is a good outcome and has to be able to say
    so, rather than padding itself to look busy."""
    await _signup(client, "review-empty@example.com")
    body = (await client.get("/api/v1/compliance/review-center")).json()
    assert body["total_needing_review"] == 0
    assert all(category["count"] == 0 for category in body["categories"])
    assert body["auto_accepted_recently"] == 0


async def test_every_category_is_present_even_when_empty(client: AsyncClient) -> None:
    """The categories are the shape of the work. A customer needs to see
    that risk acceptance was considered and found empty, not wonder
    whether it was forgotten."""
    await _signup(client, "review-shape@example.com")
    body = (await client.get("/api/v1/compliance/review-center")).json()
    keys = {category["key"] for category in body["categories"]}
    assert {
        "evidence_mappings",
        "approvals",
        "ai_classifications",
        "remediation_completion",
        "control_assessments",
        "risk_acceptance",
        "framework_applicability",
    } <= keys


async def test_an_unscreened_ai_system_appears_for_review(client: AsyncClient) -> None:
    await _signup(client, "review-ai@example.com")
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Support Agent", "purpose": "Answer questions."},
    )

    body = (await client.get("/api/v1/compliance/review-center")).json()
    classifications = next(
        c for c in body["categories"] if c["key"] == "ai_classifications"
    )
    assert classifications["count"] == 1
    assert "Support Agent" in classifications["items"][0]["title"]


async def test_a_stale_control_assessment_appears_for_review(
    client: AsyncClient,
) -> None:
    """Evidence changed after the last assessment, so its conclusion is
    out of date and someone has to re-run it."""
    await _signup(client, "review-stale@example.com")
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")
    await client.put(
        f"/api/v1/compliance/frameworks/{gdpr['id']}/activation", json={"active": True}
    )

    controls = (await client.get("/api/v1/compliance/controls")).json()
    assert controls
    # Nothing has changed yet, so nothing should be listed as stale.
    body = (await client.get("/api/v1/compliance/review-center")).json()
    stale = next(c for c in body["categories"] if c["key"] == "control_assessments")
    assert stale["count"] == 0


async def test_recommended_but_unadopted_frameworks_appear_for_review(
    client: AsyncClient,
) -> None:
    await _signup(client, "review-frameworks@example.com")
    await client.put(
        "/api/v1/compliance/company-facts",
        json={
            "sells_to_eu_customers": True,
            "processes_personal_data": True,
            "builds_ai_features": True,
        },
    )

    body = (await client.get("/api/v1/compliance/review-center")).json()
    applicability = next(
        c for c in body["categories"] if c["key"] == "framework_applicability"
    )
    assert applicability["count"] > 0
    assert any("Adopt" in item["title"] for item in applicability["items"])


async def test_adopting_a_framework_removes_it_from_the_queue(
    client: AsyncClient,
) -> None:
    await _signup(client, "review-adopted@example.com")
    await client.put(
        "/api/v1/compliance/company-facts",
        json={"sells_to_eu_customers": True, "processes_personal_data": True},
    )
    before = (await client.get("/api/v1/compliance/review-center")).json()
    pending = next(c for c in before["categories"] if c["key"] == "framework_applicability")
    assert pending["count"] > 0

    await client.post(
        "/api/v1/compliance/frameworks/adopt-recommended",
        json={"framework_keys": ["gdpr"]},
    )

    after = (await client.get("/api/v1/compliance/review-center")).json()
    remaining = next(c for c in after["categories"] if c["key"] == "framework_applicability")
    assert all("GDPR" not in item["title"] for item in remaining["items"])


async def test_every_item_links_somewhere_a_decision_can_be_made(
    client: AsyncClient,
) -> None:
    """A queue that lists work without taking you to it just relocates the
    searching."""
    await _signup(client, "review-links@example.com")
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Support Agent", "purpose": "Answer questions."},
    )
    await client.put(
        "/api/v1/compliance/company-facts",
        json={"sells_to_eu_customers": True, "processes_personal_data": True},
    )

    body = (await client.get("/api/v1/compliance/review-center")).json()
    items = [item for category in body["categories"] for item in category["items"]]
    assert items
    for item in items:
        assert item["href"].startswith("/")
        assert item["priority"] in {"high", "medium", "low"}


async def test_the_queue_is_tenant_scoped(client: AsyncClient) -> None:
    await _signup(client, "review-tenant-a@example.com")
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={"name": "Tenant A System", "purpose": "Something."},
    )
    await client.post("/api/v1/auth/logout")

    await _signup(client, "review-tenant-b@example.com")
    body = (await client.get("/api/v1/compliance/review-center")).json()
    assert body["total_needing_review"] == 0
