"""Privacy work that arrives without being asked for, and the decisions
that do not.

The product's argument is that it does the repetitive compliance work and
the human handles the judgements. Privacy had the first half — records
drafted from AI systems, transfers detected from vendors, deadlines
calculated — behind a button somebody had to remember to press, and no
route into the second: the decisions were listed on a privacy overview,
which is a second queue, and the point of a Review Center is that there
is one.

These pin both halves. Registering an AI system drafts what it implies;
approving a draft detects what *that* implies; and every judgement lands
in Review Center with the facts it was read from, what Veyntra
recommends where it has grounds to recommend anything, and what changes
if the reviewer agrees.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import privacy_review
from app.compliance.models import (
    DSAR,
    DataTransfer,
    PrivacySuggestion,
    ProcessingActivity,
    Vendor,
)
from app.compliance.review_center import build_review_center


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


async def _register_the_business(client: AsyncClient) -> None:
    """A vendor and an AI system, recorded the ordinary way.

    Nothing privacy-specific, and no analysis is requested.
    """
    await client.post(
        "/api/v1/compliance/vendors",
        json={"name": "OpenAI", "category": "ai", "country": "US"},
    )
    await _register_the_system(client)


async def _register_the_system(client: AsyncClient) -> None:
    """The AI system on its own, for the cases that register it twice.

    The vendor is not recreated: two vendors sharing a name trips a
    `scalar_one_or_none` in the AI-system registration's name lookup,
    which is a real weakness and a different one from what these tests
    are about.
    """
    await client.post(
        "/api/v1/compliance/ai-systems",
        json={
            "name": "Support Assistant",
            "vendor": "OpenAI",
            "purpose": "Respond to customer support requests",
            "affected_users": ["Customers"],
            "processed_data": [
                {"name": "Contact details", "classification": "confidential"},
                {"name": "Conversation history", "classification": "confidential"},
            ],
        },
    )


# --- work that arrives on its own ---------------------------------------


@pytest.mark.asyncio
async def test_registering_an_ai_system_drafts_what_it_implies(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2: no button. The implications are knowable at registration."""
    await _signup(client, "auto1@example.com")
    await _register_the_business(client)

    drafts = (await client.get("/api/v1/compliance/privacy/suggestions")).json()
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["kind"] == "processing_activity"
    # §3: the title describes the processing, not the tool.
    assert draft["title"] == "AI Customer Support"
    assert draft["payload"]["data_subjects"] == "Customers"
    assert draft["payload"]["data_categories"] == [
        "Contact details",
        "Conversation history",
    ]
    # §12: still the one thing it will not decide.
    assert draft["payload"]["legal_basis"] == "needs_confirmation"

    # And nothing authoritative was created.
    activities = (
        await client.get("/api/v1/compliance/processing-activities")
    ).json()
    assert activities == []


