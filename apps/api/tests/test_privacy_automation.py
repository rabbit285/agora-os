"""Privacy records drafted from what the organization already declared.

The privacy module knew nothing about the rest of the product. An
organization that had registered an AI system — its purpose, the people
it affects, the data it processes, the vendor behind it — still had to
type all of that again into a RoPA form, and again into a transfer form.

These pin the two rules that make drafting safe rather than reckless.

**A draft is never a record.** A RoPA is the statement an organization
makes to a regulator about its own processing; a table assembled by
inference is not that. Proposals live apart, and accepting one is what
creates the real row.

**A draft never contains a legal conclusion.** Every fact drafted is one
the organization already declared somewhere else. What is never drafted
is a lawful basis, an Article 9 condition, or a transfer mechanism —
those are the judgements the review exists to obtain, and pre-filling
them would answer the only question the reviewer was brought in for.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import privacy_accept, privacy_suggestions
from app.compliance.models import (
    AISystem,
    DataTransfer,
    PrivacySuggestion,
    ProcessingActivity,
    ProcessingActivityVendor,
    Vendor,
)


async def _signup(client: AsyncClient, email: str, org: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _declared_records(
    client: AsyncClient, *, country: str = "US"
) -> tuple[dict, dict]:
    """The facts an organization records in the ordinary course.

    A vendor with a location, and an AI system that names it and
    declares who it affects and what it processes. Nothing privacy-
    specific: this is what registering an AI tool already asks for.
    """
    vendor = await client.post(
        "/api/v1/compliance/vendors",
        json={
            "name": "OpenAI",
            "category": "ai",
            "country": country,
            "data_location": "United States",
        },
    )
    assert vendor.status_code == 201, vendor.text
    system = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "AI Customer Support",
            "vendor": "OpenAI",
            "purpose": "Answering customer product questions in the support inbox.",
            "affected_users": ["Customers"],
            "internal_users": ["Support agents"],
            "processed_data": [
                {"name": "Contact information", "classification": "confidential"},
                {"name": "Conversation history", "classification": "confidential"},
            ],
        },
    )
    assert system.status_code == 201, system.text
    return vendor.json(), system.json()


# --- drafting from declared facts ---------------------------------------


@pytest.mark.asyncio
async def test_an_ai_system_drafts_the_processing_activity_it_implies(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: the acceptance case, from registration to draft."""
    await _signup(client, "auto1@example.com", "Agora Origin")
    await _declared_records(client)

    # Registering the AI system already drafted this; running the
    # analysis again reconciles rather than adding.
    analysed = await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    assert analysed.status_code == 200, analysed.text
    assert analysed.json()["created"] == 0

    suggestions = (await client.get("/api/v1/compliance/privacy/suggestions")).json()
    assert len(suggestions) == 1
    draft = suggestions[0]
    assert draft["kind"] == "processing_activity"
    assert draft["title"] == "AI Customer Support"

    # Read out of records, and the reviewer is told which — a draft that
    # cannot be checked against its sources has to be taken on trust.
    labels = {(source["type"], source["label"]) for source in draft["sources"]}
    assert ("ai_system", "AI Customer Support") in labels
    assert ("vendor", "OpenAI") in labels

    payload = draft["payload"]
    assert payload["purpose"].startswith("Answering customer product questions")
    assert payload["data_subjects"] == "Customers"
    assert payload["data_categories"] == [
        "Contact information",
        "Conversation history",
    ]
    # The three things a person decides, named rather than answered.
    assert payload["legal_basis"] == "needs_confirmation"
    assert payload["special_category"] is None
    assert payload["retention_period"] is None


