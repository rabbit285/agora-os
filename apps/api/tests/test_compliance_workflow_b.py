"""AI system governance, end to end.

AI System -> EU AI Act screening -> Privacy assessment -> Risk -> Control
-> Approval -> AI Inventory.

The screening tests carry most of the weight here, and deliberately so.
Classifying a system under the EU AI Act is the point where a compliance
tool is most tempted to produce a confident answer it has no basis for,
and where doing so is most harmful — an organization that is told
"minimal risk" by software will not go looking for a second opinion.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.ai_governance import screen_eu_ai_act
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
            "full_name": "AI Governance Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


async def _ai_system(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Customer Support AI Agent",
            "vendor": "Anthropic",
            "purpose": "Generate grounded answers and suggested responses for support agents.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- The classifier itself, exercised directly ------------------------


def test_screening_never_returns_high_risk_without_a_declared_indicator() -> None:
    """B6's critical test. A tier has to come from a fact someone
    asserted, not from the tool's general impression of the system."""
    result = screen_eu_ai_act({key: False for key in ("employment_decisions",)})
    assert result.classification != "high"
    assert result.facts_relied_on == []


def test_prohibited_practice_stops_rather_than_rating() -> None:
    result = screen_eu_ai_act({"social_scoring": True})
    assert result.classification == "unacceptable"
    assert result.requires_human_review is True
    # Article 5 is a prohibition, not the top of a risk scale, and the
    # rationale has to say so or someone will try to mitigate it.
    assert "stop" in result.rationale.lower()


def test_annex_iii_use_is_high_risk_and_names_the_use() -> None:
    result = screen_eu_ai_act({"employment_decisions": True})
    assert result.classification == "high"
    assert result.facts_relied_on == [
        "Recruitment, promotion, termination, or task allocation decisions"
    ]
    assert result.requires_human_review is True


def test_conversational_system_is_limited_not_high() -> None:
    """A support assistant talks to people and writes text. That triggers
    transparency duties; it is not Annex III, and conflating the two would
    push every chatbot into a conformity assessment it does not need."""
    result = screen_eu_ai_act(
        {
            "interacts_with_people": True,
            "generates_content": True,
            **{k: False for k in ("employment_decisions", "biometric_identification")},
        }
    )
    assert result.classification == "limited"
    assert "transparency" in result.rationale.lower()


def test_unanswered_indicators_are_reported_as_uncertainty() -> None:
    """Silence is not a "no". An assessment built on three answers out of
    seventeen has to say so, or it reads as thorough."""
    result = screen_eu_ai_act({"interacts_with_people": True}, unanswered=["employment_decisions"])
    assert result.uncertainties
    assert "employment_decisions" in result.uncertainties[0]
    assert result.requires_human_review is True


# --- The endpoints ----------------------------------------------------