@pytest.mark.asyncio
async def test_approving_an_activity_detects_the_transfer_it_implies(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: the chain continues without anybody asking it to."""
    await _signup(client, "auto2@example.com")
    await _register_the_business(client)
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]

    await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={"legal_basis": "contract", "retention_period": "12 months"},
    )

    transfers = (
        await client.get("/api/v1/compliance/privacy/suggestions?kind=transfer")
    ).json()
    assert len(transfers) == 1
    payload = transfers[0]["payload"]
    assert payload["recipient_name"] == "OpenAI"
    assert payload["destination_country"] == "US"
    assert payload["transfer_mechanism"] == "needs_confirmation"


# --- Review Center -------------------------------------------------------


@pytest.mark.asyncio
async def test_the_drafted_activity_reaches_review_center_with_its_evidence(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: recommendation, why, confidence, impact — in one queue."""
    await _signup(client, "auto3@example.com")
    await _register_the_business(client)

    body = (await client.get("/api/v1/compliance/review-center")).json()
    privacy = next(
        category
        for category in body["categories"]
        if category["key"] == "privacy_decisions"
    )
    assert privacy["count"] == 1
    item = privacy["items"][0]

    assert item["title"] == "Confirm the lawful basis for AI Customer Support"
    assert item["priority"] == "high"
    # §3/§12: no recommended lawful basis, ever. Which one applies turns
    # on facts no database holds.
    assert item["recommendation"] is None

    facts = {fact["label"]: fact for fact in item["evidence"]}
    assert facts["Purpose"]["value"] == "Respond to customer support requests"
    assert facts["Data subjects"]["value"] == "Customers"
    # Confidence is quoted for facts, and says how directly each was
    # established rather than how sure a model is.
    assert facts["Purpose"]["basis"] == "declared"
    assert facts["Purpose"]["confidence"] == privacy_review.CONFIDENCE["declared"]
    assert facts["Drafted from"]["basis"] == "linked"
    assert "Support Assistant" in facts["Drafted from"]["value"]

    assert "Approving creates the RoPA entry" in item["impact"]


@pytest.mark.asyncio
async def test_a_transfer_decision_names_the_facts_and_recommends_no_mechanism(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§12: which mechanism covers a transfer is a legal call."""
    await _signup(client, "auto4@example.com")
    await _register_the_business(client)
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]
    await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={"legal_basis": "contract", "retention_period": "12 months"},
    )

    body = (await client.get("/api/v1/compliance/review-center")).json()
    privacy = next(
        category
        for category in body["categories"]
        if category["key"] == "privacy_decisions"
    )
    item = next(
        entry
        for entry in privacy["items"]
        if "transfer mechanism" in entry["title"]
    )
    assert item["recommendation"] is None
    facts = {fact["label"]: fact["value"] for fact in item["evidence"]}
    assert facts["Recipient"] == "OpenAI"
    assert facts["Destination"] == "US"


@pytest.mark.asyncio
async def test_an_overdue_request_outranks_the_rest(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The only privacy record with a statutory clock goes first."""
    org_id = await _signup(client, "auto5@example.com")
    await _register_the_business(client)
    db_session.add(
        DSAR(
            organization_id=org_id,
            requester_name="Jane Doe",
            requester_email="jane@example.com",
            request_type="access",
            received_at=datetime.now(UTC) - timedelta(days=62),
            due_at=datetime.now(UTC) - timedelta(days=31),
            verification_status="verified",
        )
    )
    await db_session.commit()

    decisions = await privacy_review.privacy_decisions(
        db_session, organization_id=org_id
    )
    assert decisions[0].kind == "data_request"
    assert "Jane Doe" in decisions[0].title
    facts = {fact["label"]: fact for fact in decisions[0].evidence}
    # The deadline is derived from a rule over a declared date, and says
    # so rather than claiming to be observed.
    assert facts["Response due"]["basis"] == "derived"
    assert facts["Received"]["basis"] == "declared"


@pytest.mark.asyncio
async def test_an_empty_queue_is_a_real_answer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An organization with nothing pending should be told so."""
    org_id = await _signup(client, "auto6@example.com")
    decisions = await privacy_review.privacy_decisions(
        db_session, organization_id=org_id
    )
    assert decisions == []

    centre = await build_review_center(db_session, organization_id=org_id)
    privacy = next(
        category
        for category in centre.categories
        if category.key == "privacy_decisions"
    )
    assert privacy.count == 0


# --- impact detection ----------------------------------------------------


@pytest.mark.asyncio
async def test_a_vendor_moving_country_flags_the_transfer_without_editing_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9: a mechanism assessed against Ireland does not cover Virginia.

    Reported as a suggested update. A human-approved privacy record is
    not something to edit because a related row changed.
    """
    org_id = await _signup(client, "auto7@example.com")
    vendor = Vendor(
        organization_id=org_id, name="Acme Cloud", category="hosting", country="IE"
    )
    db_session.add(vendor)
    await db_session.flush()
    transfer = DataTransfer(
        organization_id=org_id,
        vendor_id=vendor.id,
        recipient_name="Acme Cloud",
        destination_country="IE",
        transfer_mechanism="sccs",
    )
    db_session.add(transfer)
    await db_session.commit()

    # Nothing to say while they agree.
    quiet = await privacy_review.privacy_decisions(
        db_session, organization_id=org_id
    )
    assert not [item for item in quiet if item.kind == "suggested_update"]

    vendor.country = "US"
    await db_session.commit()

    decisions = await privacy_review.privacy_decisions(
        db_session, organization_id=org_id
    )
    update = next(item for item in decisions if item.kind == "suggested_update")
    assert "no longer matches" in update.title
    assert update.recommendation == "Reassess this transfer against US"
    assert "untouched" in update.impact

    # And the record really is untouched.
    await db_session.refresh(transfer)
    assert transfer.destination_country == "IE"
    assert transfer.transfer_mechanism == "sccs"


# --- idempotence ---------------------------------------------------------


@pytest.mark.asyncio
async def test_registering_the_same_system_twice_proposes_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§13: automation that runs on every write has to be idempotent."""
    org_id = await _signup(client, "auto8@example.com")
    await _register_the_business(client)
    await _register_the_system(client)
    await _register_the_system(client)

    drafts = (await client.get("/api/v1/compliance/privacy/suggestions")).json()
    assert len(drafts) == 1

    total = (
        await db_session.execute(
            select(func.count())
            .select_from(PrivacySuggestion)
            .where(PrivacySuggestion.organization_id == org_id)
        )
    ).scalar()
    assert total == 1


@pytest.mark.asyncio
async def test_a_second_registration_after_approval_proposes_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The processing is already recorded, so there is nothing to propose.

    This is the case the title change broke: the check compared the
    *system's* name against recorded activity names, and activities are
    named after the processing now.
    """
    org_id = await _signup(client, "auto9@example.com")
    await _register_the_business(client)
    draft = (await client.get("/api/v1/compliance/privacy/suggestions")).json()[0]
    await client.post(
        f"/api/v1/compliance/privacy/suggestions/{draft['id']}/accept",
        json={"legal_basis": "contract", "retention_period": "12 months"},
    )

    # The same tool registered again by somebody else.
    await _register_the_system(client)

    activities = (
        await db_session.execute(
            select(func.count())
            .select_from(ProcessingActivity)
            .where(ProcessingActivity.organization_id == org_id)
        )
    ).scalar()
    assert activities == 1

    open_activity_drafts = (
        await client.get(
            "/api/v1/compliance/privacy/suggestions?kind=processing_activity"
        )
    ).json()
    assert open_activity_drafts == []


@pytest.mark.asyncio
async def test_review_center_items_are_stable_across_reads(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A queue whose ids move cannot be acted on."""
    await _signup(client, "auto10@example.com")
    await _register_the_business(client)

    first = (await client.get("/api/v1/compliance/review-center")).json()
    second = (await client.get("/api/v1/compliance/review-center")).json()

    def privacy_ids(body: dict) -> list[str]:
        category = next(
            entry
            for entry in body["categories"]
            if entry["key"] == "privacy_decisions"
        )
        return [item["id"] for item in category["items"]]

    assert privacy_ids(first) == privacy_ids(second)
    assert privacy_ids(first)


@pytest.mark.asyncio
async def test_decisions_do_not_cross_organizations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "auto11@example.com")
    await _register_the_business(client)

    await _signup(client, "auto12@example.com")
    body = (await client.get("/api/v1/compliance/review-center")).json()
    privacy = next(
        category
        for category in body["categories"]
        if category["key"] == "privacy_decisions"
    )
    assert privacy["count"] == 0
