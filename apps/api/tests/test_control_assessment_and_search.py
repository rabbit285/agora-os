"""Control assessment on read, and global compliance search.

Both replace things that looked functional but were not: a control screen
that opened on an empty pass/fail form even when evidence existed, and a
search box whose results linked into modules that had been withdrawn.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.assessment import load_scoping_profile
from app.compliance.control_assessment import assess_control
from app.compliance.models import Control
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
            "full_name": "Control Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _adopt_gdpr(client: AsyncClient) -> str:
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    gdpr = next(f for f in frameworks if f["key"] == "gdpr")
    await client.put(
        f"/api/v1/compliance/frameworks/{gdpr['id']}/activation", json={"active": True}
    )
    return str(gdpr["id"])


# --- The control screen leads with an assessment ----------------------


async def test_a_control_with_no_evidence_says_so_without_asking_for_a_verdict(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The old screen opened on an empty pass/fail form. The useful thing
    to say is what is missing, not to ask the user to guess."""
    await _signup(client, "ctrl-none@example.com")
    control_id = (
        await client.post("/api/v1/compliance/controls", json={"title": "Access control"})
    ).json()["id"]

    body = (await client.get(f"/api/v1/compliance/controls/{control_id}")).json()
    assessment = body["assessment"]

    assert assessment["status"] == "no_evidence"
    assert assessment["confidence"] == 0
    assert assessment["missing"]
    # It has to name the actual next step. For a control nobody has
    # mapped to a requirement that is not "upload a document" — there is
    # nothing for a document to be assessed against yet, and saying
    # "upload" would send the customer to do work that changes nothing.
    assert "requirement" in assessment["why"].lower()
    assert "mapping to at least one requirement" in assessment["missing"].lower()


async def test_the_derived_assessment_never_overwrites_a_human_one(
    client: AsyncClient,
) -> None:
    """A person's conclusion is information, not a conflict to resolve
    silently."""
    await _signup(client, "ctrl-human@example.com")
    control_id = (
        await client.post("/api/v1/compliance/controls", json={"title": "Access control"})
    ).json()["id"]

    recorded = await client.post(
        f"/api/v1/compliance/controls/{control_id}/assessments",
        json={"status": "pass", "notes": "Verified during the internal audit."},
    )
    assert recorded.status_code in (200, 201), recorded.text

    body = (await client.get(f"/api/v1/compliance/controls/{control_id}")).json()
    assessment = body["assessment"]

    # The derived view still reports the evidence position honestly...
    assert assessment["status"] == "no_evidence"
    # ...and carries the human verdict alongside rather than hiding it.
    assert assessment["recorded_status"] == "pass"
    assert assessment["recorded_at"]


async def test_a_human_assessment_is_written_to_the_audit_trail(
    client: AsyncClient,
) -> None:
    await _signup(client, "ctrl-audit@example.com")
    control_id = (
        await client.post("/api/v1/compliance/controls", json={"title": "Access control"})
    ).json()["id"]
    await client.post(
        f"/api/v1/compliance/controls/{control_id}/assessments",
        json={"status": "fail", "notes": "No escalation procedure exists."},
    )

    events = (await client.get("/api/v1/audit-events")).json()
    actions = {event["action"] for event in events}
    assert "compliance.control.assessed" in actions, actions


async def test_assessment_is_derived_on_read_not_stored(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Calling it twice with no changes gives the same answer, and it
    never needs invalidating when evidence moves."""
    await _signup(client, "ctrl-derived@example.com")
    control_id = (
        await client.post("/api/v1/compliance/controls", json={"title": "Encryption"})
    ).json()["id"]
    control = await db_session.get(Control, uuid.UUID(control_id))
    assert control is not None

    # Scoping is resolved before coverage is counted, so the assessment
    # needs the organization profile the requirement rules read.
    profile = await load_scoping_profile(
        db_session, organization_id=control.organization_id
    )
    first = await assess_control(db_session, control=control, profile=profile)
    second = await assess_control(db_session, control=control, profile=profile)
    assert first.status == second.status
    assert first.confidence == second.confidence


# --- Global search ----------------------------------------------------


async def test_search_finds_controls_and_says_where_to_open_them(
    client: AsyncClient,
) -> None:
    await _signup(client, "search-controls@example.com")
    await _adopt_gdpr(client)

    body = (await client.get("/api/v1/search?q=access")).json()
    controls = [r for r in body["results"] if r["entity_type"] == "control"]
    assert controls, body["results"]
    assert controls[0]["href"].startswith("/compliance/controls/")


async def test_search_covers_requirements_of_adopted_frameworks(
    client: AsyncClient,
) -> None:
    """Searching a phrase from a regulation should find the article."""
    await _signup(client, "search-reqs@example.com")
    frameworks = (await client.get("/api/v1/compliance/frameworks")).json()
    ai_act = next(f for f in frameworks if f["key"] == "eu_ai_act")
    await client.put(
        f"/api/v1/compliance/frameworks/{ai_act['id']}/activation", json={"active": True}
    )

    body = (await client.get("/api/v1/search?q=human oversight")).json()
    requirements = [r for r in body["results"] if r["entity_type"] == "requirement"]
    assert requirements
    # The framework is part of the identity: "Art. 14" alone does not say
    # which regulation.
    assert "EU AI Act" in requirements[0]["label"]


async def test_requirements_of_unadopted_frameworks_are_not_returned(
    client: AsyncClient,
) -> None:
    """A hit that is real but useless pushes the ones that matter off the
    list."""
    await _signup(client, "search-unadopted@example.com")
    body = (await client.get("/api/v1/search?q=human oversight")).json()
    assert [r for r in body["results"] if r["entity_type"] == "requirement"] == []


async def test_no_result_links_into_a_withdrawn_module(client: AsyncClient) -> None:
    """The old client-side routing table sent uncovered results to
    /knowledge/graph, which no longer exists. Every href must point at a
    surface this product still has."""
    await _signup(client, "search-routes@example.com")
    await _adopt_gdpr(client)

    body = (await client.get("/api/v1/search?q=a")).json()
    assert body["results"]
    withdrawn = ("/sales", "/support", "/automation", "/knowledge", "/reports")
    for result in body["results"]:
        assert result["href"].startswith("/")
        assert not result["href"].startswith(withdrawn), result


async def test_search_is_tenant_scoped(client: AsyncClient) -> None:
    await _signup(client, "search-tenant-a@example.com")
    await client.post(
        "/api/v1/compliance/controls", json={"title": "Tenant A distinctive control"}
    )
    await client.post("/api/v1/auth/logout")

    await _signup(client, "search-tenant-b@example.com")
    body = (await client.get("/api/v1/search?q=distinctive")).json()
    assert body["results"] == []


async def test_an_empty_query_returns_nothing_rather_than_everything(
    client: AsyncClient,
) -> None:
    await _signup(client, "search-empty@example.com")
    body = (await client.get("/api/v1/search?q=")).json()
    assert body["results"] == []
