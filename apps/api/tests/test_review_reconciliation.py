"""Reconciling customer questionnaires that predate the engagement model.

The reported case, exactly: two customer-provided questionnaires, both
ready to share, both archived, both sitting under an Assessments page
reporting "Active 0 / Archived 0 / No customer security reviews".

They were unlinked for a reason that was correct and useless. Their
`customer_name` is null — the column did not exist when they were made —
and the rule is that a questionnaire naming no customer is not something
to guess about. So the backfill left them alone and reported them, and
nothing anywhere offered anybody the chance to say who the customer was.

These pin the half that was missing:

- a name read off a title is a suggestion, and the suggestion refuses to
  fire on a title that is really a question
- a person can name the customer, and that links the engagement
- the engagement follows its questionnaires into and out of the archive
- an archived engagement reports what it contained rather than zeros
- every one of those is idempotent
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance.customer_identity import suggest_customer_name
from app.compliance.customer_review import (
    progress_for,
    set_lifecycle,
    sync_lifecycle,
)
from app.compliance.models import (
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    SecurityReview,
)
from app.compliance.review_backfill import backfill_customer_reviews


async def _signup(client: AsyncClient, email: str, org: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Reconciler",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _questionnaire(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    title: str,
    source: str = "customer_provided",
    customer: str | None = None,
    answers: list[str] | None = None,
    archived: bool = False,
    status: str = "draft",
) -> Questionnaire:
    """A questionnaire shaped like the ones in the report.

    `customer=None` is the whole point: these records carry no customer,
    because there was no column for one when they were created.
    """
    questionnaire = Questionnaire(
        organization_id=org_id,
        title=title,
        source=source,
        customer_name=customer,
        status=status,
        archived_at=datetime.now(UTC) if archived else None,
    )
    db.add(questionnaire)
    await db.flush()
    for index, answer_status in enumerate(answers or []):
        question = QuestionnaireQuestion(
            organization_id=org_id,
            questionnaire_id=questionnaire.id,
            text=f"Question {index + 1}?",
            order_index=index,
        )
        db.add(question)
        await db.flush()
        db.add(
            QuestionnaireAnswer(
                organization_id=org_id,
                question_id=question.id,
                status=answer_status,
                answer_text="An answer.",
            )
        )
    await db.flush()
    return questionnaire


async def _reviews(db: AsyncSession, org_id: uuid.UUID) -> list[SecurityReview]:
    return list(
        (
            await db.execute(
                select(SecurityReview).where(
                    SecurityReview.organization_id == org_id
                )
            )
        )
        .scalars()
        .all()
    )


# --- §3 reading a customer off a title, and refusing to -----------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        # The record from the report. "cusotmer" is a transposed
        # "customer" and is removed as vocabulary, not kept as a name.
        ("Agora Origin cusotmer", "Agora Origin"),
        ("Agora Origin customer", "Agora Origin"),
        ("Nordwind Robotics vendor security questionnaire", "Nordwind Robotics"),
        ("Acme Security Questionnaire", "Acme"),
        ("Globex", "Globex"),
    ],
)
def test_a_title_that_names_a_customer(title: str, expected: str) -> None:
    suggestion = suggest_customer_name(title)
    assert suggestion is not None
    assert suggestion.name == expected
    # The reasoning travels with it, because the audit trail should say
    # the name came from the title rather than asserting somebody knew it.
    assert "title" in suggestion.reason.lower()


@pytest.mark.parametrize(
    "title",
    [
        # The other record from the report: a question used as a title.
        # Turning this into a customer called "Do You Encrypt" is the
        # exact failure the refusal exists for.
        "Do you encrypt customer data at rest?",
        "How do you handle incidents",
        "Please describe your access controls",
        # Nothing but vocabulary — there is no name in here.
        "Security Questionnaire",
        "Vendor Due Diligence Form",
        "Untitled questionnaire",
        "",
        "   ",
        # Prose, not a name.
        "Questionnaire sent over by the team we met at the conference last spring",
    ],
)
def test_a_title_that_does_not_name_a_customer(title: str) -> None:
    assert suggest_customer_name(title) is None


def test_a_suggestion_is_never_silently_applied(monkeypatch) -> None:
    """The module cannot write anything; it has no session to write with."""
    import inspect

    from app.compliance import customer_identity

    for _, function in inspect.getmembers(customer_identity, inspect.isfunction):
        assert not inspect.iscoroutinefunction(function)


# --- §4 the backfill reports rather than guesses ------------------------


@pytest.mark.anyio
async def test_unnamed_questionnaires_come_back_as_questions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"needs-{uuid.uuid4().hex[:8]}@example.com", "Needs Org")
    await _questionnaire(
        db_session, org_id, title="Agora Origin cusotmer", answers=["approved"]
    )
    await _questionnaire(
        db_session,
        org_id,
        title="Do you encrypt customer data at rest?",
        answers=["approved"],
    )

    report = await backfill_customer_reviews(
        db_session, organization_id=org_id, dry_run=False
    )

    assert report.linked == 0
    assert not await _reviews(db_session, org_id)
    assert report.unnamed == 2

    by_title = {row.title: row for row in report.needs_customer}
    # One has a name to offer.
    assert by_title["Agora Origin cusotmer"].suggested_customer == "Agora Origin"
    # The other does not, and says so rather than inventing one.
    assert by_title["Do you encrypt customer data at rest?"].suggested_customer is None
    assert report.suggested == 1


@pytest.mark.anyio
async def test_accepting_the_suggestions_links_them(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§12: the reported data, reconciled."""
    org_id = await _signup(client, f"accept-{uuid.uuid4().hex[:8]}@example.com", "Accept Org")
    agora = await _questionnaire(
        db_session,
        org_id,
        title="Agora Origin cusotmer",
        status="ready_to_share",
        answers=["approved", "approved", "approved"],
    )
    question = await _questionnaire(
        db_session,
        org_id,
        title="Do you encrypt customer data at rest?",
        status="ready_to_share",
        answers=["approved", "approved"],
    )

    report = await backfill_customer_reviews(
        db_session,
        organization_id=org_id,
        dry_run=False,
        confirm_suggested_customers=True,
    )

    assert report.linked == 1
    assert report.linked_from_title == 1
    assert report.reviews_created == 1
    # The one with no name to read is still nobody's guess.
    assert report.unnamed == 1
    assert report.needs_customer[0].questionnaire_id == question.id

    await db_session.refresh(agora)
    assert agora.security_review_id is not None
    # The name was written down, not just used in passing: the next screen
    # to read this record has to see the customer it was linked under.
    assert agora.customer_name == "Agora Origin"

    reviews = await _reviews(db_session, org_id)
    assert len(reviews) == 1
    assert reviews[0].title == "Agora Origin Security Review"
    assert reviews[0].customer_name == "Agora Origin"


