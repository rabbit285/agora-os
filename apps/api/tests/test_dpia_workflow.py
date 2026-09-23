"""Screening first, then the assessment — and nothing assessed by default.

The reported page: selecting a processing activity opened a full DPIA
with four empty prose boxes, no risks, `Inherent risk: Low`, an enabled
"Recalculate residual risk" button, and no sign anywhere that a
screening had happened.

Three separate faults behind it. `record_dpia_screening` computed a
recommendation, wrote an audit event and returned — nothing reached the
DPIA, so the page had nothing to render. `DPIA.risk_level` defaulted to
`"low"`, so a document whose purpose is to record that somebody assessed
the risk asserted a risk level nobody had assessed. And the flow created
the assessment before anyone had decided one was needed.

These pin the order — screening, recommendation, human decision,
assessment — and the rule that runs through it: Veyntra counts, the
controller concludes, and nothing is rated until somebody rates it.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import dpia_workflow
from app.compliance.models import DPIA, ProcessingActivity, Risk


async def _signup(client: AsyncClient, email: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": "Agora Origin",
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _ai_customer_support(client: AsyncClient) -> str:
    """The acceptance case: an activity drafted from an AI system."""
    await client.post(
        "/api/v1/compliance/vendors",
        json={"name": "OpenAI", "category": "ai", "country": "US"},
    )
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "AI Support Assistant",
            "vendor": "OpenAI",
            "purpose": "Respond to customer support requests",
            "affected_users": ["Customers"],
            "processed_data": [
                {"name": "Contact details", "classification": "confidential"},
                {
                    "name": "Support conversation content",
                    "classification": "confidential",
                },
            ],
        },
    )
    drafts = (await client.get("/api/v1/compliance/privacy/suggestions")).json()
    accepted = (
        await client.post(
            f"/api/v1/compliance/privacy/suggestions/{drafts[0]['id']}/accept",
            json={
                "legal_basis": "contract",
                "retention_period": "24 months",
                "special_category": True,
                "special_category_condition": "explicit_consent",
            },
        )
    ).json()
    return accepted["created_record_id"]


# --- the order ----------------------------------------------------------


@pytest.mark.asyncio
async def test_screening_comes_first_and_is_kept(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§1/§3/§11: the recommendation is stored, and the status says so."""
    await _signup(client, "dpia1@example.com")
    activity_id = await _ai_customer_support(client)

    response = await client.post(
        "/api/v1/compliance/dpias/screening/start",
        json={"processing_activity_id": activity_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # §11: not a draft assessment — nobody has decided one is needed.
    assert body["status"] == "screening"
    # §3: the recommendation, and what triggered it, are on the record.
    assert body["screening_outcome"] == "required"
    assert body["screening_rationale_text"]
    assert len(body["screening_criteria_met"]) >= 2
    assert body["screened_at"]
    # And no human decision has been invented.
    assert body["screening_decision"] is None


@pytest.mark.asyncio
async def test_the_screening_is_prefilled_from_the_records(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2: facts the activity already carries answer their own criteria."""
    await _signup(client, "dpia2@example.com")
    activity_id = await _ai_customer_support(client)

    body = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity_id},
        )
    ).json()
    criteria = " ".join(body["screening_criteria_met"]).lower()
    # Special-category data is recorded on the activity; an AI system is
    # linked to it. Both are declared facts, so both are answered.
    assert "sensitive data" in criteria
    assert "innovative" in criteria


@pytest.mark.asyncio
async def test_a_decision_is_required_before_there_is_an_assessment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§1: no jump from selecting an activity into a blank assessment."""
    await _signup(client, "dpia3@example.com")
    activity_id = await _ai_customer_support(client)

    screened = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity_id},
        )
    ).json()
    # Nothing drafted yet.
    assert screened["processing_description"] is None
    assert screened["necessity_assessment"] is None

    confirmed = (
        await client.post(
            f"/api/v1/compliance/dpias/{screened['id']}/screening/decision",
            json={"decision": "required"},
        )
    ).json()
    assert confirmed["status"] == "draft"
    assert confirmed["screening_decision"] == "required"
    assert confirmed["screening_decided_at"]


# --- the inherent-risk bug ----------------------------------------------


