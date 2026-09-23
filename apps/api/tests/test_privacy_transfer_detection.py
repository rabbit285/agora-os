"""Transfers Veyntra finds, rather than a form somebody fills in.

The Transfers page reported "Review suggestions (0)" on an organization
whose records plainly described a US transfer. The pipeline was not
broken; a payload was dropped at the acceptance boundary.

`draft_activity_from_document` reads "OpenAI" and "United States" out of
an uploaded document and, deliberately, does not resolve them to a vendor
row — a document naming a company is not proof it means the record of
that name. But acceptance only ever read `vendor_ids`, so both facts were
discarded. The activity that came out of the document knew nothing about
a processor, transfer detection had a single edge to follow
(`ProcessingActivityVendor`) and that activity had none, so it proposed
nothing. Correctly, from a record that had been stripped of the reason to
propose anything.

These pin the fix: acceptance keeps what the document said, detection
follows three edges to a recipient, and the mechanism stays a person's
decision on every one of them.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import DataTransfer, PrivacySuggestion, ProcessingActivity


async def _org(client: AsyncClient, email: str) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Zach Warren",
            "organization_name": "Agora Origin",
        },
    )


async def _activity(client: AsyncClient, **overrides) -> dict:
    body = {
        "name": "AI Customer Support",
        "purpose": "Answering customer product questions in the support inbox.",
        "legal_basis": "contract",
        "data_subjects": "Customers",
        "data_categories": ["Contact details", "Support conversation content"],
        "retention_period": "24 months",
    }
    body.update(overrides)
    return (
        await client.post("/api/v1/compliance/processing-activities", json=body)
    ).json()


async def _transfer_suggestions(client: AsyncClient) -> list[dict]:
    await client.post("/api/v1/compliance/privacy/suggestions/analyse")
    rows = (await client.get("/api/v1/compliance/privacy/suggestions")).json()
    return [row for row in rows if row["kind"] == "transfer"]


# --- §4: the root cause, pinned -----------------------------------------


@pytest.mark.asyncio
async def test_a_processor_named_in_a_document_is_detected_as_a_transfer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The exact shape that reported zero.

    No vendor link, no AI system — just an activity that came out of a
    document naming a processor and a destination.
    """
    await _org(client, "transfer1@example.com")
    activity = await _activity(client)

    # What acceptance now carries. Set directly here because the point
    # is the detection edge, not the document parser.
    row = await db_session.get(ProcessingActivity, uuid.UUID(activity["id"]))
    row.processor_named = "OpenAI"
    row.destination_country_named = "US"
    await db_session.commit()

    suggestions = await _transfer_suggestions(client)
    assert len(suggestions) == 1, suggestions

    payload = suggestions[0]["payload"]
    assert payload["recipient_name"] == "OpenAI"
    assert payload["destination_country"] == "US"
    # §5: never guessed.
    assert payload["transfer_mechanism"] == "needs_confirmation"
    # §3: the reviewer sees where the inference came from.
    assert "named in the source document" in payload["detected_from"]
    # …and what is being sent, without opening the ROPA in another tab.
    assert payload["data_subjects"] == "Customers"
    assert "Support conversation content" in payload["data_categories"]