async def test_profile_records_users_affected_people_and_data(client: AsyncClient) -> None:
    """B2/B3/B4. The affected-persons list is the one the Act cares most
    about and the one an owner-only record loses."""
    await _signup(client, "ai-profile@example.com")
    system_id = await _ai_system(client)

    response = await client.patch(
        f"/api/v1/compliance/ai-systems/{system_id}/profile",
        json={
            "model_name": "Demo AI Model",
            "internal_users": ["Support Agents", "Support Managers"],
            "affected_users": ["Customers submitting support requests"],
            "processed_data": [
                {"name": "Customer email", "classification": "confidential"},
                {"name": "Authentication secrets", "classification": "restricted"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["affected_users"] == ["Customers submitting support requests"]
    assert body["model_name"] == "Demo AI Model"
    assert len(body["processed_data"]) == 2


async def test_screening_and_privacy_assessment_are_separate_records(
    client: AsyncClient,
) -> None:
    """B6 and B7 answer different questions to different regulators, so
    one must not overwrite or stand in for the other."""
    await _signup(client, "ai-assessments@example.com")
    system_id = await _ai_system(client)

    screening = await client.post(
        f"/api/v1/compliance/ai-systems/{system_id}/eu-ai-act-screening",
        json={"indicators": {"interacts_with_people": True, "generates_content": True}},
    )
    assert screening.status_code == 201
    assert screening.json()["assessment_type"] == "eu_ai_act"

    privacy = await client.post(
        f"/api/v1/compliance/ai-systems/{system_id}/privacy-assessment",
        json={"answers": {"personal_data_processed": "Name, email, message content."}},
    )
    assert privacy.status_code == 201
    assert privacy.json()["assessment_type"] == "privacy"

    detail = (await client.get(f"/api/v1/compliance/ai-systems/{system_id}")).json()
    assert len(detail["assessments"]) == 2


async def test_screening_raises_the_recorded_classification(client: AsyncClient) -> None:
    await _signup(client, "ai-classify@example.com")
    system_id = await _ai_system(client)
    assert (await client.get(f"/api/v1/compliance/ai-systems/{system_id}")).json()[
        "risk_classification"
    ] == "minimal"

    await client.post(
        f"/api/v1/compliance/ai-systems/{system_id}/eu-ai-act-screening",
        json={"indicators": {"employment_decisions": True}},
    )
    assert (await client.get(f"/api/v1/compliance/ai-systems/{system_id}")).json()[
        "risk_classification"
    ] == "high"


async def test_screening_does_not_silently_downgrade_a_human_judgement(
    client: AsyncClient,
) -> None:
    """Someone who has already judged a system high risk keeps that
    judgement until they change it deliberately. A thin set of indicator
    answers must not quietly talk them out of it."""
    await _signup(client, "ai-nodowngrade@example.com")
    response = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Screening Tool",
            "purpose": "Ranks job applicants.",
            "risk_classification": "high",
        },
    )
    system_id = response.json()["id"]

    await client.post(
        f"/api/v1/compliance/ai-systems/{system_id}/eu-ai-act-screening",
        json={"indicators": {"interacts_with_people": True}},
    )
    assert (await client.get(f"/api/v1/compliance/ai-systems/{system_id}")).json()[
        "risk_classification"
    ] == "high"


async def test_privacy_assessment_names_the_questions_nobody_answered(
    client: AsyncClient,
) -> None:
    """"No transfer happens" and "nobody has checked whether a transfer
    happens" are different answers, and a DPO needs to tell them apart."""
    await _signup(client, "ai-privacy@example.com")
    system_id = await _ai_system(client)

    response = await client.post(
        f"/api/v1/compliance/ai-systems/{system_id}/privacy-assessment",
        json={"answers": {"personal_data_processed": "Name and email."}},
    )
    findings = response.json()["findings"]
    assert response.json()["status"] == "partial"
    assert "international_transfer" in findings["unanswered"]
    assert findings["requires_human_review"] is True


async def test_risk_links_to_the_ai_system_and_records_residual(client: AsyncClient) -> None:
    """B8/B9 plus Workflow C's residual calculation: the register has to
    say what a risk is about, and show that mitigation changed it."""
    await _signup(client, "ai-risk@example.com")
    system_id = await _ai_system(client)

    control_id = (
        await client.post(
            "/api/v1/compliance/controls",
            json={"title": "Tenant-Scoped Retrieval Enforcement"},
        )
    ).json()["id"]

    risk = await client.post(
        "/api/v1/compliance/risks",
        json={
            "title": "Cross-tenant information disclosure",
            "likelihood": "medium",
            "impact": "high",
            "control_id": control_id,
            "ai_system_id": system_id,
        },
    )
    assert risk.status_code == 201, risk.text
    risk_id = risk.json()["id"]

    residual = await client.patch(
        f"/api/v1/compliance/risks/{risk_id}/residual",
        json={"residual_likelihood": "low", "residual_impact": "high"},
    )
    assert residual.status_code == 200, residual.text
    body = residual.json()
    assert body["residual_likelihood"] == "low"
    # The inherent rating survives, or the comparison that justifies the
    # control is lost.
    assert body["likelihood"] == "medium"


async def test_indicator_catalog_is_served_rather_than_duplicated(
    client: AsyncClient,
) -> None:
    await _signup(client, "ai-catalog@example.com")
    catalog = (
        await client.get("/api/v1/compliance/ai-systems/indicator-catalog")
    ).json()
    assert "social_scoring" in catalog["prohibited"]
    assert "employment_decisions" in catalog["high_risk"]
    assert "interacts_with_people" in catalog["transparency"]
    assert "dpia_required" in catalog["privacy_questions"]


async def test_screening_is_audited(client: AsyncClient) -> None:
    await _signup(client, "ai-audit@example.com")
    system_id = await _ai_system(client)
    await client.post(
        f"/api/v1/compliance/ai-systems/{system_id}/eu-ai-act-screening",
        json={"indicators": {"interacts_with_people": True}},
    )
    await client.post(
        f"/api/v1/compliance/ai-systems/{system_id}/privacy-assessment",
        json={"answers": {"personal_data_processed": "Name."}},
    )
    events = (
        await client.get("/api/v1/audit-events?action_prefix=compliance.ai_system&limit=50")
    ).json()
    actions = {e["action"] for e in events}
    assert "compliance.ai_system.eu_ai_act_screened" in actions
    assert "compliance.ai_system.privacy_assessed" in actions
