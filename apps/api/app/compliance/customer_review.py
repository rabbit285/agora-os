"""The customer engagement a questionnaire belongs to.

A customer sends a security questionnaire. Then a privacy one. Then, if
they are buying AI, an AI governance one. That is one conversation with
one customer, and answering it is one piece of work — so the review is
the engagement and the questionnaires are what it contains.

The user should never have to build that relationship by hand. A
questionnaire marked customer-provided *is* part of an engagement by
definition; asking somebody to then go and create the engagement
separately is asking them to do bookkeeping the product already has the
information for.

Two things live here:

- **Linking.** Creating or finding the review a customer-provided
  questionnaire belongs to, without ever creating a second one for the
  same customer.
- **Rolling up.** A review's status and progress are its questionnaires'
  status and progress, aggregated. One calculation, so the review card,
  the review page and the questionnaire's own badge cannot disagree —
  the same mistake that let a questionnaire read "Ready to share" while
  its stored status said "Draft".

The customer is a name. This product has no account model and is not
getting the withdrawn CRM back, so `customer_name` is the identity, and
matching is case-folded because "Acme Corp" and "acme corp" are one
customer.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import (
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    SecurityReview,
)

logger = logging.getLogger("agora.compliance.customer_review")


def _now() -> datetime:
    return datetime.now(UTC)

# draft          — no questions to answer yet
# in_progress    — questions exist and work is outstanding
# needs_review   — Veyntra answered and a person has to decide
# ready_to_share — every question in every questionnaire is approved
# completed      — it actually went back to the customer
STATUSES = ("draft", "in_progress", "needs_review", "ready_to_share", "completed")

LABELS = {
    "draft": "Draft",
    "in_progress": "In progress",
    "needs_review": "Needs review",
    "ready_to_share": "Ready to share",
    "completed": "Completed",
}

# Statuses the old sales-coupled reviews used. Kept so those rows still
# render rather than falling through to a raw string on screen.
_LEGACY_LABELS = {"blocked": "Blocked", "cleared": "Completed"}


def label_for(status: str) -> str:
    return LABELS.get(status) or _LEGACY_LABELS.get(status) or status.replace("_", " ")


def review_title_for(customer_name: str) -> str:
    """What to call a review nobody named.

    "Agora Origin Security Review" rather than the questionnaire's own
    title, because the engagement outlives any one questionnaire in it.
    """
    return f"{customer_name.strip()} Security Review"


@dataclass
class ReviewProgress:
    """A review's work, added up across its questionnaires."""

    questionnaires: int = 0
    total: int = 0
    approved: int = 0
    needs_review: int = 0
    draft: int = 0
    unanswered: int = 0
    # Questionnaires in this review that have no questions in them. They
    # contribute nothing to the counts above, which is exactly the
    # problem: without this, a review holding one finished questionnaire
    # and one empty one adds up to "everything approved" and calls itself
    # ready, when half of it has not been started.
    empty: int = 0

    @property
    def percent_complete(self) -> int:
        """Approved answers only.

        A drafted answer nobody has read is not progress towards sending
        the questionnaire back, and counting it would tell a customer
        they are nearly done when nobody has checked anything.
        """
        return round(100 * self.approved / self.total) if self.total else 0

    @property
    def ready(self) -> bool:
        """Every questionnaire in the engagement is ready, not just the sum.

        A review is a package that goes to a customer whole. One
        questionnaire in it that nobody has put questions into is enough
        to make the package not ready, however well the rest adds up.
        """
        return self.total > 0 and self.approved == self.total and not self.empty


