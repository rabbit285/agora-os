"""A confirmed transfer is somebody's judgement, and it stays theirs.

These cover the one rule in `transfer_drift`: when a fact underneath an
approved transfer moves, the product raises a flag and changes nothing.
The temptation is to "helpfully" update the destination to match the
vendor record — which would convert an approval given for Ireland into
cover for a transfer to Virginia that nobody assessed.

They also cover the quieter half. A check that fires on missing
information is worse than no check, because it trains people to dismiss
flags; and a flag that never clears asks somebody to re-review a
disagreement that no longer exists.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import DataTransfer, Vendor
from app.core.models import Organization


async def _setup(
    client: AsyncClient,
    db: AsyncSession,
    email: str,
    *,
    vendor_country: str | None = "IE",
    dpa_status: str = "signed",
    destination: str = "IE",
    mechanism: str = "adequacy_decision",
    transfer_status: str = "active",
) -> tuple[uuid.UUID, Vendor, DataTransfer]:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Dana Whitfield",
            "organization_name": "Agora Origin",
        },
    )
    org_id = (
        await db.execute(select(Organization.id).order_by(Organization.created_at.desc()))
    ).scalars().first()

    vendor = Vendor(
        organization_id=org_id,
        name="Northwind Cloud",
        category="infrastructure",
        country=vendor_country,
        dpa_status=dpa_status,
    )
    db.add(vendor)
    await db.flush()

    transfer = DataTransfer(
        organization_id=org_id,
        recipient_name="Northwind Cloud",
        destination_country=destination,
        transfer_mechanism=mechanism,
        status=transfer_status,
        vendor_id=vendor.id,
    )
    db.add(transfer)
    await db.commit()
    return org_id, vendor, transfer


async def _refresh(db: AsyncSession, transfer_id: uuid.UUID) -> DataTransfer:
    db.expire_all()
    return await db.get(DataTransfer, transfer_id)


@pytest.mark.asyncio
async def test_a_vendor_moving_country_flags_the_transfer_without_editing_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The core case, and the core restraint."""
    _, vendor, transfer = await _setup(client, db_session, "drift1@example.com")
    transfer_id = transfer.id

    vendor.country = "US"
    await db_session.commit()

    listed = (await client.get("/api/v1/compliance/data-transfers")).json()
    row = next(item for item in listed if item["id"] == str(transfer_id))

    assert row["review_reason"] is not None
    assert "US" in row["review_reason"]
    # The judgement is untouched. Only its owner can change what this
    # transfer claims.
    assert row["destination_country"] == "IE"
    assert row["transfer_mechanism"] == "adequacy_decision"
    assert row["status"] == "active"

    stored = await _refresh(db_session, transfer_id)
    assert stored.destination_country == "IE"


@pytest.mark.asyncio
async def test_a_vendor_with_no_recorded_country_raises_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Absence is not a move. A check that fires here teaches people to
    dismiss flags."""
    _, _, transfer = await _setup(
        client, db_session, "drift2@example.com", vendor_country=None
    )
    transfer_id = transfer.id

    listed = (await client.get("/api/v1/compliance/data-transfers")).json()
    row = next(item for item in listed if item["id"] == str(transfer_id))
    assert row["review_reason"] is None


@pytest.mark.asyncio
async def test_the_flag_clears_once_the_records_agree_again(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A flag that never clears is a flag nobody reads."""
    _, vendor, transfer = await _setup(client, db_session, "drift3@example.com")
    transfer_id = transfer.id
    vendor_id = vendor.id

    vendor.country = "US"
    await db_session.commit()
    listed = (await client.get("/api/v1/compliance/data-transfers")).json()
    assert next(i for i in listed if i["id"] == str(transfer_id))["review_reason"]

    # Somebody reassessed and corrected the vendor record.
    db_session.expire_all()
    reloaded = await db_session.get(Vendor, vendor_id)
    reloaded.country = "IE"
    await db_session.commit()

    listed = (await client.get("/api/v1/compliance/data-transfers")).json()
    assert next(i for i in listed if i["id"] == str(transfer_id))["review_reason"] is None


