"""When a customer questionnaire is actually ready to share.

"Ready to share" is a claim about sending something back to somebody. A
customer-provided questionnaire with every answer approved, no customer
recorded and no security review to belong to is not ready to share with
anybody — there is nobody to share it with. That is `needs_setup`, and no
amount of approving clears it.

The rule lives in one place and is read three ways: it writes the stored
status, it is serialised for the screen, and it is what the API refuses
with. These pin all three saying the same thing.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    SecurityReview,
)
from app.audit.models import AuditEvent
from app.compliance.customer_review import recalculate as recalculate_review
from app.compliance.questionnaire_status import (
    blockers,
    derive,
    recalculate,
)


async def _signup(client: AsyncClient, email: str, org: str) -> uuid.UUID:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Readiness Tester",
            "organization_name": org,
        },
    )
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["organization"]["id"])


async def _questionnaire(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    title: str = "Acme Security Questionnaire",
    source: str = "customer_provided",
    customer: str | None = None,
    linked: bool = False,
    answers: list[str] | None = None,
    status: str = "draft",
) -> Questionnaire:
    review = None
    if linked:
        review = SecurityReview(
            organization_id=org_id,
            title=f"{customer or 'Customer'} Security Review",
            customer_name=customer,
            status="draft",
            is_deal_blocker=False,
        )
        db.add(review)
        await db.flush()

    questionnaire = Questionnaire(
        organization_id=org_id,
        title=title,
        source=source,
        customer_name=customer,
        status=status,
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
                status=answer_status,
                answer_text="An answer.",
            )
        )
    await db.flush()
    return questionnaire


# --- §2/§3 the rule, without a database ---------------------------------


@pytest.mark.parametrize(
    ("case", "kwargs", "expected"),
    [
        (
            # §19: everything approved, and still not shareable.
            "customer questionnaire with no customer",
            {"source": "customer_provided", "answer_statuses": ["approved", "approved"]},
            "needs_setup",
        ),
        (
            "customer named but no review to belong to",
            {
                "source": "customer_provided",
                "customer_name": "Acme Corp",
                "answer_statuses": ["approved"],
            },
            "needs_setup",
        ),
        (
            "customer and review, all approved",
            {
                "source": "customer_provided",
                "customer_name": "Acme Corp",
                "security_review_id": "a-review",
                "answer_statuses": ["approved"],
            },
            "ready_to_share",
        ),
        (
            # An internal assessment is not sent to anybody, so the word
            # "share" carries no customer with it.
            "internal assessment, all approved",
            {"source": "internal_template", "answer_statuses": ["approved"]},
            "ready_to_share",
        ),
        (
            # §22: one unresolved item is enough.
            "customer questionnaire, 4 approved and 1 needing review",
            {
                "source": "customer_provided",
                "customer_name": "Acme Corp",
                "security_review_id": "a-review",
                "answer_statuses": ["approved"] * 4 + ["needs_review"],
            },
            "in_review",
        ),
        (
            "customer questionnaire with an unanswered question",
            {
                "source": "customer_provided",
                "customer_name": "Acme Corp",
                "security_review_id": "a-review",
                "answer_statuses": ["approved", "unanswered"],
            },
            "draft",
        ),
    ],
)
def test_the_readiness_rule(case: str, kwargs: dict, expected: str) -> None:
    assert derive(current="draft", **kwargs) == expected, case


def test_setup_outranks_a_stored_completed() -> None:
    """A questionnaire with no customer cannot have gone to a customer.

    `completed` is otherwise sticky, because "we sent it" is a fact the
    answers cannot know. It is not sticky over this: a stored `completed`
    on a questionnaire with nobody to have sent it to is a record of
    something that did not happen.
    """
    assert (
        derive(
            answer_statuses=["approved"],
            current="completed",
            source="customer_provided",
        )
        == "needs_setup"
    )


def test_every_blocker_is_reported_not_just_the_first() -> None:
    """"Fix this, now fix the next thing" is a worse way to learn what a
    record needs."""
    found = blockers(
        source="customer_provided",
        customer_name=None,
        security_review_id=None,
        answer_statuses=["unanswered", "needs_review"],
    )
    codes = [blocker.code for blocker in found]
    assert codes == ["customer_required", "unanswered_questions", "needs_review"]
    # The customer comes first because it is the one that blocks the rest.
    assert "Customer required" in found[0].message

    # And the review is not reported separately while the customer is
    # missing — it is a consequence of that, not another thing to go and do.
    assert "review_required" not in codes


def test_an_internal_assessment_needs_no_customer() -> None:
    found = blockers(
        source="internal_template",
        customer_name=None,
        security_review_id=None,
        answer_statuses=["approved"],
    )
    assert found == []


# --- §16 the stored status follows -------------------------------------


@pytest.mark.anyio
async def test_the_stored_status_lands_on_needs_setup(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"stored-{uuid.uuid4().hex[:8]}@example.com", "Stored Org")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"]
    )

    change = await recalculate(db_session, questionnaire=questionnaire)
    assert change is not None
    assert change.after == "needs_setup"
    assert "Customer required" in change.reason
    assert questionnaire.status == "needs_setup"

    # Idempotent: nothing moved, so nothing is written or recorded.
    assert await recalculate(db_session, questionnaire=questionnaire) is None


# --- §2/§5 what the API says about it ----------------------------------


@pytest.mark.anyio
async def test_the_list_says_what_is_blocking_each_row(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"list-{uuid.uuid4().hex[:8]}@example.com", "List Org")
    await _questionnaire(
        db_session,
        org_id,
        title="Do you encrypt customer data at rest?",
        answers=["approved", "approved"],
        status="needs_setup",
    )
    await _questionnaire(
        db_session,
        org_id,
        title="Acme Security Questionnaire",
        customer="Acme Corp",
        linked=True,
        answers=["approved"],
        status="ready_to_share",
    )
    await db_session.commit()

    rows = {row["title"]: row for row in (await client.get("/api/v1/compliance/questionnaires")).json()}

    stuck = rows["Do you encrypt customer data at rest?"]
    assert stuck["status"] == "needs_setup"
    assert stuck["status_label"] == "Needs setup"
    assert stuck["readiness"]["ready"] is False
    assert stuck["readiness"]["needs_setup"] is True
    assert stuck["readiness"]["blockers"][0]["code"] == "customer_required"
    # §18: flagged for rename, and not renamed.
    assert stuck["title_looks_like_a_question"] is True

    fine = rows["Acme Security Questionnaire"]
    assert fine["status"] == "ready_to_share"
    assert fine["readiness"]["ready"] is True
    assert fine["readiness"]["needs_setup"] is False
    assert fine["title_looks_like_a_question"] is False


# --- §15 the server refuses, not just the screen ------------------------


@pytest.mark.anyio
async def test_the_server_refuses_to_mark_it_shared(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"refuse-{uuid.uuid4().hex[:8]}@example.com", "Refuse Org")
    questionnaire = await _questionnaire(
        db_session, org_id, answers=["approved", "approved"], status="needs_setup"
    )
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/status",
        json={"status": "completed"},
    )
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "Cannot mark questionnaire ready to share" in message
    # The same sentence the row shows, not a second wording of the rule.
    assert "Customer required" in message

    await db_session.refresh(questionnaire)
    assert questionnaire.status == "needs_setup"


@pytest.mark.anyio
async def test_unresolved_answers_also_block_the_transition(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"unres-{uuid.uuid4().hex[:8]}@example.com", "Unres Org")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        customer="Acme Corp",
        linked=True,
        answers=["approved", "needs_review"],
    )
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/status",
        json={"status": "completed"},
    )
    assert response.status_code == 422
    assert "need" in response.json()["error"]["message"].lower()


# --- §20 the acceptance test, end to end -------------------------------


@pytest.mark.anyio
async def test_setting_the_customer_unblocks_everything(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """2/2 approved, customer missing, Needs setup → Ready to share."""
    org_id = await _signup(client, f"unblock-{uuid.uuid4().hex[:8]}@example.com", "Unblock Org")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        title="Agora Origin questionnaire",
        answers=["approved", "approved"],
        status="needs_setup",
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/customer",
        json={"customer_name": "Agora Origin"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["review_created"] is True

    # §16: the questionnaire's own status moved with it, rather than
    # still reading "Customer required" over a customer that is now there.
    listed = {
        row["title"]: row
        for row in (await client.get("/api/v1/compliance/questionnaires")).json()
    }["Agora Origin questionnaire"]
    assert listed["status"] == "ready_to_share"
    assert listed["readiness"]["ready"] is True
    assert listed["readiness"]["blockers"] == []

    # And the engagement it now belongs to agrees.
    review = (await client.get("/api/v1/compliance/security-reviews")).json()[0]
    assert review["title"] == "Agora Origin Security Review"
    assert review["status"] == "ready_to_share"

    # No duplicates, from either side.
    assert (
        len(
            (
                await db_session.execute(
                    select(SecurityReview).where(
                        SecurityReview.organization_id == org_id
                    )
                )
            )
            .scalars()
            .all()
        )
        == 1
    )

    # And now the transition the server refused is allowed.
    shared = await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/status",
        json={"status": "completed"},
    )
    assert shared.status_code == 200, shared.text
    assert shared.json()["status"] == "completed"


# --- §11 the review is not ready while part of it is not ---------------


@pytest.mark.anyio
async def test_a_review_is_only_ready_when_all_of_it_is(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"agg-{uuid.uuid4().hex[:8]}@example.com", "Agg Org")
    finished = await _questionnaire(
        db_session,
        org_id,
        title="Acme security questionnaire",
        customer="Acme Corp",
        linked=True,
        answers=["approved", "approved"],
    )
    # Same engagement, and not finished.
    await _questionnaire(
        db_session,
        org_id,
        title="Acme privacy questionnaire",
        customer="Acme Corp",
        answers=["needs_review", "needs_review"],
    )
    for row in (
        (
            await db_session.execute(
                select(Questionnaire).where(
                    Questionnaire.organization_id == org_id,
                    Questionnaire.security_review_id.is_(None),
                )
            )
        )
        .scalars()
        .all()
    ):
        row.security_review_id = finished.security_review_id
    review_row = await db_session.get(SecurityReview, finished.security_review_id)
    await recalculate_review(db_session, review=review_row)
    await db_session.commit()

    review = (await client.get("/api/v1/compliance/security-reviews")).json()[0]
    assert review["status"] == "needs_review"
    assert review["progress"]["ready_to_share"] is False
    assert review["progress"]["needs_review"] == 2


@pytest.mark.anyio
async def test_an_empty_questionnaire_keeps_a_review_from_being_ready(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A package goes to the customer whole.

    Counting only answers, a review holding one finished questionnaire
    and one nobody has put questions into adds up to "everything
    approved" — and half of it has not been started.
    """
    org_id = await _signup(client, f"empty-{uuid.uuid4().hex[:8]}@example.com", "Empty Org")
    finished = await _questionnaire(
        db_session,
        org_id,
        title="Acme security questionnaire",
        customer="Acme Corp",
        linked=True,
        answers=["approved", "approved"],
    )
    blank = await _questionnaire(
        db_session,
        org_id,
        title="Acme privacy questionnaire",
        customer="Acme Corp",
        answers=[],
    )
    blank.security_review_id = finished.security_review_id
    review_row = await db_session.get(SecurityReview, finished.security_review_id)
    await recalculate_review(db_session, review=review_row)
    await db_session.commit()

    review = (await client.get("/api/v1/compliance/security-reviews")).json()[0]
    assert review["progress"]["questionnaires"] == 2
    assert review["progress"]["approved"] == 2
    assert review["progress"]["total"] == 2
    # Two of two approved, and still not ready.
    assert review["progress"]["ready_to_share"] is False
    assert review["status"] == "in_progress"


