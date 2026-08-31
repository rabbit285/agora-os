"""The engagement a customer questionnaire belongs to.

The reported case: a customer-provided questionnaire at 100% approved,
ready to share, sitting beside an Assessments page reporting "No customer
security reviews". Both were true. `SecurityReview` required a Sales
opportunity, that module was withdrawn, and so there was no way to create
a review at all — the questionnaire had nothing to be part of.

These pin the relationship that replaces it: a customer questionnaire
joins its customer's engagement automatically, one engagement per
customer, and the engagement's state is its questionnaires' state added
up.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance.customer_review import (
    ReviewProgress,
    derive_status,
    link_questionnaire,
    progress_for,
    review_title_for,
)
from app.compliance.models import (
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    SecurityReview,
)
from app.compliance.review_backfill import backfill_customer_reviews


async def _signup(client: AsyncClient, email: str, org: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Review Tester",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return uuid.UUID(body["user"]["id"]), uuid.UUID(body["organization"]["id"])


async def _questionnaire(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    title: str,
    source: str = "customer_provided",
    customer: str | None = None,
    answers: list[str] | None = None,
) -> Questionnaire:
    questionnaire = Questionnaire(
        organization_id=org_id,
        title=title,
        source=source,
        customer_name=customer,
        status="draft",
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


async def _review_count(db: AsyncSession, org_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count(SecurityReview.id)).where(
                    SecurityReview.organization_id == org_id
                )
            )
        ).scalar_one()
    )


# --- the rule, without a database -------------------------------------


def test_the_engagement_is_named_after_the_customer() -> None:
    assert review_title_for("Agora Origin") == "Agora Origin Security Review"
    assert review_title_for("  Acme Corp  ") == "Acme Corp Security Review"


@pytest.mark.parametrize(
    ("progress", "current", "expected"),
    [
        (ReviewProgress(), "draft", "draft"),
        (ReviewProgress(questionnaires=1, total=0), "draft", "draft"),
        (ReviewProgress(questionnaires=1, total=2, approved=1, unanswered=1), "draft", "in_progress"),
        (ReviewProgress(questionnaires=1, total=2, approved=1, needs_review=1), "draft", "needs_review"),
        (ReviewProgress(questionnaires=1, total=2, approved=2), "draft", "ready_to_share"),
        # Two questionnaires: one finished, one not. The engagement is not
        # ready because part of it is not.
        (ReviewProgress(questionnaires=2, total=3, approved=2, needs_review=1), "draft", "needs_review"),
        # Having gone to the customer is further along than being ready to.
        (ReviewProgress(questionnaires=1, total=1, approved=1), "completed", "completed"),
        # But new outstanding work makes that untrue.
        (ReviewProgress(questionnaires=1, total=2, approved=1, unanswered=1), "completed", "in_progress"),
    ],
)
def test_the_status_the_questionnaires_imply(
    progress: ReviewProgress, current: str, expected: str
) -> None:
    assert derive_status(progress, current=current) == expected


def test_percent_counts_approved_answers_only() -> None:
    """A drafted answer nobody read is not progress towards sending it back."""
    progress = ReviewProgress(questionnaires=1, total=4, approved=1, draft=3)
    assert progress.percent_complete == 25
    assert progress.ready is False


# --- §21 a customer questionnaire opens its engagement ----------------


async def test_21_a_customer_questionnaire_creates_its_review(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "cr-new@example.com", "CR New")

    response = await client.post(
        "/api/v1/compliance/questionnaires",
        json={
            "title": "Acme Security Questionnaire",
            "source": "customer_provided",
            "customer_name": "Acme Corp",
        },
    )
    assert response.status_code == 201, response.text

    reviews = (
        await db_session.execute(
            select(SecurityReview).where(SecurityReview.organization_id == org_id)
        )
    ).scalars().all()
    assert len(reviews) == 1
    assert reviews[0].title == "Acme Corp Security Review"
    assert reviews[0].customer_name == "Acme Corp"
    # Compliance-native: no sales opportunity involved.
    assert reviews[0].opportunity_id is None

    questionnaire = await db_session.get(Questionnaire, uuid.UUID(response.json()["id"]))
    assert questionnaire is not None
    assert questionnaire.security_review_id == reviews[0].id
    assert user_id is not None


# --- §22 an internal assessment is nobody's engagement ----------------


async def test_22_an_internal_assessment_creates_no_review(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "cr-internal@example.com", "CR Internal")

    response = await client.post(
        "/api/v1/compliance/questionnaires",
        json={
            "title": "Quarterly Internal GDPR Assessment",
            "source": "internal_template",
        },
    )
    assert response.status_code == 201, response.text
    assert await _review_count(db_session, org_id) == 0


async def test_a_customer_questionnaire_with_no_customer_creates_no_review(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Inventing a customer would put one in the record who does not exist."""
    _, org_id = await _signup(client, "cr-unnamed@example.com", "CR Unnamed")

    response = await client.post(
        "/api/v1/compliance/questionnaires",
        json={"title": "Some customer form", "source": "customer_provided"},
    )
    assert response.status_code == 201, response.text
    assert await _review_count(db_session, org_id) == 0


