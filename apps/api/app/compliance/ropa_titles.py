"""What a processing activity is called.

Two questions that look similar and are not:

    Organization    "who is doing the processing?"    Agora Origin
    Activity        "what processing is being done?"  Customer Support

A RoPA entry titled with the organization's name answers the first
question twice and the second not at all, and an Article 30 record that
cannot say what the processing *is* is not a record of processing.

So this does two things. It **derives** a title from the processing
context — the stated purpose, the systems involved — rather than reusing
whatever name the source record happened to have, because "Support
Assistant" is the name of a tool and "AI Customer Support" is the name
of an activity. And it **refuses** the identities that answer the wrong
question: the organization's own name, a person's name, an email
address. Where it cannot derive something better it says so and asks,
which is a worse title than a good one and a much better one than a
confident wrong one.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import ProcessingActivity
from app.core.models import Membership, Organization
from app.core.organization import looks_like_an_email
from app.identity.models import User

# What a draft is called when the context does not support a real title.
# "Needs review" beats an invented one: a reviewer who sees this knows
# there is a decision waiting, where a plausible-looking wrong title gets
# approved without anybody reading it.
NEEDS_TITLE = "Processing activity title needs review"

# Purpose wording that maps onto the name of a business operation. Small
# and explicit rather than a model call: these are the activities almost
# every organization runs, the mapping is auditable, and a title nobody
# can explain is worse than no title.
#
# Order matters — the first match wins, so the more specific phrases
# come first.
_PURPOSE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(customer|client)\s+support\b|\bsupport\s+(request|ticket|inbox|enquir)", "Customer Support"),
    (r"\b(recruit|candidate|applicant|hiring|job\s+application)", "Recruitment"),
    (r"\b(payroll|salary|wages)\b", "Payroll"),
    (r"\b(billing|invoic|payment|subscription|charg)", "Billing and Payments"),
    (r"\b(marketing|newsletter|campaign|promotional)\b", "Marketing Communications"),
    (r"\b(employee|staff|hr|personnel)\b", "Employee Management"),
    (r"\b(product\s+analytic|usage\s+analytic|telemetry|product\s+metric)", "Product Analytics"),
    (r"\b(fraud|abuse|security\s+monitoring)\b", "Fraud and Abuse Prevention"),
    (r"\b(vendor|supplier|third[- ]party)\s+(management|assessment)", "Vendor Management"),
)


def _normalise(value: str | None) -> str:
    return " ".join((value or "").split()).strip().lower()


@dataclass
class TitleProposal:
    """A name for the processing, and how it was arrived at."""

    title: str
    # purpose | system | none — what the title was derived from, so a
    # reviewer can weigh it.
    basis: str
    reason: str
    # True when nothing supported a real title and a person has to
    # supply one before the record means anything.
    needs_review: bool = False


def derive(
    *,
    purpose: str | None,
    ai_system_name: str | None = None,
    is_ai: bool = False,
) -> TitleProposal:
    """A title describing the processing, from the context available.

    Prefers the purpose, because that is what the activity *is*. Falls
    back to naming the system only when the purpose says nothing usable,
    and to asking when neither does.
    """
    text = _normalise(purpose)

    for pattern, label in _PURPOSE_PATTERNS:
        if re.search(pattern, text):
            # An AI system doing customer support is "AI Customer
            # Support" — the same operation, run a different way, and a
            # RoPA that cannot tell them apart cannot answer a DPIA
            # question about either.
            title = f"AI {label}" if is_ai else label
            return TitleProposal(
                title=title,
                basis="purpose",
                reason=(
                    f"The stated purpose describes {label.lower()}"
                    + (", carried out through an AI system." if is_ai else ".")
                ),
            )

    if ai_system_name and _normalise(ai_system_name):
        return TitleProposal(
            title=ai_system_name.strip(),
            basis="system",
            reason=(
                "Named after the system involved — the recorded purpose does "
                "not describe a recognisable business operation."
            ),
            needs_review=True,
        )

    return TitleProposal(
        title=NEEDS_TITLE,
        basis="none",
        reason=(
            "Nothing on record describes what processing this is. A title "
            "has to come from a person."
        ),
        needs_review=True,
    )


# --- the identities a title must not borrow -----------------------------


@dataclass
class TitleProblem:
    """Why this title answers the wrong question."""

    kind: str
    message: str


async def identity_conflict(
    db: AsyncSession, *, organization_id: uuid.UUID, title: str
) -> TitleProblem | None:
    """Whether a title names *who* processes rather than *what* is processed.

    Checked against the live records rather than a word list: the
    organization's own name, and the names and addresses of the people
    in it. There is no code path that sets these today — this is the
    invariant, kept where a future one would trip over it.
    """
    candidate = _normalise(title)
    if not candidate:
        return None

    if looks_like_an_email(title):
        return TitleProblem(
            kind="email",
            message=(
                "That is an email address. A processing activity is named "
                "after the processing — \"Customer Support\", \"Billing and "
                "Payments\" — not after a person."
            ),
        )

    organization = await db.get(Organization, organization_id)
    if organization is not None and _normalise(organization.name) == candidate:
        return TitleProblem(
            kind="organization",
            message=(
                f"\"{organization.name}\" is your organization's name. The "
                "organization answers who is doing the processing; a "
                "processing activity answers what processing is being done — "
                "for example \"Customer Support\" or \"Employee Management\"."
            ),
        )

    people = (
        await db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == organization_id)
        )
    ).scalars().all()
    for person in people:
        if _normalise(person.full_name) == candidate:
            return TitleProblem(
                kind="person",
                message=(
                    f"\"{person.full_name}\" is a person in your organization. "
                    "A processing activity is named after the processing, not "
                    "after who runs it."
                ),
            )
    return None


# --- repairing what is already recorded ---------------------------------


@dataclass
class TitleRepair:
    """A recorded title that answers the wrong question, and what to do."""

    activity_id: uuid.UUID
    current_title: str
    problem: TitleProblem
    suggested_title: str | None
    suggestion_reason: str | None


async def find_title_repairs(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[TitleRepair]:
    """Activities whose title names who rather than what.

    Proposes; never renames. A record somebody typed deliberately is
    theirs, and a migration that silently retitled it would be the
    product overruling its user on the one field only the user can
    write.

    Where the activity's own purpose supports a better title, that is
    offered. Where it does not, the problem is reported with no
    suggestion — an ambiguous case is not one to guess at.
    """
    activities = (
        await db.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == organization_id,
                ProcessingActivity.status != "archived",
            )
        )
    ).scalars().all()

    repairs: list[TitleRepair] = []
    for activity in activities:
        problem = await identity_conflict(
            db, organization_id=organization_id, title=activity.name
        )
        if problem is None:
            continue
        proposal = derive(purpose=activity.purpose)
        usable = proposal.basis == "purpose"
        repairs.append(
            TitleRepair(
                activity_id=activity.id,
                current_title=activity.name,
                problem=problem,
                suggested_title=proposal.title if usable else None,
                suggestion_reason=proposal.reason if usable else None,
            )
        )
    return repairs


# --- one activity, not three --------------------------------------------


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", _normalise(value))
        if token and token not in {"the", "and", "of", "for", "ai"}
    }


def similar_titles(left: str, right: str) -> bool:
    """Whether two titles plausibly name the same processing.

    Deliberately crude and deliberately not decisive: it decides whether
    to *ask*, never whether to merge. "Customer Support" and "AI Customer
    Support" are the same operation; conflating them silently would lose
    the distinction a DPIA turns on, and treating them as unrelated
    produces the three-records-for-one-activity problem.
    """
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return False
    if a == b:
        return True
    overlap = len(a & b)
    return overlap > 0 and overlap >= min(len(a), len(b))


async def possible_duplicate(
    db: AsyncSession, *, organization_id: uuid.UUID, title: str
) -> ProcessingActivity | None:
    """An existing activity this title probably describes.

    Returned so a caller can ask "is this new, or an update to Customer
    Support?" — never so it can decide.
    """
    activities = (
        await db.execute(
            select(ProcessingActivity).where(
                ProcessingActivity.organization_id == organization_id,
                ProcessingActivity.status != "archived",
            )
        )
    ).scalars().all()
    for activity in activities:
        if similar_titles(activity.name, title):
            return activity
    return None


__all__ = [
    "NEEDS_TITLE",
    "TitleProblem",
    "TitleProposal",
    "TitleRepair",
    "derive",
    "find_title_repairs",
    "identity_conflict",
    "possible_duplicate",
    "similar_titles",
]
