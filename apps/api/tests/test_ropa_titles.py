"""What a processing activity is called.

Two questions that look similar and are not:

    Organization    "who is doing the processing?"    Agora Origin
    Activity        "what processing is being done?"  Customer Support

A RoPA entry titled with the organization's name answers the first
question twice and the second not at all — and an Article 30 record that
cannot say what the processing *is* is not a record of processing.

The reported record turned out to be typed by hand rather than
generated: the audit event names a user as the actor, the organization
had no AI systems, and no suggestion had ever run in it. There was no
fallback to find. These pin the invariant anyway, in the place a future
one would trip over it, and fix the real weakness the report exposed:
a drafted activity was named after the *system* rather than the
processing.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance import ropa_titles
from app.compliance.models import ProcessingActivity


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


# --- deriving a title ---------------------------------------------------


@pytest.mark.parametrize(
    ("purpose", "expected"),
    [
        ("Respond to customer support requests", "Customer Support"),
        ("Handling the support inbox", "Customer Support"),
        ("Collect and evaluate job applications", "Recruitment"),
        ("Charge customers for their subscription", "Billing and Payments"),
        ("Invoice customers monthly", "Billing and Payments"),
        ("Send marketing newsletters", "Marketing Communications"),
        ("Manage employee records", "Employee Management"),
        ("Run payroll each month", "Payroll"),
    ],
)
def test_a_title_is_derived_from_the_processing(
    purpose: str, expected: str
) -> None:
    """§3: the title names the operation, from its stated purpose."""
    proposal = ropa_titles.derive(purpose=purpose)
    assert proposal.title == expected
    assert proposal.basis == "purpose"
    assert proposal.needs_review is False
    assert proposal.reason


def test_an_ai_system_doing_customer_support_is_ai_customer_support() -> None:
    """§11: the exact acceptance case.

    "Support Assistant" is the name of a tool. "AI Customer Support" is
    the name of an operation, and a RoPA that cannot tell them apart
    cannot answer a DPIA question about either.
    """
    proposal = ropa_titles.derive(
        purpose="Respond to customer support requests",
        ai_system_name="Support Assistant",
        is_ai=True,
    )
    assert proposal.title == "AI Customer Support"
    assert proposal.basis == "purpose"


def test_an_unrecognisable_purpose_asks_rather_than_invents() -> None:
    """§4: "Needs review" beats a confident wrong title.

    A plausible-looking one gets approved without anybody reading it.
    """
    nothing = ropa_titles.derive(purpose="Test")
    assert nothing.title == ropa_titles.NEEDS_TITLE
    assert nothing.basis == "none"
    assert nothing.needs_review is True

    # With a system to fall back on, the system is named — and flagged,
    # because a tool name is not an activity name.
    fallback = ropa_titles.derive(
        purpose="Test", ai_system_name="Support Assistant", is_ai=True
    )
    assert fallback.title == "Support Assistant"
    assert fallback.basis == "system"
    assert fallback.needs_review is True


def test_a_near_miss_word_does_not_read_as_a_business_operation() -> None:
    """Word boundaries: "discharge" is not billing."""
    assert (
        ropa_titles.derive(purpose="Discharge patients from the ward").basis == "none"
    )


# --- refusing the wrong identity ----------------------------------------


@pytest.mark.asyncio
async def test_the_organization_name_is_refused_as_an_activity_name(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2/§12: the invariant, kept where a future change would trip on it."""
    await _signup(client, "ropa1@example.com", "Agora Origin")

    refused = await client.post(
        "/api/v1/compliance/processing-activities",
        json={
            "name": "Agora Origin",
            "purpose": "Something.",
            "legal_basis": "contract",
            "data_subjects": "Customers",
            "retention_period": "24 months",
        },
    )
    assert refused.status_code == 422
    assert "is your organization's name" in refused.text
    # And it explains the distinction rather than just declining.
    assert "who is doing the processing" in refused.text


@pytest.mark.asyncio
async def test_a_person_and_an_email_are_refused_too(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "ropa2@example.com", "Agora Origin")

    for name, marker in (
        ("Zach Warren", "is a person in your organization"),
        ("ropa2@example.com", "That is an email address"),
    ):
        refused = await client.post(
            "/api/v1/compliance/processing-activities",
            json={
                "name": name,
                "purpose": "Something.",
                "legal_basis": "contract",
                "data_subjects": "Customers",
                "retention_period": "24 months",
            },
        )
        assert refused.status_code == 422, name
        assert marker in refused.text


