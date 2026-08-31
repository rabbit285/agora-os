"""Deciding what may be deleted and what may only be archived.

A compliance product has to let people clean up their mistakes. A test
questionnaire made while learning the product, a duplicate created by a
double-click, an audit scheduled against the wrong framework — none of
those are history worth keeping, and a product that forces you to live
with them forever teaches you to stop trying things.

It also has to refuse. An answer somebody approved is that person
standing behind a claim made to a customer; findings raised in an audit
are the record of what an auditor saw. Those do not become deletable
because the record they hang off looks untidy in a list.

So the rule is drawn on *evidence of use*, never on a status field alone.
A questionnaire marked "draft" that somebody has already approved an
answer in is not a draft, whatever the column says — statuses drift, get
set by imports, and get changed by hand. What actually happened is in
the dependent rows.

Everything here is a pure read. It answers "may this be deleted, and if
not, why not" and nothing else; the acting on that answer lives in the
router, where the transaction is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    Audit,
    AuditFinding,
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    SecurityReview,
)

# Answer states that represent a person's decision rather than a draft.
# `rejected` counts: somebody read the answer and turned it down, and
# that judgement is as much a record as an approval.
DECIDED_ANSWER_STATUSES = ("approved", "rejected")


@dataclass
class Eligibility:
    """Whether a record may be permanently deleted, and why not.

    `reasons` is written for the person who clicked Delete, not for a
    log. "This has approved answers" tells them what to do next; a
    boolean does not.
    """

    can_delete: bool
    can_archive: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def message(self) -> str:
        """One sentence explaining the refusal."""
        if self.can_delete:
            return ""
        if not self.reasons:
            return (
                "This record has activity that has to be kept. Archive it instead."
            )
        return f"{' '.join(self.reasons)} Archive it instead."


async def questionnaire_eligibility(
    db: AsyncSession, *, questionnaire: Questionnaire
) -> Eligibility:
    """May this questionnaire be permanently deleted?

    Deletable only when nothing has happened to it that anybody would
    miss: no decided answers, no security review hanging off it, and not
    marked complete. Draft and AI-drafted answers do not block — they are
    the product's own working-out, not a person's decision.
    """
    # Being archived neither permits nor prevents deletion: it is a
    # different question. An archived draft is still a draft nobody used,
    # and an archived questionnaire full of approved answers is still
    # full of approved answers.
    reasons: list[str] = []

    if questionnaire.status == "completed":
        reasons.append("This questionnaire has been completed.")

    decided = (
        await db.execute(
            select(func.count(QuestionnaireAnswer.id))
            .join(
                QuestionnaireQuestion,
                QuestionnaireQuestion.id == QuestionnaireAnswer.question_id,
            )
            .where(
                QuestionnaireQuestion.questionnaire_id == questionnaire.id,
                QuestionnaireAnswer.status.in_(DECIDED_ANSWER_STATUSES),
            )
        )
    ).scalar_one()
    if decided:
        reasons.append(
            f"It has {decided} answer{'' if decided == 1 else 's'} somebody has decided on."
        )

    # Belt and braces: an answer carrying an approver is a decision
    # whatever its status column says. The two disagreeing is exactly the
    # kind of drift this function exists to be robust to.
    approved_by_someone = (
        await db.execute(
            select(func.count(QuestionnaireAnswer.id))
            .join(
                QuestionnaireQuestion,
                QuestionnaireQuestion.id == QuestionnaireAnswer.question_id,
            )
            .where(
                QuestionnaireQuestion.questionnaire_id == questionnaire.id,
                QuestionnaireAnswer.approved_by.is_not(None),
            )
        )
    ).scalar_one()
    if approved_by_someone and not decided:
        reasons.append("It has answers somebody approved.")

    review = (
        await db.execute(
            select(SecurityReview).where(
                SecurityReview.questionnaire_id == questionnaire.id
            )
        )
    ).scalars().first()
    if review is not None:
        # Not merely a policy: `SecurityReview.questionnaire_id` is a
        # non-null foreign key, so deleting this row would either fail at
        # the database or leave a review pointing at nothing.
        reasons.append("It is part of a customer security review.")
        if review.trust_package_file_id is not None:
            reasons.append("A trust package has already been shared from it.")

    return Eligibility(can_delete=not reasons, can_archive=True, reasons=reasons)


async def audit_eligibility(db: AsyncSession, *, audit: Audit) -> Eligibility:
    """May this audit be permanently deleted?

    Deletable while it is still just a plan: no findings, not started,
    not completed. Once an auditor has raised something, the audit is the
    record of what they saw.
    """
    reasons: list[str] = []

    if audit.status != "planned":
        reasons.append("This audit has already started.")
    if audit.completed_at is not None:
        reasons.append("It has been completed.")

    findings = (
        await db.execute(
            select(func.count(AuditFinding.id)).where(AuditFinding.audit_id == audit.id)
        )
    ).scalar_one()
    if findings:
        reasons.append(
            f"It has {findings} finding{'' if findings == 1 else 's'} recorded against it."
        )

    return Eligibility(can_delete=not reasons, can_archive=True, reasons=reasons)


__all__ = [
    "DECIDED_ANSWER_STATUSES",
    "Eligibility",
    "audit_eligibility",
    "questionnaire_eligibility",
]
