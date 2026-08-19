"""Continuous monitoring: the connector catalog and evidence events.

The load-bearing property is honesty about what is connected. A customer
who believes their GitHub settings are being watched, and is wrong, is
worse off than one who knows they are not — they stop checking. Several
of these tests exist only to make that hard to break by accident.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.connectors import (
    CONNECTORS,
    EVENT_TYPES,
    REASSESSMENT_TRIGGERS,
    UnknownConnectorError,
    record_evidence_event,
)
from app.compliance.models import Control, EvidenceEvent
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
            "full_name": "Connector Tester",
            "organization_name": f"Acme AI {uuid.uuid4().hex[:6]}",
        },
    )
    assert response.status_code == 200, response.text


# --- The catalog tells the truth --------------------------------------


def test_no_connector_claims_to_be_available_before_one_is_built() -> None:
    """The single most damaging thing this module could ship is a catalog
    implying data is flowing when none is. If a connector genuinely goes
    live, this test should be changed deliberately — not discovered."""
    assert all(connector.status == "coming_soon" for connector in CONNECTORS)


def test_every_connector_says_what_it_would_observe() -> None:
    """"Improves your compliance posture" tells a buyer nothing about
    whether connecting it is worth doing."""
    for connector in CONNECTORS:
        assert connector.observes
        assert len(connector.observes) > 30


async def test_the_catalog_reports_zero_available(client: AsyncClient) -> None:
    await _signup(client, "conn-catalog@example.com")
    body = (await client.get("/api/v1/compliance/connectors")).json()
    assert body["available_count"] == 0
    assert body["coming_soon_count"] == len(CONNECTORS)


async def test_observations_are_empty_and_stay_empty(client: AsyncClient) -> None:
    """Never seeded with examples. Simulated monitoring data presented as
    a customer's own would make every real number in the product
    suspect."""
    await _signup(client, "conn-events-empty@example.com")
    assert (await client.get("/api/v1/compliance/evidence-events")).json() == []


# --- The ingestion path is real ---------------------------------------


async def test_a_weakening_event_marks_its_control_for_reassessment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The whole point of continuous monitoring: something changed, so the
    last assessment no longer describes reality."""
    await _signup(client, "conn-weakened@example.com")
    control_id = (
        await client.post(
            "/api/v1/compliance/controls", json={"title": "Branch protection"}
        )
    ).json()["id"]
    control = await db_session.get(Control, uuid.UUID(control_id))
    assert control is not None
    assert control.needs_reassessment is False

    event = await record_evidence_event(
        db_session,
        organization_id=control.organization_id,
        source="github",
        event_type="control_configuration_weakened",
        summary="Branch protection was disabled on the default branch.",
        control_id=control.id,
    )

    assert event.triggered_reassessment is True
    await db_session.refresh(control)
    assert control.needs_reassessment is True


async def test_a_confirmation_does_not_trigger_reassessment(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Re-running an assessment because nothing changed is churn, and it
    would bury the events that matter."""
    await _signup(client, "conn-confirmed@example.com")
    control_id = (
        await client.post("/api/v1/compliance/controls", json={"title": "Encryption"})
    ).json()["id"]
    control = await db_session.get(Control, uuid.UUID(control_id))
    assert control is not None

    event = await record_evidence_event(
        db_session,
        organization_id=control.organization_id,
        source="aws",
        event_type="control_configuration_confirmed",
        summary="Encryption at rest is still enabled on all buckets.",
        control_id=control.id,
    )

    assert event.triggered_reassessment is False
    await db_session.refresh(control)
    assert control.needs_reassessment is False


async def test_a_failed_observation_is_recorded_not_swallowed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """"We did not look" and "we looked and it was fine" must never be
    indistinguishable."""
    assert "observation_failed" in EVENT_TYPES
    assert "observation_failed" in REASSESSMENT_TRIGGERS

    await _signup(client, "conn-failed@example.com")
    control_id = (
        await client.post("/api/v1/compliance/controls", json={"title": "Access review"})
    ).json()["id"]
    control = await db_session.get(Control, uuid.UUID(control_id))
    assert control is not None

    event = await record_evidence_event(
        db_session,
        organization_id=control.organization_id,
        source="identity_provider",
        event_type="observation_failed",
        summary="Could not read role assignments: the token was rejected.",
        control_id=control.id,
    )
    assert event.triggered_reassessment is True


async def test_an_unknown_connector_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An event claiming a source we do not have is not a monitoring
    signal, it is a bug or an intrusion. Either way it must not land."""
    await _signup(client, "conn-unknown@example.com")
    with pytest.raises(UnknownConnectorError):
        await record_evidence_event(
            db_session,
            organization_id=uuid.uuid4(),
            source="not_a_real_connector",
            event_type="evidence_updated",
            summary="Something happened.",
        )


async def test_an_unknown_event_type_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "conn-badtype@example.com")
    with pytest.raises(UnknownConnectorError):
        await record_evidence_event(
            db_session,
            organization_id=uuid.uuid4(),
            source="github",
            event_type="something_invented",
            summary="Something happened.",
        )


async def test_an_event_never_changes_a_control_status_directly(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An observation is evidence the position may have moved, not a new
    position. Letting connectors grade controls would put a second scoring
    rule in the product."""
    await _signup(client, "conn-nostatus@example.com")
    control_id = (
        await client.post(
            "/api/v1/compliance/controls", json={"title": "Logging enabled"}
        )
    ).json()["id"]
    control = await db_session.get(Control, uuid.UUID(control_id))
    assert control is not None
    before = control.status

    await record_evidence_event(
        db_session,
        organization_id=control.organization_id,
        source="aws",
        event_type="control_configuration_weakened",
        summary="CloudTrail was disabled in eu-west-1.",
        control_id=control.id,
    )

    await db_session.refresh(control)
    assert control.status == before


async def test_an_event_for_another_organizations_control_does_not_link_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Tenant isolation on the ingestion path."""
    await _signup(client, "conn-tenant-a@example.com")
    control_id = (
        await client.post("/api/v1/compliance/controls", json={"title": "Tenant A control"})
    ).json()["id"]

    other_org = uuid.uuid4()
    event = await record_evidence_event(
        db_session,
        organization_id=other_org,
        source="github",
        event_type="control_configuration_weakened",
        summary="Attempted cross-tenant link.",
        control_id=uuid.UUID(control_id),
    )

    assert event.control_id is None
    assert event.triggered_reassessment is False

    control = await db_session.get(Control, uuid.UUID(control_id))
    assert control is not None
    assert control.needs_reassessment is False


async def test_events_are_listed_newest_first_and_scoped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "conn-list@example.com")
    me = (await client.get("/api/v1/auth/me")).json()
    from app.core.models import Membership

    organization_id = (
        await db_session.execute(
            select(Membership.organization_id).where(
                Membership.user_id == uuid.UUID(me["id"])
            )
        )
    ).scalar_one()

    for index in range(3):
        await record_evidence_event(
            db_session,
            organization_id=organization_id,
            source="slack",
            event_type="evidence_updated",
            summary=f"Observation {index}",
        )
    await db_session.commit()

    rows = list(
        (
            await db_session.execute(
                select(EvidenceEvent).where(
                    EvidenceEvent.organization_id == organization_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