@pytest.mark.asyncio
async def test_a_real_activity_name_is_accepted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, "ropa3@example.com", "Agora Origin")
    created = await client.post(
        "/api/v1/compliance/processing-activities",
        json={
            "name": "Customer Support",
            "purpose": "Respond to customer support requests.",
            "legal_basis": "contract",
            "data_subjects": "Customers",
            "retention_period": "24 months",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Customer Support"
    assert created.json()["status"] == "active"


@pytest.mark.asyncio
async def test_the_guard_is_scoped_to_the_tenant(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§12: another tenant's name is not a reserved word here.

    "Acme Corp" is a perfectly good activity name for an agency that
    processes on Acme's behalf.
    """
    await _signup(client, "ropa4@example.com", "Acme Corp")
    await _signup(client, "ropa5@example.com", "Agora Origin")

    allowed = await client.post(
        "/api/v1/compliance/processing-activities",
        json={
            "name": "Acme Corp",
            "purpose": "Processing carried out on behalf of a client.",
            "legal_basis": "contract",
            "data_subjects": "Customers",
            "retention_period": "24 months",
        },
    )
    assert allowed.status_code == 201, allowed.text


# --- incomplete records are drafts --------------------------------------


@pytest.mark.asyncio
async def test_an_activity_missing_a_decision_is_a_draft(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§7: recording it as active would put an incomplete claim in the
    register and stop the overview asking about it."""
    await _signup(client, "ropa6@example.com", "Agora Origin")

    draft = await client.post(
        "/api/v1/compliance/processing-activities",
        json={
            "name": "Marketing Communications",
            "purpose": "Send product updates to subscribers.",
            "data_subjects": "Subscribers",
        },
    )
    assert draft.status_code == 201, draft.text
    body = draft.json()
    assert body["status"] == "draft"
    assert body["legal_basis"] == ""

    # And the overview still asks for the missing decision.
    overview = (await client.get("/api/v1/compliance/privacy/overview")).json()
    assert any(
        item["key"].startswith("ropa-basis-") for item in overview["attention"]
    )


# --- repairing what is already recorded ---------------------------------


@pytest.mark.asyncio
async def test_a_recorded_organization_name_is_flagged_not_renamed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5: proposed, never applied.

    A record somebody typed deliberately is theirs, and silently
    retitling it would be the product overruling its user on the one
    field only the user can write.
    """
    org_id = await _signup(client, "ropa7@example.com", "Agora Origin")
    # Forced in the way the reported record got there — by hand, before
    # the guard existed.
    db_session.add(
        ProcessingActivity(
            organization_id=org_id,
            name="Agora Origin",
            purpose="Respond to customer support requests.",
            legal_basis="legal_obligation",
            data_subjects="customers",
            retention_period="24 months",
        )
    )
    await db_session.commit()

    repairs = (
        await client.get("/api/v1/compliance/processing-activities/title-repairs")
    ).json()
    assert len(repairs) == 1
    repair = repairs[0]
    assert repair["current_title"] == "Agora Origin"
    assert repair["problem"]["kind"] == "organization"
    # The purpose supports a better title, so one is offered.
    assert repair["suggested_title"] == "Customer Support"
    assert "customer support" in repair["suggestion_reason"].lower()

    # Nothing was renamed.
    activity = (
        await db_session.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == org_id
            )
        )
    ).scalars().first()
    await db_session.refresh(activity)
    assert activity.name == "Agora Origin"

    # A person applies it.
    applied = await client.post(
        f"/api/v1/compliance/processing-activities/{repair['activity_id']}/title",
        json={"title": "Customer Support"},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["name"] == "Customer Support"

    # And the repair list is empty afterwards.
    assert (
        await client.get("/api/v1/compliance/processing-activities/title-repairs")
    ).json() == []


@pytest.mark.asyncio
async def test_an_ambiguous_record_is_flagged_without_a_suggestion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5: "Do not guess when evidence is ambiguous."

    This is the shape of the actual reported record — its purpose was
    "Test", which supports nothing.
    """
    org_id = await _signup(client, "ropa8@example.com", "Agora Origin")
    db_session.add(
        ProcessingActivity(
            organization_id=org_id,
            name="Agora Origin",
            purpose="Test",
            legal_basis="legal_obligation",
            data_subjects="customers",
            retention_period="24 months",
        )
    )
    await db_session.commit()

    repairs = (
        await client.get("/api/v1/compliance/processing-activities/title-repairs")
    ).json()
    assert len(repairs) == 1
    assert repairs[0]["problem"]["kind"] == "organization"
    assert repairs[0]["suggested_title"] is None
    assert repairs[0]["suggestion_reason"] is None


@pytest.mark.asyncio
async def test_a_repair_cannot_land_back_where_it_started(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "ropa9@example.com", "Agora Origin")
    activity = ProcessingActivity(
        organization_id=org_id,
        name="Agora Origin",
        purpose="Test",
        legal_basis="legal_obligation",
        data_subjects="customers",
        retention_period="24 months",
    )
    db_session.add(activity)
    await db_session.commit()

    refused = await client.post(
        f"/api/v1/compliance/processing-activities/{activity.id}/title",
        json={"title": "Agora Origin"},
    )
    assert refused.status_code == 422
    assert "is your organization's name" in refused.text


# --- one activity, not three --------------------------------------------


def test_similar_titles_decide_whether_to_ask_not_whether_to_merge() -> None:
    """§13: "Customer Support" and "AI Customer Support" are one operation.

    Conflating them silently would lose the distinction a DPIA turns on;
    treating them as unrelated produces three records for one activity.
    """
    assert ropa_titles.similar_titles("Customer Support", "AI Customer Support")
    assert ropa_titles.similar_titles("customer support", "Customer  Support")
    assert not ropa_titles.similar_titles("Customer Support", "Recruitment")
    assert not ropa_titles.similar_titles("Customer Support", "")


@pytest.mark.asyncio
async def test_a_probable_duplicate_is_surfaced_for_a_person_to_judge(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, "ropa10@example.com", "Agora Origin")
    db_session.add(
        ProcessingActivity(
            organization_id=org_id,
            name="Customer Support",
            purpose="Respond to customer support requests.",
            legal_basis="contract",
            data_subjects="Customers",
            retention_period="24 months",
        )
    )
    await db_session.commit()

    match = await ropa_titles.possible_duplicate(
        db_session, organization_id=org_id, title="AI Customer Support"
    )
    assert match is not None
    assert match.name == "Customer Support"

    unrelated = await ropa_titles.possible_duplicate(
        db_session, organization_id=org_id, title="Recruitment"
    )
    assert unrelated is None