# --- §18 renaming, offered and never applied ---------------------------


@pytest.mark.anyio
async def test_renaming_changes_the_name_and_nothing_else(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _signup(client, f"rename-{uuid.uuid4().hex[:8]}@example.com", "Rename Org")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        title="Do you encrypt customer data at rest?",
        customer="Acme Corp",
        linked=True,
        answers=["approved"],
        status="ready_to_share",
    )
    await db_session.commit()

    before_review = questionnaire.security_review_id
    response = await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/title",
        json={"title": "Acme Corp Security Questionnaire"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Acme Corp Security Questionnaire"
    assert body["title_looks_like_a_question"] is False
    # What a questionnaire is called was never part of whether it is ready.
    assert body["status"] == "ready_to_share"

    await db_session.refresh(questionnaire)
    assert questionnaire.security_review_id == before_review
    assert questionnaire.customer_name == "Acme Corp"

    # A rename to the same words is not a rename.
    again = await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/title",
        json={"title": "Acme Corp Security Questionnaire"},
    )
    assert again.status_code == 200
    renames = list(
        (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.organization_id == org_id,
                    AuditEvent.action == "compliance.questionnaire.renamed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(renames) == 1
    assert renames[0].before_state["title"] == "Do you encrypt customer data at rest?"
    assert renames[0].after_state["title"] == "Acme Corp Security Questionnaire"


@pytest.mark.anyio
async def test_a_new_questionnaire_is_stored_in_the_status_it_is_in(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§16: the stored status and the readiness agree from the first moment.

    Creation used to leave the column at its default, so a customer
    questionnaire with no customer was stored `draft` while the same
    response reported `needs_setup` in `readiness`. Two answers to one
    question, on one record, in one payload.
    """
    await _signup(client, f"fresh-{uuid.uuid4().hex[:8]}@example.com", "Fresh Org")

    unnamed = await client.post(
        "/api/v1/compliance/questionnaires",
        json={"title": "Acme Security Questionnaire", "source": "customer_provided"},
    )
    assert unnamed.status_code in (200, 201), unnamed.text
    assert unnamed.json()["status"] == "needs_setup"

    named = await client.post(
        "/api/v1/compliance/questionnaires",
        json={
            "title": "Globex Security Questionnaire",
            "source": "customer_provided",
            "customer_name": "Globex",
        },
    )
    assert named.status_code in (200, 201), named.text
    # A customer and a review, and no questions yet: being prepared.
    assert named.json()["status"] == "draft"

    internal = await client.post(
        "/api/v1/compliance/questionnaires",
        json={
            "title": "Internal ISO 42001 Assessment",
            "source": "internal_template",
        },
    )
    assert internal.status_code in (200, 201), internal.text
    assert internal.json()["status"] == "draft"

    rows = {
        row["title"]: row
        for row in (await client.get("/api/v1/compliance/questionnaires")).json()
    }
    for title, expected in (
        ("Acme Security Questionnaire", True),
        ("Globex Security Questionnaire", False),
        ("Internal ISO 42001 Assessment", False),
    ):
        row = rows[title]
        assert row["readiness"]["needs_setup"] is expected, title
        # The stored status and the readiness cannot disagree.
        assert (row["status"] == "needs_setup") is expected, title


@pytest.mark.anyio
async def test_one_customer_cannot_have_two_open_engagements(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: there is never an ambiguous choice to put to somebody.

    A partial unique index on (organization, lower(customer_name)) where
    the review is active means a customer has at most one open
    engagement. Four questionnaires for one customer, in four spellings,
    join one review — so "which review did you mean?" is a question the
    schema makes unaskable rather than one the UI has to handle.
    """
    org_id = await _signup(client, f"one-{uuid.uuid4().hex[:8]}@example.com", "One Org")

    for name in ("Acme Corp", "acme corp", "ACME CORP", "  Acme Corp  "):
        response = await client.post(
            "/api/v1/compliance/questionnaires",
            json={
                "title": f"Questionnaire for {name}",
                "source": "customer_provided",
                "customer_name": name,
            },
        )
        assert response.status_code in (200, 201), response.text

    reviews = (await client.get("/api/v1/compliance/security-reviews")).json()
    assert len(reviews) == 1
    assert reviews[0]["progress"]["questionnaires"] == 4

    stored = list(
        (
            await db_session.execute(
                select(SecurityReview).where(
                    SecurityReview.organization_id == org_id,
                    SecurityReview.archived_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(stored) == 1
