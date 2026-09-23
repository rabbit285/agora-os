"""DPIA, end to end.

Processing Activity -> DPIA screening -> DPIA -> Risks -> Controls ->
Residual risk -> DPO approval.

The screening tests matter most. Article 35 has a legal threshold, and a
tool that guesses it in the permissive direction causes an organization
to skip an assessment the law required — the one failure here that cannot
be noticed by looking at the screen afterwards.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.dpia_screening import risk_level_from, screen_for_dpia
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
            "full_name": "Privacy Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _activity(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/compliance/processing-activities",
        json={
            "name": "AI-Assisted Customer Support",
            "purpose": "Provide customer support using an AI assistant.",
            "legal_basis": "legitimate_interests",
            "data_categories": ["names", "emails", "messages"],
            "data_subjects": "Customers",
            "retention_period": "24 months after last contact",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- The screening rule ------------------------------------------------


def test_two_edpb_criteria_require_a_dpia() -> None:
    result = screen_for_dpia({"innovative_technology": True, "systematic_monitoring": True})
    assert result.outcome == "required"
    assert len(result.criteria_met) == 2


def test_one_criterion_is_recommended_not_required() -> None:
    """The EDPB's threshold is two. Treating one as mandatory would make
    the screening useless — almost everything meets one."""
    result = screen_for_dpia({"innovative_technology": True})
    assert result.outcome == "recommended"


def test_article_35_3_case_requires_a_dpia_on_its_own() -> None:
    """The Regulation names these outright, so no counting applies."""
    result = screen_for_dpia({"large_scale_public_monitoring": True})
    assert result.outcome == "required"
    assert result.mandatory_triggers == ["large_scale_public_monitoring"]
    assert "35(3)" in result.rationale


def test_no_criteria_does_not_assert_that_no_dpia_is_needed() -> None:
    """The tool reports what was answered. Whether a DPIA is required is
    the controller's decision and a supervisory authority's to review."""
    result = screen_for_dpia({"innovative_technology": False})
    assert result.outcome == "not_indicated"
    lowered = result.rationale.lower()
    assert "controller remains responsible" in lowered
    assert "not a determination by a supervisory authority" in lowered


def test_risk_matrix_is_shared_by_inherent_and_residual() -> None:
    """Scoring the two on different scales would let a mitigation look
    effective purely through arithmetic."""
    assert risk_level_from("medium", "high") == "high"
    assert risk_level_from("low", "medium") == "low"
    assert risk_level_from("high", "high") == "high"


# --- The endpoints -----------------------------------------------------


async def test_screening_endpoint_explains_its_outcome(client: AsyncClient) -> None:
    await _signup(client, "dpia-screen@example.com")
    activity_id = await _activity(client)

    response = await client.post(
        "/api/v1/compliance/dpias/screening",
        json={
            "processing_activity_id": activity_id,
            "answers": {"innovative_technology": True, "systematic_monitoring": True},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "required"
    assert len(body["criteria_met"]) == 2
    # Unanswered criteria are surfaced, not treated as "no".
    assert body["unanswered"]


async def test_screening_rejects_another_organizations_activity(
    client: AsyncClient,
) -> None:
    await _signup(client, "dpia-tenant-a@example.com")
    activity_id = await _activity(client)
    await client.post("/api/v1/auth/logout")

    await _signup(client, "dpia-tenant-b@example.com")
    response = await client.post(
        "/api/v1/compliance/dpias/screening",
        json={"processing_activity_id": activity_id, "answers": {"large_scale": True}},
    )
    assert response.status_code == 404


async def test_dpia_sections_are_separately_recorded(client: AsyncClient) -> None:
    """Article 35(7) content. One prose blob cannot show a reviewer that
    necessity was never addressed."""
    await _signup(client, "dpia-sections@example.com")
    activity_id = await _activity(client)
    dpia_id = (
        await client.post(
            "/api/v1/compliance/dpias",
            json={
                "title": "DPIA: AI-Assisted Customer Support",
                "processing_activity_id": activity_id,
                "risk_level": "high",
            },
        )
    ).json()["id"]

    response = await client.patch(
        f"/api/v1/compliance/dpias/{dpia_id}/sections",
        json={
            "necessity_assessment": "Message content is necessary to generate a relevant answer.",
            "proportionality_assessment": "Agents review every draft before sending.",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["necessity_assessment"].startswith("Message content")
    # Untouched sections stay null rather than being blanked, so partial
    # completion is visible.
    assert body["consultation_notes"] is None


async def test_residual_risk_does_not_improve_because_nobody_reassessed(
    client: AsyncClient,
) -> None:
    """The property that makes a residual rating worth having. A risk with
    no residual assessment counts at its inherent level — otherwise a DPIA
    reaches "low" through inaction."""
    await _signup(client, "dpia-residual@example.com")
    activity_id = await _activity(client)
    dpia_id = (
        await client.post(
            "/api/v1/compliance/dpias",
            json={
                "title": "DPIA: Support",
                "processing_activity_id": activity_id,
                "risk_level": "high",
            },
        )
    ).json()["id"]

    risk_id = (
        await client.post(
            "/api/v1/compliance/risks",
            json={
                "title": "Unauthorized cross-customer disclosure",
                "likelihood": "medium",
                "impact": "high",
                "dpia_id": dpia_id,
            },
        )
    ).json()["id"]

    before = await client.post(f"/api/v1/compliance/dpias/{dpia_id}/recalculate-residual")
    assert before.json()["residual_risk_level"] == "high"

    await client.patch(
        f"/api/v1/compliance/risks/{risk_id}/residual",
        json={"residual_likelihood": "low", "residual_impact": "medium"},
    )
    after = await client.post(f"/api/v1/compliance/dpias/{dpia_id}/recalculate-residual")
    assert after.json()["residual_risk_level"] == "low"


async def test_residual_takes_the_worst_risk_not_the_average(client: AsyncClient) -> None:
    """Averaging would let a pile of trivial risks mask a severe one."""
    await _signup(client, "dpia-worst@example.com")
    activity_id = await _activity(client)
    dpia_id = (
        await client.post(
            "/api/v1/compliance/dpias",
            json={"title": "DPIA", "processing_activity_id": activity_id, "risk_level": "high"},
        )
    ).json()["id"]

    for likelihood, impact in (("low", "low"), ("high", "high")):
        risk_id = (
            await client.post(
                "/api/v1/compliance/risks",
                json={
                    "title": f"{likelihood}/{impact}",
                    "likelihood": likelihood,
                    "impact": impact,
                    "dpia_id": dpia_id,
                },
            )
        ).json()["id"]
        await client.patch(
            f"/api/v1/compliance/risks/{risk_id}/residual",
            json={"residual_likelihood": likelihood, "residual_impact": impact},
        )

    result = await client.post(f"/api/v1/compliance/dpias/{dpia_id}/recalculate-residual")
    assert result.json()["residual_risk_level"] == "high"


async def test_high_risk_dpia_cannot_be_approved_without_its_approval(
    client: AsyncClient,
) -> None:
    """C8/C9. Sign-off is the point of a DPIA; a status field anyone can
    set to "approved" records a decision nobody made."""
    await _signup(client, "dpia-approval@example.com")
    activity_id = await _activity(client)
    dpia = (
        await client.post(
            "/api/v1/compliance/dpias",
            json={
                "title": "DPIA: Support",
                "processing_activity_id": activity_id,
                "risk_level": "high",
            },
        )
    ).json()
    assert dpia["approval_id"] is not None

    # Draft → in_review → approved. The lifecycle no longer lets a
    # status field skip a stage, so the gate is reached the way a person
    # would reach it.
    moved = await client.patch(
        f"/api/v1/compliance/dpias/{dpia['id']}/status", json={"status": "in_review"}
    )
    assert moved.status_code == 200, moved.text

    response = await client.patch(
        f"/api/v1/compliance/dpias/{dpia['id']}/status", json={"status": "approved"}
    )
    assert response.status_code == 422
    assert "approval" in response.json()["error"]["message"].lower()


async def test_risk_linked_to_an_unknown_dpia_is_a_404_not_a_500(
    client: AsyncClient,
) -> None:
    """Found by driving the API: an unknown id reached the foreign key and
    surfaced as an opaque server error, which reads as our fault rather
    than the caller's typo."""
    await _signup(client, "dpia-badlink@example.com")
    response = await client.post(
        "/api/v1/compliance/risks",
        json={
            "title": "Orphan",
            "likelihood": "low",
            "impact": "low",
            "dpia_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 404


async def test_screening_is_audited(client: AsyncClient) -> None:
    await _signup(client, "dpia-audit@example.com")
    activity_id = await _activity(client)
    await client.post(
        "/api/v1/compliance/dpias/screening",
        json={"processing_activity_id": activity_id, "answers": {"large_scale": True}},
    )
    events = (
        await client.get("/api/v1/audit-events?action_prefix=compliance.dpia&limit=20")
    ).json()
    assert "compliance.dpia.screened" in {e["action"] for e in events}