@pytest.mark.anyio
async def test_confirmation_is_not_implied_by_writing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """`dry_run=False` means "write"; it does not mean "trust the titles"."""
    org_id = await _signup(client, f"implied-{uuid.uuid4().hex[:8]}@example.com", "Implied Org")
    await _questionnaire(db_session, org_id, title="Agora Origin cusotmer")

    report = await backfill_customer_reviews(
        db_session, organization_id=org_id, dry_run=False
    )

    assert report.linked == 0
    assert report.unnamed == 1
    assert not await _reviews(db_session, org_id)


@pytest.mark.anyio
async def test_archived_questionnaires_are_backfilled_too(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4: not skipping the records most likely to need the history."""
    org_id = await _signup(client, f"arch-{uuid.uuid4().hex[:8]}@example.com", "Arch Org")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        title="Agora Origin cusotmer",
        status="ready_to_share",
        archived=True,
        answers=["approved", "approved", "approved"],
    )

    report = await backfill_customer_reviews(
        db_session,
        organization_id=org_id,
        dry_run=False,
        confirm_suggested_customers=True,
    )

    assert report.linked == 1
    await db_session.refresh(questionnaire)
    assert questionnaire.security_review_id is not None
    # And the engagement it landed in is closed, because everything in it
    # is: an Active tab advertising finished work would be a lie.
    assert report.reviews_archived == 1
    review = (await _reviews(db_session, org_id))[0]
    assert review.archived_at is not None
    # Nobody archived it, so nobody's decision is recorded against it.
    assert review.archived_by is None


@pytest.mark.anyio
async def test_an_archived_engagement_reports_what_it_held(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6/§7: 3 questions, 100% approved — not "0 of 0"."""
    org_id = await _signup(client, f"hist-{uuid.uuid4().hex[:8]}@example.com", "Hist Org")
    await _questionnaire(
        db_session,
        org_id,
        title="Agora Origin cusotmer",
        status="ready_to_share",
        archived=True,
        answers=["approved", "approved", "approved"],
    )
    await backfill_customer_reviews(
        db_session,
        organization_id=org_id,
        dry_run=False,
        confirm_suggested_customers=True,
    )
    review = (await _reviews(db_session, org_id))[0]

    history = await progress_for(db_session, review_id=review.id, include_archived=True)
    assert (history.questionnaires, history.total, history.approved) == (1, 3, 3)
    assert history.percent_complete == 100
    # Workflow and lifecycle are separate dimensions: ready to share, and
    # archived, is a perfectly ordinary thing for a finished review to be.
    assert review.status == "ready_to_share"
    assert review.archived_at is not None

    # And asking without forcing the history gives the same answer, because
    # the scope follows the questionnaires: there is no live work in this
    # engagement, so what it held is what there is to report. Counting only
    # live rows here would blank a finished review to "0 of 0".
    assert (await progress_for(db_session, review_id=review.id)) == history


# --- §10 idempotency ----------------------------------------------------


@pytest.mark.anyio
async def test_reconciliation_repeats_without_duplicating(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"idem-{uuid.uuid4().hex[:8]}@example.com", "Idem Org")
    await _questionnaire(db_session, org_id, title="Agora Origin cusotmer", answers=["approved"])
    await _questionnaire(db_session, org_id, title="Agora Origin customer", answers=["approved"])

    kwargs = {"dry_run": False, "confirm_suggested_customers": True}
    first = await backfill_customer_reviews(
        db_session, organization_id=org_id, **kwargs
    )
    events_after_first = int(
        (
            await db_session.execute(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.organization_id == org_id
                )
            )
        ).scalar_one()
    )
    second = await backfill_customer_reviews(
        db_session, organization_id=org_id, **kwargs
    )
    events_after_second = int(
        (
            await db_session.execute(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.organization_id == org_id
                )
            )
        ).scalar_one()
    )

    # Two questionnaires, one customer, one engagement.
    assert first.linked == 2
    assert first.reviews_created == 1
    assert len(await _reviews(db_session, org_id)) == 1

    # The second pass finds nothing to do and says nothing about it.
    assert second.linked == 0
    assert second.already_linked == 2
    assert second.reviews_created == 0
    assert events_after_second == events_after_first