# --- §23 and §24 one engagement per customer --------------------------


async def test_23_a_second_questionnaire_joins_the_same_review(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "cr-second@example.com", "CR Second")

    first = await client.post(
        "/api/v1/compliance/questionnaires",
        json={
            "title": "Acme Security Questionnaire",
            "source": "customer_provided",
            "customer_name": "Acme Corp",
        },
    )
    second = await client.post(
        "/api/v1/compliance/questionnaires",
        json={
            "title": "Acme Privacy Questionnaire",
            "source": "customer_provided",
            "customer_name": "Acme Corp",
        },
    )

    assert await _review_count(db_session, org_id) == 1
    a = await db_session.get(Questionnaire, uuid.UUID(first.json()["id"]))
    b = await db_session.get(Questionnaire, uuid.UUID(second.json()["id"]))
    assert a is not None and b is not None
    assert a.security_review_id == b.security_review_id


async def test_24_the_customer_name_is_matched_case_folded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """"Acme Corp" and "acme corp" are one customer."""
    _, org_id = await _signup(client, "cr-case@example.com", "CR Case")

    for name in ("Acme Corp", "acme corp", "  ACME CORP  "):
        response = await client.post(
            "/api/v1/compliance/questionnaires",
            json={
                "title": f"Questionnaire for {name}",
                "source": "customer_provided",
                "customer_name": name,
            },
        )
        assert response.status_code == 201, response.text

    assert await _review_count(db_session, org_id) == 1


async def test_24_linking_the_same_questionnaire_twice_changes_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Retries must not produce a second engagement or a second event."""
    user_id, org_id = await _signup(client, "cr-retry@example.com", "CR Retry")
    questionnaire = await _questionnaire(
        db_session, org_id, title="Acme questionnaire", customer="Acme Corp"
    )
    await db_session.commit()

    for _ in range(3):
        await link_questionnaire(
            db_session,
            organization_id=org_id,
            questionnaire=questionnaire,
            actor_user_id=user_id,
        )
    await db_session.commit()

    assert await _review_count(db_session, org_id) == 1
    created = (
        await db_session.execute(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "compliance.security_review.created",
            )
        )
    ).scalar_one()
    assert created == 1


# --- §10 and §11 the engagement's work is its questionnaires' ---------


async def test_10_progress_adds_up_across_questionnaires(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "cr-agg@example.com", "CR Aggregate")
    first = await _questionnaire(
        db_session,
        org_id,
        title="Security",
        customer="Acme Corp",
        answers=["approved", "approved"],
    )
    review = await link_questionnaire(
        db_session, organization_id=org_id, questionnaire=first, actor_user_id=user_id
    )
    second = await _questionnaire(
        db_session,
        org_id,
        title="Privacy",
        customer="Acme Corp",
        answers=["approved", "needs_review"],
    )
    await link_questionnaire(
        db_session, organization_id=org_id, questionnaire=second, actor_user_id=user_id
    )
    await db_session.commit()

    assert review is not None
    progress = await progress_for(db_session, review_id=review.id)
    assert progress.questionnaires == 2
    assert progress.total == 4
    assert progress.approved == 3
    assert progress.needs_review == 1
    assert progress.percent_complete == 75
    assert progress.ready is False


async def test_11_one_finished_questionnaire_does_not_make_a_review_ready(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The engagement is not ready while part of it is not."""
    user_id, org_id = await _signup(client, "cr-ready@example.com", "CR Ready")
    finished = await _questionnaire(
        db_session,
        org_id,
        title="Security",
        customer="Acme Corp",
        answers=["approved"],
    )
    review = await link_questionnaire(
        db_session, organization_id=org_id, questionnaire=finished, actor_user_id=user_id
    )
    await db_session.commit()
    assert review is not None
    await db_session.refresh(review)
    assert review.status == "ready_to_share"

    outstanding = await _questionnaire(
        db_session,
        org_id,
        title="Privacy",
        customer="Acme Corp",
        answers=["needs_review"],
    )
    await link_questionnaire(
        db_session,
        organization_id=org_id,
        questionnaire=outstanding,
        actor_user_id=user_id,
    )
    await db_session.commit()

    await db_session.refresh(review)
    assert review.status == "needs_review"


# --- §5 and §20 the questionnaires that predate the engagement --------