@pytest.mark.asyncio
async def test_no_risks_means_no_inherent_risk(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5: "0 risks raised" beside "Inherent risk: Low" is invalid.

    A level nobody derived, printed on the document whose purpose is to
    record that somebody derived one, is the most misleading thing this
    page can say.
    """
    await _signup(client, "dpia4@example.com")
    activity_id = await _ai_customer_support(client)
    body = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity_id},
        )
    ).json()

    assert body["risk_count"] == 0
    assert body["inherent_risk"] is None
    assert body["residual_risk"] is None

    # And the stored column is null rather than "low".
    dpia = await db_session.get(DPIA, uuid.UUID(body["id"]))
    assert dpia.risk_level is None


@pytest.mark.asyncio
async def test_residual_risk_cannot_be_calculated_before_the_work_exists(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: the button is disabled, and says what is missing."""
    org_id = await _signup(client, "dpia5@example.com")
    activity_id = await _ai_customer_support(client)
    started = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity_id},
        )
    ).json()
    dpia = await db_session.get(DPIA, uuid.UUID(started["id"]))

    # No risks at all.
    state = await dpia_workflow.risk_state(
        db_session, organization_id=org_id, dpia=dpia
    )
    assert state.can_calculate_residual is False
    assert "No risks have been raised" in state.blocked_reason

    # Rated when raised — the schema requires it — but never reassessed
    # after mitigation. A residual rating with nothing behind it is the
    # inherent rating wearing a different name.
    risk = Risk(
        organization_id=org_id,
        dpia_id=dpia.id,
        title="Sensitive data in free text",
        category="privacy",
        likelihood="medium",
        impact="high",
    )
    db_session.add(risk)
    await db_session.commit()
    state = await dpia_workflow.risk_state(
        db_session, organization_id=org_id, dpia=dpia
    )
    assert state.inherent == "high"
    assert state.can_calculate_residual is False
    assert "reassessed after mitigation" in state.blocked_reason

    # Only once a residual rating exists does the calculation open up.
    risk.residual_likelihood = "low"
    risk.residual_impact = "medium"
    await db_session.commit()
    state = await dpia_workflow.risk_state(
        db_session, organization_id=org_id, dpia=dpia
    )
    assert state.can_calculate_residual is True
    assert state.blocked_reason is None


# --- reuse --------------------------------------------------------------


@pytest.mark.asyncio
async def test_screening_the_same_activity_twice_reuses_the_dpia(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4/§18: two half-finished assessments for one activity is an
    auditor asking which is authoritative."""
    org_id = await _signup(client, "dpia6@example.com")
    activity_id = await _ai_customer_support(client)

    first = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity_id},
        )
    ).json()
    second = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity_id},
        )
    ).json()

    assert first["id"] == second["id"]
    assert first["reused_existing"] is False
    assert second["reused_existing"] is True

    total = (
        await db_session.execute(
            select(func.count()).select_from(DPIA).where(DPIA.organization_id == org_id)
        )
    ).scalar()
    assert total == 1


# --- the assessment, drafted -------------------------------------------


@pytest.mark.asyncio
async def test_confirming_drafts_the_assessment_from_known_facts(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§7/§8: not four empty boxes."""
    await _signup(client, "dpia7@example.com")
    activity_id = await _ai_customer_support(client)
    started = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity_id},
        )
    ).json()
    body = (
        await client.post(
            f"/api/v1/compliance/dpias/{started['id']}/screening/decision",
            json={"decision": "required"},
        )
    ).json()

    description = body["processing_description"]
    assert description.startswith(dpia_workflow.DRAFT_MARKER)
    # The facts are reused rather than re-typed.
    assert "customer support" in description.lower()
    assert "AI Support Assistant" in description
    assert "OpenAI" in description
    assert "special-category data" in description.lower()

    assert body["necessity_assessment"].startswith(dpia_workflow.DRAFT_MARKER)
    assert body["proportionality_assessment"].startswith(dpia_workflow.DRAFT_MARKER)
    # Consultation is not drafted — whether a DPO was consulted is a fact
    # about something that happened, and Veyntra has no record of it.
    # Left empty rather than prompted: a prompt in the field is the
    # thing a reviewer ends up approving. The consultation record asks
    # the question instead.
    assert body["consultation_notes"] is None


@pytest.mark.asyncio
async def test_a_draft_never_overwrites_what_a_person_wrote(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "dpia8@example.com")
    activity_id = await _ai_customer_support(client)
    started = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity_id},
        )
    ).json()

    dpia = await db_session.get(DPIA, uuid.UUID(started["id"]))
    dpia.necessity_assessment = "We considered three alternatives and rejected them."
    await db_session.commit()

    body = (
        await client.post(
            f"/api/v1/compliance/dpias/{started['id']}/screening/decision",
            json={"decision": "required"},
        )
    ).json()
    assert body["necessity_assessment"] == (
        "We considered three alternatives and rejected them."
    )
    # The sections nobody wrote still get a draft.
    assert body["processing_description"].startswith(dpia_workflow.DRAFT_MARKER)