async def progress_for(
    db: AsyncSession,
    *,
    review_id: uuid.UUID,
    include_archived: bool = False,
) -> ReviewProgress:
    """Add up every question in every questionnaire on this review.

    One question with no answer row counts as unanswered — the left join
    is what makes a review with an empty questionnaire report honestly
    rather than looking finished.

    What "on this review" means depends on whether there is any live
    work in it, and the rule is one sentence: **count the live
    questionnaires, and if there are none, count all of them.**

    Both halves matter. An engagement with two questionnaires, one filed
    away, is judged on the one still open — an archived questionnaire is
    not outstanding work. An engagement where everything is filed away is
    judged on what it held, because the alternative is a finished review
    reporting "1 questionnaire, 0 of 0 approved" and calling itself a
    draft: its history erased at exactly the moment it became history.

    Deriving that from the questionnaires rather than from the review's
    own `archived_at` is what keeps the numbers still when somebody
    reopens a finished engagement. Keyed to the review's flag, restoring
    it flipped a completed review to "Draft, 0 of 0" and archiving it
    flipped it back — the same three approved answers, described two
    different ways depending on which tab it was sitting under.

    `include_archived` forces the second reading, for a caller that wants
    the whole history of an engagement that still has live work in it.
    """
    # Everything in the engagement, live or filed away, in one query:
    # which rows to count is decided below rather than in the WHERE
    # clause, because that decision depends on what came back.
    #
    # The question id comes back too, so "this questionnaire has no
    # questions" is distinguishable from "this question has no answer".
    # Both arrive as a null answer status, and counting them the same way
    # would make an empty questionnaire look like outstanding work.
    rows = (
        await db.execute(
            select(
                Questionnaire.id,
                Questionnaire.archived_at,
                QuestionnaireQuestion.id,
                QuestionnaireAnswer.status,
            )
            .select_from(Questionnaire)
            .outerjoin(
                QuestionnaireQuestion,
                QuestionnaireQuestion.questionnaire_id == Questionnaire.id,
            )
            .outerjoin(
                QuestionnaireAnswer,
                QuestionnaireAnswer.question_id == QuestionnaireQuestion.id,
            )
            .where(Questionnaire.security_review_id == review_id)
        )
    ).all()

    has_live = any(archived_at is None for _, archived_at, _, _ in rows)
    counting_live_only = has_live and not include_archived

    progress = ReviewProgress()
    seen: set[uuid.UUID] = set()
    seen_questions: set[uuid.UUID] = set()
    for questionnaire_id, archived_at, question_id, answer_status in rows:
        if counting_live_only and archived_at is not None:
            continue
        seen.add(questionnaire_id)
        if question_id is None:
            continue
        progress.total += 1
        seen_questions.add(questionnaire_id)
        # A question with no answer row is unanswered, the same as one
        # whose answer says so.
        match answer_status or "unanswered":
            case "approved":
                progress.approved += 1
            case "needs_review":
                progress.needs_review += 1
            case "draft":
                progress.draft += 1
            case _:
                progress.unanswered += 1

    progress.questionnaires = len(seen)
    progress.empty = len(seen - seen_questions)
    return progress


def derive_status(progress: ReviewProgress, *, current: str) -> str:
    """The status the questionnaires imply.

    Pure, so the rule reads without a database.

    `completed` is sticky against `ready_to_share` only: it means the
    package went back to the customer, which is further along than being
    ready to. A new unanswered question makes that untrue and the derived
    state wins. `cleared` is the old vocabulary for the same thing.
    """
    if current in ("completed", "cleared") and progress.ready:
        return current

    if not progress.questionnaires or not progress.total:
        return "draft"
    if progress.needs_review:
        return "needs_review"
    if progress.ready:
        return "ready_to_share"
    return "in_progress"


async def recalculate(
    db: AsyncSession, *, review: SecurityReview
) -> tuple[str, str] | None:
    """Bring a review's status in line with its questionnaires.

    Returns `(before, after)` on a real transition, None otherwise —
    so a retried recalculation writes nothing and records nothing.
    """
    progress = await progress_for(db, review_id=review.id)
    before = review.status
    after = derive_status(progress, current=before)
    if after == before:
        return None

    review.status = after
    await record_event(
        db,
        organization_id=review.organization_id,
        # Derived from the questionnaires, not chosen by anybody.
        actor_user_id=None,
        action="compliance.security_review.status_changed",
        object_type="security_review",
        object_id=str(review.id),
        before_state={"status": before},
        after_state={
            "status": after,
            "title": review.title or "Customer security review",
            "reason": (
                f"{progress.approved} of {progress.total} answers approved across "
                f"{progress.questionnaires} questionnaire"
                f"{'' if progress.questionnaires == 1 else 's'}."
            ),
        },
    )
    await db.flush()
    return (before, after)