async def test_20_the_backfill_links_an_existing_customer_questionnaire(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The reported case: 100% approved, and no review to belong to."""
    user_id, org_id = await _signup(client, "cr-backfill@example.com", "CR Backfill")
    stranded = await _questionnaire(
        db_session,
        org_id,
        title="Agora Origin customer",
        customer="Agora Origin",
        answers=["approved", "approved"],
    )
    await db_session.commit()
    assert stranded.security_review_id is None
    assert await _review_count(db_session, org_id) == 0

    preview = await backfill_customer_reviews(
        db_session, organization_id=org_id, actor_user_id=user_id, dry_run=True
    )
    assert preview.linked == 1
    assert await _review_count(db_session, org_id) == 0, "a dry run creates nothing"

    applied = await backfill_customer_reviews(
        db_session, organization_id=org_id, actor_user_id=user_id, dry_run=False
    )
    await db_session.commit()

    assert applied.linked == 1
    assert applied.reviews_created == 1
    await db_session.refresh(stranded)
    assert stranded.security_review_id is not None

    review = await db_session.get(SecurityReview, stranded.security_review_id)
    assert review is not None
    assert review.title == "Agora Origin Security Review"
    assert review.status == "ready_to_share"


async def test_5_the_backfill_does_not_guess_a_customer(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A title is not a customer name.

    Reading "Agora Origin" out of "Agora Origin cusotmer" would put a
    name into a compliance record on a string match, and a typo in a
    title would become a customer in the audit trail.
    """
    user_id, org_id = await _signup(client, "cr-guess@example.com", "CR Guess")
    await _questionnaire(db_session, org_id, title="Agora Origin cusotmer", customer=None)
    await db_session.commit()

    report = await backfill_customer_reviews(
        db_session, organization_id=org_id, actor_user_id=user_id, dry_run=False
    )
    await db_session.commit()

    assert report.unnamed == 1
    assert report.linked == 0
    assert await _review_count(db_session, org_id) == 0


async def test_5_the_backfill_is_safe_to_run_again(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "cr-again@example.com", "CR Again")
    await _questionnaire(
        db_session, org_id, title="Acme questionnaire", customer="Acme Corp"
    )
    await db_session.commit()

    first = await backfill_customer_reviews(
        db_session, organization_id=org_id, actor_user_id=user_id, dry_run=False
    )
    await db_session.commit()
    second = await backfill_customer_reviews(
        db_session, organization_id=org_id, actor_user_id=user_id, dry_run=False
    )
    await db_session.commit()

    assert first.linked == 1
    assert second.linked == 0
    assert second.already_linked == 1
    assert await _review_count(db_session, org_id) == 1


# --- the API surface ---------------------------------------------------


async def test_the_review_list_carries_its_progress(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: one calculation, so the card cannot disagree with the page."""
    await _signup(client, "cr-api@example.com", "CR Api")
    await client.post(
        "/api/v1/compliance/questionnaires",
        json={
            "title": "Acme Security Questionnaire",
            "source": "customer_provided",
            "customer_name": "Acme Corp",
        },
    )

    listed = await client.get("/api/v1/compliance/security-reviews")
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["title"] == "Acme Corp Security Review"
    assert rows[0]["customer_name"] == "Acme Corp"
    assert rows[0]["progress"]["questionnaires"] == 1
    assert rows[0]["status_label"]

    detail = await client.get(f"/api/v1/compliance/security-reviews/{rows[0]['id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert [q["title"] for q in body["questionnaires"]] == [
        "Acme Security Questionnaire"
    ]
    # The card and the page report the same numbers.
    assert body["progress"] == rows[0]["progress"]


async def test_a_review_from_another_organization_is_not_reachable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, other_org = await _signup(client, "cr-them@example.com", "CR Them")
    theirs = await _questionnaire(
        db_session, other_org, title="Theirs", customer="Their Customer"
    )
    review = await link_questionnaire(
        db_session, organization_id=other_org, questionnaire=theirs, actor_user_id=user_id
    )
    await db_session.commit()
    assert review is not None

    await _signup(client, "cr-mine@example.com", "CR Mine")

    listed = await client.get("/api/v1/compliance/security-reviews")
    assert listed.json() == []

    detail = await client.get(f"/api/v1/compliance/security-reviews/{review.id}")
    assert detail.status_code == 404


# --- §18 the trail -----------------------------------------------------


async def test_18_creating_and_linking_are_both_recorded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "cr-trail@example.com", "CR Trail")
    await client.post(
        "/api/v1/compliance/questionnaires",
        json={
            "title": "Acme Security Questionnaire",
            "source": "customer_provided",
            "customer_name": "Acme Corp",
        },
    )

    actions = [
        row
        for row in (
            await db_session.execute(
                select(AuditEvent.action).where(
                    AuditEvent.organization_id == org_id,
                    AuditEvent.action.like("compliance.security_review.%"),
                )
            )
        )
        .scalars()
        .all()
    ]

    assert "compliance.security_review.created" in actions
    assert "compliance.security_review.questionnaire_linked" in actions
