"""Looking before importing.

Creating a hundred questions the moment somebody pastes something is
fast and unsafe: they cannot see what was found, what was thrown away or
what already existed, and by the time they can it is a hundred rows to
unpick by hand.

These pin the two halves. Analysis writes nothing and describes
everything — including the lines it refused, because a questionnaire
where eight rows vanished without comment is one nobody can trust they
have answered. Confirmation creates exactly what a person approved.
"""

from __future__ import annotations

import uuid

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
from app.compliance.questionnaire_analysis import (
    NEAR_DUPLICATE_RATIO,
    analyse_import,
    normalize,
    similarity,
)

PASTE = """SECTION 1 - GOVERNANCE
Do you have an information security policy?
Do you encrypt customer data at rest?
Do you have an incident-response process?
Do you maintain an AI governance policy?
Security controls / yes / no / comments"""


async def _signup(client: AsyncClient, email: str, org: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Import Tester",
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
    questions: list[str] | None = None,
) -> Questionnaire:
    # A customer questionnaire that is actually set up: a named customer
    # and the security review it belongs to. These tests are about
    # importing questions, and without that context every one of them
    # would stop at `needs_setup` before reaching the behaviour it checks.
    review = SecurityReview(
        organization_id=org_id,
        title="Agora Origin Security Review",
        customer_name="Agora Origin",
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
        customer_name="Agora Origin",
        security_review_id=review.id,
    )
    db.add(questionnaire)
    await db.flush()
    for index, text in enumerate(questions or []):
        question = QuestionnaireQuestion(
            organization_id=org_id,
            questionnaire_id=questionnaire.id,
            text=text,
            category="security",
            order_index=index,
        )
        db.add(question)
        await db.flush()
        # Every question carries an answer row from the moment it exists,
        # the same way the import creates them.
        db.add(
            QuestionnaireAnswer(
                organization_id=org_id, question_id=question.id, status="unanswered"
            )
        )
    await db.flush()
    return questionnaire


async def _count_questions(db: AsyncSession, questionnaire_id: uuid.UUID) -> int:
    return int(
        (
            await db.execute(
                select(func.count(QuestionnaireQuestion.id)).where(
                    QuestionnaireQuestion.questionnaire_id == questionnaire_id
                )
            )
        ).scalar_one()
    )


# --- normalization and similarity -------------------------------------


def test_case_punctuation_and_spacing_are_not_what_a_question_asks() -> None:
    """The duplicate bug this normalization exists to prevent."""
    assert normalize("Do you encrypt customer data at rest?") == normalize(
        "  do you encrypt CUSTOMER data at rest  "
    )
    assert normalize("Is data encrypted?") == normalize("Is data encrypted")


def test_two_ways_of_asking_the_same_thing_score_close() -> None:
    score = similarity(
        "Do you encrypt customer data at rest?",
        "Is customer data encrypted while stored?",
    )
    assert score > 0, "no overlap at all would make near-duplicates undetectable"


def test_two_different_questions_do_not_look_alike() -> None:
    """Scaffolding words are why this needs a stopword list.

    "Do you have a..." is in most questionnaire questions and says
    nothing about which one this is.
    """
    score = similarity(
        "Do you have an information security policy?",
        "Do you have a business continuity plan?",
    )
    assert score < NEAR_DUPLICATE_RATIO


# --- analysis writes nothing ------------------------------------------


async def test_analysis_creates_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§4: the whole reason there is a preview step."""
    _, org_id = await _signup(client, "imp-safe@example.com", "Import Safe")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/analyze",
        json={"questions_text": PASTE},
    )

    assert response.status_code == 200, response.text
    assert response.json()["new"] == 4
    assert await _count_questions(db_session, questionnaire.id) == 0


async def test_analysis_reports_the_lines_it_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§15: nothing is dropped silently.

    A questionnaire where rows vanished without comment is one nobody
    can trust they have answered.
    """
    _, org_id = await _signup(client, "imp-reject@example.com", "Import Reject")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/analyze",
        json={"questions_text": PASTE},
    )
    body = response.json()

    assert body["unparsed"] == 2
    refused = [line for line in body["lines"] if line["outcome"] == "unparsed"]
    assert {line["text"] for line in refused} == {
        "SECTION 1 - GOVERNANCE",
        "Security controls / yes / no / comments",
    }
    # And each says why, specifically enough to act on.
    for line in refused:
        assert line["reason"]
        assert line["reason"] != "Could not parse"
    heading = next(line for line in refused if "GOVERNANCE" in line["text"])
    assert "heading" in heading["reason"].lower()


