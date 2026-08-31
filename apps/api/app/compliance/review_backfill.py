"""Giving existing customer questionnaires the engagement they belong to.

Customer-provided questionnaires exist that predate the link — most
visibly the one sitting at 100% approved, ready to share, beside an
Assessments page reporting "No customer security reviews". Nothing was
wrong with those records; there was simply no review for them to point
at, because `SecurityReview` required a Sales opportunity and that module
was withdrawn.

Those rows also carry no `customer_name`, because the column did not
exist when they were made. So the interesting question here is not how to
link a questionnaire to its customer's review — that is one call — but
what to do about a questionnaire whose customer nobody ever recorded.

The answer is in three parts:

- **A stored customer name is a fact.** Link it, no questions asked.
- **A name read off the title is a suggestion.** It is reported, with the
  reasoning attached, and it links only when a caller says in so many
  words that they accept the suggestions. Otherwise a typo in a title
  becomes a customer in an audit trail on the strength of a string match.
- **No name and no suggestion is a question for a person.** The record
  comes back in `needs_customer` so the screen can ask, instead of the
  product deciding.

Archived questionnaires are backfilled like any other. They are the ones
most likely to need it — the engagement they belonged to is exactly the
history somebody will want to read later — and skipping them would leave
the Archived tab empty while archived questionnaires sat under it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.customer_identity import suggest_customer_name
from app.compliance.customer_review import (
    link_questionnaire,
    sync_lifecycle,
)
from app.compliance.models import Questionnaire, SecurityReview

logger = logging.getLogger("agora.compliance.review_backfill")


@dataclass
class NeedsCustomer:
    """A questionnaire the pass would not name a customer for on its own."""

    questionnaire_id: uuid.UUID
    title: str
    archived: bool
    suggested_customer: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "questionnaire_id": str(self.questionnaire_id),
            "title": self.title,
            "archived": self.archived,
            "suggested_customer": self.suggested_customer,
            "reason": self.reason,
        }


@dataclass
class BackfillReport:
    """What the pass linked, and what it would not decide on its own."""

    examined: int = 0
    linked: int = 0
    reviews_created: int = 0
    reviews_archived: int = 0
    already_linked: int = 0
    # Linked because a caller accepted a name read off the title. Counted
    # apart from `linked` so the two kinds of evidence never blur.
    linked_from_title: int = 0
    needs_customer: list[NeedsCustomer] = field(default_factory=list)

    @property
    def unnamed(self) -> int:
        return len(self.needs_customer)

    @property
    def suggested(self) -> int:
        return sum(1 for row in self.needs_customer if row.suggested_customer)

    def as_dict(self) -> dict[str, object]:
        return {
            "examined": self.examined,
            "linked": self.linked,
            "linked_from_title": self.linked_from_title,
            "reviews_created": self.reviews_created,
            "reviews_archived": self.reviews_archived,
            "already_linked": self.already_linked,
            "unnamed": self.unnamed,
            "suggested": self.suggested,
            "needs_customer": [row.as_dict() for row in self.needs_customer],
        }


async def backfill_customer_reviews(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    dry_run: bool = True,
    confirm_suggested_customers: bool = False,
) -> BackfillReport:
    """Link customer questionnaires to their engagements.

    `dry_run` defaults to true: the first thing anybody should do with a
    pass that creates records across a customer's compliance data is read
    what it would create.

    `confirm_suggested_customers` is the caller saying they have read the
    suggestions and accept them. It is deliberately not the default and
    deliberately not implied by `dry_run=False`, because "link the
    records whose customer we know" and "and also trust what the titles
    say" are different decisions and only one of them can be wrong.

    Idempotent. A questionnaire already linked is counted and skipped;
    two questionnaires for one customer join one review rather than
    making two; and a second run of an accepted pass finds nothing left
    to do.
    """
    report = BackfillReport()

    # The engagements that already existed, so "created" counts the ones
    # this pass actually made rather than every one it linked to.
    before_ids = set(
        (
            await db.execute(
                select(SecurityReview.id).where(
                    SecurityReview.organization_id == organization_id
                )
            )
        )
        .scalars()
        .all()
    )

    candidates = list(
        (
            await db.execute(
                select(Questionnaire)
                .where(
                    Questionnaire.organization_id == organization_id,
                    Questionnaire.source == "customer_provided",
                )
                .order_by(Questionnaire.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    touched: set[uuid.UUID] = set()

    for questionnaire in candidates:
        report.examined += 1

        if questionnaire.security_review_id is not None:
            report.already_linked += 1
            touched.add(questionnaire.security_review_id)
            continue

        stored = (questionnaire.customer_name or "").strip()
        from_title = False

        if not stored:
            suggestion = suggest_customer_name(questionnaire.title)
            if suggestion is None or not confirm_suggested_customers:
                report.needs_customer.append(
                    NeedsCustomer(
                        questionnaire_id=questionnaire.id,
                        title=questionnaire.title,
                        archived=questionnaire.archived_at is not None,
                        suggested_customer=(
                            suggestion.name if suggestion else None
                        ),
                        reason=suggestion.reason if suggestion else None,
                    )
                )
                continue
            stored = suggestion.name
            from_title = True

        if dry_run:
            report.linked += 1
            if from_title:
                report.linked_from_title += 1
            continue

        if from_title:
            # Written down as the questionnaire's customer, not held in a
            # variable: the next screen that reads this record has to see
            # the same customer this pass linked it to.
            questionnaire.customer_name = stored

        before = questionnaire.security_review_id
        review = await link_questionnaire(
            db,
            organization_id=organization_id,
            questionnaire=questionnaire,
            actor_user_id=actor_user_id,
        )
        if review is None or questionnaire.security_review_id == before:
            continue

        report.linked += 1
        if from_title:
            report.linked_from_title += 1
        touched.add(review.id)
        if review.id not in before_ids:
            report.reviews_created += 1
            before_ids.add(review.id)

    # Lifecycle last, and only once every link exists. Doing it inside the
    # loop would archive a review the moment its first archived
    # questionnaire joined, and the customer's next questionnaire would
    # then find no open engagement and start a second one.
    if not dry_run:
        for review_id in touched:
            review = await db.get(SecurityReview, review_id)
            if review is None:  # pragma: no cover - just linked to it
                continue
            if await sync_lifecycle(db, review=review) == "archived":
                report.reviews_archived += 1
        await db.flush()

    logger.info(
        "Customer review backfill for %s: linked=%d created=%d needs_customer=%d",
        organization_id,
        report.linked,
        report.reviews_created,
        report.unnamed,
    )
    return report


__all__ = ["BackfillReport", "NeedsCustomer", "backfill_customer_reviews"]