async def find_active_for_customer(
    db: AsyncSession, *, organization_id: uuid.UUID, customer_name: str
) -> SecurityReview | None:
    """The customer's open engagement, if there is exactly one.

    Case-folded: "Acme Corp" and "acme corp" are one customer. Archived
    reviews do not count — a closed engagement is not the one a new
    questionnaire belongs to.
    """
    name = (customer_name or "").strip()
    if not name:
        return None
    return (
        await db.execute(
            select(SecurityReview).where(
                SecurityReview.organization_id == organization_id,
                func.lower(SecurityReview.customer_name) == name.lower(),
                SecurityReview.archived_at.is_(None),
            )
        )
    ).scalars().first()


async def link_questionnaire(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    questionnaire: Questionnaire,
    actor_user_id: uuid.UUID | None,
) -> SecurityReview | None:
    """Put a customer questionnaire into its customer's engagement.

    Only for `customer_provided` questionnaires that name a customer. An
    internal assessment is nobody's engagement but our own, and a
    customer questionnaire with no customer named is not something to
    guess about — inventing "Untitled Customer Security Review" would put
    a customer in the record who does not exist.

    Idempotent three ways: a questionnaire already linked keeps its
    review, a customer with an open review joins it rather than getting a
    second, and a concurrent create loses to the unique index and reads
    the winner back.
    """
    if questionnaire.security_review_id is not None:
        return await db.get(SecurityReview, questionnaire.security_review_id)
    if questionnaire.source != "customer_provided":
        return None
    customer = (questionnaire.customer_name or "").strip()
    if not customer:
        return None

    existing = await find_active_for_customer(
        db, organization_id=organization_id, customer_name=customer
    )
    if existing is not None:
        questionnaire.security_review_id = existing.id
        await _record_link(
            db,
            organization_id=organization_id,
            review=existing,
            questionnaire=questionnaire,
            actor_user_id=actor_user_id,
            created=False,
        )
        await recalculate(db, review=existing)
        return existing

    review = SecurityReview(
        organization_id=organization_id,
        title=review_title_for(customer),
        customer_name=customer,
        status="draft",
        is_deal_blocker=False,
    )
    db.add(review)
    try:
        # Inside a savepoint: losing the race to another request must not
        # discard the caller's transaction, only this insert.
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        # Somebody created this customer's review between the read above
        # and here. Theirs is the review; there is no second engagement.
        winner = await find_active_for_customer(
            db, organization_id=organization_id, customer_name=customer
        )
        if winner is None:  # pragma: no cover - the index guarantees one
            raise
        questionnaire.security_review_id = winner.id
        await db.flush()
        return winner

    questionnaire.security_review_id = review.id
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.security_review.created",
        object_type="security_review",
        object_id=str(review.id),
        after_state={"title": review.title, "customer": customer},
    )
    await _record_link(
        db,
        organization_id=organization_id,
        review=review,
        questionnaire=questionnaire,
        actor_user_id=actor_user_id,
        created=True,
    )
    await recalculate(db, review=review)
    logger.info("Linked questionnaire %s to review %s", questionnaire.id, review.id)
    return review


async def _record_link(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    review: SecurityReview,
    questionnaire: Questionnaire,
    actor_user_id: uuid.UUID | None,
    created: bool,
) -> None:
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.security_review.questionnaire_linked",
        object_type="security_review",
        object_id=str(review.id),
        after_state={
            "questionnaire": questionnaire.title,
            "review": review.title or "Customer security review",
            "review_created": created,
        },
    )