@pytest.mark.asyncio
async def test_a_pending_dpa_undercuts_sccs_but_not_an_adequacy_decision(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SCCs are a contractual instrument; adequacy is not, so the same
    missing DPA is only relevant to one of them."""
    _, _, sccs = await _setup(
        client,
        db_session,
        "drift4@example.com",
        vendor_country="US",
        destination="US",
        mechanism="sccs",
        dpa_status="pending",
    )
    sccs_id = sccs.id

    listed = (await client.get("/api/v1/compliance/data-transfers")).json()
    row = next(item for item in listed if item["id"] == str(sccs_id))
    assert "standard contractual clauses" in row["review_reason"]
    assert "pending" in row["review_reason"]

    # Same vendor state, adequacy mechanism: not a finding.
    _, _, adequacy = await _setup(
        client,
        db_session,
        "drift5@example.com",
        vendor_country="US",
        destination="US",
        mechanism="adequacy_decision",
        dpa_status="pending",
    )
    listed = (await client.get("/api/v1/compliance/data-transfers")).json()
    row = next(item for item in listed if item["id"] == str(adequacy.id))
    assert row["review_reason"] is None


@pytest.mark.asyncio
async def test_a_dpa_marked_not_required_is_a_decision_and_is_left_alone(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Somebody already judged this. Re-raising it second-guesses them."""
    _, _, transfer = await _setup(
        client,
        db_session,
        "drift6@example.com",
        vendor_country="US",
        destination="US",
        mechanism="sccs",
        dpa_status="not_required",
    )
    listed = (await client.get("/api/v1/compliance/data-transfers")).json()
    row = next(item for item in listed if item["id"] == str(transfer.id))
    assert row["review_reason"] is None


@pytest.mark.asyncio
async def test_a_terminated_transfer_is_not_re_raised(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nobody is relying on it, so nobody needs to re-approve it."""
    _, vendor, transfer = await _setup(
        client, db_session, "drift7@example.com", transfer_status="terminated"
    )
    transfer_id = transfer.id

    vendor.country = "US"
    await db_session.commit()

    listed = (await client.get("/api/v1/compliance/data-transfers")).json()
    row = next(item for item in listed if item["id"] == str(transfer_id))
    assert row["review_reason"] is None


@pytest.mark.asyncio
async def test_detection_does_not_reach_into_another_organization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The failure that made transfer detection wrong the first time."""
    _, other_vendor, other_transfer = await _setup(
        client, db_session, "drift8@example.com"
    )
    other_id = other_transfer.id
    other_vendor.country = "US"
    await db_session.commit()

    # A second organization, signed up after, whose reads must not touch
    # the first one's rows.
    await _setup(client, db_session, "drift9@example.com")

    await client.get("/api/v1/compliance/data-transfers")

    untouched = await _refresh(db_session, other_id)
    assert untouched.review_reason is None


@pytest.mark.asyncio
async def test_the_detail_view_shows_both_claims_rather_than_reconciling_them(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: the two records side by side.

    A single reconciled destination would hide exactly the disagreement
    that makes the review worth doing.
    """
    _, vendor, transfer = await _setup(
        client,
        db_session,
        "detail1@example.com",
        vendor_country="IE",
        destination="IE",
        mechanism="sccs",
        dpa_status="pending",
    )
    transfer_id = transfer.id

    vendor.country = "US"
    await db_session.commit()

    detail = (
        await client.get(f"/api/v1/compliance/data-transfers/{transfer_id}")
    ).json()

    # What the transfer claims, untouched.
    assert detail["destination_country"] == "IE"
    # What the vendor record says, alongside it.
    assert detail["vendor_country"] == "US"
    assert detail["vendor_dpa_status"] == "pending"
    assert detail["vendor_name"] == "Northwind Cloud"
    # Somebody has to be sending the data for this to be assessable.
    assert detail["exporter_name"] == "Agora Origin"
    # Opening a transfer runs the same check the list does, so a stale
    # link does not show a flag the list already cleared.
    assert detail["review_reason"] is not None


@pytest.mark.asyncio
async def test_the_detail_view_refuses_another_organizations_transfer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, _, other = await _setup(client, db_session, "detail2@example.com")
    other_id = other.id
    await _setup(client, db_session, "detail3@example.com")

    response = await client.get(f"/api/v1/compliance/data-transfers/{other_id}")
    assert response.status_code == 404
