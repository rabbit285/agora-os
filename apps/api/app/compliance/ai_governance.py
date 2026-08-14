"""EU AI Act applicability screening and AI privacy assessment.

Both are **indicator-driven, not generative**, for the same reason the
framework assessment is: a model asked "is this high risk under the EU AI
Act?" will return a tier with an air of authority regardless of what it
knows about the system. The Act does not classify by vibe — it classifies
by whether the system does one of a specific list of things, and that list
is answerable with yes/no by the people who built it.

So the organization answers the indicators, and the rules map those
answers to a tier. The output always carries:

* which indicators were answered yes (the facts relied on),
* the rule that produced the tier (the reasoning),
* what remains uncertain,
* whether a human still has to look.

That separation is the guide's own requirement — fact, versus regulatory
analysis, versus needs-human-review — and it is what stops the screening
from reading as legal advice. Nothing here concludes that an organization
is compliant or in breach. It says which obligations appear to attach and
recommends who should confirm.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import AIAssessment, AISystem

# Article 5 — practices the Act prohibits outright. A "yes" here is not a
# risk rating, it is a stop.
PROHIBITED_INDICATORS: dict[str, str] = {
    "social_scoring": "Evaluates or classifies people's trustworthiness based on social behaviour",
    "manipulative_techniques": "Uses subliminal or purposefully manipulative techniques",
    "exploits_vulnerabilities": "Exploits vulnerabilities of age, disability, or social situation",
    "untargeted_face_scraping": "Builds facial recognition databases by untargeted scraping",
    "emotion_inference_work_education": "Infers emotions in the workplace or in education",
    "realtime_remote_biometric_id": "Real-time remote biometric identification in public spaces",
}

# Annex III — the enumerated high-risk use cases.
HIGH_RISK_INDICATORS: dict[str, str] = {
    "biometric_identification": "Biometric identification or categorisation of people",
    "critical_infrastructure": "Safety component of critical infrastructure",
    "education_access": "Determines access to, or evaluation in, education or training",
    "employment_decisions": "Recruitment, promotion, termination, or task allocation decisions",
    "essential_services": "Determines access to essential public or private services or credit",
    "law_enforcement": "Used by or for law enforcement",
    "migration_border": "Migration, asylum, or border control",
    "justice_democracy": "Administration of justice or democratic processes",
}

# Chapter IV — transparency obligations. These do not make a system high
# risk; they attach duties to tell people what they are dealing with.
TRANSPARENCY_INDICATORS: dict[str, str] = {
    "interacts_with_people": "Interacts directly with natural persons",
    "generates_content": "Generates or manipulates text, image, audio, or video content",
    "emotion_or_biometric_categorisation": "Performs emotion recognition or biometric categorisation",
}

ALL_INDICATORS = {
    **PROHIBITED_INDICATORS,
    **HIGH_RISK_INDICATORS,
    **TRANSPARENCY_INDICATORS,
}

# The privacy questions the guide's B7 expects an answer to. Held as data
# so the assessment records which were answered and which were skipped,
# rather than silently producing a shorter report.
PRIVACY_QUESTIONS: dict[str, str] = {
    "personal_data_processed": "What personal data does the system process?",
    "processing_purpose": "Why is that data processed?",
    "necessity": "Is each category necessary for the stated purpose?",
    "data_source": "Where does the data come from?",
    "provider_recipient": "Which provider or processor receives the data?",
    "international_transfer": "Does processing involve a transfer outside the EEA?",
    "retention": "How long is the data retained, by us and by the provider?",
    "data_subject_rights": "How can data subjects exercise their rights over this processing?",
    "dpia_required": "Does this processing require a DPIA?",
}


@dataclass(frozen=True)
class ScreeningResult:
    classification: str
    rationale: str
    facts_relied_on: list[str]
    uncertainties: list[str]
    requires_human_review: bool


def screen_eu_ai_act(
    indicators: dict[str, bool], *, unanswered: list[str] | None = None
) -> ScreeningResult:
    """Map declared indicators to an EU AI Act tier, with the reasoning.

    Deliberately conservative in one direction only: unanswered indicators
    never *lower* a tier, and anything that lands above `minimal` is
    flagged for human confirmation. Classifying an AI system is ultimately
    a legal judgement, and this function's job is to prepare that
    judgement, not to substitute for it.
    """
    unanswered = unanswered or []
    yes = {key for key, value in indicators.items() if value}

    prohibited_hits = sorted(yes & PROHIBITED_INDICATORS.keys())
    high_hits = sorted(yes & HIGH_RISK_INDICATORS.keys())
    transparency_hits = sorted(yes & TRANSPARENCY_INDICATORS.keys())

    uncertainties: list[str] = []
    if unanswered:
        uncertainties.append(
            "Not every indicator was answered, so this screening is based on partial "
            f"information. Unanswered: {', '.join(sorted(unanswered))}."
        )

    if prohibited_hits:
        return ScreeningResult(
            classification="unacceptable",
            rationale=(
                "One or more practices prohibited under Article 5 were declared. A system "
                "matching Article 5 may not be placed on the market or put into service in "
                "the EU at all — this is a stop, not a risk rating to be mitigated."
            ),
            facts_relied_on=[PROHIBITED_INDICATORS[k] for k in prohibited_hits],
            uncertainties=uncertainties,
            requires_human_review=True,
        )

    if high_hits:
        return ScreeningResult(
            classification="high",
            rationale=(
                "The declared use falls within one or more Annex III high-risk categories. "
                "High-risk systems carry obligations including risk management, data "
                "governance, technical documentation, logging, human oversight, and "
                "conformity assessment before deployment."
            ),
            facts_relied_on=[HIGH_RISK_INDICATORS[k] for k in high_hits],
            uncertainties=uncertainties,
            requires_human_review=True,
        )

    if transparency_hits:
        return ScreeningResult(
            classification="limited",
            rationale=(
                "No prohibited practice or Annex III high-risk use was declared, but the "
                "system triggers Chapter IV transparency obligations — people must be told "
                "they are interacting with an AI system, and generated content must be "
                "marked as such. This is a disclosure duty, not a high-risk classification."
            ),
            facts_relied_on=[TRANSPARENCY_INDICATORS[k] for k in transparency_hits],
            uncertainties=uncertainties,
            # Transparency duties are comparatively mechanical, so this
            # tier does not by itself demand legal sign-off — but partial
            # answers still do.
            requires_human_review=bool(unanswered),
        )

    return ScreeningResult(
        classification="minimal",
        rationale=(
            "None of the prohibited, Annex III high-risk, or transparency indicators were "
            "declared for this system. On the declared facts no specific EU AI Act "
            "obligation appears to attach beyond general good practice. This reflects what "
            "was declared, and is not an independent verification of it."
        ),
        facts_relied_on=[],
        uncertainties=uncertainties,
        requires_human_review=bool(unanswered),
    )


async def record_eu_ai_act_assessment(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ai_system: AISystem,
    indicators: dict[str, bool],
    assessed_by: uuid.UUID | None,
) -> tuple[AIAssessment, ScreeningResult]:
    """Screen the system and file the result against it.

    The screening may *raise* the recorded classification but never lowers
    it silently: someone who has already judged a system high risk keeps
    that judgement until they change it deliberately, rather than having a
    thin set of indicator answers quietly downgrade it.
    """
    unanswered = [key for key in ALL_INDICATORS if key not in indicators]
    result = screen_eu_ai_act(indicators, unanswered=unanswered)

    order = ["minimal", "limited", "high", "unacceptable"]
    if order.index(result.classification) > order.index(ai_system.risk_classification):
        ai_system.risk_classification = result.classification

    assessment = AIAssessment(
        organization_id=organization_id,
        ai_system_id=ai_system.id,
        assessment_type="eu_ai_act",
        # Screening is not a verdict on whether the system is operating
        # correctly, so it is never recorded as pass/fail — that vocabulary
        # belongs to control assessments.
        status="partial" if result.requires_human_review else "pass",
        notes=result.rationale,
        findings={
            "classification": result.classification,
            "rationale": result.rationale,
            "facts_relied_on": result.facts_relied_on,
            "uncertainties": result.uncertainties,
            "requires_human_review": result.requires_human_review,
            "indicators_answered": {k: v for k, v in indicators.items()},
            "indicators_unanswered": unanswered,
        },
        assessed_by=assessed_by,
    )
    db.add(assessment)
    ai_system.last_reviewed_at = datetime.now(UTC)
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=assessed_by,
        action="compliance.ai_system.eu_ai_act_screened",
        object_type="ai_system",
        object_id=str(ai_system.id),
        after_state={
            "classification": result.classification,
            "requires_human_review": result.requires_human_review,
        },
    )
    return assessment, result


async def record_privacy_assessment(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    ai_system: AISystem,
    answers: dict[str, str],
    assessed_by: uuid.UUID | None,
) -> AIAssessment:
    """File the privacy assessment, recording what was *not* answered.

    An assessment that silently omits the questions nobody answered reads
    as complete. Listing them keeps the difference between "no transfer
    happens" and "nobody has checked whether a transfer happens" visible,
    which is exactly the distinction a DPO needs.
    """
    unanswered = [key for key in PRIVACY_QUESTIONS if not answers.get(key)]
    dpia_flag = (answers.get("dpia_required") or "").strip().lower()
    dpia_indicated = dpia_flag.startswith("y")

    assessment = AIAssessment(
        organization_id=organization_id,
        ai_system_id=ai_system.id,
        assessment_type="privacy",
        status="partial" if unanswered else "pass",
        notes=(
            f"{len(PRIVACY_QUESTIONS) - len(unanswered)} of {len(PRIVACY_QUESTIONS)} "
            "privacy questions answered."
        ),
        findings={
            "questions": PRIVACY_QUESTIONS,
            "answers": answers,
            "unanswered": unanswered,
            "dpia_indicated": dpia_indicated,
            "requires_human_review": bool(unanswered) or dpia_indicated,
        },
        assessed_by=assessed_by,
    )
    db.add(assessment)
    ai_system.last_reviewed_at = datetime.now(UTC)
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=assessed_by,
        action="compliance.ai_system.privacy_assessed",
        object_type="ai_system",
        object_id=str(ai_system.id),
        after_state={"unanswered": len(unanswered), "dpia_indicated": dpia_indicated},
    )
    return assessment


def indicator_catalog() -> dict[str, Any]:
    """The indicator list, served to the UI so the questions live in one
    place rather than being duplicated in a form component."""
    return {
        "prohibited": PROHIBITED_INDICATORS,
        "high_risk": HIGH_RISK_INDICATORS,
        "transparency": TRANSPARENCY_INDICATORS,
        "privacy_questions": PRIVACY_QUESTIONS,
    }
