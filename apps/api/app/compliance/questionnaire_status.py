"""What state a questionnaire is actually in.

One calculation, in one place, derived from the answers themselves.

The bug this exists to end: `Questionnaire.status` was a column nothing
maintained. It was set to `draft` at creation and then only ever changed
by somebody pressing a button on the status screen. Meanwhile the detail
page computed its own progress from the answers and reported "Ready to
share". Two sources of truth for one idea, one of which never updated —
so a questionnaire with every answer approved sat in the list marked
`Draft` indefinitely, and both screens were telling the truth as they
understood it.

Deriving it fresh on every read would have been the other fix, and it is
worse: the status has to be queryable, sortable and reportable, and a
value nothing stores cannot be any of those. So it is stored, and this
module is the only thing that writes it.

Workflow status is not lifecycle state. `archived_at` says where a
record lives; this says how far the work got. An archived questionnaire
whose answers were all approved is `Archived · Ready to share`, and
archiving must never touch this column.

Readiness is more than the answers. A customer-provided questionnaire is
something we send back to a named customer as part of their security
review, so "ready to share" is a claim about the engagement as much as
about the answers. A questionnaire with every answer approved, no
customer recorded and no review to belong to is not ready to share with
anybody — there is nobody to share it with. That is `needs_setup`, and it
outranks everything the answers say, because no amount of approving
fixes it.

Internal assessments have no customer and need none. The rule only
applies where the word "share" means something.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import (
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
)

logger = logging.getLogger("agora.compliance.questionnaire_status")

# needs_setup   — it cannot be shared with anybody yet, whatever the
#                 answers say: nobody has recorded who it is for
# draft         — there is work nobody has done yet
# in_review     — Veyntra answered, and a person has to decide
# ready_to_share— every question has an answer somebody stood behind
# completed     — it actually went back to the customer
STATUSES = ("needs_setup", "draft", "in_review", "ready_to_share", "completed")

LABELS = {
    "needs_setup": "Needs setup",
    "draft": "Draft",
    "in_review": "In review",
    "ready_to_share": "Ready to share",
    "completed": "Completed",
}

# Answer states that mean somebody still has to do something. A rejected
# answer is outstanding work, not a decision that closes the question.
_UNFINISHED = ("unanswered", "draft", "rejected")

CUSTOMER_PROVIDED = "customer_provided"


@dataclass(frozen=True)
class Blocker:
    """One reason a questionnaire cannot be shared, and what to do.

    `code` is for the UI to key an action off; `message` is the sentence
    a person reads. Both come from here so the screen, the API refusal
    and the audit trail say the same thing in the same words.
    """

    code: str
    message: str


def blockers(
    *,
    source: str,
    customer_name: str | None,
    security_review_id: object | None,
    answer_statuses: list[str],
) -> list[Blocker]:
    """Everything standing between this questionnaire and being shared.

    In the order somebody has to deal with them: who it is for, then
    where it belongs, then the work itself. All of them are returned
    rather than just the first, because "fix this, now fix the next
    thing" is a worse way to find out what a record needs.
    """
    found: list[Blocker] = []

    if source == CUSTOMER_PROVIDED:
        if not (customer_name or "").strip():
            found.append(
                Blocker(
                    code="customer_required",
                    message=(
                        "Customer required before this questionnaire can be "
                        "shared."
                    ),
                )
            )
        elif security_review_id is None:
            # Only worth saying once the customer is known. Before that it
            # is a consequence of the missing customer, not a separate
            # thing for somebody to go and fix.
            found.append(
                Blocker(
                    code="review_required",
                    message=(
                        "This questionnaire is not part of a customer "
                        "security review yet."
                    ),
                )
            )

    outstanding = sum(1 for status in answer_statuses if status in _UNFINISHED)
    if not answer_statuses:
        found.append(
            Blocker(
                code="no_questions",
                message="This questionnaire has no questions yet.",
            )
        )
    elif outstanding:
        found.append(
            Blocker(
                code="unanswered_questions",
                message=(
                    f"{outstanding} question{'' if outstanding == 1 else 's'} "
                    f"still need{'s' if outstanding == 1 else ''} an answer."
                ),
            )
        )

    needs_review = sum(1 for status in answer_statuses if status == "needs_review")
    if needs_review:
        found.append(
            Blocker(
                code="needs_review",
                message=(
                    f"{needs_review} answer{'' if needs_review == 1 else 's'} "
                    f"need{'s' if needs_review == 1 else ''} a person to decide."
                ),
            )
        )

    return found


def setup_blockers(blocking: list[Blocker]) -> list[Blocker]:
    """The ones no amount of answering will clear."""
    return [b for b in blocking if b.code in ("customer_required", "review_required")]


@dataclass(frozen=True)
class StatusChange:
    """A transition worth recording, and why it happened."""

    before: str
    after: str
    reason: str


def derive(
    *,
    answer_statuses: list[str],
    current: str,
    source: str = "internal_template",
    customer_name: str | None = None,
    security_review_id: object | None = None,
) -> str:
    """The status the questionnaire is actually in.

    Pure, so the rule can be read and tested without a database.

    `needs_setup` comes first and beats everything, including `completed`.
    A customer questionnaire with no customer cannot have gone back to a
    customer, so a stored `completed` on one of those is a record of
    something that did not happen.

    `completed` is otherwise sticky against `ready_to_share` and nothing
    else. It means the questionnaire went back to the customer, which is
    further along than being ready to — but a new unanswered question
    makes it untrue, and then the derived state wins.
    """
    blocking = blockers(
        source=source,
        customer_name=customer_name,
        security_review_id=security_review_id,
        answer_statuses=answer_statuses,
    )

    if setup_blockers(blocking):
        return "needs_setup"

    if not answer_statuses:
        # Nothing to answer yet. A questionnaire with no questions is
        # being prepared, whatever else is true of it.
        return "draft"

    if any(status in _UNFINISHED for status in answer_statuses):
        return "draft"

    if any(status == "needs_review" for status in answer_statuses):
        return "in_review"

    # Everything left is approved. Ready to share is *not* the same as
    # having been shared, so a questionnaire that already went out stays
    # completed rather than sliding backwards.
    if current == "completed":
        return "completed"
    return "ready_to_share"


def explain(
    *,
    answer_statuses: list[str],
    after: str,
    blocking: list[Blocker] | None = None,
) -> str:
    """Why the status is what it is, for the audit trail.

    In the words somebody reading the trail would use, with the counts
    that produced the answer — "all 2 required answers were approved"
    tells a reader something a status name on its own does not.
    """
    total = len(answer_statuses)
    approved = sum(1 for status in answer_statuses if status == "approved")
    needs_review = sum(1 for status in answer_statuses if status == "needs_review")
    outstanding = sum(1 for status in answer_statuses if status in _UNFINISHED)

    if after == "needs_setup":
        setup = setup_blockers(blocking or [])
        return (
            setup[0].message
            if setup
            else "This questionnaire cannot be shared yet."
        )
    if after == "ready_to_share":
        return f"All {approved} answer{'' if approved == 1 else 's'} were approved."
    if after == "in_review":
        return (
            f"{needs_review} answer{'' if needs_review == 1 else 's'} "
            f"need{'s' if needs_review == 1 else ''} a person to decide."
        )
    if after == "completed":
        return "The questionnaire was shared with the customer."
    if not total:
        return "The questionnaire has no questions yet."
    return (
        f"{outstanding} of {total} question{'' if total == 1 else 's'} "
        "still needs an answer."
    )


async def _answer_statuses(
    db: AsyncSession, *, questionnaire_id: uuid.UUID
) -> list[str]:
    """One entry per question, so a question with no answer row counts.

    Left join rather than reading the answers table: a question nobody
    has answered is exactly the case that keeps a questionnaire in draft,
    and an inner join would hide it.
    """
    rows = (
        await db.execute(
            select(QuestionnaireAnswer.status)
            .select_from(QuestionnaireQuestion)
            .outerjoin(
                QuestionnaireAnswer,
                QuestionnaireAnswer.question_id == QuestionnaireQuestion.id,
            )
            .where(QuestionnaireQuestion.questionnaire_id == questionnaire_id)
        )
    ).all()
    return [row[0] or "unanswered" for row in rows]


async def recalculate(
    db: AsyncSession, *, questionnaire: Questionnaire
) -> StatusChange | None:
    """Bring the stored status in line with the answers. Returns the
    transition, or None when nothing moved.

    Idempotent by construction: it compares before writing, so running it
    three times over unchanged data writes once at most and records one
    event. Only real transitions reach the audit trail — a recalculation
    that confirms the status is a no-op, not news.

    Never touches `archived_at`. Lifecycle is a different dimension and
    a different column.
    """
    statuses = await _answer_statuses(db, questionnaire_id=questionnaire.id)
    before = questionnaire.status
    blocking = blockers(
        source=questionnaire.source,
        customer_name=questionnaire.customer_name,
        security_review_id=questionnaire.security_review_id,
        answer_statuses=statuses,
    )
    after = derive(
        answer_statuses=statuses,
        current=before,
        source=questionnaire.source,
        customer_name=questionnaire.customer_name,
        security_review_id=questionnaire.security_review_id,
    )

    if after == before:
        return None

    questionnaire.status = after
    reason = explain(answer_statuses=statuses, after=after, blocking=blocking)

    await record_event(
        db,
        organization_id=questionnaire.organization_id,
        # Nobody chose this; it follows from the answers. Attributing it
        # to whoever happened to approve the last one would put a
        # decision in their name that they did not make.
        actor_user_id=None,
        action="compliance.questionnaire.status_changed",
        object_type="questionnaire",
        object_id=str(questionnaire.id),
        before_state={"status": before},
        after_state={
            "status": after,
            "reason": reason,
            "title": questionnaire.title,
        },
    )
    await db.flush()

    logger.info(
        "Questionnaire %s: %s → %s (%s)", questionnaire.id, before, after, reason
    )
    return StatusChange(before=before, after=after, reason=reason)


async def recalculate_by_id(
    db: AsyncSession, *, organization_id: uuid.UUID, questionnaire_id: uuid.UUID
) -> StatusChange | None:
    """The same, for callers holding only an id."""
    questionnaire = await db.get(Questionnaire, questionnaire_id)
    if questionnaire is None or questionnaire.organization_id != organization_id:
        return None
    return await recalculate(db, questionnaire=questionnaire)


async def readiness_for(
    db: AsyncSession, *, questionnaire: Questionnaire
) -> list[Blocker]:
    """What is standing between this questionnaire and being shared.

    The same call the status derivation makes, exposed for the API to
    serialise and for the transition endpoint to refuse with. One rule,
    read three ways — the screen, the refusal and the stored status
    cannot disagree because there is nothing for them to disagree about.
    """
    return blockers(
        source=questionnaire.source,
        customer_name=questionnaire.customer_name,
        security_review_id=questionnaire.security_review_id,
        answer_statuses=await _answer_statuses(
            db, questionnaire_id=questionnaire.id
        ),
    )


__all__ = [
    "CUSTOMER_PROVIDED",
    "LABELS",
    "STATUSES",
    "Blocker",
    "StatusChange",
    "blockers",
    "derive",
    "explain",
    "readiness_for",
    "recalculate",
    "recalculate_by_id",
    "setup_blockers",
]
