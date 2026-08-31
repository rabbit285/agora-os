"""One questionnaire, one status, wherever you read it from.

The bug: `Questionnaire.status` was a column nothing maintained. Set to
`draft` at creation, moved only by a button, while the detail page
computed its own progress from the answers and reported "Ready to share".
A questionnaire with every answer approved sat in the list marked Draft,
and both screens were telling the truth as they understood it.

These pin the invariant that ends it — given the same answers, every
surface reports the same workflow status — and the separation that makes
it comprehensible: how far the work got is not where the record lives.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance.models import (
    SecurityReview,
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
)
from app.compliance.questionnaire_status import LABELS, STATUSES, derive, recalculate


async def _signup(client: AsyncClient, email: str, org: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Status Tester",
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
    title: str = "Agora Origin customer",
    status: str = "draft",
    answers: list[str] | None = None,
    customer: str | None = "Agora Origin",
    linked: bool = True,
) -> Questionnaire:
    """A questionnaire whose questions carry the given answer states.

    Set up the way a real customer questionnaire is: a named customer and
    the security review it belongs to. These tests are about how the
    answers move the status, and without that context every one of them
    would stop at `needs_setup` before reaching the rule it is checking.

    `customer=None` or `linked=False` produces the unfinished shape
    deliberately, for the tests that are about that.
    """
    review = None
    if customer and linked:
        review = SecurityReview(
            organization_id=org_id,
            title=f"{customer} Security Review",
            customer_name=customer,
            status="draft",
            is_deal_blocker=False,
        )
        db.add(review)
        await db.flush()

    questionnaire = Questionnaire(
        organization_id=org_id,
        title=title,
        status=status,
        source="customer_provided",
        customer_name=customer,
        security_review_id=review.id if review else None,
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
                answer_text="An answer." if answer_status != "unanswered" else None,
                status=answer_status,
            )
        )
    await db.flush()
    return questionnaire


# --- the rule, without a database -------------------------------------


@pytest.mark.parametrize(
    ("answers", "current", "expected"),
    [
        ([], "draft", "draft"),
        (["unanswered"], "draft", "draft"),
        (["draft"], "draft", "draft"),
        (["approved", "unanswered"], "draft", "draft"),
        (["approved", "draft"], "draft", "draft"),
        (["approved", "needs_review"], "draft", "in_review"),
        (["needs_review", "needs_review"], "draft", "in_review"),
        (["approved"], "draft", "ready_to_share"),
        (["approved", "approved"], "draft", "ready_to_share"),
        # A rejected answer is outstanding work, not a closed question.
        (["approved", "rejected"], "draft", "draft"),
        # Having been shared is further along than being ready to be.
        (["approved", "approved"], "completed", "completed"),
        # But a new unanswered question makes "completed" untrue.
        (["approved", "unanswered"], "completed", "draft"),
        (["approved", "needs_review"], "completed", "in_review"),
    ],
)
def test_the_status_the_answers_imply(
    answers: list[str], current: str, expected: str
) -> None:
    assert derive(answer_statuses=answers, current=current) == expected


def test_every_status_has_words_for_it() -> None:
    """A status nobody can read is a status nobody can act on."""
    assert set(LABELS) == set(STATUSES)
    assert LABELS["ready_to_share"] == "Ready to share"
    assert LABELS["in_review"] == "In review"


def test_archived_is_not_one_of_them() -> None:
    """Lifecycle is a different dimension and a different column.

    An archived questionnaire whose answers were all approved is
    "Archived · Ready to share" — two facts, not one overwriting the
    other.
    """
    assert "archived" not in STATUSES


# --- §14 the reported bug ---------------------------------------------


async def test_14_two_of_two_approved_is_ready_to_share(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The exact record from the report: 2/2 approved, stored as draft."""
    _, org_id = await _signup(client, "st-bug@example.com", "Status Bug")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"]
    )
    await db_session.commit()
    assert questionnaire.status == "draft", "the stale state being reproduced"

    change = await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()

    assert change is not None
    assert change.before == "draft"
    assert change.after == "ready_to_share"
    assert "approved" in change.reason

    await db_session.refresh(questionnaire)
    assert questionnaire.status == "ready_to_share"


