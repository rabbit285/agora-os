"""The privacy workspace: deadlines that are right, and a worklist.

Two problems the privacy module had.

**The response deadline was thirty days.** The window is one month from
receipt, and those are different dates for most of the year. A request
received on 31 January is due on 28 February; adding thirty days answers
on 2 March — two days past a statutory deadline, with the product's own
screen saying the request is on time. That is the worst kind of bug in a
compliance tool: it does not fail, it reassures.

**Four lists on one page answered the wrong question.** A privacy officer
opens the product asking "what needs me this week", and that is derivable
from the same records. So it is derived, and every item leads to the
record it is about.

Nothing here concludes anything legal. "Missing lawful basis" is a fact
about a form field; "transfer mechanism needs review" says a person
should look, not that a transfer is unlawful.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import privacy_deadlines, privacy_overview
from app.compliance.models import DSAR, DataTransfer, ProcessingActivity


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


# --- the deadline -------------------------------------------------------


@pytest.mark.parametrize(
    ("received", "expected"),
    [
        # The case that made this a bug rather than a rounding quibble.
        # Thirty days from 31 January is 2 March.
        ((2026, 1, 31), (2026, 2, 28)),
        # And in a leap year the clamp lands a day later, not on the 28th.
        ((2024, 1, 31), (2024, 2, 29)),
        # 31 of a 31-day month into a 30-day month.
        ((2026, 8, 31), (2026, 9, 30)),
        ((2026, 5, 31), (2026, 6, 30)),
        # An ordinary month keeps the day of month.
        ((2026, 3, 15), (2026, 4, 15)),
        # December rolls the year.
        ((2026, 12, 15), (2027, 1, 15)),
        ((2026, 12, 31), (2027, 1, 31)),
        # 29 February is only a date in a leap year.
        ((2024, 2, 29), (2024, 3, 29)),
        ((2024, 1, 29), (2024, 2, 29)),
    ],
)
def test_one_month_is_a_calendar_month(
    received: tuple[int, int, int], expected: tuple[int, int, int]
) -> None:
    due = privacy_deadlines.response_due(
        datetime(*received, 9, 30, tzinfo=UTC)
    )
    assert (due.year, due.month, due.day) == expected
    # The hour the request arrived is preserved, so a deadline does not
    # quietly move to midnight.
    assert (due.hour, due.minute) == (9, 30)


def test_thirty_days_and_one_month_are_not_the_same_date() -> None:
    """The specific arithmetic the product was doing, stated plainly."""
    received = datetime(2026, 1, 31, tzinfo=UTC)
    assert privacy_deadlines.response_due(received) == datetime(
        2026, 2, 28, tzinfo=UTC
    )
    assert received + timedelta(days=30) == datetime(2026, 3, 2, tzinfo=UTC)
    # Two days apart, on the wrong side of the deadline.
    assert (received + timedelta(days=30)) > privacy_deadlines.response_due(received)


def test_an_extension_adds_months_and_is_bounded() -> None:
    received = datetime(2026, 1, 31, tzinfo=UTC)
    assert privacy_deadlines.response_due(received, extension_months=2) == datetime(
        2026, 4, 30, tzinfo=UTC
    )
    # Two further months is the limit the product records.
    assert privacy_deadlines.clamp_extension(5) == 2
    assert privacy_deadlines.clamp_extension(-1) == 0
    assert privacy_deadlines.clamp_extension(1) == 1


def test_the_deadline_reads_as_words_and_a_completed_request_is_never_overdue() -> None:
    received = datetime(2026, 1, 1, tzinfo=UTC)
    now = datetime(2026, 2, 5, tzinfo=UTC)

    late = privacy_deadlines.describe(received_at=received, now=now)
    assert late.overdue is True
    assert late.label == "Overdue by 4 days"

    # Answered. Whether it was answered late is a fact about the
    # response, not something to keep flashing on a worklist forever.
    done = privacy_deadlines.describe(
        received_at=received, completed_at=datetime(2026, 1, 20, tzinfo=UTC), now=now
    )
    assert done.overdue is False
    assert done.label == "Completed"

    soon = privacy_deadlines.describe(
        received_at=datetime(2026, 1, 10, tzinfo=UTC),
        now=datetime(2026, 2, 8, tzinfo=UTC),
    )
    assert soon.due_soon is True
    assert soon.label == "Due in 2 days"

    today = privacy_deadlines.describe(
        received_at=datetime(2026, 1, 10, tzinfo=UTC),
        now=datetime(2026, 2, 10, tzinfo=UTC),
    )
    assert today.label == "Due today"
    assert today.overdue is False


# --- the deadline, through the API --------------------------------------


@pytest.mark.asyncio
async def test_a_logged_request_is_due_one_month_after_receipt(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "privacy1@example.com", "Privacy One")
    response = await client.post(
        "/api/v1/compliance/dsars",
        json={
            "requester_name": "Dana Okafor",
            "requester_email": "dana@example.com",
            "request_type": "access",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["received_at"]
    assert body["deadline_label"].startswith("Due in")

    dsar = await db_session.get(DSAR, uuid.UUID(body["id"]))
    assert privacy_deadlines.as_utc(dsar.due_at) == privacy_deadlines.response_due(
        dsar.received_at
    )
    assert dsar.organization_id == org_id


@pytest.mark.asyncio
async def test_an_extension_is_recorded_with_its_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§13: an extension is a decision somebody makes, not a longer default."""
    await _signup(client, "privacy2@example.com", "Privacy Two")
    created = (
        await client.post(
            "/api/v1/compliance/dsars",
            json={
                "requester_name": "Dana Okafor",
                "requester_email": "dana@example.com",
                "request_type": "access",
            },
        )
    ).json()

    extended = await client.post(
        f"/api/v1/compliance/dsars/{created['id']}/extension",
        json={"months": 2, "reason": "The request covers six years of records."},
    )
    assert extended.status_code == 200, extended.text
    body = extended.json()
    assert body["extension_months"] == 2
    assert body["extension_reason"] == "The request covers six years of records."
    assert body["extension_granted_at"]
    # The base deadline is kept, so the screen can say "extended to"
    # rather than showing a later date as though it were the deadline.
    assert body["base_due_at"] < body["due_at"]

    dsar = await db_session.get(DSAR, uuid.UUID(created["id"]))
    await db_session.refresh(dsar)
    assert privacy_deadlines.as_utc(dsar.due_at) == privacy_deadlines.response_due(
        dsar.received_at, extension_months=2
    )

    # More than two further months is not something this product records.
    too_long = await client.post(
        f"/api/v1/compliance/dsars/{created['id']}/extension",
        json={"months": 6, "reason": "Much longer."},
    )
    assert too_long.status_code == 422


