"""Cleaning up mistakes without destroying history.

Two things a compliance product has to do at once. People make test
records, duplicates and typos, and a product that makes them live with
those forever teaches them to stop trying things. But an answer somebody
approved is that person standing behind a claim made to a customer, and
that does not become disposable because the row above it looks untidy in
a list.

So: draft and unused may be deleted, anything with history may only be
archived, and the server is what decides — never the client, and never a
status column on its own.

Every assertion reads the database. An endpoint that returns 204 while
leaving a security review pointing at nothing has failed in the only way
that matters.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditEvent
from app.compliance.lifecycle import audit_eligibility, questionnaire_eligibility
from app.compliance.models import (
    Audit,
    AuditFinding,
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    SecurityReview,
)


async def _signup(client: AsyncClient, email: str, org: str) -> tuple[uuid.UUID, uuid.UUID]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "correct-horse-battery",
            "full_name": "Lifecycle Tester",
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
    title: str = "Test Questionnaire",
    status: str = "draft",
    questions: int = 0,
    answer_status: str | None = None,
    approved_by: uuid.UUID | None = None,
) -> Questionnaire:
    questionnaire = Questionnaire(
        organization_id=org_id, title=title, status=status, source="customer_provided"
    )
    db.add(questionnaire)
    await db.flush()

    for index in range(questions):
        question = QuestionnaireQuestion(
            organization_id=org_id,
            questionnaire_id=questionnaire.id,
            text=f"Question {index + 1}?",
            order_index=index,
        )
        db.add(question)
        await db.flush()
        if answer_status is not None:
            db.add(
                QuestionnaireAnswer(
                    organization_id=org_id,
                    question_id=question.id,
                    answer_text="An answer.",
                    status=answer_status,
                    approved_by=approved_by,
                    approved_at=datetime.now(UTC) if approved_by else None,
                )
            )
    await db.flush()
    return questionnaire


# --- §17 deleting a draft ---------------------------------------------


async def test_17_a_draft_with_unanswered_questions_can_be_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The acceptance case: a test questionnaire nobody used."""
    _, org_id = await _signup(client, "lc-draft@example.com", "Lifecycle Draft")
    questionnaire = await _questionnaire(db_session, org_id, questions=2)
    await db_session.commit()

    eligibility = await questionnaire_eligibility(db_session, questionnaire=questionnaire)
    assert eligibility.can_delete
    assert eligibility.reasons == []

    response = await client.delete(f"/api/v1/compliance/questionnaires/{questionnaire.id}")

    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True

    # Gone, and nothing left behind pointing at it.
    assert await db_session.get(Questionnaire, questionnaire.id) is None
    remaining_questions = (
        await db_session.execute(
            select(func.count(QuestionnaireQuestion.id)).where(
                QuestionnaireQuestion.questionnaire_id == questionnaire.id
            )
        )
    ).scalar_one()
    assert remaining_questions == 0


