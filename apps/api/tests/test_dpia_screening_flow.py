"""Starting a DPIA by screening, not by guessing at the risk.

The flow opened on a title, a risk dropdown and "Start DPIA" — which
asks somebody to classify the risk *before* the screening that exists to
establish it, and then to retype facts already sitting in the record
they are assessing.

These pin the replacement. The context is read from what the
organization recorded; the screening answers it can support are proposed
with the reason for each and everything else is left blank, because
silence on a criterion is not a "no"; and the outcome stays a
recommendation the controller confirms.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import dpia_prefill


async def _org_with_records(client: AsyncClient, email: str) -> dict:
    """An AI system and a vendor, recorded the ordinary way, then the
    processing activity Veyntra drafts from them."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": "Agora Origin",
        },
    )
    await client.post(
        "/api/v1/compliance/vendors",
        json={"name": "OpenAI", "category": "ai", "country": "US"},
    )
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "AI Customer Support",
            "vendor": "OpenAI",
            "purpose": "Answering customer product questions in the support inbox.",
            "affected_users": ["Customers"],
            "processed_data": [
                {"name": "Contact information", "classification": "confidential"},
                {"name": "Conversation history", "classification": "confidential"},
            ],
        },
    )
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    suggestions = (
        await client.get("/api/v1/compliance/privacy/suggestions")
    ).json()
    accepted = (
        await client.post(
            f"/api/v1/compliance/privacy/suggestions/{suggestions[0]['id']}/accept",
            json={
                "legal_basis": "contract",
                "retention_period": "24 months",
                "special_category": True,
                "special_category_condition": "explicit_consent",
            },
        )
    ).json()
    return accepted


@pytest.mark.asyncio
async def test_the_dpia_reads_the_facts_already_recorded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5/§26: nobody retypes what the processing activity already says."""
    accepted = await _org_with_records(client, "dpia1@example.com")
    activity_id = accepted["created_record_id"]

    response = await client.get(
        f"/api/v1/compliance/dpias/prefill?processing_activity_id={activity_id}"
    )
    assert response.status_code == 200, response.text
    context = response.json()

    assert context["title"] == "AI Customer Support DPIA"
    assert context["purpose"].startswith("Answering customer product questions")
    assert context["data_subjects"] == "Customers"
    assert context["data_categories"] == [
        "Contact information",
        "Conversation history",
    ]
    assert context["special_category"] is True
    assert [row["label"] for row in context["ai_systems"]] == ["AI Customer Support"]
    assert [row["label"] for row in context["vendors"]] == ["OpenAI"]
    # The vendor's country rides along, which is what makes the transfer
    # question answerable without asking again.
    assert context["vendors"][0]["detail"] == "US"


@pytest.mark.asyncio
async def test_suggested_answers_carry_their_reason_and_nothing_else_is_answered(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6/§22: a screening whose answers were guessed recommends nothing.

    Only criteria a declared fact speaks to are proposed. The rest are
    named as unanswered rather than defaulted to "no", which would turn
    an empty form into a clean result.
    """
    accepted = await _org_with_records(client, "dpia2@example.com")
    context = (
        await client.get(
            "/api/v1/compliance/dpias/prefill"
            f"?processing_activity_id={accepted['created_record_id']}"
        )
    ).json()

    proposed = {
        answer["criterion"]: answer for answer in context["suggested_answers"]
    }
    assert set(proposed) == {"sensitive_data", "innovative_technology"}
    assert proposed["sensitive_data"]["value"] is True
    assert "special-category data" in proposed["sensitive_data"]["reason"]
    assert "registered as an AI system" in proposed["innovative_technology"]["reason"]

    # Nothing is inferred about scale, monitoring or automated decisions
    # from the existence of a customer database.
    for criterion in (
        "large_scale",
        "systematic_monitoring",
        "automated_decision_making",
        "vulnerable_subjects",
    ):
        assert criterion not in proposed
        assert criterion in context["unknown"]