# --- the worklist -------------------------------------------------------


@pytest.mark.asyncio
async def test_the_overview_counts_and_links_to_the_records(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "privacy3@example.com", "Privacy Three")
    await client.post(
        "/api/v1/compliance/processing-activities",
        json={
            "name": "Customer Support",
            "purpose": "Answering product questions from customers.",
            "legal_basis": "contract",
            "data_categories": ["contact_details"],
            "data_subjects": "Customers",
            "retention_period": "24 months",
        },
    )
    await client.post(
        "/api/v1/compliance/data-transfers",
        json={
            "recipient_name": "OpenAI",
            "destination_country": "US",
            "transfer_mechanism": "sccs",
        },
    )

    response = await client.get("/api/v1/compliance/privacy/overview")
    assert response.status_code == 200, response.text
    body = response.json()

    metrics = {metric["key"]: metric for metric in body["metrics"]}
    assert metrics["processing_activities"]["value"] == 1
    assert metrics["transfers"]["value"] == 1
    # Every number leads somewhere. A dashboard figure that does not is a
    # decoration.
    for metric in body["metrics"]:
        assert metric["href"].startswith("/compliance/privacy")

    # An SCC transfer with no safeguards recorded is a gap somebody can
    # close — and is reported as needing review, not as unlawful.
    safeguards = next(
        item for item in body["attention"] if item["record_type"] == "transfer"
    )
    assert "records no safeguards" in safeguards["title"]
    assert "unlawful" not in safeguards["detail"].lower()
    assert safeguards["href"].startswith("/compliance/privacy/transfers/")
    assert org_id is not None


