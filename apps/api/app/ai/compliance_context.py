"""Answering compliance questions from the database, not from documents.

"What controls are missing evidence?" has an exact answer sitting in
Postgres. Sending it through document retrieval asks a language model to
infer, from whatever policy text happens to embed near the question,
something the product already knows for certain — and returns nothing at
all when no document mentions the phrase. The Copilot answered "I don't
have any indexed documents" to a question that never needed one.

So the Copilot has two sources, and the question decides which:

- **Structured** — control coverage, open gaps, readiness, what is
  awaiting review, overdue remediation. Read from the same services every
  screen reads, so the Copilot cannot disagree with the dashboard.
- **Retrieval** — what a document *says*. Grounded in chunks, cited.

Mixed questions get both, which is the common case: "which controls are
missing evidence and what does our security policy say about backups"
needs the register and the document.

**Nothing here is generated.** This module assembles facts and hands them
to the prompt as context. The model's job is to phrase them, not to
decide them — the same rule the rest of the compliance engine follows.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.assessment import load_scoping_profile
from app.compliance.control_assessment import ASSESSMENT_LABELS, assess_controls
from app.compliance.models import ComplianceGap, Control, Framework, Requirement
from app.core.models import Task

# Phrases that mean "read my compliance state", not "read my documents".
# Deliberately explicit rather than a model call: routing a question is a
# decision, and a wrong one here is invisible to the customer — they just
# get a worse answer with no way to tell why.
_STRUCTURED_PATTERNS = (
    r"\bcontrols?\b.*\b(missing|without|no|lack\w*)\b.*\bevidence\b",
    r"\bevidence\b.*\bmissing\b",
    r"\b(open|current|outstanding)\s+gaps?\b",
    r"\bwhat\s+gaps?\b",
    r"\bgaps?\b.*\b(open|remain|outstanding|left)\b",
    r"\bneeds?\s+(my\s+)?review\b",
    r"\bawaiting\s+review\b",
    r"\breadiness\b",
    r"\bhow\s+ready\b",
    r"\bwhich\s+framework\b",
    r"\blowest\b.*\b(readiness|score)\b",
    r"\bremediation\b.*\b(overdue|due|late|outstanding)\b",
    r"\boverdue\b",
    r"\bwhat\s+(do\s+i|should\s+i|needs?)\b.*\b(fix|do next|attention)\b",
    r"\bnot\s+applicable\b",
    r"\bcoverage\b",
)

_STRUCTURED_RE = tuple(re.compile(p, re.IGNORECASE) for p in _STRUCTURED_PATTERNS)


def wants_structured_context(question: str) -> bool:
    """Whether this question is about compliance state rather than text."""
    return any(pattern.search(question) for pattern in _STRUCTURED_RE)


@dataclass(frozen=True)
class ComplianceFact:
    """One value read from Veyntra's own records.

    Shown to the customer separately from document citations, and labelled
    as coming from the compliance database, because it did. "Current
    status: Needs review" is a decision this product made from declared
    facts — attributing it to a paragraph in an uploaded PDF would be a
    lie about where the answer came from, and would send anyone
    disagreeing with it to argue with the wrong thing.
    """

    label: str
    value: str
    detail: str | None = None


@dataclass
class ComplianceContext:
    """Facts about the organization, ready to put in front of a model.

    `lines` is prose for the prompt. `facts` is the same information in a
    structured form the UI can render on its own, without the model
    standing between the customer and their own data.
    """

    lines: list[str] = field(default_factory=list)
    facts: list[ComplianceFact] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.lines

    def render(self) -> str:
        return "\n".join(self.lines)


async def _control_lines(
    db: AsyncSession, *, organization_id: uuid.UUID, question: str = "", limit: int = 40
) -> tuple[list[str], list[ComplianceFact]]:
    controls = list(
        (
            await db.execute(
                select(Control)
                .where(Control.organization_id == organization_id)
                .order_by(Control.title)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not controls:
        return (["No controls exist yet — adopt a framework to create them."], [])

    profile = await load_scoping_profile(db, organization_id=organization_id)
    views = await assess_controls(
        db, organization_id=organization_id, controls=controls, profile=profile
    )

    lines = ["CONTROLS AND WHAT THE EVIDENCE SHOWS:"]
    for control in controls:
        view = views[control.id]
        label = ASSESSMENT_LABELS.get(view.status, view.status)
        detail = (
            f"- {control.title}: {label}"
            f" ({view.satisfied_count} of {view.applicable_count} applicable "
            f"requirements evidenced, {len(view.evidence)} evidence item(s))"
        )
        if view.missing:
            detail += f". Missing: {view.missing}"
        lines.append(detail)

    settled = sum(1 for c in controls if views[c.id].status in ("evidenced", "passed"))
    awaiting = sum(1 for c in controls if views[c.id].review_required)
    facts = [
        ComplianceFact(label="Controls evidenced", value=f"{settled} of {len(controls)}")
    ]
    if awaiting:
        facts.append(
            ComplianceFact(
                label="Controls awaiting your review",
                value=str(awaiting),
                detail="An AI assessment is waiting on a human decision.",
            )
        )

    # A question that names one control gets that control's status as a
    # fact of its own, from the register — not inferred from whatever
    # document happened to retrieve well.
    lowered_question = question.lower()
    named = [c for c in controls if len(c.title) > 8 and c.title.lower() in lowered_question]
    if len(named) == 1:
        view = views[named[0].id]
        facts.insert(
            0,
            ComplianceFact(
                label="Current status",
                value=ASSESSMENT_LABELS.get(view.status, view.status),
                detail=named[0].title,
            ),
        )
    return (lines, facts)


async def _gap_lines(
    db: AsyncSession, *, organization_id: uuid.UUID, limit: int = 25
) -> tuple[list[str], list[ComplianceFact]]:
    rows = list(
        (
            await db.execute(
                select(ComplianceGap, Requirement, Framework)
                .join(Requirement, Requirement.id == ComplianceGap.requirement_id)
                .join(Framework, Framework.id == ComplianceGap.framework_id)
                .where(
                    ComplianceGap.organization_id == organization_id,
                    ComplianceGap.status != "resolved",
                )
                .order_by(ComplianceGap.severity.desc(), ComplianceGap.created_at)
                .limit(limit)
            )
        ).all()
    )
    if not rows:
        return (["OPEN GAPS: none."], [ComplianceFact(label="Open gaps", value="None")])

    lines = [f"OPEN GAPS ({len(rows)}):"]
    for gap, requirement, framework in rows:
        entry = (
            f"- {framework.name} {requirement.reference_code} "
            f"({gap.severity} severity, {gap.status}): {gap.summary}"
        )
        if gap.missing_conditions:
            entry += f" Not covered: {'; '.join(gap.missing_conditions)}."
        lines.append(entry)

    high = sum(1 for gap, _, _ in rows if gap.severity in ("high", "critical"))
    return (
        lines,
        [
            ComplianceFact(
                label="Open gaps",
                value=str(len(rows)),
                detail=f"{high} high or critical severity." if high else None,
            )
        ],
    )


async def _readiness_lines(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> tuple[list[str], list[ComplianceFact]]:
    from app.compliance.assessment import evaluate_framework, summarize_readiness
    from app.compliance.models import FrameworkActivation

    frameworks = list(
        (
            await db.execute(
                select(Framework)
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
    if not frameworks:
        return (["FRAMEWORK READINESS: no framework has been adopted yet."], [])

    lines = ["FRAMEWORK READINESS:"]
    facts: list[ComplianceFact] = []
    for framework in frameworks:
        evaluations = await evaluate_framework(
            db, organization_id=organization_id, framework=framework
        )
        breakdown = summarize_readiness(evaluations)
        lines.append(
            f"- {framework.name}: {breakdown.percent}% ready across "
            f"{breakdown.total} applicable requirement(s) — "
            f"{breakdown.satisfied} satisfied, {breakdown.needs_review} awaiting review, "
            f"{breakdown.deficient} with an identified deficiency, "
            f"{breakdown.evidence_missing} missing evidence."
        )
        facts.append(
            ComplianceFact(
                label=f"{framework.name} readiness",
                value=f"{breakdown.percent}%",
                detail=(
                    f"{breakdown.satisfied} of {breakdown.total} applicable "
                    "requirements satisfied."
                ),
            )
        )
    return (lines, facts)


async def _remediation_lines(
    db: AsyncSession, *, organization_id: uuid.UUID, limit: int = 15
) -> tuple[list[str], list[ComplianceFact]]:
    now = datetime.now(UTC)
    rows = list(
        (
            await db.execute(
                select(Task)
                .where(
                    Task.organization_id == organization_id,
                    Task.module == "compliance",
                    Task.status.notin_(("done", "cancelled")),
                )
                .order_by(Task.due_at)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return (
            ["REMEDIATION: no open remediation tasks."],
            [ComplianceFact(label="Open remediation tasks", value="None")],
        )

    lines = [f"REMEDIATION TASKS ({len(rows)} open):"]
    overdue_count = sum(1 for task in rows if task.due_at is not None and task.due_at < now)
    for task in rows:
        overdue = task.due_at is not None and task.due_at < now
        when = (
            f"due {task.due_at.date().isoformat()}{' — OVERDUE' if overdue else ''}"
            if task.due_at
            else "no due date"
        )
        done = sum(1 for item in (task.checklist or []) if item.get("done"))
        total = len(task.checklist or [])
        lines.append(
            f"- {task.title} ({task.priority} priority, {task.status}, {when}"
            + (f", {done}/{total} checklist items complete" if total else "")
            + ")"
        )
    return (
        lines,
        [
            ComplianceFact(
                label="Open remediation tasks",
                value=str(len(rows)),
                detail=f"{overdue_count} overdue." if overdue_count else None,
            )
        ],
    )


async def _review_lines(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> tuple[list[str], list[ComplianceFact]]:
    from app.compliance.models import EvidenceSuggestion

    counts = dict(
        (
            await db.execute(
                select(EvidenceSuggestion.status, func.count())
                .where(EvidenceSuggestion.organization_id == organization_id)
                .group_by(EvidenceSuggestion.status)
            )
        ).all()
    )
    proposed = int(counts.get("proposed", 0))
    if not proposed:
        return (
            ["AWAITING REVIEW: nothing is waiting on a person."],
            [ComplianceFact(label="Awaiting your review", value="Nothing")],
        )
    return (
        [
            f"AWAITING REVIEW: {proposed} evidence mapping(s) need a human decision "
            "in the Review Center."
        ],
        [
            ComplianceFact(
                label="Awaiting your review",
                value=f"{proposed} evidence mapping" + ("" if proposed == 1 else "s"),
                detail="Waiting for a decision in the Review Center.",
            )
        ],
    )


async def gather(
    db: AsyncSession, *, organization_id: uuid.UUID, question: str
) -> ComplianceContext:
    """Collect the compliance facts this question needs.

    Everything is read through the services the screens use, so an answer
    here can never contradict what the customer sees on the dashboard.
    """
    lowered = question.lower()
    lines: list[str] = []
    facts: list[ComplianceFact] = []

    wants_controls = any(
        word in lowered for word in ("control", "evidence", "coverage", "missing")
    )
    wants_gaps = any(word in lowered for word in ("gap", "deficien", "fix", "issue"))
    wants_readiness = any(
        word in lowered for word in ("ready", "readiness", "framework", "score", "percent")
    )
    wants_remediation = any(
        word in lowered for word in ("remediation", "task", "overdue", "due", "owner")
    )
    wants_review = any(word in lowered for word in ("review", "approve", "decision"))

    # A question that matched the router but none of the topics above gets
    # the overview rather than nothing.
    if not any(
        (wants_controls, wants_gaps, wants_readiness, wants_remediation, wants_review)
    ):
        wants_readiness = wants_gaps = True

    def collect(result: tuple[list[str], list[ComplianceFact]]) -> None:
        section_lines, section_facts = result
        lines.extend(section_lines)
        facts.extend(section_facts)

    if wants_controls:
        collect(await _control_lines(db, organization_id=organization_id, question=question))
    if wants_gaps:
        collect(await _gap_lines(db, organization_id=organization_id))
    if wants_readiness:
        collect(await _readiness_lines(db, organization_id=organization_id))
    if wants_remediation:
        collect(await _remediation_lines(db, organization_id=organization_id))
    if wants_review:
        collect(await _review_lines(db, organization_id=organization_id))

    return ComplianceContext(lines=lines, facts=facts)


__all__ = ["ComplianceContext", "ComplianceFact", "gather", "wants_structured_context"]