async def test_14_the_list_and_the_detail_agree(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§8: no case where the detail says one thing and the list another."""
    _, org_id = await _signup(client, "st-agree@example.com", "Status Agree")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"]
    )
    await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()

    listed = await client.get("/api/v1/compliance/questionnaires")
    detail = await client.get(f"/api/v1/compliance/questionnaires/{questionnaire.id}")

    assert listed.json()[0]["status"] == "ready_to_share"
    assert detail.json()["status"] == "ready_to_share"
    assert detail.json()["progress"]["ready_to_share"] is True


# --- §15 approving the last answer ------------------------------------


async def test_15_approving_the_last_answer_moves_the_questionnaire(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """In review → Ready to share, through the endpoint a person uses."""
    _, org_id = await _signup(client, "st-approve@example.com", "Status Approve")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "needs_review"]
    )
    await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()
    assert questionnaire.status == "in_review"

    outstanding = (
        await db_session.execute(
            select(QuestionnaireAnswer)
            .join(
                QuestionnaireQuestion,
                QuestionnaireQuestion.id == QuestionnaireAnswer.question_id,
            )
            .where(
                QuestionnaireQuestion.questionnaire_id == questionnaire.id,
                QuestionnaireAnswer.status == "needs_review",
            )
        )
    ).scalars().one()

    response = await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}"
        f"/questions/{outstanding.question_id}/answer",
        json={"answer_text": "Yes — documented and tested.", "status": "approved"},
    )
    assert response.status_code == 200, response.text

    await db_session.refresh(questionnaire)
    assert questionnaire.status == "ready_to_share"


# --- §17 reopening an approved answer ---------------------------------


async def test_17_reopening_an_answer_takes_ready_to_share_away(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The reverse has to work too, or the status only ever ratchets up."""
    _, org_id = await _signup(client, "st-reopen@example.com", "Status Reopen")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"]
    )
    await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()
    assert questionnaire.status == "ready_to_share"

    first = (
        await db_session.execute(
            select(QuestionnaireAnswer)
            .join(
                QuestionnaireQuestion,
                QuestionnaireQuestion.id == QuestionnaireAnswer.question_id,
            )
            .where(QuestionnaireQuestion.questionnaire_id == questionnaire.id)
            .limit(1)
        )
    ).scalars().one()

    await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}"
        f"/questions/{first.question_id}/answer",
        json={"answer_text": "Actually, let me redo this.", "status": "draft"},
    )

    await db_session.refresh(questionnaire)
    assert questionnaire.status == "draft"


# --- §16 a new question ------------------------------------------------


async def test_16_adding_a_question_takes_ready_to_share_away(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "st-add@example.com", "Status Add")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"]
    )
    await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()
    assert questionnaire.status == "ready_to_share"

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/questions",
        json={"text": "Do you run penetration tests annually?", "category": "security"},
    )
    assert response.status_code in (200, 201), response.text

    await db_session.refresh(questionnaire)
    assert questionnaire.status == "draft"


async def test_16_importing_questions_takes_ready_to_share_away(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: the import path uses the same calculation as everything else."""
    _, org_id = await _signup(client, "st-import@example.com", "Status Import")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"]
    )
    await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()
    assert questionnaire.status == "ready_to_share"

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
        json={
            "questions": ["Do you encrypt customer data at rest?"],
            "draft_answers": False,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status_before"] == "ready_to_share"
    assert response.json()["status_after"] == "draft"

    await db_session.refresh(questionnaire)
    assert questionnaire.status == "draft"


# --- §7 archive and restore leave the workflow alone -------------------


async def test_7_archiving_preserves_the_workflow_status(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """"Archived · Ready to share", never "Archived · Draft"."""
    _, org_id = await _signup(client, "st-archive@example.com", "Status Archive")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"]
    )
    await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()

    archived = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/archive"
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "ready_to_share"

    await db_session.refresh(questionnaire)
    assert questionnaire.status == "ready_to_share"
    assert questionnaire.archived_at is not None

    restored = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/restore"
    )
    assert restored.json()["status"] == "ready_to_share"
    await db_session.refresh(questionnaire)
    assert questionnaire.status == "ready_to_share"
    assert questionnaire.archived_at is None


# --- §12 idempotency ---------------------------------------------------


async def test_12_recalculating_repeatedly_changes_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Only real transitions are news."""
    _, org_id = await _signup(client, "st-idem@example.com", "Status Idempotent")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"]
    )
    await db_session.commit()

    first = await recalculate(db_session, questionnaire=questionnaire)
    second = await recalculate(db_session, questionnaire=questionnaire)
    third = await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()

    assert first is not None
    assert second is None, "a recalculation that confirms the status is not a change"
    assert third is None

    events = (
        await db_session.execute(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "compliance.questionnaire.status_changed",
            )
        )
    ).scalar_one()
    assert events == 1