async def test_analysis_marks_what_is_already_here(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19: the incident-response question already exists."""
    _, org_id = await _signup(client, "imp-dupe@example.com", "Import Dupe")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        questions=["Do you have an incident-response process?"],
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/analyze",
        json={"questions_text": PASTE},
    )
    body = response.json()

    assert body["detected"] == 4
    assert body["new"] == 3
    assert body["duplicates"] == 1
    duplicate = next(line for line in body["lines"] if line["outcome"] == "duplicate")
    assert duplicate["matches"] == "Do you have an incident-response process?"
    assert duplicate["importable"] is False


async def test_a_differently_worded_question_is_flagged_not_merged(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5: merging would silently drop a question a customer asked.

    So it is pointed at, marked importable, and left to the reader.
    """
    _, org_id = await _signup(client, "imp-near@example.com", "Import Near")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        questions=["Do you encrypt customer data at rest?"],
    )
    await db_session.commit()

    analysis = await analyse_import(
        db_session,
        organization_id=org_id,
        questionnaire_id=questionnaire.id,
        raw_lines=["Do you encrypt customer data at rest across all environments?"],
    )

    assert analysis.possible_duplicates == 1
    line = analysis.lines[0]
    assert line.outcome == "possible_duplicate"
    assert line.matches == "Do you encrypt customer data at rest?"
    assert line.importable, "the reader decides, so it has to be importable"


async def test_the_same_question_twice_in_one_paste_counts_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A spreadsheet asking the same thing on three tabs asks once."""
    _, org_id = await _signup(client, "imp-repeat@example.com", "Import Repeat")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    analysis = await analyse_import(
        db_session,
        organization_id=org_id,
        questionnaire_id=questionnaire.id,
        raw_lines=[
            "Do you have an information security policy?",
            "do you have an information security policy",
            "Do you have an information security policy?",
        ],
    )

    assert analysis.new == 1


# --- confirming creates what was approved -----------------------------


async def test_19_confirming_creates_only_the_new_questions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§19: four in, one already here, four total afterwards — not five."""
    _, org_id = await _signup(client, "imp-confirm@example.com", "Import Confirm")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        questions=["Do you have an incident-response process?"],
    )
    await db_session.commit()

    analysis = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/analyze",
        json={"questions_text": PASTE},
    )
    chosen = [line["text"] for line in analysis.json()["lines"] if line["importable"]]

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
        json={"questions": chosen, "draft_answers": False},
    )

    assert response.status_code == 200, response.text
    assert response.json()["created"] == 3
    assert await _count_questions(db_session, questionnaire.id) == 4


async def test_confirming_creates_only_what_was_chosen(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A reader who skipped a possible duplicate must not get it anyway."""
    _, org_id = await _signup(client, "imp-chosen@example.com", "Import Chosen")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
        json={
            "questions": ["Do you have an information security policy?"],
            "draft_answers": False,
        },
    )

    assert response.json()["created"] == 1
    texts = (
        await db_session.execute(
            select(QuestionnaireQuestion.text).where(
                QuestionnaireQuestion.questionnaire_id == questionnaire.id
            )
        )
    ).scalars().all()
    assert list(texts) == ["Do you have an information security policy?"]


# --- §9 / §10 stale completion state ----------------------------------


async def test_9_importing_into_a_finished_questionnaire_reopens_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9 and §10: the screenshot's exact situation.

    100% complete, ready to share — then four new questions arrive.
    Leaving it marked complete over unanswered questions is the stale
    state this exists to prevent.
    """
    _, org_id = await _signup(client, "imp-reopen@example.com", "Import Reopen")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        status="completed",
        questions=["Do you have an incident-response process?"],
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
        json={
            "questions": ["Do you have an information security policy?"],
            "draft_answers": False,
        },
    )

    # Derived from the answers like every other change, rather than the
    # hand-rolled "completed → in_progress" this endpoint used to do: the
    # imported question is unanswered, so the questionnaire is a draft.
    body = response.json()
    assert body["status_before"] == "completed"
    assert body["status_after"] == "draft"

    await db_session.refresh(questionnaire)
    assert questionnaire.status == "draft"

    # And the change is in the trail, with the reason.
    events = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "compliance.questionnaire.status_changed",
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].before_state["status"] == "completed"
    assert "needs an answer" in events[0].after_state["reason"].lower()


