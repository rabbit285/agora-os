"""DPIA screening (GDPR Article 35) and residual risk.

Article 35(1) requires a DPIA where processing is "likely to result in a
high risk to the rights and freedoms of natural persons". That phrase is
not self-applying, so the EDPB published nine criteria and said, in
substance: meet two and you should assume a DPIA is required; meet one
and think hard about it.

That is a rule, and rules belong in code. What does *not* belong is a
model's opinion on whether a given processing activity is "high risk" —
the same objection as everywhere else in this module, sharper here
because Article 35 has a legal threshold and getting it wrong in the
permissive direction means skipping an assessment the law required.

So the controller answers the criteria and the rule counts them. The
output names which criteria were met, which rule fired, and always
records that the controller — not this tool — decides.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import DPIA, ProcessingActivity, Risk

# Article 35(3) — the cases the Regulation names outright. Any one of
# these makes a DPIA mandatory; no counting required.
MANDATORY_CRITERIA: dict[str, str] = {
    "systematic_extensive_evaluation": (
        "Systematic and extensive evaluation of personal aspects based on automated "
        "processing, including profiling, on which decisions with legal or similarly "
        "significant effects are based (Art. 35(3)(a))"
    ),
    "large_scale_special_category": (
        "Processing on a large scale of special categories of data, or of personal data "
        "relating to criminal convictions and offences (Art. 35(3)(b))"
    ),
    "large_scale_public_monitoring": (
        "Systematic monitoring of a publicly accessible area on a large scale (Art. 35(3)(c))"
    ),
}

# The EDPB WP248 nine criteria. Two or more indicates a DPIA is required;
# one indicates it should be seriously considered.
EDPB_CRITERIA: dict[str, str] = {
    "evaluation_or_scoring": "Evaluation or scoring, including profiling and predicting",
    "automated_decision_making": "Automated decision-making with legal or similar significant effect",
    "systematic_monitoring": "Systematic monitoring of data subjects",
    "sensitive_data": "Sensitive data or data of a highly personal nature",
    "large_scale": "Processing at large scale",
    "matching_or_combining": "Matching or combining datasets",
    "vulnerable_subjects": "Data concerning vulnerable data subjects (children, employees, patients)",
    "innovative_technology": "Innovative use or application of new technological or organisational solutions",
    "prevents_rights_exercise": "Processing that prevents data subjects exercising a right or using a service",
}

ALL_CRITERIA = {**MANDATORY_CRITERIA, **EDPB_CRITERIA}

_LEVEL_SCORE = {"low": 1, "medium": 2, "high": 3}
_SCORE_LEVEL = {1: "low", 2: "low", 3: "medium", 4: "medium", 6: "high", 9: "high"}


def risk_level_from(likelihood: str, impact: str) -> str:
    """A 3x3 matrix, stated once so inherent and residual ratings are
    computed the same way — otherwise a mitigation can appear to help
    purely because the two were scored on different scales."""
    return _SCORE_LEVEL[_LEVEL_SCORE[likelihood] * _LEVEL_SCORE[impact]]


@dataclass(frozen=True)
class DpiaScreeningResult:
    outcome: str  # required | recommended | not_indicated
    rationale: str
    criteria_met: list[str]
    mandatory_triggers: list[str]
    unanswered: list[str]


def screen_for_dpia(
    answers: dict[str, bool], *, unanswered: list[str] | None = None
) -> DpiaScreeningResult:
    unanswered = unanswered or []
    met = {key for key, value in answers.items() if value}

    mandatory = sorted(met & MANDATORY_CRITERIA.keys())
    edpb = sorted(met & EDPB_CRITERIA.keys())

    if mandatory:
        return DpiaScreeningResult(
            outcome="required",
            rationale=(
                "This processing falls within a case Article 35(3) names explicitly, so a DPIA "
                "is required before the processing begins — the EDPB criteria do not need to be "
                "counted."
            ),
            criteria_met=[MANDATORY_CRITERIA[k] for k in mandatory],
            mandatory_triggers=mandatory,
            unanswered=unanswered,
        )

    if len(edpb) >= 2:
        return DpiaScreeningResult(
            outcome="required",
            rationale=(
                f"{len(edpb)} of the EDPB's nine criteria were met. The EDPB guidance treats two "
                "or more as indicating processing likely to result in high risk, so a DPIA "
                "should be carried out before the processing begins."
            ),
            criteria_met=[EDPB_CRITERIA[k] for k in edpb],
            mandatory_triggers=[],
            unanswered=unanswered,
        )

    if len(edpb) == 1:
        return DpiaScreeningResult(
            outcome="recommended",
            rationale=(
                "One of the EDPB's nine criteria was met. A single criterion does not by itself "
                "indicate high risk, but the EDPB advises carrying out a DPIA where there is any "
                "doubt — and recording the decision either way."
            ),
            criteria_met=[EDPB_CRITERIA[k] for k in edpb],
            mandatory_triggers=[],
            unanswered=unanswered,
        )

    return DpiaScreeningResult(
        outcome="not_indicated",
        rationale=(
            "None of the Article 35(3) cases or EDPB criteria were reported for this processing. "
            "On the answers given, a DPIA does not appear to be required. This reflects what was "
            "answered here and is not a determination by a supervisory authority — the "
            "controller remains responsible for the decision, and for recording it."
        ),
        criteria_met=[],
        mandatory_triggers=[],
        unanswered=unanswered,
    )


async def record_dpia_screening(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    activity: ProcessingActivity,
    answers: dict[str, bool],
    actor_user_id: uuid.UUID | None,
) -> DpiaScreeningResult:
    unanswered = [key for key in ALL_CRITERIA if key not in answers]
    result = screen_for_dpia(answers, unanswered=unanswered)

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dpia.screened",
        object_type="processing_activity",
        object_id=str(activity.id),
        after_state={
            "outcome": result.outcome,
            "criteria_met": len(result.criteria_met),
            "answers": answers,
        },
    )
    return result


async def recalculate_residual_risk(
    db: AsyncSession, *, organization_id: uuid.UUID, dpia: DPIA
) -> str | None:
    """Derive a DPIA's residual level from the risks raised against it.

    Takes the worst residual rating across its risks, and only counts
    risks that have actually been reassessed. A risk still carrying no
    residual rating is not treated as mitigated — that would let a DPIA
    reach "low" by nobody having looked, which is the exact failure mode
    a residual rating exists to prevent.
    """
    risks = list(
        (
            await db.execute(
                select(Risk).where(
                    Risk.dpia_id == dpia.id, Risk.organization_id == organization_id
                )
            )
        )
        .scalars()
        .all()
    )
    if not risks:
        return None

    unassessed = [r for r in risks if not (r.residual_likelihood and r.residual_impact)]
    if unassessed:
        # Fall back to the inherent level for anything unreassessed, so the
        # DPIA cannot improve just because work was left undone.
        levels = [
            risk_level_from(r.residual_likelihood, r.residual_impact)
            if r.residual_likelihood and r.residual_impact
            else risk_level_from(r.likelihood, r.impact)
            for r in risks
        ]
    else:
        levels = [
            risk_level_from(r.residual_likelihood, r.residual_impact)  # type: ignore[arg-type]
            for r in risks
        ]

    for level in ("high", "medium", "low"):
        if level in levels:
            dpia.residual_risk_level = level
            return level
    return None