@pytest.mark.asyncio
async def test_screening_returns_a_recommendation_not_a_conclusion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: Veyntra counts the criteria; the controller decides."""
    accepted = await _org_with_records(client, "dpia3@example.com")
    activity_id = accepted["created_record_id"]
    context = (
        await client.get(
            f"/api/v1/compliance/dpias/prefill?processing_activity_id={activity_id}"
        )
    ).json()

    answers = {
        answer["criterion"]: answer["value"]
        for answer in context["suggested_answers"]
    }
    result = await client.post(
        "/api/v1/compliance/dpias/screening",
        json={"answers": answers, "processing_activity_id": activity_id},
    )
    assert result.status_code == 200, result.text
    body = result.json()

    # Two EDPB criteria met, which is the threshold the guidance names.
    assert body["outcome"] == "required"
    assert "two or more" in body["rationale"]
    # And the wording never claims to have decided anything.
    for word in ("we conclude", "you must", "is unlawful"):
        assert word not in body["rationale"].lower()


@pytest.mark.asyncio
async def test_a_clean_screening_says_so_without_deciding_for_anyone(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    accepted = await _org_with_records(client, "dpia4@example.com")
    activity_id = accepted["created_record_id"]

    body = (
        await client.post(
            "/api/v1/compliance/dpias/screening",
            json={"answers": {}, "processing_activity_id": activity_id},
        )
    ).json()
    assert body["outcome"] == "not_indicated"
    # It says whose decision it remains.
    assert "controller remains responsible" in body["rationale"]


@pytest.mark.asyncio
async def test_an_ai_system_can_be_screened_without_a_processing_activity(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4: an AI system is a legitimate starting point of its own."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "dpia5@example.com",
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": "Agora Origin",
        },
    )
    created = (
        await client.post(
            "/api/v1/compliance/ai-systems",
            json={
                "name": "Support Assistant",
                "purpose": "Drafting replies to customer questions.",
                "affected_users": ["Customers"],
                "processed_data": [
                    {"name": "Conversation history", "classification": "confidential"}
                ],
            },
        )
    ).json()

    context = (
        await client.get(
            f"/api/v1/compliance/dpias/prefill?ai_system_id={created['id']}"
        )
    ).json()
    assert context["title"] == "Support Assistant DPIA"
    assert context["data_subjects"] == "Customers"
    assert context["ai_system_id"] == created["id"]
    assert context["processing_activity_id"] is None
    # An AI system registration has no Article 9 flag, so this is left
    # for a person rather than guessed from a category name.
    assert context["special_category"] is False
    assert "sensitive_data" in context["unknown"]


@pytest.mark.asyncio
async def test_prefill_needs_a_subject_and_stays_inside_the_tenant(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    accepted = await _org_with_records(client, "dpia6@example.com")

    nothing = await client.get("/api/v1/compliance/dpias/prefill")
    assert nothing.status_code == 422
    assert "processing activity or an AI system" in nothing.text

    missing = await client.get(
        f"/api/v1/compliance/dpias/prefill?processing_activity_id={uuid.uuid4()}"
    )
    assert missing.status_code == 404

    # Another tenant cannot read it.
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "dpia7@example.com",
            "password": "correct-horse-battery",
            "full_name": "Somebody Else",
            "organization_name": "Another Company",
        },
    )
    across = await client.get(
        "/api/v1/compliance/dpias/prefill"
        f"?processing_activity_id={accepted['created_record_id']}"
    )
    assert across.status_code == 404


def test_only_declared_facts_produce_a_suggestion() -> None:
    """The unit boundary: no fact, no suggestion."""
    none = dpia_prefill._suggest_from_facts(
        special_category=False, ai_systems=[], data_categories=["Contact details"]
    )
    assert none == []

    both = dpia_prefill._suggest_from_facts(
        special_category=True,
        ai_systems=[
            dpia_prefill.LinkedRecord(
                id=uuid.uuid4(), label="Support Assistant", kind="ai_system"
            )
        ],
        data_categories=[],
    )
    assert {answer.criterion for answer in both} == {
        "sensitive_data",
        "innovative_technology",
    }
    assert all(answer.reason for answer in both)


@pytest.mark.asyncio
async def test_a_data_request_deadline_runs_from_the_date_it_was_received(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8/§27: a request logged three days late gets no extra days."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "dsar-date@example.com",
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": "Agora Origin",
        },
    )
    response = await client.post(
        "/api/v1/compliance/dsars",
        json={
            "requester_name": "Jane Doe",
            "requester_email": "jane@example.com",
            "request_type": "access",
            "received_at": "2027-01-31T09:00:00Z",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["received_at"].startswith("2027-01-31")
    # One calendar month, clamped to a real date — not thirty days,
    # which would answer on 2 March.
    assert body["due_at"].startswith("2027-02-28")