async def test_17_deleting_a_draft_removes_its_draft_answers_too(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§9: no orphaned rows. An answer whose question is gone is a row
    nothing can ever reach again."""
    _, org_id = await _signup(client, "lc-cascade@example.com", "Lifecycle Cascade")
    questionnaire = await _questionnaire(
        db_session, org_id, questions=3, answer_status="draft"
    )
    await db_session.commit()

    before = (
        await db_session.execute(
            select(func.count(QuestionnaireAnswer.id)).where(
                QuestionnaireAnswer.organization_id == org_id
            )
        )
    ).scalar_one()
    assert before == 3

    response = await client.delete(f"/api/v1/compliance/questionnaires/{questionnaire.id}")
    assert response.status_code == 200, response.text

    after = (
        await db_session.execute(
            select(func.count(QuestionnaireAnswer.id)).where(
                QuestionnaireAnswer.organization_id == org_id
            )
        )
    ).scalar_one()
    assert after == 0


async def test_17_an_ai_drafted_answer_does_not_make_it_undeletable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Veyntra's own working-out is not somebody's decision.

    A questionnaire the product drafted answers into, that nobody has
    looked at, is still a test record its owner may throw away.
    """
    _, org_id = await _signup(client, "lc-ai@example.com", "Lifecycle AI")
    questionnaire = await _questionnaire(
        db_session, org_id, questions=2, answer_status="needs_review"
    )
    await db_session.commit()

    eligibility = await questionnaire_eligibility(db_session, questionnaire=questionnaire)
    assert eligibility.can_delete, eligibility.reasons


async def test_17_the_deletion_leaves_a_tombstone_in_the_trail(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§6: enough to answer "what happened to that questionnaire", and
    not the content somebody asked to have destroyed."""
    user_id, org_id = await _signup(client, "lc-tomb@example.com", "Lifecycle Tomb")
    questionnaire = await _questionnaire(
        db_session, org_id, title="Test Questionnaire", questions=2
    )
    await db_session.commit()
    questionnaire_id = questionnaire.id

    await client.delete(f"/api/v1/compliance/questionnaires/{questionnaire_id}")

    events = (
        await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "compliance.questionnaire.deleted",
            )
        )
    ).scalars().all()

    assert len(events) == 1
    event = events[0]
    assert event.object_id == str(questionnaire_id)
    assert event.before_state["title"] == "Test Questionnaire"
    assert event.actor_user_id == user_id
    assert event.created_at is not None
    # The questions themselves are not kept — they were the content.
    assert "Question 1?" not in str(event.before_state) + str(event.after_state)


# --- §18 protecting a used questionnaire ------------------------------


async def test_18_an_approved_answer_blocks_permanent_deletion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The acceptance case: approve one answer, then try to delete."""
    user_id, org_id = await _signup(client, "lc-used@example.com", "Lifecycle Used")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        title="Acme Customer Security Questionnaire",
        questions=2,
        answer_status="approved",
        approved_by=None,
    )
    await db_session.commit()

    eligibility = await questionnaire_eligibility(db_session, questionnaire=questionnaire)
    assert not eligibility.can_delete
    assert eligibility.can_archive
    assert "decided on" in eligibility.message
    assert "Archive it instead" in eligibility.message

    response = await client.delete(f"/api/v1/compliance/questionnaires/{questionnaire.id}")

    assert response.status_code == 409
    assert "archive" in response.json()["error"]["message"].lower()
    # And it is still there.
    assert await db_session.get(Questionnaire, questionnaire.id) is not None
    assert user_id is not None


async def test_18_an_approver_on_the_row_blocks_it_even_if_the_status_disagrees(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Statuses drift; what happened is in the dependent rows.

    An answer carrying an approver is a decision whatever its status
    column says, and the two disagreeing is exactly the case a rule read
    off `status` alone would get wrong.
    """
    user_id, org_id = await _signup(client, "lc-drift@example.com", "Lifecycle Drift")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        questions=1,
        answer_status="draft",
        approved_by=None,
    )
    await db_session.flush()
    answer = (
        await db_session.execute(
            select(QuestionnaireAnswer).where(
                QuestionnaireAnswer.organization_id == org_id
            )
        )
    ).scalars().one()
    answer.approved_by = user_id
    answer.approved_at = datetime.now(UTC)
    await db_session.commit()

    eligibility = await questionnaire_eligibility(db_session, questionnaire=questionnaire)
    assert not eligibility.can_delete
    assert "approved" in eligibility.message


async def test_18_a_security_review_blocks_deletion(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§12: never leave a review pointing at a deleted questionnaire.

    `SecurityReview.questionnaire_id` is a non-null foreign key, so this
    is not only a policy — deleting would fail at the database or corrupt
    the review.
    """
    from app.sales.models import Account, Opportunity

    _, org_id = await _signup(client, "lc-review@example.com", "Lifecycle Review")
    questionnaire = await _questionnaire(db_session, org_id, questions=1)
    account = Account(organization_id=org_id, name="Acme")
    db_session.add(account)
    await db_session.flush()
    opportunity = Opportunity(
        organization_id=org_id,
        account_id=account.id,
        title="Acme renewal",
        stage="proposal",
        value=100000,
    )
    db_session.add(opportunity)
    await db_session.flush()
    db_session.add(
        SecurityReview(
            organization_id=org_id,
            opportunity_id=opportunity.id,
            questionnaire_id=questionnaire.id,
            status="in_progress",
        )
    )
    await db_session.commit()

    eligibility = await questionnaire_eligibility(db_session, questionnaire=questionnaire)
    assert not eligibility.can_delete
    assert "customer security review" in eligibility.message

    response = await client.delete(f"/api/v1/compliance/questionnaires/{questionnaire.id}")
    assert response.status_code == 409

    review = (
        await db_session.execute(
            select(SecurityReview).where(SecurityReview.organization_id == org_id)
        )
    ).scalars().one()
    assert review.questionnaire_id == questionnaire.id


async def test_18_a_completed_questionnaire_cannot_be_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "lc-done@example.com", "Lifecycle Done")
    questionnaire = await _questionnaire(db_session, org_id, status="completed")
    await db_session.commit()

    eligibility = await questionnaire_eligibility(db_session, questionnaire=questionnaire)
    assert not eligibility.can_delete
    assert "completed" in eligibility.message


async def test_18_archiving_preserves_everything(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The whole promise of archiving. Nothing is removed."""
    user_id, org_id = await _signup(client, "lc-arch@example.com", "Lifecycle Archive")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        title="Acme Customer Security Questionnaire",
        status="in_progress",
        questions=3,
        answer_status="approved",
    )
    await db_session.flush()
    answer = (
        await db_session.execute(
            select(QuestionnaireAnswer)
            .where(QuestionnaireAnswer.organization_id == org_id)
            .limit(1)
        )
    ).scalars().one()
    answer.approved_by = user_id
    answer.citations = [{"reference": "AI Governance Policy — §7 Monitoring"}]
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/archive"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is True
    # The status it was in is reported back, not overwritten.
    assert body["status"] == "in_progress"

    await db_session.refresh(questionnaire)
    assert questionnaire.archived_at is not None
    assert questionnaire.archived_by == user_id
    assert questionnaire.status == "in_progress", "archiving is not a status change"

    questions = (
        await db_session.execute(
            select(func.count(QuestionnaireQuestion.id)).where(
                QuestionnaireQuestion.questionnaire_id == questionnaire.id
            )
        )
    ).scalar_one()
    assert questions == 3

    await db_session.refresh(answer)
    assert answer.status == "approved"
    assert answer.approved_by == user_id
    assert answer.citations, "source citations survive archiving"


async def test_18_archived_leaves_the_active_list_and_appears_under_archived(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§5 and §7: the working set gets shorter, which is the point."""
    _, org_id = await _signup(client, "lc-list@example.com", "Lifecycle List")
    kept = await _questionnaire(db_session, org_id, title="Still working on this")
    put_away = await _questionnaire(db_session, org_id, title="Done with this")
    await db_session.commit()

    await client.post(f"/api/v1/compliance/questionnaires/{put_away.id}/archive")

    active = await client.get("/api/v1/compliance/questionnaires")
    assert [row["id"] for row in active.json()] == [str(kept.id)]

    archived = await client.get("/api/v1/compliance/questionnaires?archived=true")
    assert [row["id"] for row in archived.json()] == [str(put_away.id)]


async def test_18_the_list_says_which_rows_may_be_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§1: the menu is drawn from this, so it has to be right per row."""
    _, org_id = await _signup(client, "lc-menu@example.com", "Lifecycle Menu")
    await _questionnaire(db_session, org_id, title="A draft", questions=1)
    await _questionnaire(
        db_session, org_id, title="A used one", questions=1, answer_status="approved"
    )
    await db_session.commit()

    rows = {row["title"]: row for row in (await client.get(
        "/api/v1/compliance/questionnaires"
    )).json()}

    assert rows["A draft"]["can_delete"] is True
    assert rows["A draft"]["delete_blocked_reason"] is None
    assert rows["A used one"]["can_delete"] is False
    assert "Archive it instead" in rows["A used one"]["delete_blocked_reason"]


# --- §10 Review Center ------------------------------------------------


async def test_10_archiving_takes_the_questionnaire_out_of_review_work(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Somebody who archived a questionnaire is telling us they are not
    working on it. A review queue that keeps asking is arguing."""
    _, org_id = await _signup(client, "lc-rc@example.com", "Lifecycle Review Centre")
    questionnaire = await _questionnaire(
        db_session, org_id, questions=2, answer_status="needs_review"
    )
    await db_session.commit()

    before = await client.get("/api/v1/compliance/review-center")
    assert before.status_code == 200, before.text
    outstanding = {
        category["key"]: category["items"] for category in before.json()["categories"]
    }
    assert outstanding.get("questionnaire_answers"), "the fixture should raise items"

    await client.post(f"/api/v1/compliance/questionnaires/{questionnaire.id}/archive")

    after = await client.get("/api/v1/compliance/review-center")
    still = {
        category["key"]: category["items"] for category in after.json()["categories"]
    }
    assert not still.get("questionnaire_answers")


async def test_10_restoring_brings_the_review_work_straight_back(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nothing was deleted, so nothing has to be rebuilt."""
    _, org_id = await _signup(client, "lc-rc2@example.com", "Lifecycle Review Two")
    questionnaire = await _questionnaire(
        db_session, org_id, questions=2, answer_status="needs_review"
    )
    await db_session.commit()

    await client.post(f"/api/v1/compliance/questionnaires/{questionnaire.id}/archive")
    await client.post(f"/api/v1/compliance/questionnaires/{questionnaire.id}/restore")

    response = await client.get("/api/v1/compliance/review-center")
    items = {
        category["key"]: category["items"] for category in response.json()["categories"]
    }
    assert items.get("questionnaire_answers")


# --- §19 restore ------------------------------------------------------


async def test_19_restoring_returns_it_unchanged(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user_id, org_id = await _signup(client, "lc-restore@example.com", "Lifecycle Restore")
    questionnaire = await _questionnaire(
        db_session,
        org_id,
        status="in_progress",
        questions=2,
        answer_status="approved",
        approved_by=None,
    )
    await db_session.commit()

    await client.post(f"/api/v1/compliance/questionnaires/{questionnaire.id}/archive")
    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/restore"
    )

    assert response.status_code == 200, response.text
    assert response.json()["changed"] is True

    await db_session.refresh(questionnaire)
    assert questionnaire.archived_at is None
    assert questionnaire.archived_by is None
    assert questionnaire.status == "in_progress"

    # No duplicates anywhere.
    questionnaires = (
        await db_session.execute(
            select(func.count(Questionnaire.id)).where(
                Questionnaire.organization_id == org_id
            )
        )
    ).scalar_one()
    assert questionnaires == 1
    questions = (
        await db_session.execute(
            select(func.count(QuestionnaireQuestion.id)).where(
                QuestionnaireQuestion.questionnaire_id == questionnaire.id
            )
        )
    ).scalar_one()
    assert questions == 2
    assert user_id is not None


# --- §16 idempotency --------------------------------------------------


async def test_16_archiving_twice_records_one_event(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A retried request must not look like a second archiving."""
    _, org_id = await _signup(client, "lc-idem@example.com", "Lifecycle Idempotent")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    first = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/archive"
    )
    second = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/archive"
    )
    third = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/archive"
    )

    assert first.json()["changed"] is True
    assert second.json()["changed"] is False
    assert third.json()["changed"] is False
    # And the archived-at time did not move under the retries.
    assert second.json()["archived_at"] == first.json()["archived_at"]

    events = (
        await db_session.execute(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "compliance.questionnaire.archived",
            )
        )
    ).scalar_one()
    assert events == 1