# --- §5 the engagement follows its questionnaires -----------------------


@pytest.mark.anyio
async def test_archiving_the_last_questionnaire_closes_the_engagement(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"sync-{uuid.uuid4().hex[:8]}@example.com", "Sync Org")
    first = await _questionnaire(
        db_session, org_id, title="Acme A", customer="Acme Corp", answers=["approved"]
    )
    second = await _questionnaire(
        db_session, org_id, title="Acme B", customer="Acme Corp", answers=["approved"]
    )
    await backfill_customer_reviews(
        db_session, organization_id=org_id, dry_run=False
    )
    review = (await _reviews(db_session, org_id))[0]
    assert review.archived_at is None

    # One of two archived: the engagement still has live work in it.
    first.archived_at = datetime.now(UTC)
    await db_session.flush()
    assert await sync_lifecycle(db_session, review=review) is None
    assert review.archived_at is None

    # Both archived: nothing about this engagement is open any more.
    second.archived_at = datetime.now(UTC)
    await db_session.flush()
    assert await sync_lifecycle(db_session, review=review) == "archived"
    assert review.archived_at is not None

    # And a repeat writes nothing.
    assert await sync_lifecycle(db_session, review=review) is None

    # Restoring one brings the engagement back — same row, same id.
    review_id = review.id
    second.archived_at = None
    await db_session.flush()
    assert await sync_lifecycle(db_session, review=review) == "restored"
    assert review.archived_at is None
    assert review.id == review_id
    assert len(await _reviews(db_session, org_id)) == 1

    # The link was never touched through any of it.
    await db_session.refresh(first)
    await db_session.refresh(second)
    assert first.security_review_id == review_id
    assert second.security_review_id == review_id


