"""Intake is manual; everything after it is not.

A data request starts because a person outside the organization made
contact, so somebody types it in. What must not be manual is the work
that follows — the deadline, the scope, the case.

Two rules run through these.

**Receipt is not entry.** A request logged three days late does not get
three extra days, so the clock runs from when it arrived and the intake
asks for that date rather than assuming today.

**A scope is proposed, never searched.** `/likely-locations` reads the
privacy graph and returns places; `/discover` looks the person up and
returns counts of their data. A product that searched everything it could
reach and then asked would have already done the thing it was asking
permission for.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


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


# --- §10/§19: the deadline runs from receipt ----------------------------


@pytest.mark.asyncio
async def test_the_deadline_is_calculated_from_when_the_request_arrived(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19: received 31 January, and the month-end rule applies.

    Not 30 days: Article 12(3) says one month, and one month after 31
    January is 28 February in a common year — a fixed 30-day window would
    give the wrong date in both directions depending on the month.
    """
    await _org(client, "dsar1@example.com")
    created = (
        await client.post(
            "/api/v1/compliance/dsars",
            json={
                "requester_name": "Jane Doe",
                "requester_email": "jane@example.com",
                "request_type": "access",
                "received_at": "2027-01-31T09:00:00Z",
            },
        )
    ).json()

    assert created["received_at"].startswith("2027-01-31")
    # One calendar month, clamped to the last day of a shorter month.
    assert created["due_at"].startswith("2027-02-28")
    assert created["status"] == "received"
    # §11: identity is unverified until somebody verifies it, and that
    # gates disclosure.
    assert created["verification_status"] == "pending"


@pytest.mark.asyncio
async def test_a_request_logged_late_does_not_get_extra_time(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The failure the received date exists to prevent."""
    await _org(client, "dsar2@example.com")
    late = (
        await client.post(
            "/api/v1/compliance/dsars",
            json={
                "requester_name": "Jane Doe",
                "requester_email": "jane@example.com",
                "request_type": "access",
                "received_at": "2027-03-01T09:00:00Z",
            },
        )
    ).json()
    assert late["due_at"].startswith("2027-04-01")


# --- the scope, proposed and not searched -------------------------------
#
# These used to run against `/likely-locations`, which proposed a scope
# nothing downstream consumed. `/scope` replaced it: the same question,
# except the answer is a decision discovery then obeys exactly.


async def _scope(client: AsyncClient, dsar_id: str) -> dict[str, dict]:
    rows = (await client.get(f"/api/v1/compliance/dsars/{dsar_id}/scope")).json()
    return {row["name"]: row for row in rows}


@pytest.mark.asyncio
async def test_an_empty_register_offers_only_what_veyntra_itself_holds(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nothing recorded is not nothing held.

    With no processing activities, the only source is the one Veyntra
    genuinely owns. That is a gap in the register, and the screen says so
    — it is never a finding that this person's data is absent.
    """
    await _org(client, "dsar4@example.com")
    dsar = (
        await client.post(
            "/api/v1/compliance/dsars",
            json={
                "requester_name": "Jane Doe",
                "requester_email": "jane@example.com",
                "request_type": "access",
            },
        )
    ).json()

    scope = await _scope(client, dsar["id"])
    assert set(scope) == {"User accounts"}
    # And nothing from a product module this product no longer ships.
    assert "Support records" not in scope


@pytest.mark.asyncio
async def test_a_processor_with_no_vendor_row_is_still_in_scope(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Leaving it out because it lacks a row would narrow the search by
    an administrative accident."""
    import uuid as _uuid

    from app.compliance.models import ProcessingActivity

    await _org(client, "dsar5@example.com")
    activity = (
        await client.post(
            "/api/v1/compliance/processing-activities",
            json={
                "name": "Customer support",
                "purpose": "Answer customer questions.",
                "legal_basis": "contract",
                "data_subjects": "Customers",
                "retention_period": "24 months",
            },
        )
    ).json()
    row = await db_session.get(ProcessingActivity, _uuid.UUID(activity["id"]))
    row.processor_named = "SomeUnregisteredProcessor"
    await db_session.commit()

    dsar = (
        await client.post(
            "/api/v1/compliance/dsars",
            json={
                "requester_name": "Jane Doe",
                "requester_email": "jane@example.com",
                "request_type": "access",
            },
        )
    ).json()

    scope = await _scope(client, dsar["id"])
    sources = scope["Customer support"]["potential_sources"]
    named = [row for row in sources if row["kind"] == "named_processor"]

    assert len(named) == 1
    assert named[0]["name"] == "SomeUnregisteredProcessor"
    # A processor's systems are never ours to search.
    assert named[0]["capability"] == "processor_follow_up"


@pytest.mark.asyncio
async def test_reading_the_scope_does_not_search_anything(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The scope is a question. Discovery is the answer, and it is a
    separate call somebody has to make after confirming."""
    await _org(client, "dsar6@example.com")
    dsar = (
        await client.post(
            "/api/v1/compliance/dsars",
            json={
                "requester_name": "Jane Doe",
                "requester_email": "jane@example.com",
                "request_type": "access",
            },
        )
    ).json()

    await _scope(client, dsar["id"])

    fresh = (await client.get(f"/api/v1/compliance/dsars/{dsar['id']}")).json()
    assert fresh["discovery_run_at"] is None
    assert fresh["discovery_findings"] is None