async def test_16_deleting_twice_is_not_an_error(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A double click, a retry, or an id that never existed. None of
    those is something to show somebody an error about."""
    _, org_id = await _signup(client, "lc-idem2@example.com", "Lifecycle Idempotent Two")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    first = await client.delete(f"/api/v1/compliance/questionnaires/{questionnaire.id}")
    second = await client.delete(f"/api/v1/compliance/questionnaires/{questionnaire.id}")

    assert first.status_code == 200
    assert first.json()["deleted"] is True
    assert second.status_code == 200
    assert second.json()["deleted"] is False

    events = (
        await db_session.execute(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "compliance.questionnaire.deleted",
            )
        )
    ).scalar_one()
    assert events == 1, "the retry must not write a second tombstone"


async def test_16_restoring_something_active_changes_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "lc-idem3@example.com", "Lifecycle Idempotent Three")
    questionnaire = await _questionnaire(db_session, org_id)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/compliance/questionnaires/{questionnaire.id}/restore"
    )

    assert response.status_code == 200
    assert response.json()["changed"] is False
    events = (
        await db_session.execute(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action == "compliance.questionnaire.restored",
            )
        )
    ).scalar_one()
    assert events == 0


# --- §20 audits -------------------------------------------------------


async def test_20_an_empty_planned_audit_can_be_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "lc-audit@example.com", "Lifecycle Audit")
    audit = Audit(organization_id=org_id, title="Planned ISO audit", status="planned")
    db_session.add(audit)
    await db_session.commit()

    eligibility = await audit_eligibility(db_session, audit=audit)
    assert eligibility.can_delete

    response = await client.delete(f"/api/v1/compliance/audits/{audit.id}")
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True
    assert await db_session.get(Audit, audit.id) is None


async def test_20_an_audit_with_findings_cannot_be_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """An audit is the record of what an auditor saw."""
    _, org_id = await _signup(client, "lc-audit2@example.com", "Lifecycle Audit Two")
    audit = Audit(organization_id=org_id, title="ISO 27001", status="planned")
    db_session.add(audit)
    await db_session.flush()
    db_session.add(
        AuditFinding(
            organization_id=org_id,
            audit_id=audit.id,
            title="Key rotation not evidenced",
            severity="high",
            status="open",
        )
    )
    await db_session.commit()

    eligibility = await audit_eligibility(db_session, audit=audit)
    assert not eligibility.can_delete
    assert "finding" in eligibility.message

    response = await client.delete(f"/api/v1/compliance/audits/{audit.id}")
    assert response.status_code == 409
    assert await db_session.get(Audit, audit.id) is not None


async def test_20_a_started_audit_cannot_be_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "lc-audit3@example.com", "Lifecycle Audit Three")
    audit = Audit(organization_id=org_id, title="In flight", status="in_progress")
    db_session.add(audit)
    await db_session.commit()

    eligibility = await audit_eligibility(db_session, audit=audit)
    assert not eligibility.can_delete
    assert "already started" in eligibility.message


async def test_20_an_audit_with_findings_can_be_archived_and_keeps_them(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, org_id = await _signup(client, "lc-audit4@example.com", "Lifecycle Audit Four")
    audit = Audit(organization_id=org_id, title="Completed audit", status="completed")
    db_session.add(audit)
    await db_session.flush()
    db_session.add(
        AuditFinding(
            organization_id=org_id,
            audit_id=audit.id,
            title="Offboarding evidence missing",
            severity="medium",
            status="open",
        )
    )
    await db_session.commit()

    response = await client.post(f"/api/v1/compliance/audits/{audit.id}/archive")
    assert response.status_code == 200, response.text

    await db_session.refresh(audit)
    assert audit.archived_at is not None
    assert audit.status == "completed"
    findings = (
        await db_session.execute(
            select(func.count(AuditFinding.id)).where(AuditFinding.audit_id == audit.id)
        )
    ).scalar_one()
    assert findings == 1

    active = await client.get("/api/v1/compliance/audits")
    assert [row["id"] for row in active.json()] == []
    archived = await client.get("/api/v1/compliance/audits?archived=true")
    assert [row["id"] for row in archived.json()] == [str(audit.id)]
    assert archived.json()[0]["finding_count"] == 1
    assert archived.json()[0]["can_delete"] is False


# --- §13 permissions --------------------------------------------------


async def test_13_deleting_needs_more_than_permission_to_work_on_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Archive is day-to-day work; permanent deletion is not.

    A compliance manager can do everything with a questionnaire except
    destroy it — and since archiving is always available, withholding
    that takes nothing away they need.
    """
    from app.core.rbac import COMPLIANCE_PERMISSIONS, PERMISSIONS, ROLE_PERMISSION_GRANTS

    assert "compliance.questionnaires.delete" in PERMISSIONS
    assert "compliance.audits.delete" in PERMISSIONS
    assert "compliance.questionnaires.delete" not in COMPLIANCE_PERMISSIONS
    assert "compliance.audits.delete" not in COMPLIANCE_PERMISSIONS

    compliance_manager = ROLE_PERMISSION_GRANTS["compliance_manager"]
    assert "compliance.questionnaires.manage" in compliance_manager
    assert "compliance.questionnaires.delete" not in compliance_manager

    assert "compliance.questionnaires.delete" in ROLE_PERMISSION_GRANTS["org_admin"]


# --- tenancy ----------------------------------------------------------


async def test_another_organizations_questionnaire_is_not_reachable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, other_org = await _signup(client, "lc-them@example.com", "Lifecycle Them")
    theirs = await _questionnaire(db_session, other_org, title="Theirs")
    await db_session.commit()

    await _signup(client, "lc-mine@example.com", "Lifecycle Mine")

    archive = await client.post(f"/api/v1/compliance/questionnaires/{theirs.id}/archive")
    assert archive.status_code == 404

    deleted = await client.delete(f"/api/v1/compliance/questionnaires/{theirs.id}")
    # Reported as "nothing there", which is what it is from this
    # organization's point of view — and nothing was touched.
    assert deleted.json()["deleted"] is False
    assert await db_session.get(Questionnaire, theirs.id) is not None


# --- the trail reads as English ---------------------------------------


async def test_lifecycle_events_read_as_english_in_the_audit_trail(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from app.audit.presentation import build_views

    user_id, org_id = await _signup(client, "lc-trail@example.com", "Lifecycle Trail")
    questionnaire = await _questionnaire(db_session, org_id, title="Test Questionnaire")
    await db_session.commit()

    await client.post(f"/api/v1/compliance/questionnaires/{questionnaire.id}/archive")
    await client.post(f"/api/v1/compliance/questionnaires/{questionnaire.id}/restore")

    events = (
        await db_session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.organization_id == org_id,
                AuditEvent.action.like("compliance.questionnaire.%"),
            )
            .order_by(AuditEvent.created_at.asc())
        )
    ).scalars().all()

    views = await build_views(db_session, organization_id=org_id, events=list(events))
    titles = [view.title for view in views]

    assert "Questionnaire archived" in titles
    assert "Questionnaire restored" in titles
    for view in views:
        assert "compliance." not in view.title
        assert str(questionnaire.id) not in view.title
        # A person did this, so the trail must not credit the AI.
        assert view.actor_kind != "ai"
    assert user_id is not None