@pytest.mark.anyio
async def test_a_deliberate_archive_is_not_undone_by_a_restore(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Somebody closed this engagement. That is a decision, not a state."""
    org_id = await _signup(client, f"defer-{uuid.uuid4().hex[:8]}@example.com", "Defer Org")
    actor = uuid.uuid4()
    questionnaire = await _questionnaire(
        db_session, org_id, title="Acme A", customer="Acme Corp", answers=["approved"]
    )
    await backfill_customer_reviews(db_session, organization_id=org_id, dry_run=False)
    review = (await _reviews(db_session, org_id))[0]

    # Archived by a person, with live work still in it.
    await set_lifecycle(
        db_session, review=review, archived=True, actor_user_id=actor
    )
    assert review.archived_by == actor

    # The questionnaire is live, so the derived rule would reopen it. It
    # does not, because a person's decision is not a thing to recompute.
    assert questionnaire.archived_at is None
    assert await sync_lifecycle(db_session, review=review) is None
    assert review.archived_at is not None


@pytest.mark.anyio
async def test_archiving_a_review_keeps_its_questionnaires(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Closing a conversation is not an instruction to bury the evidence."""
    org_id = await _signup(client, f"keep-{uuid.uuid4().hex[:8]}@example.com", "Keep Org")
    questionnaire = await _questionnaire(
        db_session, org_id, title="Acme A", customer="Acme Corp", answers=["approved"]
    )
    await backfill_customer_reviews(db_session, organization_id=org_id, dry_run=False)
    review = (await _reviews(db_session, org_id))[0]

    await set_lifecycle(
        db_session, review=review, archived=True, actor_user_id=uuid.uuid4()
    )

    await db_session.refresh(questionnaire)
    assert questionnaire.archived_at is None
    assert questionnaire.security_review_id == review.id

    # And setting the same state again changes nothing.
    assert (
        await set_lifecycle(
            db_session, review=review, archived=True, actor_user_id=uuid.uuid4()
        )
        is False
    )


# --- §8, §13-§17 through the API ---------------------------------------


@pytest.mark.anyio
async def test_naming_the_customer_repairs_the_link(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§3's repair, and §12's acceptance: the reported record, fixed."""
    org_id = await _signup(client, f"repair-{uuid.uuid4().hex[:8]}@example.com", "Repair Org")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        title="Agora Origin cusotmer",
        status="ready_to_share",
        archived=True,
        answers=["approved", "approved", "approved"],
    )
    await db_session.commit()

    # The detail page offers the repair, with what the title appears to say.
    detail = await client.get(f"/api/v1/compliance/questionnaires/{questionnaire.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["needs_customer"] is True
    assert detail.json()["suggested_customer"] == "Agora Origin"
    assert detail.json()["security_review_id"] is None

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/customer",
        json={"customer_name": "Agora Origin"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review_created"] is True
    assert body["security_review_title"] == "Agora Origin Security Review"

    # §7: it is under Archived, not missing.
    active = await client.get("/api/v1/compliance/security-reviews?archived=false")
    archived = await client.get("/api/v1/compliance/security-reviews?archived=true")
    assert active.json() == []
    assert len(archived.json()) == 1
    review = archived.json()[0]
    assert review["title"] == "Agora Origin Security Review"
    assert review["customer_name"] == "Agora Origin"
    # §6: the history, not zeros.
    assert review["progress"]["questionnaires"] == 1
    assert review["progress"]["total"] == 3
    assert review["progress"]["approved"] == 3
    assert review["progress"]["percent_complete"] == 100
    assert review["status"] == "ready_to_share"
    assert review["archived_at"] is not None

    # §8: and the questionnaire now says which engagement it belongs to.
    detail = await client.get(f"/api/v1/compliance/questionnaires/{questionnaire.id}")
    assert detail.json()["needs_customer"] is False
    assert detail.json()["security_review_title"] == "Agora Origin Security Review"
    assert detail.json()["security_review_status_label"] == "Ready to share"
    assert detail.json()["security_review_archived_at"] is not None


@pytest.mark.anyio
async def test_repairing_twice_finds_the_same_engagement(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: no second review, no second link, no second event."""
    org_id = await _signup(client, f"twice-{uuid.uuid4().hex[:8]}@example.com", "Twice Org")
    first = await _questionnaire(db_session, org_id, title="Agora A", answers=["approved"])
    second = await _questionnaire(db_session, org_id, title="Agora B", answers=["approved"])
    await db_session.commit()

    for questionnaire in (first, second):
        for _ in range(2):
            response = await client.post(
                f"/api/v1/compliance/questionnaires/{questionnaire.id}/customer",
                json={"customer_name": "Agora Origin"},
            )
            assert response.status_code == 200, response.text

    reviews = await client.get("/api/v1/compliance/security-reviews")
    assert len(reviews.json()) == 1
    assert reviews.json()[0]["progress"]["questionnaires"] == 2


@pytest.mark.anyio
async def test_an_internal_assessment_belongs_to_no_customer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§14: refused at the endpoint, not merely skipped by the backfill."""
    org_id = await _signup(client, f"int-{uuid.uuid4().hex[:8]}@example.com", "Internal Org")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        title="Internal ISO 42001 Assessment",
        source="internal_template",
        answers=["approved"],
    )
    await db_session.commit()

    detail = await client.get(f"/api/v1/compliance/questionnaires/{questionnaire.id}")
    # Nothing is missing here, so nothing is offered.
    assert detail.json()["needs_customer"] is False

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/customer",
        json={"customer_name": "Acme Corp"},
    )
    assert response.status_code == 409
    assert (await client.get("/api/v1/compliance/security-reviews")).json() == []


@pytest.mark.anyio
async def test_a_review_archives_and_restores_by_hand(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§15: same ids, no duplicates, questionnaires untouched."""
    org_id = await _signup(client, f"hand-{uuid.uuid4().hex[:8]}@example.com", "Hand Org")
    questionnaire = await _questionnaire(
        db_session, org_id, title="Acme A", customer="Acme Corp", answers=["approved"]
    )
    await db_session.commit()
    await client.post("/api/v1/compliance/security-reviews/backfill?dry_run=false")

    reviews = (await client.get("/api/v1/compliance/security-reviews")).json()
    assert len(reviews) == 1
    review_id = reviews[0]["id"]

    archived = await client.post(
        f"/api/v1/compliance/security-reviews/{review_id}/archive"
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["changed"] is True
    # A retry is not a second archiving.
    assert (
        await client.post(f"/api/v1/compliance/security-reviews/{review_id}/archive")
    ).json()["changed"] is False

    assert (
        await client.get("/api/v1/compliance/security-reviews?archived=false")
    ).json() == []
    assert (
        len((await client.get("/api/v1/compliance/security-reviews?archived=true")).json())
        == 1
    )

    # §5: the questionnaire is still live and still linked.
    await db_session.refresh(questionnaire)
    assert questionnaire.archived_at is None
    assert str(questionnaire.security_review_id) == review_id

    restored = await client.post(
        f"/api/v1/compliance/security-reviews/{review_id}/restore"
    )
    assert restored.status_code == 200, restored.text
    active = (
        await client.get("/api/v1/compliance/security-reviews?archived=false")
    ).json()
    assert len(active) == 1
    assert active[0]["id"] == review_id


@pytest.mark.anyio
async def test_reopening_is_refused_when_the_customer_has_an_open_review(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two live engagements for one customer is the state to prevent."""
    org_id = await _signup(client, f"clash-{uuid.uuid4().hex[:8]}@example.com", "Clash Org")
    await _questionnaire(
        db_session, org_id, title="Acme A", customer="Acme Corp", answers=["approved"]
    )
    await db_session.commit()
    await client.post("/api/v1/compliance/security-reviews/backfill?dry_run=false")
    first_id = (await client.get("/api/v1/compliance/security-reviews")).json()[0]["id"]
    await client.post(f"/api/v1/compliance/security-reviews/{first_id}/archive")

    # A new questionnaire for the same customer opens a new engagement,
    # which is right: the last one was closed.
    await _questionnaire(
        db_session, org_id, title="Acme B", customer="Acme Corp", answers=["approved"]
    )
    await db_session.commit()
    await client.post("/api/v1/compliance/security-reviews/backfill?dry_run=false")
    assert (
        len((await client.get("/api/v1/compliance/security-reviews?archived=false")).json())
        == 1
    )

    response = await client.post(
        f"/api/v1/compliance/security-reviews/{first_id}/restore"
    )
    assert response.status_code == 409
    assert (
        "already has an open security review"
        in response.json()["error"]["message"]
    )


@pytest.mark.anyio
async def test_the_trail_names_who_did_what(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: a person named the customer; the archive was derived."""
    org_id = await _signup(client, f"trail-{uuid.uuid4().hex[:8]}@example.com", "Trail Org")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        title="Agora Origin cusotmer",
        archived=True,
        answers=["approved"],
    )
    await db_session.commit()
    await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/customer",
        json={"customer_name": "Agora Origin"},
    )

    events = list(
        (
            await db_session.execute(
                select(AuditEvent).where(AuditEvent.organization_id == org_id)
            )
        )
        .scalars()
        .all()
    )
    by_action = {event.action: event for event in events}

    # A person chose the customer, and the trail says which person.
    named = by_action["compliance.questionnaire.customer_set"]
    assert named.actor_user_id is not None
    assert named.after_state["customer"] == "Agora Origin"

    # Closing the engagement was derived from its questionnaires, so no
    # actor is claimed for it and the reason is recorded instead.
    closed = by_action["compliance.security_review.archived"]
    assert closed.actor_user_id is None
    assert closed.after_state["derived"] is True
    assert "archived" in closed.after_state["reason"].lower()

    assert "compliance.security_review.created" in by_action
    assert "compliance.security_review.questionnaire_linked" in by_action


@pytest.mark.anyio
async def test_a_review_left_over_from_the_sales_flow_can_be_named(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§11: legacy rows stay valid, and become repairable.

    A review created before the sales module was withdrawn identifies its
    customer through an opportunity that no longer exists, so it has no
    `customer_name` and often no title. Its questionnaire is already
    inside it, so nothing needs linking — what is missing is the name.

    Without this, such a review never matches a customer lookup, and the
    customer's next questionnaire opens a second engagement beside it.
    """
    org_id = await _signup(client, f"legacy-{uuid.uuid4().hex[:8]}@example.com", "Legacy Org")
    review = SecurityReview(
        organization_id=org_id,
        title=None,
        customer_name=None,
        status="in_progress",
        is_deal_blocker=False,
    )
    db_session.add(review)
    await db_session.flush()
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        title="Nordwind Robotics vendor security questionnaire",
        answers=["approved"],
    )
    questionnaire.security_review_id = review.id
    await db_session.commit()

    # Linked, but nobody can tell whose it is — so the repair is offered.
    detail = await client.get(f"/api/v1/compliance/questionnaires/{questionnaire.id}")
    assert detail.json()["needs_customer"] is True
    assert detail.json()["suggested_customer"] == "Nordwind Robotics"

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/customer",
        json={"customer_name": "Nordwind Robotics"},
    )
    assert response.status_code == 200, response.text
    # The existing review was named. No second engagement was opened.
    assert response.json()["review_created"] is False
    assert response.json()["security_review_id"] == str(review.id)

    await db_session.refresh(review)
    assert review.customer_name == "Nordwind Robotics"
    assert review.title == "Nordwind Robotics Security Review"
    assert len(await _reviews(db_session, org_id)) == 1

    # And now the customer's next questionnaire joins it rather than
    # starting a second engagement beside it.
    second = await _questionnaire(
        db_session,
        org_id,
        title="Nordwind privacy questionnaire",
        customer="Nordwind Robotics",
        answers=["approved"],
    )
    await db_session.commit()
    await client.post("/api/v1/compliance/security-reviews/backfill?dry_run=false")
    await db_session.refresh(second)
    assert second.security_review_id == review.id
    assert len(await _reviews(db_session, org_id)) == 1


@pytest.mark.anyio
async def test_reopening_a_finished_engagement_does_not_rewrite_its_numbers(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Found by watching somebody use it.

    They archived a finished review, restored it, and archived it again.
    Each toggle rewrote the status: "Ready to share, 3 of 3" became
    "Draft, 0 of 0" on restore and back again on archive — the same three
    approved answers described two different ways depending on which tab
    the review was sitting under.

    The cause was scoping the progress to the review's own `archived_at`.
    An engagement's work is its questionnaires' work, and that does not
    change because somebody moved the engagement between two tabs.
    """
    org_id = await _signup(client, f"wobble-{uuid.uuid4().hex[:8]}@example.com", "Wobble Org")
    await _questionnaire(
        db_session,
        org_id,
        title="Agora Origin cusotmer",
        status="ready_to_share",
        archived=True,
        answers=["approved", "approved", "approved"],
    )
    await db_session.commit()
    await client.post(
        "/api/v1/compliance/security-reviews/backfill"
        "?dry_run=false&confirm_suggested_customers=true"
    )

    review_id = (
        await client.get("/api/v1/compliance/security-reviews?archived=true")
    ).json()[0]["id"]

    def read(payload: dict) -> tuple[str, int, int]:
        return (
            payload["status"],
            payload["progress"]["approved"],
            payload["progress"]["total"],
        )

    async def current() -> tuple[str, int, int]:
        return read(
            (
                await client.get(f"/api/v1/compliance/security-reviews/{review_id}")
            ).json()
        )

    archived_state = await current()
    assert archived_state == ("ready_to_share", 3, 3)

    # Reopened. Its one questionnaire is still filed away, so there is no
    # live work — but the engagement did what it did.
    await client.post(f"/api/v1/compliance/security-reviews/{review_id}/restore")
    assert await current() == archived_state

    # And put away again.
    await client.post(f"/api/v1/compliance/security-reviews/{review_id}/archive")
    assert await current() == archived_state


@pytest.mark.anyio
async def test_a_live_questionnaire_is_what_an_open_engagement_is_judged_on(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The other half of the same rule.

    With live work in the engagement, an archived questionnaire is not
    counted — it is not outstanding, and including it would hold an open
    review to answers somebody deliberately filed away.
    """
    org_id = await _signup(client, f"mixed-{uuid.uuid4().hex[:8]}@example.com", "Mixed Org")
    await _questionnaire(
        db_session,
        org_id,
        title="Acme first",
        customer="Acme Corp",
        archived=True,
        answers=["approved", "approved"],
    )
    live = await _questionnaire(
        db_session,
        org_id,
        title="Acme second",
        customer="Acme Corp",
        answers=["approved", "unanswered"],
    )
    await db_session.commit()
    await client.post("/api/v1/compliance/security-reviews/backfill?dry_run=false")

    review = (
        await client.get("/api/v1/compliance/security-reviews?archived=false")
    ).json()[0]
    # The live questionnaire only: 1 of 2, not 3 of 4.
    assert (review["progress"]["approved"], review["progress"]["total"]) == (1, 2)
    assert review["progress"]["questionnaires"] == 1
    assert review["status"] == "in_progress"

    # File the last live one away and the engagement reports its history.
    await client.post(f"/api/v1/compliance/questionnaires/{live.id}/archive")
    after = (
        await client.get("/api/v1/compliance/security-reviews?archived=true")
    ).json()[0]
    assert (after["progress"]["approved"], after["progress"]["total"]) == (3, 4)
    assert after["progress"]["questionnaires"] == 2