@pytest.mark.asyncio
async def test_a_named_processor_matches_the_vendor_register_when_one_exists(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The register's country wins: it is maintained, a document is a
    snapshot of what somebody wrote once."""
    await _org(client, "transfer2@example.com")
    await client.post(
        "/api/v1/compliance/vendors",
        json={"name": "OpenAI", "category": "ai", "country": "IN"},
    )
    activity = await _activity(client)
    row = await db_session.get(ProcessingActivity, uuid.UUID(activity["id"]))
    row.processor_named = "openai"  # however the document capitalised it
    row.destination_country_named = "US"
    await db_session.commit()

    suggestions = await _transfer_suggestions(client)
    assert len(suggestions) == 1
    payload = suggestions[0]["payload"]
    # Matched to the register, so the recipient reads as the record and
    # the country is the maintained one.
    assert payload["recipient_name"] == "OpenAI"
    assert payload["destination_country"] == "IN"
    assert payload["vendor_id"] is not None


# --- §3: the AI-system edge ---------------------------------------------


@pytest.mark.asyncio
async def test_a_transfer_is_found_through_a_linked_ai_system(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§18: the ordinary path, end to end and through the API only."""
    await _org(client, "transfer3@example.com")
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
                {"name": "Contact details", "classification": "confidential"},
            ],
        },
    )
    drafts = (await client.get("/api/v1/compliance/privacy/suggestions")).json()
    activity_draft = next(row for row in drafts if row["kind"] == "processing_activity")
    await client.post(
        f"/api/v1/compliance/privacy/suggestions/{activity_draft['id']}/accept",
        json={"legal_basis": "contract", "retention_period": "24 months"},
    )

    suggestions = await _transfer_suggestions(client)
    assert len(suggestions) == 1, suggestions
    payload = suggestions[0]["payload"]
    assert payload["recipient_name"] == "OpenAI"
    assert payload["destination_country"] == "US"
    assert payload["transfer_mechanism"] == "needs_confirmation"

    # §18: confirming produces exactly one transfer record…
    confirmed = await client.post(
        f"/api/v1/compliance/privacy/suggestions/{suggestions[0]['id']}/accept",
        json={"transfer_mechanism": "sccs"},
    )
    assert confirmed.status_code == 200, confirmed.text

    transfers = (await client.get("/api/v1/compliance/data-transfers")).json()
    assert len(transfers) == 1
    assert transfers[0]["recipient_name"] == "OpenAI"
    assert transfers[0]["transfer_mechanism"] == "sccs"

    # …and re-running detection still finds one.
    again = await _transfer_suggestions(client)
    assert [row for row in again if row["status"] == "proposed"] == []
    transfers = (await client.get("/api/v1/compliance/data-transfers")).json()
    assert len(transfers) == 1


# --- §17: one transfer however many edges reach it ----------------------


@pytest.mark.asyncio
async def test_edges_that_agree_produce_one_proposal(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A processor linked directly *and* named in the document is one
    transfer, not two."""
    await _org(client, "transfer4@example.com")
    vendor = (
        await client.post(
            "/api/v1/compliance/vendors",
            json={"name": "OpenAI", "category": "ai", "country": "US"},
        )
    ).json()
    activity = await _activity(client)

    from app.compliance.models import ProcessingActivityVendor

    db_session.add(
        ProcessingActivityVendor(
            processing_activity_id=uuid.UUID(activity["id"]),
            vendor_id=uuid.UUID(vendor["id"]),
        )
    )
    row = await db_session.get(ProcessingActivity, uuid.UUID(activity["id"]))
    row.processor_named = "OpenAI"
    row.destination_country_named = "US"
    await db_session.commit()

    suggestions = await _transfer_suggestions(client)
    assert len(suggestions) == 1, [row["title"] for row in suggestions]

    # And running it repeatedly does not accumulate.
    await _transfer_suggestions(client)
    await _transfer_suggestions(client)
    rows = list(
        (
            await db_session.execute(
                select(PrivacySuggestion).where(PrivacySuggestion.kind == "transfer")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


# --- nothing is proposed where there is nothing to propose --------------


@pytest.mark.asyncio
async def test_an_eea_processor_is_not_a_transfer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _org(client, "transfer5@example.com")
    activity = await _activity(client)
    row = await db_session.get(ProcessingActivity, uuid.UUID(activity["id"]))
    row.processor_named = "A German processor"
    row.destination_country_named = "DE"
    await db_session.commit()

    assert await _transfer_suggestions(client) == []


@pytest.mark.asyncio
async def test_an_unrecorded_destination_is_not_a_finding(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Missing information is not a conclusion that nothing leaves."""
    await _org(client, "transfer6@example.com")
    activity = await _activity(client)
    row = await db_session.get(ProcessingActivity, uuid.UUID(activity["id"]))
    row.processor_named = "Some processor"
    row.destination_country_named = None
    await db_session.commit()

    assert await _transfer_suggestions(client) == []


# --- detection stays inside the tenant ----------------------------------


@pytest.mark.asyncio
async def test_detection_does_not_read_another_tenants_links(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The link query used to select every row in the database and rely
    on the vendor lookup to miss."""
    await _org(client, "transfer7a@example.com")
    await _activity(client)

    await _org(client, "transfer7b@example.com")
    await client.post(
        "/api/v1/compliance/vendors",
        json={"name": "OpenAI", "category": "ai", "country": "US"},
    )
    second = await _activity(client)
    row = await db_session.get(ProcessingActivity, uuid.UUID(second["id"]))
    row.processor_named = "OpenAI"
    await db_session.commit()

    suggestions = await _transfer_suggestions(client)
    assert len(suggestions) == 1

    transfers = list(
        (await db_session.execute(select(DataTransfer))).scalars().all()
    )
    assert transfers == []