async def test_10_ready_to_share_is_revoked_by_new_questions(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§10: derived from the answers, so it cannot go stale.

    One approved of one is ready. One approved of five is not, and the
    figure has to say so the moment the questions land.
    """
    user_id, org_id = await _signup(client, "imp-ready@example.com", "Import Ready")
    questionnaire = await _questionnaire(
        db_session, org_id, questions=["Do you have an incident-response process?"]
    )
    await db_session.flush()
    question = (
        await db_session.execute(
            select(QuestionnaireQuestion).where(
                QuestionnaireQuestion.questionnaire_id == questionnaire.id
            )
        )
    ).scalars().one()
    await client.patch(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/questions/{question.id}/answer",
        json={"answer_text": "Yes — documented and tested.", "status": "approved"},
    )
    await db_session.commit()

    before = await client.get(f"/api/v1/compliance/questionnaires/{questionnaire.id}")
    assert before.json()["progress"]["ready_to_share"] is True
    assert before.json()["progress"]["percent_complete"] == 100

    await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
        json={
            "questions": [
                "Do you have an information security policy?",
                "Do you encrypt customer data at rest?",
                "Do you maintain an AI governance policy?",
                "Do you run penetration tests annually?",
            ],
            "draft_answers": False,
        },
    )

    after = await client.get(f"/api/v1/compliance/questionnaires/{questionnaire.id}")
    progress = after.json()["progress"]
    assert progress["total"] == 5
    assert progress["approved"] == 1
    assert progress["percent_complete"] == 20
    assert progress["ready_to_share"] is False
    assert user_id is not None


# --- §6 / §20 idempotency ---------------------------------------------


async def test_20_importing_the_same_set_again_creates_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§20: retries, double clicks, the same spreadsheet sent twice."""
    _, org_id = await _signup(client, "imp-again@example.com", "Import Again")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    chosen = [
        "Do you have an information security policy?",
        "Do you encrypt customer data at rest?",
    ]
    first = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
        json={"questions": chosen, "draft_answers": False},
    )
    second = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
        json={"questions": chosen, "draft_answers": False},
    )
    third = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
        json={"questions": chosen, "draft_answers": False},
    )

    assert first.json()["created"] == 2
    assert second.json()["created"] == 0
    assert second.json()["duplicates_skipped"] == 2
    assert third.json()["created"] == 0
    assert await _count_questions(db_session, questionnaire.id) == 2


async def test_20_a_retry_writes_no_second_import_event(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§17: no duplicate business events from technical retries."""
    _, org_id = await _signup(client, "imp-events@example.com", "Import Events")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    for _ in range(3):
        await client.post(
            f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
            json={
                "questions": ["Do you have an information security policy?"],
                "draft_answers": False,
            },
        )

    events = (
        await db_session.execute(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "compliance.questionnaire.questions_imported",
            )
        )
    ).scalar_one()
    assert events == 1


async def test_a_differently_cased_repeat_is_still_a_repeat(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: normalized identity, not exact text.

    Re-sending the same spreadsheet with different capitalisation is the
    same spreadsheet.
    """
    _, org_id = await _signup(client, "imp-case@example.com", "Import Case")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
        json={
            "questions": ["Do you have an information security policy?"],
            "draft_answers": False,
        },
    )
    await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/confirm",
        json={
            "questions": ["  DO YOU HAVE AN INFORMATION SECURITY POLICY  "],
            "draft_answers": False,
        },
    )

    assert await _count_questions(db_session, questionnaire.id) == 1


# --- input handling ---------------------------------------------------


async def test_an_empty_input_is_refused_with_a_reason(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "imp-empty@example.com", "Import Empty")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/analyze",
        json={},
    )

    assert response.status_code == 422
    assert "paste" in response.json()["error"]["message"].lower()


async def test_an_unreadable_file_type_names_the_ones_that_work(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§2: do not claim unsupported file types, and do not just refuse."""
    from app.core.models import File

    user_id, org_id = await _signup(client, "imp-badfile@example.com", "Import Bad File")
    questionnaire = await _questionnaire(db_session, org_id)
    unreadable = File(
        organization_id=org_id,
        storage_key=f"org/{org_id}/{uuid.uuid4()}/photo.png",
        original_filename="photo.png",
        content_type="image/png",
        size_bytes=1024,
        uploaded_by=user_id,
        processing_status="uploaded",
    )
    db_session.add(unreadable)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/import/analyze",
        json={"file_id": str(unreadable.id)},
    )

    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "CSV" in message and "Excel" in message


async def test_another_organizations_questionnaire_is_not_importable_into(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, other_org = await _signup(client, "imp-them@example.com", "Import Them")
    theirs = await _questionnaire(db_session, other_org)
    await db_session.commit()

    await _signup(client, "imp-mine@example.com", "Import Mine")

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{theirs.id}/import/analyze",
        json={"questions_text": PASTE},
    )

    assert response.status_code == 404
    assert await _count_questions(db_session, theirs.id) == 0