async def _questionnaire_lifecycle(
    db: AsyncSession, *, review_id: uuid.UUID
) -> tuple[int, int]:
    """How many questionnaires this review holds, and how many are live."""
    rows = (
        await db.execute(
            select(Questionnaire.archived_at).where(
                Questionnaire.security_review_id == review_id
            )
        )
    ).scalars().all()
    return len(rows), sum(1 for archived_at in rows if archived_at is None)


async def sync_lifecycle(
    db: AsyncSession, *, review: SecurityReview
) -> str | None:
    """Follow the review's questionnaires into and out of the archive.

    An engagement is where its work is. When the last live questionnaire
    is archived there is nothing open about the engagement any more, and
    when one comes back there is. Doing that automatically is what keeps
    the Archived tab from disagreeing with the questionnaires under it.

    It defers to people, in both directions. A review a person archived
    carries their id in `archived_by`, and restoring a questionnaire does
    not overturn that decision — the questionnaire comes back inside a
    review somebody deliberately closed, which is a state the screen can
    show and this function has no business rewriting.

    Returns "archived", "restored", or None when nothing changed, so a
    repeated call writes nothing.
    """
    held, live = await _questionnaire_lifecycle(db, review_id=review.id)
    if not held:
        # An engagement with nothing in it yet is not evidence of
        # anything. Leave it where its owner put it.
        return None

    if live == 0 and review.archived_at is None:
        review.archived_at = _now()
        review.archived_by = None  # derived, not decided
        await _record_lifecycle(db, review=review, action="archived", derived=True)
        await recalculate(db, review=review)
        await db.flush()
        return "archived"

    if live > 0 and review.archived_at is not None:
        if review.archived_by is not None:
            # Somebody closed this engagement on purpose.
            return None
        if await find_active_for_customer(
            db,
            organization_id=review.organization_id,
            customer_name=review.customer_name or "",
        ):
            # The customer opened a new engagement after this one closed.
            # Two open reviews for one customer is what the unique index
            # exists to prevent; this one stays closed.
            return None
        review.archived_at = None
        review.archived_by = None
        await _record_lifecycle(db, review=review, action="restored", derived=True)
        await recalculate(db, review=review)
        await db.flush()
        return "restored"

    return None


async def set_lifecycle(
    db: AsyncSession,
    *,
    review: SecurityReview,
    archived: bool,
    actor_user_id: uuid.UUID | None,
) -> bool:
    """A person archiving or restoring the engagement itself.

    The questionnaires inside keep their own lifecycle and their link
    either way. Closing an engagement is a statement about a conversation
    with a customer, not an instruction to go and bury three
    questionnaires and every answer in them.
    """
    if archived == (review.archived_at is not None):
        return False
    if archived:
        review.archived_at = _now()
        review.archived_by = actor_user_id
    else:
        review.archived_at = None
        review.archived_by = None
    await _record_lifecycle(
        db,
        review=review,
        action="archived" if archived else "restored",
        derived=False,
        actor_user_id=actor_user_id,
    )
    await recalculate(db, review=review)
    await db.flush()
    return True


async def _record_lifecycle(
    db: AsyncSession,
    *,
    review: SecurityReview,
    action: str,
    derived: bool,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    detail = {
        "title": review.title or "Customer security review",
        "customer": review.customer_name,
        "derived": derived,
    }
    if derived:
        detail["reason"] = (
            "Every questionnaire in this review is archived."
            if action == "archived"
            else "A questionnaire in this review was restored."
        )
    await record_event(
        db,
        organization_id=review.organization_id,
        actor_user_id=actor_user_id,
        action=f"compliance.security_review.{action}",
        object_type="security_review",
        object_id=str(review.id),
        after_state=detail,
    )


__all__ = [
    "LABELS",
    "STATUSES",
    "ReviewProgress",
    "derive_status",
    "find_active_for_customer",
    "label_for",
    "link_questionnaire",
    "progress_for",
    "recalculate",
    "review_title_for",
    "set_lifecycle",
    "sync_lifecycle",
]
