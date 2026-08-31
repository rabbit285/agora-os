"""What we can say about one control, and why.

**This is the only place a control's status is decided.** The controls
list, the control detail screen, search results and the dashboard all
read from here. They used not to: the detail screen called this service
while the list rendered `Control.status`, a stored workflow field written
by `record_assessment`, so the same control read "Partially evidenced,
33%, missing Art. 15 and Art. 72" on one screen and "not started" on the
other. Two sources of truth for one question is one too many, and the
answer a customer saw depended on which screen they happened to open.

`Control.status` survives as secondary metadata — *has anyone declared
this control operational* — which is a different question from *does the
evidence support the requirements it serves*. It is never the primary
badge again.

**Applicability is resolved before coverage is counted.** A control
serving Art. 15, Art. 72 and ISO 9.1 at a company that deploys no
high-risk AI serves two applicable requirements, not three. Counting the
third would report 33% where the honest figure is 50%, and would make a
company in scope of fewer obligations look less prepared than one in
scope of more.

**Derived, not stored.** Computed from the evidence currently attached
and the requirements the control serves, so it cannot go stale against
them. A stored verdict would need invalidating every time a document was
approved, and the version that got missed would be the one someone acted
on.

**A human decision always wins.** `recorded_status` carries the most
recent human assessment, and the UI shows it alongside rather than
instead of this. Nothing here overwrites what a person concluded.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.evidence_coverage import analyse_coverage
from app.compliance.models import (
    Control,
    ControlAssessment,
    ControlMapping,
    Evidence,
    EvidenceSuggestion,
    Framework,
    Requirement,
)
from app.compliance.requirement_applicability import (
    OrganizationProfile,
    evaluate_applicability,
)
from app.core.models import File
from app.knowledge.documents import hrefs_for_files

# What the evidence on file supports. Deliberately distinct from the
# control's own `status` (a workflow state someone sets) and from the
# recorded human assessment — conflating the three is how a control ends
# up reading "implemented" because a row exists.
# Each state is a range of the coverage figure, not an independent
# judgement — see `_summarise`, where the status is *derived* from the
# count. Stating them as ranges is what makes "Partially evidenced · 0%"
# unrepresentable rather than merely unlikely:
#
#   not_applicable        no applicable requirements
#   no_evidence           no evidence items exist
#   evidence_insufficient evidence exists, 0% demonstrated, and we can
#                         name what is missing
#   partially_evidenced   >0% and <100%
#   evidenced             100%
#
# `needs_review` is the exception and is deliberately not a range. It
# means "evidence is here and Veyntra cannot confirm it covers the
# requirement in full", which is orthogonal to how much of the control
# that evidence reaches: it happens at 0% when nothing can be
# attributed, and at 100% when every applicable requirement has
# evidence cited against it but no expectation set to check it against.
# Calling either of those `evidenced` would overstate the position.
ASSESSMENT_STATES = (
    "not_applicable",
    "no_evidence",
    "evidence_insufficient",
    "needs_review",
    "partially_evidenced",
    "evidenced",
)

# States that are always 0% by construction. `needs_review` is not one
# of them — see above.
ZERO_COVERAGE_STATES = frozenset(
    {"not_applicable", "no_evidence", "evidence_insufficient"}
)

# How each state reads to someone who does not work in compliance daily.
# Held here rather than in the frontend so every screen says the same
# word for the same state.
ASSESSMENT_LABELS = {
    "not_applicable": "Not applicable",
    "no_evidence": "No evidence",
    "evidence_insufficient": "Evidence insufficient",
    "needs_review": "Needs review",
    "partially_evidenced": "Partially evidenced",
    "evidenced": "Evidenced",
    # Human verdicts. They join the same vocabulary because they answer
    # the same question — what state is this control in — and a reader
    # should not have to learn which scale a word came from.
    "passed": "Passed",
    "failed": "Failed",
    "partially_implemented": "Partially implemented",
}

# What `record_assessment` stores, mapped onto the shared vocabulary.
# `not_assessed` deliberately maps to nothing: recording "I have not
# assessed this" is not a decision, so it must not override what Veyntra
# derived.
HUMAN_VERDICTS = {
    "pass": "passed",
    "fail": "failed",
    "partial": "partially_implemented",
}


def effective_status(ai_status: str, human_status: str | None) -> str:
    """The one state a user should act on.

    **This is the only place that decision is made.** Every screen —
    the controls list, the control detail, framework requirements,
    readiness, the Review Center — reads it from here, because a control
    that reads "Passed" on one screen and "Needs review" on another is
    the same class of bug as the list and the detail disagreeing.

    A human decision wins when one exists. That is the point of taking
    it: leaving the headline at "Needs review" after somebody has
    reviewed it tells them their decision did nothing.

    The AI's own conclusion is never overwritten — it travels beside
    this as `ai_status`, because "a person disagreed with the automated
    assessment" is exactly what an auditor wants to see.
    """
    return human_status or ai_status


def requires_human_review(ai_status: str, human_status: str | None) -> bool:
    """Whether this control is still waiting on a person.

    Drives the Review Center. Once somebody has decided, the item leaves
    the queue — continuing to list it is how a queue stops being
    trusted.
    """
    return human_status is None and ai_status == "needs_review"


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """`1 piece of evidence`, `2 pieces of evidence`.

    Customer-facing strings are read by people, and "1 piece(s) of
    evidence are mapped" is the sort of thing that makes a product feel
    machine-generated in the one place it is asking to be trusted.
    """
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def _verb(count: int) -> str:
    return "is" if count == 1 else "are"


@dataclass
class EvidenceProvenance:
    """One piece of evidence, with where it came from."""

    evidence_id: uuid.UUID
    file_id: uuid.UUID
    filename: str
    title: str
    # Where the document this came from opens — the same Document Detail
    # route the library and a Copilot citation use. None when the file has
    # no indexed document, so the UI shows a filename without a link
    # rather than a link that 404s.
    document_href: str | None = None
    # Null for evidence attached by hand — there is no model citation
    # behind it, and inventing one would misrepresent how it got here.
    source_location: str | None = None
    evidence_type: str | None = None
    model_confidence: float | None = None
    quoted_passage: str | None = None
    # auto | human | manual
    mapped_by: str = "manual"


@dataclass
class RequirementCoverageLine:
    """One requirement this control serves, and where it stands.

    Carried per requirement rather than summarised away so the detail
    screen can show which obligations are covered, which are not, and
    which do not bind this organization at all — and so the percentage
    beside it can be checked against the same list.
    """

    requirement_id: uuid.UUID
    reference_code: str
    title: str
    framework_key: str
    # applicable | likely_applicable | needs_review | not_applicable
    applicability: str
    applicability_reason: str
    # satisfied | deficient | uncertain | no_evidence
    coverage: str
    # Firm evidence is cited against this requirement and nothing is
    # known to be missing from it. The numerator for control coverage —
    # a requirement, not a document.
    covered: bool = False
    missing_conditions: list[str] = field(default_factory=list)


@dataclass
class ControlAssessmentView:
    """Three dimensions, kept apart.

    They used to be two fields rendered as one badge — "Needs review ·
    100%" — which asked the reader to hold an assessment state and a
    coverage percentage in one glance and work out that they were
    different kinds of thing. And the human decision was carried
    alongside without ever becoming the answer, so a control could read
    "Needs review" after somebody had reviewed it.
    """

    control_id: uuid.UUID
    # What Veyntra derived from the evidence. Never overwritten.
    status: str
    # Share of *applicable* requirements this control serves that the
    # evidence on file supports, 0-100.
    confidence: int
    # Plain sentences a non-specialist can act on.
    why: str
    missing: str | None
    evidence: list[EvidenceProvenance] = field(default_factory=list)
    requirement_codes: list[str] = field(default_factory=list)
    requirements: list[RequirementCoverageLine] = field(default_factory=list)
    # The last human verdict, if a person recorded one. Shown beside this
    # assessment, never replaced by it.
    recorded_status: str | None = None
    recorded_at: str | None = None
    recorded_by: uuid.UUID | None = None

    @property
    def ai_status(self) -> str:
        return self.status

    @property
    def ai_label(self) -> str:
        return ASSESSMENT_LABELS.get(self.status, self.status)

    @property
    def human_status(self) -> str | None:
        """The human verdict in the shared vocabulary, or None.

        `not_assessed` maps to None on purpose: recording "I have not
        assessed this" is not a decision and must not override what
        Veyntra derived.
        """
        if self.recorded_status is None:
            return None
        return HUMAN_VERDICTS.get(self.recorded_status)

    @property
    def effective_status(self) -> str:
        return effective_status(self.status, self.human_status)

    @property
    def label(self) -> str:
        """The headline. Effective, not derived — this is the word the
        user acts on."""
        status = self.effective_status
        return ASSESSMENT_LABELS.get(status, status)

    @property
    def review_required(self) -> bool:
        return requires_human_review(self.status, self.human_status)

    @property
    def applicable_count(self) -> int:
        return sum(1 for line in self.requirements if line.applicability != "not_applicable")

    @property
    def satisfied_count(self) -> int:
        return sum(
            1
            for line in self.requirements
            if line.applicability != "not_applicable" and line.covered
        )


async def evidence_by_control(
    db: AsyncSession, *, organization_id: uuid.UUID, control_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[EvidenceProvenance]]:
    """Every control's evidence, in one round trip.

    Public because the audit workspace needs the same answer, and the
    audit had a second copy of this that read three fields `Evidence`
    does not have — the provenance lives on the file, the suggestion and
    the document index, not on the evidence row. A second derivation of
    something this fiddly is a bug waiting for the first organization
    with evidence on file.

    Batched because the controls list assesses a whole page at once, and
    a per-control query here is the difference between one query and
    thirty.
    """
    if not control_ids:
        return {}

    rows = list(
        (
            await db.execute(
                select(Evidence, File)
                .join(File, File.id == Evidence.file_id)
                .where(Evidence.control_id.in_(control_ids))
                .order_by(Evidence.created_at.desc())
            )
        ).all()
    )

    suggestions = {
        suggestion.evidence_id: suggestion
        for suggestion in (
            await db.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.control_id.in_(control_ids),
                    EvidenceSuggestion.evidence_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    }

    # One query for every file in the batch, rather than one per row:
    # this runs for the whole controls list.
    hrefs = await hrefs_for_files(
        db,
        organization_id=organization_id,
        file_ids=[file_record.id for _, file_record in rows],
    )

    by_control: dict[uuid.UUID, list[EvidenceProvenance]] = {
        control_id: [] for control_id in control_ids
    }
    for evidence, file_record in rows:
        suggestion = suggestions.get(evidence.id)
        by_control.setdefault(evidence.control_id, []).append(
            EvidenceProvenance(
                evidence_id=evidence.id,
                file_id=evidence.file_id,
                filename=file_record.original_filename,
                title=evidence.title,
                document_href=hrefs.get(file_record.id),
                source_location=suggestion.source_location if suggestion else None,
                evidence_type=suggestion.evidence_type if suggestion else None,
                model_confidence=suggestion.confidence if suggestion else None,
                quoted_passage=suggestion.quoted_passage if suggestion else None,
                mapped_by=(
                    "auto"
                    if suggestion and suggestion.status == "auto_approved"
                    else "human"
                    if suggestion
                    else "manual"
                ),
            )
        )
    return by_control


async def _requirements_by_control(
    db: AsyncSession, *, control_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[Requirement, str]]]:
    """Mapped requirements per control, each with its framework key."""
    if not control_ids:
        return {}

    rows = list(
        (
            await db.execute(
                select(ControlMapping.control_id, Requirement, Framework.key)
                .join(Requirement, Requirement.id == ControlMapping.requirement_id)
                .join(Framework, Framework.id == Requirement.framework_id)
                .where(ControlMapping.control_id.in_(control_ids))
                .order_by(Requirement.reference_code)
            )
        ).all()
    )

    by_control: dict[uuid.UUID, list[tuple[Requirement, str]]] = {
        control_id: [] for control_id in control_ids
    }
    for control_id, requirement, framework_key in rows:
        by_control.setdefault(control_id, []).append((requirement, framework_key))
    return by_control


async def _latest_assessments(
    db: AsyncSession, *, control_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ControlAssessment]:
    if not control_ids:
        return {}
    rows = list(
        (
            await db.execute(
                select(ControlAssessment)
                .where(ControlAssessment.control_id.in_(control_ids))
                .order_by(ControlAssessment.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    latest: dict[uuid.UUID, ControlAssessment] = {}
    for row in rows:
        latest.setdefault(row.control_id, row)
    return latest


def _coverage_percent(covered: int, applicable: int) -> int:
    """The share of applicable requirements demonstrated, 0-100.

    Clamped at both ends rather than left to `round`, because rounding
    is what lets a figure disagree with the words beside it: one covered
    requirement out of two hundred rounds to 0%, and one uncovered out
    of two hundred rounds to 100%. Both would print a number that
    contradicts its own status badge."""
    if applicable <= 0:
        return 0
    if covered <= 0:
        return 0
    if covered >= applicable:
        return 100
    return min(99, max(1, round(100 * covered / applicable)))


def _summarise(
    *,
    lines: list[RequirementCoverageLine],
    evidence: list[EvidenceProvenance],
) -> tuple[str, int, str, str | None]:
    """Roll per-requirement conclusions into one control-level answer."""
    applicable = [line for line in lines if line.applicability != "not_applicable"]
    excluded = len(lines) - len(applicable)
    scope_note = (
        f" {_plural(excluded, 'mapped requirement')} "
        f"{'does' if excluded == 1 else 'do'} not apply to your organization and "
        f"{_verb(excluded)} excluded."
        if excluded
        else ""
    )

    if not lines:
        return (
            "no_evidence",
            0,
            "This control is not mapped to any requirement yet, so there is nothing to "
            "assess it against.",
            "A mapping to at least one requirement.",
        )

    if not applicable:
        return (
            "not_applicable",
            0,
            "None of the requirements this control is mapped to currently binds your "
            "organization, so there is nothing here to evidence."
            + (f" ({', '.join(line.reference_code for line in lines)})" if lines else ""),
            None,
        )

    # Requirements over requirements, and each requirement counts once.
    # Four documents all citing the same obligation demonstrate one
    # requirement, not four — `covered` is a list of requirement lines,
    # so duplicates cannot inflate it. The old figure divided the number
    # of *documents* by the number of *mapped* requirements, so one
    # policy on a three-requirement control read 33% whether it answered
    # one obligation or all of them.
    covered = [line for line in applicable if line.covered]
    deficient = [line for line in applicable if line.coverage == "deficient"]
    uncertain = [line for line in applicable if line.coverage == "uncertain" and line.covered]
    uncovered = [line for line in applicable if not line.covered]
    coverage = _coverage_percent(len(covered), len(applicable))

    if not evidence:
        return (
            "no_evidence",
            0,
            "No evidence has been mapped to this control yet. Upload a policy or "
            "procedure and Veyntra will propose which controls it supports." + scope_note,
            "Evidence demonstrating "
            + ", ".join(line.reference_code for line in applicable)
            + ".",
        )

    evidence_phrase = (
        f"{_plural(len(evidence), 'piece of evidence', 'pieces of evidence')} "
        f"{_verb(len(evidence))} mapped"
    )

    auto = [item for item in evidence if item.mapped_by == "auto"]
    auto_note = (
        f" {_plural(len(auto), 'mapping')} {_verb(len(auto))} accepted automatically "
        + ("and remains reversible." if len(auto) == 1 else "and remain reversible.")
        if auto
        else ""
    )

    if len(covered) == len(applicable):
        subject = (
            "the requirement"
            if len(applicable) == 1
            else f"all {len(applicable)} requirements"
        )
        why = f"{evidence_phrase}, covering {subject} this control serves.{scope_note}"
        # Covered is not the same as confirmed. Where Veyntra has no
        # itemised expectation set for a requirement it can see that
        # evidence was cited against it but not that the evidence is
        # complete, and saying `Evidenced` there would overstate it.
        if uncertain:
            return (
                "needs_review",
                coverage,
                why
                + " Veyntra cannot confirm on its own that "
                + ("it covers" if len(uncertain) == 1 else "they cover")
                + f" {', '.join(line.reference_code for line in uncertain)} in full."
                + auto_note,
                "A person to confirm the evidence covers "
                + ", ".join(line.reference_code for line in uncertain)
                + ".",
            )
        return "evidenced", coverage, why + auto_note, None

    if covered:
        return (
            "partially_evidenced",
            coverage,
            f"{evidence_phrase}, covering {len(covered)} of the {len(applicable)} "
            f"applicable requirements this control serves.{scope_note}{auto_note}",
            "Evidence for "
            + ", ".join(line.reference_code for line in uncovered)
            + ".",
        )

    # Nothing is covered. "Partially evidenced" would be a contradiction
    # of the number beside it, so the two 0% states divide by whether we
    # can say *why*: a named deficiency is a finding, an unattributable
    # document is a question.
    if deficient:
        named = sorted({c for line in deficient for c in line.missing_conditions})
        return (
            "evidence_insufficient",
            coverage,
            f"{evidence_phrase}, but {'it does' if len(evidence) == 1 else 'they do'} "
            "not demonstrate any of the requirements this control serves."
            + scope_note
            + auto_note,
            ("Evidence providing " + "; ".join(named) + ".")
            if named
            else "Evidence for "
            + ", ".join(line.reference_code for line in deficient)
            + ".",
        )

    return (
        "needs_review",
        coverage,
        f"{evidence_phrase} and nothing has been found wrong with "
        f"{'it' if len(evidence) == 1 else 'them'}, but Veyntra cannot tell which of the "
        "requirements this control serves "
        f"{'it answers' if len(evidence) == 1 else 'they answer'}." + scope_note,
        "A person to confirm the evidence covers "
        + ", ".join(line.reference_code for line in uncovered)
        + ".",
    )


def _assert_consistent(status: str, coverage: int) -> None:
    """The badge and the number beside it must agree.

    `Partially evidenced · 0%` shipped because the status and the
    percentage were decided in different branches and nothing checked
    them against each other. This is cheap, runs on every control, and
    fails loudly here rather than reading as a contradiction on screen.
    """
    if status == "evidenced" and coverage != 100:
        raise AssertionError(f"evidenced at {coverage}%")
    if status == "partially_evidenced" and not 0 < coverage < 100:
        raise AssertionError(f"partially evidenced at {coverage}%")
    if status in ZERO_COVERAGE_STATES and coverage != 0:
        raise AssertionError(f"{status} at {coverage}%")
    if not 0 <= coverage <= 100:
        raise AssertionError(f"coverage out of range: {coverage}")


async def assess_controls(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    controls: list[Control],
    profile: OrganizationProfile,
) -> dict[uuid.UUID, ControlAssessmentView]:
    """Assess many controls at once. The single source of truth.

    Every screen that shows a control's status calls this — directly, or
    through `assess_control` for the single-control case. Adding a second
    derivation anywhere else reintroduces the bug this module exists to
    close.
    """
    control_ids = [control.id for control in controls]
    # Named apart from the function it calls: assigning the result to the
    # function's own name shadows it, and Python then treats the call
    # itself as a read of an unassigned local.
    evidence_for_control = await evidence_by_control(
        db, organization_id=organization_id, control_ids=control_ids
    )
    requirements_by_control = await _requirements_by_control(db, control_ids=control_ids)
    latest = await _latest_assessments(db, control_ids=control_ids)

    views: dict[uuid.UUID, ControlAssessmentView] = {}
    for control in controls:
        evidence = evidence_for_control.get(control.id, [])
        mapped = requirements_by_control.get(control.id, [])

        lines: list[RequirementCoverageLine] = []
        for requirement, framework_key in mapped:
            applicability = evaluate_applicability(
                profile,
                framework_key=framework_key,
                reference_code=requirement.reference_code,
            )
            if not applicability.counts_toward_coverage:
                lines.append(
                    RequirementCoverageLine(
                        requirement_id=requirement.id,
                        reference_code=requirement.reference_code,
                        title=requirement.title,
                        framework_key=framework_key,
                        applicability="not_applicable",
                        applicability_reason=applicability.reason,
                        coverage="not_applicable",
                    )
                )
                continue

            if not evidence:
                coverage_verdict, missing, covered = "no_evidence", [], False
            else:
                analysed = await analyse_coverage(
                    db,
                    organization_id=organization_id,
                    requirement=requirement,
                    framework_key=framework_key,
                    control_ids=[control.id],
                    document_names=[item.filename for item in evidence],
                )
                coverage_verdict, missing = analysed.verdict, analysed.unmet
                # A named deficiency is never covered, however much
                # evidence sits beside it.
                covered = coverage_verdict != "deficient" and (
                    coverage_verdict == "satisfied" or analysed.has_cited_evidence
                )

            lines.append(
                RequirementCoverageLine(
                    requirement_id=requirement.id,
                    reference_code=requirement.reference_code,
                    title=requirement.title,
                    framework_key=framework_key,
                    applicability=applicability.status,
                    applicability_reason=applicability.reason,
                    coverage=coverage_verdict,
                    covered=covered,
                    missing_conditions=list(missing),
                )
            )

        status, coverage, why, missing_text = _summarise(lines=lines, evidence=evidence)
        _assert_consistent(status, coverage)
        recorded = latest.get(control.id)
        views[control.id] = ControlAssessmentView(
            control_id=control.id,
            status=status,
            confidence=coverage,
            why=why,
            missing=missing_text,
            evidence=evidence,
            requirement_codes=[line.reference_code for line in lines],
            requirements=lines,
            recorded_status=recorded.status if recorded else None,
            recorded_at=recorded.created_at.isoformat() if recorded else None,
            recorded_by=recorded.assessed_by if recorded else None,
        )
    return views


async def assess_control(
    db: AsyncSession,
    *,
    control: Control,
    profile: OrganizationProfile,
) -> ControlAssessmentView:
    """Everything the control screen needs, derived from what is on file."""
    views = await assess_controls(
        db,
        organization_id=control.organization_id,
        controls=[control],
        profile=profile,
    )
    return views[control.id]


__all__ = [
    "ASSESSMENT_LABELS",
    "evidence_by_control",
    "ASSESSMENT_STATES",
    "HUMAN_VERDICTS",
    "effective_status",
    "requires_human_review",
    "ControlAssessmentView",
    "EvidenceProvenance",
    "RequirementCoverageLine",
    "assess_control",
    "assess_controls",
]
