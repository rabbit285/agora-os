"""What the evidence on file actually shows about one requirement.

This is the step the product was missing. Document intelligence found
evidence and mapped it to a control; the assessment then knew only *how
many* documents were attached, so a requirement with evidence and no
human sign-off came out as a confirmed medium-severity gap. That is not a
deficiency — it is an assessment that has not happened yet, and reporting
it as a finding is how a gap list stops being read.

So the question here is narrower and answerable: given the expectations
written against this requirement (see `app.compliance.remediation`), and
the evidence types actually cited against it, **which conditions are
demonstrably unmet, and are we certain enough to say so?**

Three outcomes, and the distinction between the last two is the whole
point:

- `satisfied` — every checkable expectation is covered by verified
  evidence.
- `deficient` — at least one checkable expectation has nothing behind it.
  We can name it, so this is a real finding and earns a gap.
- `uncertain` — evidence exists but we cannot responsibly conclude
  either way: no expectations are written for this requirement, or the
  citations behind the evidence are weak, or the requirement is one where
  a wrong mapping is expensive and only a machine has looked. No gap is
  raised. A human is asked instead.

**Absence of a citation is not absence of a document.** A conclusion here
is always about what Veyntra can see, and the wording it produces says so.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Evidence, EvidenceSuggestion, Requirement
from app.compliance.remediation import expectations_for

# Below this, a machine-proposed mapping is not firm enough to close an
# expectation on its own. Matches the auto-approval bar in
# app.compliance.evidence_ai deliberately: evidence that was not certain
# enough to accept without a human is not certain enough to mark a
# condition met without one either.
CONFIDENCE_FLOOR = 0.90


@dataclass
class RequirementCoverage:
    """What the evidence supports, and how sure we are."""

    # satisfied | deficient | uncertain
    verdict: str
    # Expectations with evidence behind them.
    met: list[str] = field(default_factory=list)
    # Expectations with nothing behind them. Only ever populated when the
    # verdict is `deficient` — naming a condition we could not check is
    # the failure mode this module exists to avoid.
    unmet: list[str] = field(default_factory=list)
    # Why we could not conclude. Only set when the verdict is `uncertain`.
    uncertainty: str | None = None
    # Filenames behind the evidence, for the plan to name.
    documents: list[str] = field(default_factory=list)
    evidence_count: int = 0
    # Whether firm evidence is cited against *this* requirement, as
    # opposed to sitting on the same control. This is the numerator for
    # control coverage: counting documents instead let one policy read
    # as covering six obligations, and counting only `satisfied` would
    # score a requirement at zero merely because no expectation list has
    # been written for it yet.
    has_cited_evidence: bool = False


@dataclass
class _CitedEvidence:
    evidence_type: str | None
    confidence: float | None
    quote_verified: bool
    # True for evidence a person attached or approved by hand.
    human_backed: bool
    cites_requirement: bool


async def _cited_evidence(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    control_ids: list[uuid.UUID],
    requirement_id: uuid.UUID,
) -> list[_CitedEvidence]:
    """Every evidence row on these controls, with the citation behind it."""
    rows = list(
        (
            await db.execute(
                select(Evidence, EvidenceSuggestion)
                .outerjoin(
                    EvidenceSuggestion, EvidenceSuggestion.evidence_id == Evidence.id
                )
                .where(
                    Evidence.control_id.in_(control_ids),
                    Evidence.organization_id == organization_id,
                )
            )
        ).all()
    )

    cited: list[_CitedEvidence] = []
    for _evidence, suggestion in rows:
        if suggestion is None:
            # Attached by hand. There is no machine citation to weigh, and
            # a person chose to put it here — treated as firm, but as
            # making no claim about which specific requirement it answers.
            cited.append(
                _CitedEvidence(
                    evidence_type=None,
                    confidence=None,
                    quote_verified=True,
                    human_backed=True,
                    cites_requirement=False,
                )
            )
            continue
        cited.append(
            _CitedEvidence(
                evidence_type=suggestion.evidence_type,
                confidence=suggestion.confidence,
                quote_verified=bool(suggestion.quote_verified),
                human_backed=suggestion.status == "approved",
                cites_requirement=suggestion.requirement_id == requirement_id,
            )
        )
    return cited


def _is_firm(item: _CitedEvidence) -> bool:
    """Whether one piece of evidence is solid enough to close a condition.

    A person's decision always counts. A machine's counts when the quote
    it cited was found in the document and it was confident — the same two
    conditions that let the mapping be accepted without a human at all.
    """
    if item.human_backed:
        return True
    return item.quote_verified and (item.confidence or 0.0) >= CONFIDENCE_FLOOR


async def analyse_coverage(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    requirement: Requirement,
    framework_key: str,
    control_ids: list[uuid.UUID],
    document_names: list[str],
) -> RequirementCoverage:
    """Decide what the evidence on file shows about this requirement."""
    cited = await _cited_evidence(
        db,
        organization_id=organization_id,
        control_ids=control_ids,
        requirement_id=requirement.id,
    )
    coverage = RequirementCoverage(
        verdict="uncertain",
        documents=document_names,
        evidence_count=len(cited),
    )
    if not cited:
        coverage.uncertainty = "No evidence is attached to the mapped controls."
        return coverage

    firm = [item for item in cited if _is_firm(item)]
    # Attribution, not proximity. Evidence sitting on the same control
    # is not evidence *for this requirement* — the mapping has to have
    # named it. Counting the rest would let one policy read as covering
    # every obligation the control happens to serve.
    coverage.has_cited_evidence = any(item.cites_requirement for item in firm)

    expectations = expectations_for(framework_key, requirement.reference_code)
    checkable = [item for item in expectations if item.satisfied_by]

    if not checkable:
        # No written expectations for this requirement, so there is no
        # list to check the evidence against. Saying "part of this is
        # uncovered" here would be a guess dressed as a finding.
        coverage.uncertainty = (
            f"{len(cited)} document(s) are mapped to this requirement, but Veyntra has no "
            "itemised expectation set for it yet, so it cannot confirm on its own that they "
            "cover it in full."
        )
        return coverage

    # A requirement where a wrong mapping is expensive to discover later
    # always goes to a person if only a machine has looked at it.
    if requirement.sensitivity == "high" and not any(item.human_backed for item in cited):
        coverage.uncertainty = (
            "Every document here was mapped automatically, and this requirement is one "
            "where a wrong mapping is expensive to discover later. A person should confirm "
            "the mappings before Veyntra draws a conclusion."
        )
        return coverage

    if not firm:
        coverage.uncertainty = (
            f"{len(cited)} document(s) are mapped, but none of the citations behind them is "
            "firm enough to conclude from — the quoted passage could not be verified, or the "
            "match was not confident. A person should review them."
        )
        return coverage

    # Types present. Evidence a person attached by hand carries no type
    # claim, so it cannot close a specific condition — but its presence is
    # why an all-manual control lands at `uncertain` rather than at a
    # confident deficiency below.
    present = {item.evidence_type for item in firm if item.evidence_type}
    typed = [item for item in firm if item.evidence_type]

    if not typed:
        coverage.uncertainty = (
            f"{len(cited)} document(s) were attached by hand, which records that someone "
            "considered them relevant but not which part of the requirement each one answers. "
            "A person should confirm this requirement is covered."
        )
        return coverage

    met = [item.description for item in checkable if present & set(item.satisfied_by)]
    unmet = [item.description for item in checkable if not (present & set(item.satisfied_by))]

    if unmet:
        coverage.verdict = "deficient"
        coverage.met = met
        coverage.unmet = unmet
        return coverage

    coverage.verdict = "satisfied"
    coverage.met = met
    return coverage


__all__ = [
    "CONFIDENCE_FLOOR",
    "RequirementCoverage",
    "analyse_coverage",
]
