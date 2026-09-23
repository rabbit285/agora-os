"""One queue for everything waiting on a person.

The product's argument is that AI does the repetitive compliance work and
the human handles exceptions. That only holds if the exceptions are in
one place. Spread across six screens, "5 things need you" becomes "go and
look everywhere, repeatedly" — which is the job the customer was trying
to stop doing.

**Only real decisions appear here.** Every item is something a person can
act on now, backed by a row that exists. Nothing is listed because it
might matter later, and nothing is invented to make the queue look busy —
an empty Review Center is a good outcome and has to be able to say so.

**The counts are honest about what was automatic.** Reporting "41
accepted automatically" alongside "5 need your review" is only meaningful
if the first number is real work the customer did not have to do. Both
come from the same `EvidenceSuggestion` rows, counted by status.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    AISystem,
    ComplianceGap,
    Control,
    EvidenceSuggestion,
    Framework,
    FrameworkActivation,
    Risk,
)
from app.core.models import Approval, Task

# How far back "recent AI activity" looks. Long enough that a customer
# returning after a week still sees what happened while they were away.
ACTIVITY_WINDOW = timedelta(days=7)


@dataclass
class ReviewItem:
    """One thing a person has to decide.

    `href` points at the screen where the decision is actually made. A
    queue that lists work without taking you to it just relocates the
    searching.

    The fields below `href` carry what makes a decision possible to make
    rather than merely visible: what Veyntra recommends where it has
    grounds to recommend anything, the facts it read, and what changes
    if the reviewer agrees. They are optional because most categories
    here are "somebody must look at this", not "here is a proposed
    answer" — and a recommendation invented to fill a field is worse
    than an empty one.
    """

    id: str
    title: str
    detail: str
    # high | medium | low
    priority: str
    href: str
    recommendation: str | None = None
    recommendation_reason: str | None = None
    # Named facts with how directly each was established. Never a
    # model's confidence in a legal conclusion — that is not a
    # measurement of anything.
    evidence: list[dict] = field(default_factory=list)
    impact: str | None = None


@dataclass
class ReviewCategory:
    key: str
    label: str
    description: str
    items: list[ReviewItem] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass
class ReviewCenter:
    categories: list[ReviewCategory]
    total_needing_review: int
    # What the AI did without asking, in the same window. Shown beside the
    # review count so the customer can see the ratio they are buying.
    auto_accepted_recently: int
    proposals_recently: int


def _priority_for_gap(severity: str) -> str:
    return {"high": "high", "medium": "medium"}.get(severity, "low")


async def _evidence_mappings(
    db: AsyncSession, organization_id: uuid.UUID
) -> ReviewCategory:
    category = ReviewCategory(
        key="evidence_mappings",
        label="Evidence mappings",
        description=(
            "AI proposed these as evidence. Check the quoted passage against the document, "
            "then approve or reject."
        ),
    )
    rows = list(
        (
            await db.execute(
                select(EvidenceSuggestion, Control)
                .join(Control, Control.id == EvidenceSuggestion.control_id)
                .where(
                    EvidenceSuggestion.organization_id == organization_id,
                    EvidenceSuggestion.status.in_(("proposed", "unverifiable")),
                )
                .order_by(EvidenceSuggestion.created_at.desc())
            )
        ).all()
    )
    for suggestion, control in rows:
        unverifiable = suggestion.status == "unverifiable"
        category.items.append(
            ReviewItem(
                id=str(suggestion.id),
                title=control.title,
                detail=(
                    "The quoted passage was not found in the document, so this cannot be "
                    "approved — dismiss it, or attach the document by hand if it is relevant."
                    if unverifiable
                    else (suggestion.routing_reason or "Waiting on your decision.")
                ),
                priority="medium" if unverifiable else "high",
                href="/compliance#controls",
            )
        )
    return category


async def _questionnaire_answers(
    db: AsyncSession, organization_id: uuid.UUID
) -> ReviewCategory:
    """Answers Veyntra drafted that it could not stand behind.

    A questionnaire goes back to a customer over the organization's name,
    so an answer the product is unsure of is exactly the kind of decision
    the Review Center exists to surface. The reason travels with it —
    "needs review" without saying what is missing just moves the guessing
    somewhere else.
    """
    from app.compliance.models import Questionnaire, QuestionnaireAnswer, QuestionnaireQuestion

    category = ReviewCategory(
        key="questionnaire_answers",
        label="Questionnaire answers",
        description=(
            "Veyntra drafted these answers but could not confirm them. They go to a "
            "customer over your name, so a person decides."
        ),
    )
    rows = list(
        (
            await db.execute(
                select(QuestionnaireAnswer, QuestionnaireQuestion, Questionnaire)
                .join(
                    QuestionnaireQuestion,
                    QuestionnaireQuestion.id == QuestionnaireAnswer.question_id,
                )
                .join(
                    Questionnaire,
                    Questionnaire.id == QuestionnaireQuestion.questionnaire_id,
                )
                .where(
                    QuestionnaireAnswer.organization_id == organization_id,
                    QuestionnaireAnswer.status == "needs_review",
                    # Archived work is not outstanding work. Somebody who
                    # put a questionnaire away is telling us they are not
                    # working on it, and a review queue that keeps asking
                    # about it is arguing with them. The answers are
                    # untouched — restoring brings the item straight back.
                    Questionnaire.archived_at.is_(None),
                )
                .order_by(QuestionnaireAnswer.updated_at.desc())
            )
        ).all()
    )
    for answer, question, questionnaire in rows:
        confidence = (
            f" Confidence {round(answer.confidence * 100)}%."
            if answer.confidence is not None
            else ""
        )
        category.items.append(
            ReviewItem(
                id=str(answer.id),
                title=question.text[:200],
                detail=(
                    f"{questionnaire.title}. "
                    f"{answer.review_reason or 'Waiting on your decision.'}"
                    f"{confidence}"
                ),
                priority="high",
                href=f"/compliance/questionnaires/{questionnaire.id}",
            )
        )
    return category


async def _framework_applicability(
    db: AsyncSession, organization_id: uuid.UUID, *, recommended_keys: list[str]
) -> ReviewCategory:
    """Frameworks the rules say are in scope that nobody has adopted.

    Takes the recommendation keys as an argument rather than recomputing
    them: applicability is decided in one place, and a second copy of that
    logic here would eventually disagree with the first.
    """
    category = ReviewCategory(
        key="framework_applicability",
        label="Framework applicability",
        description="These look like they apply to you, based on what you told us about the company.",
    )
    if not recommended_keys:
        return category

    active = set(
        (
            await db.execute(
                select(Framework.key)
                .join(FrameworkActivation, FrameworkActivation.framework_id == Framework.id)
                .where(
                    FrameworkActivation.organization_id == organization_id,
                    FrameworkActivation.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    pending = [key for key in recommended_keys if key not in active]
    if not pending:
        return category

    frameworks = list(
        (
            await db.execute(
                select(Framework).where(
                    Framework.key.in_(pending), Framework.organization_id.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )
    for framework in frameworks:
        category.items.append(
            ReviewItem(
                id=str(framework.id),
                title=f"Adopt {framework.name}?",
                detail=(
                    "Indicated by the facts you declared, and not yet adopted. Adopting it "
                    "builds its control set so your documents can map to it."
                ),
                priority="medium",
                href="/compliance",
            )
        )
    return category


async def _ai_risk_classifications(
    db: AsyncSession, organization_id: uuid.UUID
) -> ReviewCategory:
    category = ReviewCategory(
        key="ai_classifications",
        label="AI risk classifications",
        description=(
            "An AI system's risk tier decides which obligations apply to it. These have not "
            "been established from how the system is actually used."
        ),
    )
    systems = list(
        (
            await db.execute(
                select(AISystem).where(AISystem.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    for system in systems:
        screened = await db.scalar(
            select(func.count())
            .select_from(Risk)
            .where(Risk.ai_system_id == system.id)
        )
        # Screening is recorded as an AIAssessment; a system with none has
        # a classification nobody has justified.
        from app.compliance.models import AIAssessment

        has_screening = bool(
            await db.scalar(
                select(func.count(AIAssessment.id)).where(
                    AIAssessment.ai_system_id == system.id,
                    AIAssessment.assessment_type == "eu_ai_act_screening",
                )
            )
        )
        if has_screening:
            continue
        category.items.append(
            ReviewItem(
                id=str(system.id),
                title=f"Screen {system.name}",
                detail=(
                    f"Currently recorded as {system.risk_classification} risk, but no screening "
                    "is on file to support that."
                    + (f" {screened} linked risk(s)." if screened else "")
                ),
                priority=(
                    "high"
                    if system.deployment_status in ("pilot", "production")
                    else "medium"
                ),
                href=f"/compliance/ai-systems/{system.id}",
            )
        )
    return category


async def _stale_assessments(db: AsyncSession, organization_id: uuid.UUID) -> ReviewCategory:
    category = ReviewCategory(
        key="control_assessments",
        label="Control assessments",
        description="Evidence changed after these were last assessed, so their conclusion is out of date.",
    )
    controls = list(
        (
            await db.execute(
                select(Control).where(
                    Control.organization_id == organization_id,
                    Control.needs_reassessment.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    for control in controls:
        category.items.append(
            ReviewItem(
                id=str(control.id),
                title=control.title,
                detail="New evidence was approved after the last assessment. Re-run it to bring the position up to date.",
                priority="medium",
                href=f"/compliance/controls/{control.id}",
            )
        )
    return category


async def _risk_acceptance(db: AsyncSession, organization_id: uuid.UUID) -> ReviewCategory:
    category = ReviewCategory(
        key="risk_acceptance",
        label="Risk acceptance",
        description="Open risks with no mitigation recorded. Someone has to accept, mitigate or transfer each one.",
    )
    risks = list(
        (
            await db.execute(
                select(Risk).where(
                    Risk.organization_id == organization_id,
                    Risk.status == "open",
                    Risk.residual_likelihood.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for risk in risks:
        high = risk.likelihood == "high" or risk.impact == "high"
        category.items.append(
            ReviewItem(
                id=str(risk.id),
                title=risk.title,
                detail=(
                    f"Inherent {risk.likelihood} likelihood / {risk.impact} impact, with no "
                    "residual rating recorded yet."
                ),
                priority="high" if high else "medium",
                href="/compliance#controls",
            )
        )
    return category


async def _remediation_completion(
    db: AsyncSession, organization_id: uuid.UUID
) -> ReviewCategory:
    """Remediation tasks marked done whose gap is still open.

    The moment worth catching: somebody finished the work, and nobody has
    confirmed the evidence actually closes the gap. Left alone, the gap
    stays open forever and the task list says everything is finished.
    """
    category = ReviewCategory(
        key="remediation_completion",
        label="Remediation completion",
        description="Work was marked done. Confirm the evidence closes the gap, then reassess.",
    )
    gaps = list(
        (
            await db.execute(
                select(ComplianceGap, Task)
                .join(Task, Task.id == ComplianceGap.task_id)
                .where(
                    ComplianceGap.organization_id == organization_id,
                    ComplianceGap.status != "resolved",
                    Task.status == "done",
                )
            )
        ).all()
    )
    for gap, task in gaps:
        category.items.append(
            ReviewItem(
                id=str(gap.id),
                title=task.title,
                detail=(
                    "The remediation task is complete but the gap is still open. Attach the "
                    "evidence it produced, then re-run the assessment."
                ),
                priority=_priority_for_gap(gap.severity),
                href="/compliance",
            )
        )
    return category


async def _pending_approvals(db: AsyncSession, organization_id: uuid.UUID) -> ReviewCategory:
    category = ReviewCategory(
        key="approvals",
        label="Approvals",
        description="Decisions this product refused to take on its own.",
    )
    approvals = list(
        (
            await db.execute(
                select(Approval).where(
                    Approval.organization_id == organization_id,
                    Approval.status == "pending",
                )
            )
        )
        .scalars()
        .all()
    )
    for approval in approvals:
        category.items.append(
            ReviewItem(
                id=str(approval.id),
                title=approval.action_type.replace("_", " "),
                detail=f"{approval.risk_class} risk · awaiting a decision.",
                priority="high" if approval.risk_class in ("high", "critical") else "medium",
                href="/approvals",
            )
        )
    return category


async def _privacy_decisions(
    db: AsyncSession, organization_id: uuid.UUID
) -> ReviewCategory:
    """The privacy judgements, in the one queue with everything else.

    Privacy had been surfacing these on its own overview, which is a
    second queue — and the whole argument for a Review Center is that
    there is only one place to look.
    """
    from app.compliance.privacy_review import privacy_decisions

    decisions = await privacy_decisions(db, organization_id=organization_id)
    return ReviewCategory(
        key="privacy_decisions",
        label="Privacy decisions",
        description=(
            "Veyntra drafted these records from your systems, vendors and "
            "documents. These are the judgements it cannot make for you."
        ),
        items=[
            ReviewItem(
                id=decision.id,
                title=decision.title,
                detail=decision.detail,
                priority=decision.priority,
                href=decision.href,
                recommendation=decision.recommendation,
                recommendation_reason=decision.recommendation_reason,
                evidence=decision.evidence,
                impact=decision.impact,
            )
            for decision in decisions
        ],
    )


async def build_review_center(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    recommended_framework_keys: list[str] | None = None,
) -> ReviewCenter:
    """Everything waiting on a person, in one queue."""
    categories = [
        await _privacy_decisions(db, organization_id),
        await _evidence_mappings(db, organization_id),
        await _pending_approvals(db, organization_id),
        await _ai_risk_classifications(db, organization_id),
        await _remediation_completion(db, organization_id),
        await _stale_assessments(db, organization_id),
        await _risk_acceptance(db, organization_id),
        await _questionnaire_answers(db, organization_id),
        await _framework_applicability(
            db, organization_id, recommended_keys=recommended_framework_keys or []
        ),
    ]

    since = datetime.now(UTC) - ACTIVITY_WINDOW
    auto_accepted = int(
        await db.scalar(
            select(func.count(EvidenceSuggestion.id)).where(
                EvidenceSuggestion.organization_id == organization_id,
                EvidenceSuggestion.status == "auto_approved",
                EvidenceSuggestion.created_at >= since,
            )
        )
        or 0
    )
    proposals = int(
        await db.scalar(
            select(func.count(EvidenceSuggestion.id)).where(
                EvidenceSuggestion.organization_id == organization_id,
                EvidenceSuggestion.created_at >= since,
            )
        )
        or 0
    )

    return ReviewCenter(
        categories=categories,
        total_needing_review=sum(category.count for category in categories),
        auto_accepted_recently=auto_accepted,
        proposals_recently=proposals,
    )


__all__ = [
    "ACTIVITY_WINDOW",
    "ReviewCategory",
    "ReviewCenter",
    "ReviewItem",
    "build_review_center",
]