@pytest.mark.asyncio
async def test_an_overdue_request_outranks_everything_else(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The only privacy record with a statutory clock goes first."""
    org_id = await _signup(client, "privacy4@example.com", "Privacy Four")

    # A request received two months ago and never answered.
    stale = DSAR(
        organization_id=org_id,
        requester_name="Dana Okafor",
        requester_email="dana@example.com",
        request_type="access",
        received_at=datetime.now(UTC) - timedelta(days=62),
        due_at=datetime.now(UTC) - timedelta(days=31),
        verification_status="verified",
    )
    db_session.add(stale)
    # And an activity with no lawful basis, which is a gap but not a
    # missed deadline.
    db_session.add(
        ProcessingActivity(
            organization_id=org_id,
            name="Marketing emails",
            purpose="Sending product updates.",
            legal_basis="",
            data_subjects="Subscribers",
            retention_period="12 months",
        )
    )
    await db_session.commit()

    overview = await privacy_overview.build_overview(
        db_session, organization_id=org_id
    )
    assert overview.attention[0].severity == "overdue"
    assert "Dana Okafor" in overview.attention[0].title

    keys = [item.key for item in overview.attention]
    assert any(key.startswith("ropa-basis-") for key in keys)


@pytest.mark.asyncio
async def test_a_missing_lawful_basis_is_reported_as_a_gap_not_a_verdict(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The product cannot know whether processing is lawful, and must not
    imply that it does."""
    org_id = await _signup(client, "privacy5@example.com", "Privacy Five")
    db_session.add(
        ProcessingActivity(
            organization_id=org_id,
            name="Marketing emails",
            purpose="Sending product updates.",
            legal_basis="",
            data_subjects="Subscribers",
            retention_period="12 months",
        )
    )
    await db_session.commit()

    overview = await privacy_overview.build_overview(
        db_session, organization_id=org_id
    )
    item = next(
        entry for entry in overview.attention if entry.key.startswith("ropa-basis-")
    )
    assert item.title == "Marketing emails has no lawful basis recorded"
    assert "somebody has to make and record" in item.detail
    for word in ("unlawful", "non-compliant", "breach", "violation"):
        assert word not in item.detail.lower()


@pytest.mark.asyncio
async def test_special_category_processing_needs_its_own_condition(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A lawful basis is not an Article 9 condition, and a record that
    conflates them cannot show whether the second was ever answered."""
    org_id = await _signup(client, "privacy6@example.com", "Privacy Six")
    db_session.add(
        ProcessingActivity(
            organization_id=org_id,
            name="Occupational health records",
            purpose="Managing workplace adjustments.",
            legal_basis="legal_obligation",
            data_subjects="Employees",
            retention_period="6 years",
            special_category=True,
        )
    )
    await db_session.commit()

    overview = await privacy_overview.build_overview(
        db_session, organization_id=org_id
    )
    item = next(
        entry for entry in overview.attention if entry.key.startswith("ropa-article9-")
    )
    assert "special-category data" in item.title
    assert "in addition to a lawful basis" in item.detail


@pytest.mark.asyncio
async def test_reviewing_an_activity_records_who_and_when(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: the review is the evidence, not the date field."""
    org_id = await _signup(client, "privacy7@example.com", "Privacy Seven")
    created = (
        await client.post(
            "/api/v1/compliance/processing-activities",
            json={
                "name": "Customer Support",
                "purpose": "Answering product questions.",
                "legal_basis": "contract",
                "data_categories": ["contact_details"],
                "data_subjects": "Customers",
                "retention_period": "24 months",
            },
        )
    ).json()
    assert created["last_reviewed_at"] is None
    assert created["review_overdue"] is False

    response = await client.post(
        f"/api/v1/compliance/processing-activities/{created['id']}/review",
        json={"next_review_months": 12},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["last_reviewed_at"]
    assert body["last_reviewed_by"]
    assert body["next_review_at"]
    assert body["review_overdue"] is False

    activity = await db_session.get(ProcessingActivity, uuid.UUID(created["id"]))
    await db_session.refresh(activity)
    assert privacy_deadlines.as_utc(
        activity.next_review_at
    ) == privacy_deadlines.next_review_from(activity.last_reviewed_at, months=12)
    assert activity.organization_id == org_id


@pytest.mark.asyncio
async def test_an_activity_past_its_review_date_surfaces_as_needing_one(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Derived, so a record does not become overdue only once a job runs."""
    org_id = await _signup(client, "privacy8@example.com", "Privacy Eight")
    db_session.add(
        ProcessingActivity(
            organization_id=org_id,
            name="Payroll",
            purpose="Paying employees.",
            legal_basis="contract",
            data_subjects="Employees",
            retention_period="7 years",
            last_reviewed_at=datetime.now(UTC) - timedelta(days=400),
            next_review_at=datetime.now(UTC) - timedelta(days=35),
        )
    )
    await db_session.commit()

    overview = await privacy_overview.build_overview(
        db_session, organization_id=org_id
    )
    item = next(
        entry for entry in overview.attention if entry.key.startswith("ropa-review-")
    )
    assert item.title == "Payroll is due for review"
    metrics = {metric.key: metric for metric in overview.metrics}
    assert metrics["activities_need_review"].value == 1
    assert metrics["activities_need_review"].tone == "attention"

    listed = (await client.get("/api/v1/compliance/processing-activities")).json()
    assert listed[0]["review_overdue"] is True


@pytest.mark.asyncio
async def test_a_transfer_with_no_mechanism_needs_review_rather_than_a_verdict(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: incomplete is not the same claim as non-compliant."""
    org_id = await _signup(client, "privacy9@example.com", "Privacy Nine")
    db_session.add(
        DataTransfer(
            organization_id=org_id,
            recipient_name="Acme Analytics",
            destination_country="US",
            transfer_mechanism="",
        )
    )
    await db_session.commit()

    overview = await privacy_overview.build_overview(
        db_session, organization_id=org_id
    )
    item = next(
        entry
        for entry in overview.attention
        if entry.key.startswith("transfer-mechanism-")
    )
    assert "no mechanism recorded" in item.title
    assert "mark it for review" in item.detail
    for word in ("unlawful", "non-compliant", "prohibited"):
        assert word not in item.detail.lower()


@pytest.mark.asyncio
async def test_a_completed_request_leaves_the_worklist(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "privacy10@example.com", "Privacy Ten")
    db_session.add(
        DSAR(
            organization_id=org_id,
            requester_name="Dana Okafor",
            requester_email="dana@example.com",
            request_type="access",
            status="fulfilled",
            received_at=datetime.now(UTC) - timedelta(days=62),
            due_at=datetime.now(UTC) - timedelta(days=31),
            fulfilled_at=datetime.now(UTC) - timedelta(days=40),
            verification_status="verified",
        )
    )
    await db_session.commit()

    overview = await privacy_overview.build_overview(
        db_session, organization_id=org_id
    )
    assert overview.attention == []
    metrics = {metric.key: metric for metric in overview.metrics}
    assert metrics["open_requests"].value == 0


@pytest.mark.asyncio
async def test_the_overview_scales_without_changing_shape(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§34: fifty activities is the case the old page could not serve.

    The overview stays a fixed set of numbers and a ranked worklist; it
    does not grow a row per record.
    """
    org_id = await _signup(client, "privacy11@example.com", "Privacy Eleven")
    for index in range(50):
        db_session.add(
            ProcessingActivity(
                organization_id=org_id,
                name=f"Activity {index + 1}",
                purpose="Doing something with personal data.",
                # Half of them are incomplete, so the worklist has work.
                legal_basis="" if index % 2 else "contract",
                data_subjects="Customers",
                retention_period="24 months",
            )
        )
    for index in range(40):
        db_session.add(
            DataTransfer(
                organization_id=org_id,
                recipient_name=f"Processor {index + 1}",
                destination_country="US",
                transfer_mechanism="adequacy_decision",
            )
        )
    await db_session.commit()

    overview = await privacy_overview.build_overview(
        db_session, organization_id=org_id
    )
    metrics = {metric.key: metric for metric in overview.metrics}
    assert metrics["processing_activities"].value == 50
    assert metrics["transfers"].value == 40
    # Seven numbers, whatever the record count.
    assert len(overview.metrics) == 7
    # And 25 real gaps, worst first, each pointing at one record.
    assert len(overview.attention) == 25
    assert all(item.href.count("/") >= 3 for item in overview.attention)


@pytest.mark.asyncio
async def test_the_overview_is_scoped_to_one_organization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "privacy12@example.com", "Privacy Twelve")
    db_session.add(
        ProcessingActivity(
            organization_id=org_id,
            name="Somebody else's activity",
            purpose="Not visible from another tenant.",
            legal_basis="",
            data_subjects="Customers",
            retention_period="24 months",
        )
    )
    await db_session.commit()

    await _signup(client, "privacy13@example.com", "Privacy Thirteen")
    body = (await client.get("/api/v1/compliance/privacy/overview")).json()
    metrics = {metric["key"]: metric for metric in body["metrics"]}
    assert metrics["processing_activities"]["value"] == 0
    assert body["attention"] == []