# --- §11 the trail -----------------------------------------------------


async def test_11_the_transition_says_why_and_credits_nobody(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nobody chose this; it follows from the answers.

    Attributing it to whoever approved the last one would put a decision
    in their name they did not make.
    """
    _, org_id = await _signup(client, "st-trail@example.com", "Status Trail")
    questionnaire = await _questionnaire(
        db_session, org_id, title="Agora Origin customer", answers=["approved", "approved"]
    )
    await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()

    event = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "compliance.questionnaire.status_changed",
            )
        )
    ).scalars().one()

    assert event.before_state["status"] == "draft"
    assert event.after_state["status"] == "ready_to_share"
    assert event.after_state["reason"] == "All 2 answers were approved."
    assert event.after_state["title"] == "Agora Origin customer"
    assert event.actor_user_id is None

    from app.audit.presentation import build_views

    view = (await build_views(db_session, organization_id=org_id, events=[event]))[0]
    assert "compliance." not in view.title
    assert str(questionnaire.id) not in view.title


# --- §9 coverage is not readiness --------------------------------------


async def test_9_full_coverage_with_one_unresolved_review_is_not_ready(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Every question answered, one still awaiting a person."""
    _, org_id = await _signup(client, "st-cover@example.com", "Status Coverage")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "needs_review"]
    )
    await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()

    assert questionnaire.status == "in_review"

    detail = await client.get(f"/api/v1/compliance/questionnaires/{questionnaire.id}")
    body = detail.json()
    assert body["status"] == "in_review"
    assert body["progress"]["ready_to_share"] is False


# --- the manual endpoint ------------------------------------------------


async def test_marking_it_completed_is_the_one_thing_a_person_sets(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Reading the answers cannot tell us it went to the customer."""
    _, org_id = await _signup(client, "st-manual@example.com", "Status Manual")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"]
    )
    await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/status",
        json={"status": "completed"},
    )
    assert response.status_code == 200, response.text

    await db_session.refresh(questionnaire)
    assert questionnaire.status == "completed"

    # And it stays completed through a recalculation.
    assert await recalculate(db_session, questionnaire=questionnaire) is None


async def test_a_hand_set_draft_over_approved_answers_does_not_stick(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """This is the disagreement the endpoint used to create.

    Somebody choosing "draft" for a questionnaire whose answers are all
    approved is asking for the two to disagree. The status goes back to
    what the answers say instead.
    """
    _, org_id = await _signup(client, "st-override@example.com", "Status Override")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"]
    )
    await recalculate(db_session, questionnaire=questionnaire)
    await db_session.commit()

    await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/status",
        json={"status": "draft"},
    )

    await db_session.refresh(questionnaire)
    assert questionnaire.status == "ready_to_share"


# --- tenancy -----------------------------------------------------------


async def test_recalculation_does_not_reach_another_organization(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.compliance.questionnaire_status import recalculate_by_id

    _, other_org = await _signup(client, "st-them@example.com", "Status Them")
    theirs = await _questionnaire(
        db_session, other_org, answers=["approved", "approved"]
    )
    await db_session.commit()

    _, mine = await _signup(client, "st-mine@example.com", "Status Mine")

    change = await recalculate_by_id(
        db_session, organization_id=mine, questionnaire_id=theirs.id
    )

    assert change is None
    await db_session.refresh(theirs)
    assert theirs.status == "draft", "another organization's record was not touched"