@pytest.mark.asyncio
async def test_risks_are_suggested_with_the_fact_behind_each(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9: proposals tied to records, not a generic checklist."""
    await _signup(client, "dpia9@example.com")
    activity_id = await _ai_customer_support(client)
    body = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity_id},
        )
    ).json()

    suggested = body["suggested_risks"]
    assert len(suggested) >= 3
    titles = " ".join(risk["title"] for risk in suggested).lower()
    assert "ai output" in titles
    assert "unauthorised party" in titles
    for risk in suggested:
        assert risk["reason"]
        assert risk["description"]

    # Suggested only — nothing was added to the register.
    assert body["risk_count"] == 0


# --- deciding no --------------------------------------------------------


@pytest.mark.asyncio
async def test_deciding_a_dpia_is_not_required_needs_a_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: "we looked and decided no" is defensible; an unexplained no
    is not."""
    await _signup(client, "dpia10@example.com")
    created = (
        await client.post(
            "/api/v1/compliance/processing-activities",
            json={
                "name": "Office visitor log",
                "purpose": "Record who visited the office reception.",
                "legal_basis": "legitimate_interests",
                "data_subjects": "Visitors",
                "retention_period": "30 days",
            },
        )
    ).json()
    started = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": created["id"]},
        )
    ).json()
    assert started["screening_outcome"] == "not_indicated"

    refused = await client.post(
        f"/api/v1/compliance/dpias/{started['id']}/screening/decision",
        json={"decision": "not_required"},
    )
    assert refused.status_code == 422
    assert "needs a reason" in refused.text

    accepted = await client.post(
        f"/api/v1/compliance/dpias/{started['id']}/screening/decision",
        json={
            "decision": "not_required",
            "rationale": "No monitoring, no special-category data, small scale.",
        },
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["screening_decision"] == "not_required"
    assert body["screening_decision_rationale"]
    # No assessment was drafted for processing nobody is assessing.
    assert body["processing_description"] is None


@pytest.mark.asyncio
async def test_a_decision_cannot_precede_the_screening(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "dpia11@example.com")
    dpia = DPIA(organization_id=org_id, title="Unscreened", status="screening")
    db_session.add(dpia)
    await db_session.commit()

    refused = await client.post(
        f"/api/v1/compliance/dpias/{dpia.id}/screening/decision",
        json={"decision": "required"},
    )
    assert refused.status_code == 422
    assert "has not been screened yet" in refused.text


# --- completion ---------------------------------------------------------


@pytest.mark.asyncio
async def test_completion_says_exactly_what_is_missing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§14: listed together, so the work can be finished in one pass."""
    org_id = await _signup(client, "dpia12@example.com")
    activity_id = await _ai_customer_support(client)
    started = (
        await client.post(
            "/api/v1/compliance/dpias/screening/start",
            json={"processing_activity_id": activity_id},
        )
    ).json()
    body = (
        await client.post(
            f"/api/v1/compliance/dpias/{started['id']}/screening/decision",
            json={"decision": "required"},
        )
    ).json()

    messages = " ".join(b["message"] for b in body["completion_blockers"])
    assert "Nobody has approved" in messages
    assert "risk assessment has not been reviewed" in messages

    # Approving each section clears those blockers — and rewriting the
    # text does not. Review is a decision somebody records, not a
    # deduction from the words no longer looking like a draft: under
    # that rule, deleting one word counted as having read it, and a
    # reviewer who agreed with the draft verbatim could not say so.
    dpia = await db_session.get(DPIA, uuid.UUID(started["id"]))
    dpia.processing_description = (
        "A description a person wrote about the support processing, the "
        "customers it concerns and the contact details it holds."
    )
    await db_session.commit()

    blockers = await dpia_workflow.completion_blockers(
        db_session, organization_id=org_id, dpia=dpia
    )
    assert "processing_description_unreviewed" in {b.code for b in blockers}

    # Consultation is not among these: it is resolved by recording the
    # consultation decision, not by approving a section.
    for section in dpia_workflow.NARRATIVE_SECTIONS:
        dpia_workflow.approve_section(dpia, section=section, actor_user_id=None)
    await db_session.commit()

    blockers = await dpia_workflow.completion_blockers(
        db_session, organization_id=org_id, dpia=dpia
    )
    codes = {blocker.code for blocker in blockers}
    assert "risk_review_incomplete" in codes
    # Scoped to the narrative sections. `suggested_risks_unreviewed` is a
    # different blocker and is expected here — nobody has ruled on the
    # proposals — and consultation is resolved by its own record rather
    # than by a section sign-off.
    assert not any(
        f"{section}_unreviewed" in codes
        for section in dpia_workflow.NARRATIVE_SECTIONS
    )


@pytest.mark.asyncio
async def test_screening_stays_inside_the_tenant(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "dpia13@example.com")
    activity_id = await _ai_customer_support(client)

    await _signup(client, "dpia14@example.com")
    across = await client.post(
        "/api/v1/compliance/dpias/screening/start",
        json={"processing_activity_id": activity_id},
    )
    assert across.status_code == 404