# --- §11 nothing is left pointing at a record that is gone -------------


async def test_11_deleting_leaves_no_task_or_notification_behind(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Nothing in the product creates a task or notification against a
    questionnaire today. This pins that, so the day something does, it
    fails here rather than leaving a customer with a notification that
    opens nothing.
    """
    from app.core.models import Notification, Task

    _, org_id = await _signup(client, "lc-orphan@example.com", "Lifecycle Orphan")
    questionnaire = await _questionnaire(db_session, org_id, questions=2)
    await db_session.commit()
    questionnaire_id = str(questionnaire.id)

    await client.delete(f"/api/v1/compliance/questionnaires/{questionnaire_id}")

    dangling_tasks = (
        await db_session.execute(
            select(func.count(Task.id)).where(
                Task.organization_id == org_id,
                Task.entity_type == "questionnaire",
                Task.entity_id == questionnaire_id,
            )
        )
    ).scalar_one()
    assert dangling_tasks == 0

    notifications = (
        await db_session.execute(
            select(func.count(Notification.id)).where(
                Notification.organization_id == org_id
            )
        )
    ).scalar_one()
    # Deleting a draft is housekeeping. Nobody needs telling about it in
    # their notification list; the audit trail is where it belongs.
    assert notifications == 0


async def test_11_archiving_an_audit_keeps_its_remediation_tasks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """§11 and §14: a remediation task outlives the engagement.

    Somebody still has to rotate the keys. Closing the task because the
    audit was tidied away would lose real outstanding work.
    """
    from app.core.models import Task

    user_id, org_id = await _signup(client, "lc-tasks@example.com", "Lifecycle Tasks")
    audit = Audit(organization_id=org_id, title="Annual audit", status="completed")
    db_session.add(audit)
    await db_session.flush()
    task = Task(
        organization_id=org_id,
        title="Rotate signing keys",
        status="open",
        entity_type="audit_finding",
        created_by=user_id,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(
        AuditFinding(
            organization_id=org_id,
            audit_id=audit.id,
            title="Key rotation not evidenced",
            severity="high",
            status="open",
            related_task_id=task.id,
        )
    )
    await db_session.commit()

    await client.post(f"/api/v1/compliance/audits/{audit.id}/archive")

    await db_session.refresh(task)
    assert task.status == "open", "remediation outlives the engagement that raised it"