@pytest.mark.asyncio
async def test_a_draft_never_carries_a_lawful_basis(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§12: the one question the review exists to ask.

    Pre-filling a lawful basis would answer it, and an answered-looking
    field is worse than a blank one because nobody checks it again.
    """
    org_id = await _signup(client, "auto2@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")

    rows = (
        await db_session.execute(
            select(PrivacySuggestion).where(
                PrivacySuggestion.organization_id == org_id
            )
        )
    ).scalars().all()
    assert rows
    for row in rows:
        payload = row.payload or {}
        for key in ("legal_basis", "transfer_mechanism"):
            if key in payload:
                assert payload[key] == privacy_suggestions.NEEDS_CONFIRMATION
        # And never one of the real values, by any route.
        assert payload.get("legal_basis") not in privacy_accept.LAWFUL_BASES
        assert (
            payload.get("transfer_mechanism")
            not in privacy_accept.TRANSFER_MECHANISMS
        )


@pytest.mark.asyncio
async def test_a_proposal_is_not_a_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The whole reason proposals have their own table."""
    org_id = await _signup(client, "auto3@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")

    activities = (
        await db_session.execute(
            select(func.count())
            .select_from(ProcessingActivity)
            .where(ProcessingActivity.organization_id == org_id)
        )
    ).scalar()
    assert activities == 0

    # And the overview counts records, not drafts.
    overview = (await client.get("/api/v1/compliance/privacy/overview")).json()
    metrics = {metric["key"]: metric["value"] for metric in overview["metrics"]}
    assert metrics["processing_activities"] == 0


# --- idempotence --------------------------------------------------------


@pytest.mark.asyncio
async def test_analysing_twice_proposes_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§16: re-analysis reconciles rather than duplicating."""
    org_id = await _signup(client, "auto4@example.com", "Agora Origin")
    await _declared_records(client)

    first = (
        await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    ).json()
    second = (
        await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    ).json()
    third = (
        await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    ).json()

    # The draft was created when the AI system was registered, so every
    # explicit pass reconciles against it and creates nothing.
    for result in (first, second, third):
        assert result["created"] == 0
    assert first["already_proposed"] == 1

    total = (
        await db_session.execute(
            select(func.count())
            .select_from(PrivacySuggestion)
            .where(PrivacySuggestion.organization_id == org_id)
        )
    ).scalar()
    assert total == 1


@pytest.mark.asyncio
async def test_a_dismissed_proposal_is_not_resurrected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Re-proposing what somebody rejected teaches them to ignore the
    product."""
    await _signup(client, "auto5@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]

    dismissed = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/dismiss",
        json={"reason": "Covered by an existing register entry."},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    again = (
        await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    ).json()
    assert again["created"] == 0
    assert (await client.get("/api/v1/compliance/privacy/suggestions")).json() == []


@pytest.mark.asyncio
async def test_an_activity_already_recorded_is_not_proposed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The product does not argue with its own user."""
    org_id = await _signup(client, "auto6@example.com", "Agora Origin")
    await _declared_records(client)
    db_session.add(
        ProcessingActivity(
            organization_id=org_id,
            name="AI Customer Support",
            purpose="Already written down by hand.",
            legal_basis="contract",
            data_subjects="Customers",
            retention_period="24 months",
        )
    )
    await db_session.commit()

    result = (
        await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    ).json()
    assert result["created"] == 0
    assert result["already_recorded"] == 1


# --- accepting ----------------------------------------------------------


@pytest.mark.asyncio
async def test_accepting_requires_the_judgements_a_draft_cannot_make(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "auto7@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]

    # No lawful basis.
    refused = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={"retention_period": "24 months"},
    )
    assert refused.status_code == 422
    assert "lawful basis" in refused.text

    # A lawful basis, but no retention period.
    no_retention = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={"legal_basis": "contract"},
    )
    assert no_retention.status_code == 422
    assert "retention period" in no_retention.text

    # "Needs confirmation" is not an answer either.
    still_unanswered = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={
            "legal_basis": "needs_confirmation",
            "retention_period": "24 months",
        },
    )
    assert still_unanswered.status_code == 422

    accepted = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={"legal_basis": "contract", "retention_period": "24 months"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["created_record_id"]


@pytest.mark.asyncio
async def test_special_category_processing_needs_its_condition_to_be_accepted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "auto8@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]

    refused = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={
            "legal_basis": "consent",
            "retention_period": "24 months",
            "special_category": True,
        },
    )
    assert refused.status_code == 422
    assert "Article 9" in refused.text

    accepted = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={
            "legal_basis": "consent",
            "retention_period": "24 months",
            "special_category": True,
            "special_category_condition": "explicit_consent",
        },
    )
    assert accepted.status_code == 200, accepted.text


@pytest.mark.asyncio
async def test_accepting_twice_creates_one_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "auto9@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]

    body = {"legal_basis": "contract", "retention_period": "24 months"}
    first = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept", json=body
    )
    second = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept", json=body
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["created_record_id"] == second.json()["created_record_id"]

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(ProcessingActivity)
            .where(ProcessingActivity.organization_id == org_id)
        )
    ).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_an_accepted_activity_stays_linked_to_what_it_came_from(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5/§6: nobody maintains the same fact in two places."""
    await _signup(client, "auto10@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]
    accepted = (
        await client.post(
            f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
            json={"legal_basis": "contract", "retention_period": "24 months"},
        )
    ).json()

    related = await client.get(
        f"/api/v1/compliance/processing-activities/{accepted['created_record_id']}/related"
    )
    assert related.status_code == 200, related.text
    body = related.json()
    assert [row["label"] for row in body["ai_systems"]] == ["AI Customer Support"]
    assert [row["label"] for row in body["vendors"]] == ["OpenAI"]
    # And each link is navigable.
    assert body["ai_systems"][0]["href"].startswith("/ai-systems/")
    assert body["vendors"][0]["href"].startswith("/compliance/vendors/")


# --- transfers ----------------------------------------------------------


def test_where_a_processor_is_decides_whether_to_propose_a_transfer() -> None:
    """§19: three answers, and none of them is "lawful"."""
    assert privacy_suggestions.transfer_disposition("DE") == "inside_eea"
    assert privacy_suggestions.transfer_disposition("ie") == "inside_eea"
    assert privacy_suggestions.transfer_disposition("US") == "third_country"
    assert privacy_suggestions.transfer_disposition("IN") == "third_country"
    # An adequacy decision is still a transfer, and still gets recorded.
    assert privacy_suggestions.transfer_disposition("GB") == "adequacy_candidate"
    assert privacy_suggestions.transfer_disposition("JP") == "adequacy_candidate"
    # Nowhere recorded is not a finding either way.
    assert privacy_suggestions.transfer_disposition(None) == "unknown"
    assert privacy_suggestions.transfer_disposition("  ") == "unknown"


@pytest.mark.asyncio
async def test_a_third_country_processor_proposes_a_transfer_for_review(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19: the acceptance case."""
    await _signup(client, "auto11@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]
    await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={"legal_basis": "contract", "retention_period": "24 months"},
    )

    # Accepting the activity already detected the transfer its own
    # processor implies, so this pass finds it rather than making it.
    result = (
        await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    ).json()
    assert result["created"] == 0

    transfers = (
        await client.get("/api/v1/compliance/privacy/suggestions?kind=transfer")
    ).json()
    assert len(transfers) == 1
    payload = transfers[0]["payload"]
    assert payload["destination_country"] == "US"
    assert payload["disposition"] == "third_country"
    assert payload["transfer_mechanism"] == "needs_confirmation"
    # And the note says what to do, not what the law concludes.
    assert "needs a mechanism" in payload["note"]
    for word in ("unlawful", "prohibited", "illegal"):
        assert word not in payload["note"].lower()

    # The mechanism is the reviewer's call.
    refused = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{transfers[0]['id']}/accept",
        json={},
    )
    assert refused.status_code == 422
    assert "transfer mechanism" in refused.text

    accepted = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{transfers[0]['id']}/accept",
        json={
            "transfer_mechanism": "sccs",
            "safeguards_description": "Encryption in transit and at rest.",
        },
    )
    assert accepted.status_code == 200, accepted.text

    record = (
        await db_session.execute(
            select(DataTransfer).where(
                DataTransfer.id == uuid.UUID(accepted.json()["created_record_id"])
            )
        )
    ).scalars().first()
    assert record is not None
    assert record.transfer_mechanism == "sccs"
    # Linked to both ends, so neither has to be retyped.
    assert record.vendor_id is not None
    assert record.processing_activity_id is not None


@pytest.mark.asyncio
async def test_a_processor_inside_the_eea_proposes_no_transfer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """There is no third-country transfer to record, and saying there is
    would be noise a privacy team learns to ignore."""
    org_id = await _signup(client, "auto12@example.com", "Agora Origin")
    await _declared_records(client, country="DE")
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]
    await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={"legal_basis": "contract", "retention_period": "24 months"},
    )

    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    transfers = (
        await client.get("/api/v1/compliance/privacy/suggestions?kind=transfer")
    ).json()
    assert transfers == []

    linked = (
        await db_session.execute(
            select(func.count()).select_from(ProcessingActivityVendor)
        )
    ).scalar()
    assert linked == 1
    assert org_id is not None


@pytest.mark.asyncio
async def test_a_transfer_already_recorded_is_not_proposed_again(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "auto13@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]
    accepted = (
        await client.post(
            f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
            json={"legal_basis": "contract", "retention_period": "24 months"},
        )
    ).json()

    # Somebody records the transfer by hand first.
    db_session.add(
        DataTransfer(
            organization_id=org_id,
            processing_activity_id=uuid.UUID(accepted["created_record_id"]),
            recipient_name="OpenAI",
            destination_country="US",
            transfer_mechanism="sccs",
        )
    )
    await db_session.commit()

    result = (
        await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    ).json()
    assert result["created"] == 0
    assert result["already_recorded"] >= 1


# --- where to look ------------------------------------------------------


@pytest.mark.asyncio
async def test_data_locations_are_a_search_scope_not_a_search(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§20: Veyntra says where to look. It does not look, and it does
    not disclose."""
    await _signup(client, "auto14@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]
    await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={"legal_basis": "contract", "retention_period": "24 months"},
    )

    locations = (
        await client.get("/api/v1/compliance/privacy/data-locations")
    ).json()
    kinds = {entry["kind"] for entry in locations}
    assert kinds == {"processing_activity", "ai_system", "vendor"}
    for entry in locations:
        assert entry["label"]
        assert entry["reason"]
        assert entry["record_id"]

    vendor = next(entry for entry in locations if entry["kind"] == "vendor")
    assert "US" in vendor["reason"]


@pytest.mark.asyncio
async def test_suggestions_do_not_cross_organizations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "auto15@example.com", "Agora Origin")
    await _declared_records(client)
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    assert (await client.get("/api/v1/compliance/privacy/suggestions")).json()

    await _signup(client, "auto16@example.com", "Another Company")
    assert (await client.get("/api/v1/compliance/privacy/suggestions")).json() == []
    analysed = (
        await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    ).json()
    assert analysed["created"] == 0
    assert (
        await client.get("/api/v1/compliance/privacy/data-locations")
    ).json() == []


@pytest.mark.asyncio
async def test_an_ai_system_with_no_declared_data_still_drafts_what_it_has(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A thin registration produces a thin draft, not a fabricated one."""
    await _signup(client, "auto17@example.com", "Agora Origin")
    created = await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Internal Summariser",
            "purpose": "Summarising internal meeting notes.",
        },
    )
    assert created.status_code == 201

    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]
    payload = draft["payload"]
    assert payload["purpose"] == "Summarising internal meeting notes."
    # Nothing invented to fill the gaps.
    assert payload["data_subjects"] == ""
    assert payload["data_categories"] == []
    assert payload["legal_basis"] == "needs_confirmation"
