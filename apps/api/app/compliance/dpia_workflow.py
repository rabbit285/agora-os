"""Screening first, then the assessment — and never a blank form.

The DPIA flow had the right pieces in the wrong order. Selecting a
processing activity opened a full assessment: four empty prose boxes, no
risks, `Inherent risk: Low` on a document where nobody had assessed
anything, and no sign anywhere of a screening. `record_dpia_screening`
computed a recommendation, wrote an audit event and returned — nothing
reached the DPIA, so the page had nothing to show even after somebody
had screened.

The order this restores:

    screening → recommendation → **a person decides** → assessment

Nothing becomes a draft assessment until a controller says a DPIA is
required, and the screening that led there stays attached to it
afterwards, with who decided and why, because that record is the point.

Two rules run through the file.

**Veyntra counts; the controller concludes.** The recommendation comes
from Article 35(3) and the EDPB's nine criteria applied to reported
answers — arithmetic over a published rule. Whether a DPIA is required
is a decision, it is stored separately from the recommendation, and a
"not required" answer needs a reason.

**Nothing is assessed until somebody assesses it.** No inherent risk
before there are risks, no residual risk before mitigations, and no
completion while a required section is empty. A DPIA that fills its own
gaps with defaults is worse than an empty one, because an empty one
still looks unfinished.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance import dpia_quality
from app.compliance.dpia_screening import (
    ALL_CRITERIA,
    risk_level_from,
    screen_for_dpia,
)
from app.compliance.models import (
    DPIA,
    AISystem,
    DataTransfer,
    DpiaRiskSuggestion,
    ProcessingActivity,
    ProcessingActivityAISystem,
    ProcessingActivityVendor,
    Risk,
    Vendor,
)
from app.core.models import Approval

# Where a DPIA is in its own lifecycle. `screening` is the state this
# module adds: the record exists because somebody started screening, and
# it is not a draft assessment until they decide one is needed.
SCREENING = "screening"
DRAFT = "draft"
IN_REVIEW = "in_review"
APPROVED = "approved"
COMPLETED = "completed"
REJECTED = "rejected"
# Terminal, and off the assessment lifecycle entirely: somebody screened
# this and concluded no DPIA is needed. It used to be stored as
# `approved`, which reads on every list as though the assessment had been
# carried out and signed off — the opposite of what was decided.
NOT_REQUIRED = "not_required"

# The lifecycle, in order. Anything not in here is not a DPIA state.
LIFECYCLE = (SCREENING, DRAFT, IN_REVIEW, APPROVED, COMPLETED)

# What can follow what. Screening leads nowhere by hand: the way out of
# it is to decide it, which is a different endpoint with a different
# record, so a status dropdown cannot be used to skip the decision the
# screening exists to capture.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    SCREENING: (),
    DRAFT: (IN_REVIEW, REJECTED),
    IN_REVIEW: (DRAFT, APPROVED, REJECTED),
    # Not COMPLETED. Completion runs the check that freezes the
    # snapshot, so it happens through that endpoint — leaving it here
    # would let the status dropdown finish a DPIA with nothing recorded
    # about what it concluded.
    APPROVED: (IN_REVIEW,),
    # A completed DPIA is a statement about what was assessed. Reopening
    # it is a new assessment, not an edit to the old one.
    COMPLETED: (),
    REJECTED: (DRAFT,),
    NOT_REQUIRED: (),
}


def transition_refusal(current: str, target: str) -> str | None:
    """Why this status change cannot happen, or None if it can."""
    if current == target:
        return None
    allowed = TRANSITIONS.get(current)
    if allowed is None:
        return f"{current} is not a status this DPIA can move out of."
    if target in allowed:
        return None
    if current == SCREENING:
        return (
            "This DPIA is still being screened. Record the screening "
            "decision — whether an assessment is required — rather than "
            "setting a status by hand."
        )
    if current == COMPLETED:
        return (
            "This DPIA is complete and its record is frozen. Start a "
            "reassessment rather than editing what was concluded."
        )
    if current == NOT_REQUIRED:
        return (
            "The screening concluded no DPIA is required, so there is no "
            "assessment to move through review."
        )
    if target == COMPLETED:
        return "A DPIA is completed through the completion check, not by status."
    readable = ", ".join(allowed) or "nothing"
    return f"A {current} DPIA can only move to: {readable}."


DECISION_REQUIRED = "required"
DECISION_NOT_REQUIRED = "not_required"

# Prose Veyntra drafted rather than a person wrote. Prefixed so the
# distinction survives being read quickly, and so a reviewer editing the
# text removes the marker as they take ownership of it.
DRAFT_MARKER = "[Veyntra draft — review required]"


# Article 35(7)'s sections, in the order the Article states them.
SECTIONS: dict[str, str] = {
    "processing_description": "the description of the processing",
    "necessity_assessment": "the necessity assessment",
    "proportionality_assessment": "the proportionality assessment",
    "consultation_notes": "the consultation record",
}

# The three a reviewer signs off as prose. Consultation is deliberately
# not among them: it is resolved by recording the consultation decision,
# which is a statement about something that did or did not happen rather
# than an argument somebody drafted.
#
# They were once the same list, so a DPIA could show "No consultation
# performed" beside "Nobody has approved the consultation record" — two
# states for one fact, one of which then blocked completion after the
# question had been answered.
NARRATIVE_SECTIONS: dict[str, str] = {
    key: label for key, label in SECTIONS.items() if key != "consultation_notes"
}

# --- the one consultation state -----------------------------------------
CONSULTATION_NOT_DECIDED = "not_decided"
CONSULTATION_PERFORMED = "consultation_performed"
CONSULTATION_NONE = "no_consultation"


def consultation_state(dpia: DPIA) -> str:
    """Where the consultation stands, from the single field that holds it."""
    if dpia.consultation_performed is None:
        return CONSULTATION_NOT_DECIDED
    return (
        CONSULTATION_PERFORMED
        if dpia.consultation_performed
        else CONSULTATION_NONE
    )


def consultation_resolved(dpia: DPIA) -> bool:
    """True once somebody has answered Article 35(2) either way."""
    return dpia.consultation_performed is not None


# --- what the risk review concluded -------------------------------------
RISK_NOT_REVIEWED = "not_reviewed"
RISKS_IDENTIFIED = "risks_identified"
NO_MATERIAL_RISKS = "no_material_risks"


def risk_conclusion_of(dpia: DPIA) -> str:
    return dpia.risk_conclusion or RISK_NOT_REVIEWED


def risk_review_complete(dpia: DPIA) -> bool:
    """A risk assessment somebody actually carried out.

    "Nobody looked" and "looked, and judged none material" are different
    claims that a risk count of zero cannot tell apart, which is why the
    conclusion is stored rather than inferred.
    """
    return risk_conclusion_of(dpia) in (RISKS_IDENTIFIED, NO_MATERIAL_RISKS)


class DpiaRefused(Exception):
    """The DPIA cannot move as asked, and why."""


def _now() -> datetime:
    return datetime.now(UTC)


# --- finding or opening the one DPIA for this processing ----------------


async def existing_for(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    processing_activity_id: uuid.UUID | None = None,
    ai_system_id: uuid.UUID | None = None,
) -> DPIA | None:
    """The DPIA already covering this processing, if there is one.

    Screening the same activity twice must reach the same record. A
    second DPIA for one activity is not a second assessment, it is two
    half-finished ones and an auditor asking which is authoritative.
    """
    query = select(DPIA).where(DPIA.organization_id == organization_id)
    if processing_activity_id is not None:
        query = query.where(DPIA.processing_activity_id == processing_activity_id)
    elif ai_system_id is not None:
        query = query.where(DPIA.ai_system_id == ai_system_id)
    else:
        return None
    return (
        (await db.execute(query.order_by(DPIA.created_at))).scalars().first()
    )


# --- what the assessment can be drafted from ----------------------------


@dataclass
class ProcessingContext:
    """The facts an assessment is written from, already on record."""

    title: str
    purpose: str | None = None
    data_subjects: str | None = None
    data_categories: list[str] = field(default_factory=list)
    special_category: bool = False
    retention: str | None = None
    ai_systems: list[str] = field(default_factory=list)
    vendors: list[tuple[str, str | None]] = field(default_factory=list)
    transfers: list[str] = field(default_factory=list)


async def context_for(
    db: AsyncSession, *, activity: ProcessingActivity
) -> ProcessingContext:
    ai_rows = (
        await db.execute(
            select(AISystem)
            .join(
                ProcessingActivityAISystem,
                ProcessingActivityAISystem.ai_system_id == AISystem.id,
            )
            .where(ProcessingActivityAISystem.processing_activity_id == activity.id)
        )
    ).scalars().all()
    vendor_rows = (
        await db.execute(
            select(Vendor)
            .join(
                ProcessingActivityVendor,
                ProcessingActivityVendor.vendor_id == Vendor.id,
            )
            .where(ProcessingActivityVendor.processing_activity_id == activity.id)
        )
    ).scalars().all()
    transfer_rows = (
        await db.execute(
            select(DataTransfer).where(
                DataTransfer.processing_activity_id == activity.id
            )
        )
    ).scalars().all()

    return ProcessingContext(
        title=activity.name,
        purpose=activity.purpose,
        data_subjects=activity.data_subjects,
        data_categories=list(activity.data_categories or []),
        special_category=bool(activity.special_category),
        retention=activity.retention_period,
        ai_systems=[row.name for row in ai_rows],
        vendors=[(row.name, row.country) for row in vendor_rows],
        transfers=[
            f"{row.recipient_name} ({row.destination_country})"
            for row in transfer_rows
        ],
    )


def suggested_answers(context: ProcessingContext) -> dict[str, bool]:
    """Screening answers the record already supports.

    Only criteria a declared fact speaks to. Nothing is inferred about
    scale or monitoring from the existence of a customer database —
    those are the questions the screening is asking, and answering them
    from nothing would make the recommendation a recommendation about
    nothing.
    """
    answers: dict[str, bool] = {}
    if context.special_category:
        answers["sensitive_data"] = True
    if context.ai_systems:
        answers["innovative_technology"] = True
    return answers


# --- the assessment, drafted from those facts ---------------------------


def _sentence(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


def draft_sections(context: ProcessingContext) -> dict[str, str | None]:
    """Article 35(7)'s narrative sections, drafted from what is on record.

    These are the analysis, not the questions. The drafts used to end on
    an instruction — "State why this processing is necessary", "Assess
    whether the data collected is limited" — which a reviewer could press
    Approve on, producing a formal-looking DPIA whose argument was the
    prompt for writing one. `dpia_quality.section_problem` now refuses
    that, and this supplies something worth approving instead.

    Two things the drafting will not do. It does not assert a lawful
    basis or an Article 9 condition: those are the conclusions the review
    exists to reach. And where the record is missing what a section is
    judged against, it says so plainly rather than writing around the
    gap — a proportionality paragraph that reads well without knowing
    what data is processed is worse than one that admits it cannot be
    concluded.
    """
    def _stop(text: str) -> str:
        """One full stop at the end, however the source was punctuated."""
        cleaned = text.strip().rstrip(".").strip()
        return f"{cleaned}." if cleaned else ""

    parts: list[str] = []
    if context.purpose:
        purpose = context.purpose.strip()
        parts.append(f"The processing exists to {purpose[0].lower()}{purpose[1:]}")
    if context.data_subjects:
        scope = f"It concerns {context.data_subjects.strip().lower()}"
        if context.data_categories:
            scope += f", and covers {_sentence(context.data_categories).lower()}"
        parts.append(scope)
    elif context.data_categories:
        parts.append(f"It covers {_sentence(context.data_categories).lower()}")
    description = " ".join(filter(None, (_stop(part) for part in parts)))
    if context.ai_systems:
        description += (
            f" The processing runs through {_sentence(context.ai_systems)}."
        )
    if context.vendors:
        named = _sentence(
            [f"{name} ({country})" if country else name for name, country in context.vendors]
        )
        description += f" {named} acts as a processor."
    if context.transfers:
        description += (
            f" Personal data is transferred to {_sentence(context.transfers)}."
        )
    if context.special_category:
        description += " The activity records special-category data."

    # --- necessity, as an argument rather than a prompt ----------------
    #
    # This used to end on "State why this processing is necessary…", which
    # a reviewer could approve as though it were the assessment. A draft
    # has to be the analysis somebody edits, not the question they were
    # asked. It stays marked as Veyntra's words, and approving it is
    # still the controller adopting the argument as their own.
    necessity_parts: list[str] = []
    if context.purpose:
        purpose = context.purpose.strip().rstrip(".")
        subjects = (context.data_subjects or "the data subjects").strip().lower()
        necessity_parts.append(
            f"Processing {subjects}' personal data is necessary to "
            f"{purpose[0].lower()}{purpose[1:]}, which is the purpose recorded "
            "for this activity."
        )
        if context.data_categories:
            necessity_parts.append(
                f"Achieving it requires {_sentence(context.data_categories).lower()}, "
                "because that is the information the recorded purpose is "
                "carried out on."
            )
        # The less-intrusive alternative, named rather than requested.
        alternative = (
            "Operating without an automated system was considered; handling "
            "this manually would process the same personal data with weaker "
            "access control and audit, so it is not less intrusive."
            if context.ai_systems
            else "Achieving the same purpose without this personal data was "
            "considered, and the recorded purpose cannot be met without the "
            "categories above."
        )
        necessity_parts.append(alternative)
        necessity_parts.append(
            "Processing is therefore limited to the minimum information "
            "needed for this purpose."
        )
        if context.special_category:
            necessity_parts.append(
                "Special-category data is recorded against this activity, so "
                "an Article 9 condition must be identified and relied on in "
                "addition to the lawful basis — that condition is a "
                "controller decision and is not asserted here."
            )
        necessity = f"{DRAFT_MARKER} " + " ".join(necessity_parts)
    else:
        # No purpose means no necessity argument exists to draft. Saying
        # so is a finding; inventing one would not be.
        necessity = (
            f"{DRAFT_MARKER} This activity has no recorded purpose, so no "
            "necessity argument can be made for it. Necessity is assessed "
            "against a purpose, and none has been recorded."
        )

    # --- proportionality, likewise --------------------------------------
    proportion: list[str] = []
    if context.data_categories:
        proportion.append(
            f"The processing collects {_sentence(context.data_categories).lower()}, "
            "which is the data the recorded purpose operates on."
        )
    else:
        proportion.append(
            "No personal-data categories are recorded against this activity, "
            "so whether the data collected is limited to what the purpose "
            "requires cannot be established from the record."
        )
    if context.retention:
        proportion.append(
            f"It is retained for {context.retention.strip().rstrip('.')}, which "
            "bounds how long the data remains available."
        )
    else:
        proportion.append(
            "No retention period is recorded, so nothing currently limits how "
            "long the data is held."
        )
    if context.vendors:
        named = _sentence([name for name, _ in context.vendors])
        proportion.append(
            f"{named} processes the data on the organization's behalf under a "
            "processor relationship, which keeps the data within a contracted "
            "boundary."
        )
    if context.transfers:
        proportion.append(
            f"Personal data reaches {_sentence(context.transfers)}, so the "
            "safeguards relied on for that transfer form part of the "
            "proportionality position."
        )
    if context.special_category:
        proportion.append(
            "The activity records special-category data, which raises what "
            "proportionality requires of the safeguards applied."
        )
    proportion.append(
        "On the facts above the processing is proportionate to its purpose "
        "where the recorded categories and retention are not exceeded."
        if context.data_categories and context.retention
        else "Proportionality cannot be concluded from the record as it "
        "stands, because the information it would be judged against is "
        "incomplete."
    )
    proportion = [f"{DRAFT_MARKER} " + " ".join(proportion)]

    return {
        "processing_description": (
            f"{DRAFT_MARKER} {description.strip()}"
            if description.strip()
            else f"{DRAFT_MARKER} Nothing is recorded about this processing yet."
        ),
        "necessity_assessment": necessity,
        "proportionality_assessment": " ".join(proportion),
        # Deliberately not drafted, and deliberately left empty rather
        # than filled with a prompt. Whether a DPO or data subjects were
        # consulted is a fact about an event, Veyntra has no record of it
        # either way, and a prompt sitting in the field is the thing a
        # reviewer ends up approving. The consultation record asks the
        # question instead.
        "consultation_notes": None,
    }


# --- risks Veyntra can propose ------------------------------------------


@dataclass
class SuggestedRisk:
    title: str
    description: str
    reason: str


def suggest_risks(context: ProcessingContext) -> list[SuggestedRisk]:
    """Candidate risks the recorded facts imply.

    Proposals, each tied to a fact on record. Nothing here is added to
    the DPIA — a risk register assembled without a person deciding these
    are the real risks is a list, not an assessment.
    """
    risks: list[SuggestedRisk] = []

    if context.ai_systems:
        systems = _sentence(context.ai_systems)
        risks.append(
            SuggestedRisk(
                title="AI output may be inaccurate or inappropriate",
                description=(
                    f"{systems} generates content that reaches data subjects. "
                    "Inaccurate or inappropriate output can cause harm before "
                    "anybody notices."
                ),
                reason=f"An AI system is recorded against this activity: {systems}.",
            )
        )
        risks.append(
            SuggestedRisk(
                title="More personal data than necessary is sent to the model",
                description=(
                    "Free-text content passed to a model can carry more than "
                    "the purpose requires, including data nobody intended to "
                    "send."
                ),
                reason="The processing runs through an AI system.",
            )
        )

    if context.vendors:
        named = _sentence([name for name, _ in context.vendors])
        risks.append(
            SuggestedRisk(
                title="Personal data is disclosed to an unauthorised party",
                description=(
                    f"{named} processes personal data on the organization's "
                    "behalf. A failure of access control or contract at the "
                    "processor reaches the data subjects directly."
                ),
                reason=f"A processor is recorded against this activity: {named}.",
            )
        )

    if context.transfers:
        risks.append(
            SuggestedRisk(
                title="International transfer weakens available protections",
                description=(
                    f"Data reaches {_sentence(context.transfers)}. Rights and "
                    "remedies available to data subjects may differ there."
                ),
                reason="A transfer is recorded against this activity.",
            )
        )

    if context.special_category or any(
        "free" in category.lower() or "content" in category.lower()
        for category in context.data_categories
    ):
        risks.append(
            SuggestedRisk(
                title="Special-category data appears without being asked for",
                description=(
                    "Free-text fields can contain health, belief or other "
                    "special-category information a data subject volunteers, "
                    "outside any Article 9 condition the organization relies "
                    "on."
                ),
                reason=(
                    "The activity records special-category data."
                    if context.special_category
                    else "The activity records free-text content."
                ),
            )
        )

    if not context.retention:
        risks.append(
            SuggestedRisk(
                title="Personal data is kept longer than the purpose requires",
                description=(
                    "No retention period is recorded, so nothing limits how "
                    "long this data is held."
                ),
                reason="No retention period is recorded against this activity.",
            )
        )

    return risks


# --- what the DPIA can honestly say about its own risk ------------------


@dataclass
class RiskState:
    """Whether a level can be stated at all, and why not when it cannot."""

    inherent: str | None
    residual: str | None
    risk_count: int
    assessed_count: int
    mitigated_count: int
    can_calculate_residual: bool
    blocked_reason: str | None = None


async def risk_state(
    db: AsyncSession, *, organization_id: uuid.UUID, dpia: DPIA
) -> RiskState:
    """The DPIA's risk position, computed rather than defaulted.

    With no risks there is no inherent level — not "low". A level nobody
    derived, printed on the document whose purpose is to record that
    somebody derived one, is the most misleading thing this page can say.
    """
    risks = list(
        (
            await db.execute(
                select(Risk).where(
                    Risk.dpia_id == dpia.id,
                    Risk.organization_id == organization_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not risks:
        return RiskState(
            inherent=None,
            residual=None,
            risk_count=0,
            assessed_count=0,
            mitigated_count=0,
            can_calculate_residual=False,
            blocked_reason=(
                "No risks have been raised yet. There is nothing to rate."
            ),
        )

    assessed = [r for r in risks if r.likelihood and r.impact]
    mitigated = [r for r in risks if r.residual_likelihood and r.residual_impact]

    inherent = None
    if assessed:
        levels = [risk_level_from(r.likelihood, r.impact) for r in assessed]
        for level in ("high", "medium", "low"):
            if level in levels:
                inherent = level
                break

    if len(assessed) < len(risks):
        return RiskState(
            inherent=inherent,
            residual=None,
            risk_count=len(risks),
            assessed_count=len(assessed),
            mitigated_count=len(mitigated),
            can_calculate_residual=False,
            blocked_reason=(
                f"{len(risks) - len(assessed)} risk"
                f"{'' if len(risks) - len(assessed) == 1 else 's'} still need a "
                "likelihood and an impact."
            ),
        )
    if not mitigated:
        return RiskState(
            inherent=inherent,
            residual=None,
            risk_count=len(risks),
            assessed_count=len(assessed),
            mitigated_count=0,
            can_calculate_residual=False,
            blocked_reason=(
                "No risk has been reassessed after mitigation. A residual "
                "rating with nothing behind it is the inherent rating with a "
                "different name."
            ),
        )

    return RiskState(
        inherent=inherent,
        residual=dpia.residual_risk_level,
        risk_count=len(risks),
        assessed_count=len(assessed),
        mitigated_count=len(mitigated),
        can_calculate_residual=True,
    )


# --- the screening decision ---------------------------------------------


async def record_screening(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dpia: DPIA,
    answers: dict[str, bool],
    actor_user_id: uuid.UUID | None,
) -> DPIA:
    """Run the screening and keep it on the DPIA.

    The result used to exist only as an audit event, so the page that
    should show "here is what was screened and why" had nothing to read.
    """
    unanswered = [key for key in ALL_CRITERIA if key not in answers]
    result = screen_for_dpia(answers, unanswered=unanswered)

    dpia.screening_outcome = result.outcome
    dpia.screening_findings = {
        "rationale": result.rationale,
        "criteria_met": list(result.criteria_met),
        "mandatory_triggers": list(result.mandatory_triggers),
        "unanswered": list(result.unanswered),
        "answers": {key: bool(value) for key, value in answers.items()},
    }
    dpia.screened_at = _now()
    # Re-running the screening refreshes what was counted. It does not
    # reopen a decision somebody already made: an assessment in progress
    # does not fall back to "being screened" because the criteria were
    # recounted, and a completed one certainly does not.
    if dpia.screening_decision is None and dpia.status not in (
        IN_REVIEW,
        APPROVED,
        COMPLETED,
    ):
        dpia.status = SCREENING

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dpia.screened",
        object_type="dpia",
        object_id=str(dpia.id),
        after_state={
            "outcome": result.outcome,
            "criteria_met": len(result.criteria_met),
        },
    )
    await db.flush()
    return dpia


async def decide_screening(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dpia: DPIA,
    decision: str,
    rationale: str | None,
    actor_user_id: uuid.UUID | None,
    context: ProcessingContext | None = None,
) -> DPIA:
    """A person concludes whether a DPIA is required.

    Confirming opens the assessment and drafts what can be drafted.
    Declining needs a reason: "we looked and decided no" is a defensible
    record and an unexplained no is not.
    """
    if dpia.screening_outcome is None:
        raise DpiaRefused(
            "This has not been screened yet. Run the screening before "
            "deciding on it."
        )
    if decision not in (DECISION_REQUIRED, DECISION_NOT_REQUIRED):
        raise DpiaRefused(f"Unknown decision: {decision}")
    if decision == DECISION_NOT_REQUIRED and not (rationale or "").strip():
        raise DpiaRefused(
            "Deciding a DPIA is not required needs a reason. That reason is "
            "the record you would rely on if the decision were ever "
            "questioned."
        )

    dpia.screening_decision = decision
    dpia.screening_decided_by = actor_user_id
    dpia.screening_decided_at = _now()
    dpia.screening_rationale = (rationale or "").strip() or None

    if decision == DECISION_REQUIRED:
        dpia.status = DRAFT
        if context is not None:
            # Only where the reviewer has not already written something.
            # Overwriting their words with a draft would be the product
            # taking the assessment back off them.
            for field_name, value in draft_sections(context).items():
                if not (getattr(dpia, field_name) or "").strip():
                    setattr(dpia, field_name, value)
            dpia.source_digest = context_digest(context)
    else:
        # Terminal, and not `approved`. Nothing was assessed, so there is
        # no assessment to approve — the screening itself is the record,
        # and any sections a previous pass drafted are cleared rather
        # than left sitting under a decision that says they should not
        # exist.
        dpia.status = NOT_REQUIRED
        for field_name in SECTIONS:
            value = (getattr(dpia, field_name) or "").strip()
            if value.startswith(DRAFT_MARKER):
                setattr(dpia, field_name, None)
        dpia.section_reviews = {}

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dpia.screening_decided",
        object_type="dpia",
        object_id=str(dpia.id),
        after_state={
            "decision": decision,
            "recommendation": dpia.screening_outcome,
            "rationale": dpia.screening_rationale,
        },
    )
    await db.flush()
    return dpia


# --- content quality, as opposed to workflow completeness ---------------


async def content_gaps(
    db: AsyncSession, *, organization_id: uuid.UUID, dpia: DPIA
) -> tuple[list, list, set[str]]:
    """Missing facts, unanswered Article 9 signals, and stale sign-offs.

    Computed once and shared, because the completion predicate and the
    screen both need it and each is a query against the processing
    activity.

    Returns `(missing_facts, unresolved_special_signals, stale_sections)`.
    A DPIA with no linked activity returns nothing: there is no record to
    read facts out of, and inventing gaps against one that does not exist
    would block a DPIA for the wrong reason.
    """
    if not dpia.processing_activity_id:
        return [], [], set()
    activity = await db.get(ProcessingActivity, dpia.processing_activity_id)
    if activity is None:
        return [], [], set()

    context = await context_for(db, activity=activity)
    missing = dpia_quality.missing_facts(
        context, activity_id=str(dpia.processing_activity_id)
    )

    # Signals stay unresolved only while nobody has answered them. Either
    # answer closes them: confirmed present, or ruled out with a reason.
    unresolved = (
        dpia_quality.special_category_signals(context)
        if dpia.special_category_confirmed is None
        else []
    )

    # §12: a sign-off is about particular words describing particular
    # facts. When the facts move, the words may no longer hold.
    current = context_digest(context)
    stale = {
        section
        for section, review in (dpia.section_reviews or {}).items()
        if isinstance(review, dict)
        and review.get("context_digest")
        and review["context_digest"] != current
    }
    return missing, unresolved, stale


# --- what stops it being finished ---------------------------------------


@dataclass
class Blocker:
    code: str
    message: str


async def completion_blockers(
    db: AsyncSession, *, organization_id: uuid.UUID, dpia: DPIA
) -> list[Blocker]:
    """Everything standing between this DPIA and being complete.

    Two kinds of thing, listed together and specifically so the work can
    be finished in one pass. **Workflow completeness** is whether each
    step happened; **content completeness** is whether what it produced
    is an assessment somebody could defend. A DPIA used to pass the first
    while failing the second — guidance approved as an argument, a
    rationale of "ok", no data categories recorded — and completed
    looking formal and answering nothing.
    """
    blockers: list[Blocker] = []
    missing, unresolved_special, stale_sections = await content_gaps(
        db, organization_id=organization_id, dpia=dpia
    )

    if dpia.screening_decision is None:
        blockers.append(
            Blocker(
                "screening_undecided",
                "The screening has no recorded decision yet.",
            )
        )

    elif dpia.screening_decision == DECISION_NOT_REQUIRED:
        # Nothing further is owed. The screening is the record.
        return []

    reviews = dpia.section_reviews or {}
    for field_name, label in NARRATIVE_SECTIONS.items():
        value = (getattr(dpia, field_name) or "").strip()
        # Content quality first: an approved section that still holds
        # guidance is worse than an unapproved one, because the record
        # says somebody stood behind it.
        problem = dpia_quality.section_problem(field_name, value)
        if problem is not None:
            blockers.append(Blocker(f"{field_name}_not_substantive", problem))
        elif field_name not in reviews:
            blockers.append(
                Blocker(
                    f"{field_name}_unreviewed",
                    f"Nobody has approved {label}."
                    + (
                        " It is still Veyntra's draft."
                        if value.startswith(DRAFT_MARKER)
                        else ""
                    ),
                )
            )
        elif stale_sections and field_name in stale_sections:
            blockers.append(
                Blocker(
                    f"{field_name}_stale",
                    f"{label.capitalize()} was approved against processing "
                    "details that have since changed. It needs another look.",
                )
            )

    # §5/§7: absent context is not a benign finding. A DPIA written
    # against a record with no data categories cannot say what was
    # assessed.
    for gap in missing:
        blockers.append(Blocker(gap.code, gap.message))

    # §6: Veyntra detected Article 9 signals and nobody has answered.
    # "No categories recorded" must never become "nothing sensitive here".
    if unresolved_special:
        kinds = _sentence([signal.kind for signal in unresolved_special])
        blockers.append(
            Blocker(
                "special_category_unconfirmed",
                f"Possible special-category data ({kinds}) was detected in "
                "this processing and has not been confirmed or ruled out.",
            )
        )

    if not consultation_resolved(dpia):
        blockers.append(
            Blocker(
                "consultation_not_recorded",
                "The consultation decision has not been recorded. Article "
                "35(2) needs an answer either way — including that none was "
                "needed, and why.",
            )
        )

    pending = await pending_risk_suggestions(
        db, organization_id=organization_id, dpia=dpia
    )
    if pending:
        blockers.append(
            Blocker(
                "suggested_risks_unreviewed",
                f"{pending} suggested risk{'' if pending == 1 else 's'} "
                f"{'has' if pending == 1 else 'have'} not been approved or "
                "dismissed.",
            )
        )

    state = await risk_state(db, organization_id=organization_id, dpia=dpia)

    if not risk_review_complete(dpia):
        # Not "no risks have been raised" — that confused an unreviewed
        # DPIA with one whose reviewer had concluded there was nothing
        # material, and forced the second to invent a risk to finish.
        blockers.append(
            Blocker(
                "risk_review_incomplete",
                "The risk assessment has not been reviewed."
                + (
                    ""
                    if state.risk_count
                    else " Add the risks this processing carries, or record "
                    "that none are material and why."
                ),
            )
        )
    elif state.risk_count:
        # A register with risks on it still has to add up.
        if state.blocked_reason:
            blockers.append(Blocker("risks_incomplete", state.blocked_reason))
        elif dpia.residual_risk_level is None:
            blockers.append(
                Blocker(
                    "residual_not_calculated",
                    "The residual risk has not been calculated.",
                )
            )

    # Article 36(1): high residual risk is the case where the controller
    # cannot simply sign its own homework.
    if dpia.residual_risk_level == "high":
        approval = await _approval_for(db, dpia=dpia)
        if approval is None:
            blockers.append(
                Blocker(
                    "high_residual_needs_approval",
                    "The residual risk is high. That needs a recorded "
                    "approval before this can be completed — Article 36 "
                    "treats unmitigated high risk as the case a controller "
                    "cannot sign off alone.",
                )
            )
        elif approval.status != "approved":
            blockers.append(
                Blocker(
                    "high_residual_approval_pending",
                    "The approval for this DPIA's high residual risk is "
                    f"{approval.status}. Article 36 treats unmitigated high "
                    "risk as the case a controller cannot sign off alone.",
                )
            )

    return blockers


async def _approval_for(db: AsyncSession, *, dpia: DPIA) -> Approval | None:
    if dpia.approval_id is None:
        return None
    return await db.get(Approval, dpia.approval_id)


async def pending_risk_suggestions(
    db: AsyncSession, *, organization_id: uuid.UUID, dpia: DPIA
) -> int:
    """How many proposed risks nobody has ruled on yet."""
    return int(
        await db.scalar(
            select(func.count(DpiaRiskSuggestion.id)).where(
                DpiaRiskSuggestion.dpia_id == dpia.id,
                DpiaRiskSuggestion.organization_id == organization_id,
                DpiaRiskSuggestion.status == "suggested",
            )
        )
        or 0
    )


# --- Article 35(2): the one consultation decision -----------------------


async def record_consultation(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dpia: DPIA,
    performed: bool,
    party: str | None,
    role: str | None,
    consulted_at: datetime | None,
    notes: str | None,
    actor_user_id: uuid.UUID | None,
) -> DPIA:
    """Resolve the consultation, in either direction.

    Both answers are decisions. "No consultation was carried out" is a
    conclusion somebody reached and can defend; the absence of an answer
    is not, which is why they are stored differently and why declining
    needs a reason for the same argument that makes "DPIA not required"
    need one.

    Veyntra never drafts any of this. Whether a DPO advised is a fact
    about an event, and inventing the advice would be fabricating a
    compliance record.

    Writing the record is also what satisfies Article 35(7)'s
    consultation section — there is no second sign-off, because there is
    only one decision here to make.
    """
    # Captured before the write, so a change to an existing decision is
    # auditable as a change rather than as a fresh record.
    before = {
        "state": consultation_state(dpia),
        "party": dpia.consulted_party,
        "role": dpia.consulted_role,
        "notes": dpia.consultation_notes,
    }
    changing = consultation_resolved(dpia)

    if performed and not (party or "").strip():
        raise DpiaRefused(
            "Recording that a consultation happened needs to say who was "
            "consulted."
        )
    if not performed and not (notes or "").strip():
        raise DpiaRefused(
            "Recording that no consultation was needed requires a reason. "
            "That reason is the record you would rely on if the decision "
            "were ever questioned."
        )

    dpia.consultation_performed = performed
    dpia.consulted_party = (party or "").strip() or None if performed else None
    dpia.consulted_role = (role or "").strip() or None if performed else None
    dpia.consulted_at = consulted_at if performed else None
    dpia.consultation_notes = (notes or "").strip() or None
    dpia.consultation_recorded_by = actor_user_id
    dpia.consultation_recorded_at = _now()

    # Any earlier sign-off on the old consultation *section* is about
    # words that no longer govern anything. Dropping it stops the page
    # showing a stale "Approved" beside a decision made afterwards.
    reviews = dict(dpia.section_reviews or {})
    reviews.pop("consultation_notes", None)
    dpia.section_reviews = reviews

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=(
            # A revision of an answered question is a different event from
            # answering it, and an auditor reading the log should not have
            # to infer which happened from timestamps.
            "compliance.dpia.consultation_changed"
            if changing
            else "compliance.dpia.consultation_performed"
            if performed
            else "compliance.dpia.consultation_not_performed"
        ),
        object_type="dpia",
        object_id=str(dpia.id),
        before_state=before if changing else None,
        after_state={
            "state": consultation_state(dpia),
            "party": dpia.consulted_party,
            "role": dpia.consulted_role,
            "reason": None if performed else dpia.consultation_notes,
        },
    )
    await db.flush()
    return dpia


# --- and the one risk-review conclusion ---------------------------------


async def conclude_no_material_risks(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dpia: DPIA,
    rationale: str,
    actor_user_id: uuid.UUID | None,
) -> DPIA:
    """Record that the risks were reviewed and none met the threshold.

    Refused while anything is still open, because the conclusion is a
    claim about a completed review: a suggestion nobody ruled on means
    the review is not finished, and an accepted risk on the register
    contradicts the conclusion outright.
    """
    pending = await pending_risk_suggestions(
        db, organization_id=organization_id, dpia=dpia
    )
    if pending:
        raise DpiaRefused(
            f"{pending} suggested risk{'' if pending == 1 else 's'} "
            f"{'is' if pending == 1 else 'are'} still waiting on a decision. "
            "Concluding that nothing is material means having looked at "
            "everything proposed."
        )
    accepted = int(
        await db.scalar(
            select(func.count(Risk.id)).where(
                Risk.dpia_id == dpia.id, Risk.organization_id == organization_id
            )
        )
        or 0
    )
    if accepted:
        raise DpiaRefused(
            f"This DPIA has {accepted} risk{'' if accepted == 1 else 's'} on "
            "its register, so it has identified risks. Remove them, or leave "
            "the conclusion as it stands."
        )
    # "ok" was the case that prompted this, but a character count would
    # also pass a restatement of the conclusion. The test is whether the
    # text engages with anything concrete about the processing.
    weak = dpia_quality.rationale_problem(rationale)
    if weak is not None:
        raise DpiaRefused(weak)

    before = {
        "conclusion": risk_conclusion_of(dpia),
        "rationale": dpia.risk_conclusion_rationale,
    }
    changing = dpia.risk_conclusion is not None

    dpia.risk_conclusion = NO_MATERIAL_RISKS
    dpia.risk_conclusion_rationale = rationale.strip()
    dpia.risk_reviewed_by = actor_user_id
    dpia.risk_reviewed_at = _now()
    # Nothing to rate, and "not assessed" would misread as "nobody
    # looked" on a DPIA where somebody did.
    dpia.risk_level = None
    dpia.residual_risk_level = None

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=(
            "compliance.dpia.risk_conclusion_changed"
            if changing
            else "compliance.dpia.no_material_risks_concluded"
        ),
        object_type="dpia",
        object_id=str(dpia.id),
        before_state=before if changing else None,
        after_state={
            "conclusion": NO_MATERIAL_RISKS,
            "rationale": dpia.risk_conclusion_rationale,
        },
    )
    await db.flush()
    return dpia


async def note_risks_identified(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dpia: DPIA,
    actor_user_id: uuid.UUID | None,
) -> DPIA:
    """A risk reached the register, so that is what the review concluded.

    Called whenever a risk is accepted. It also clears an earlier "no
    material risks" conclusion, which the presence of a risk contradicts
    — leaving both would let a DPIA claim it found nothing while listing
    what it found.
    """
    if dpia.risk_conclusion == RISKS_IDENTIFIED:
        return dpia
    before = {
        "conclusion": risk_conclusion_of(dpia),
        "rationale": dpia.risk_conclusion_rationale,
    }
    overturning = dpia.risk_conclusion == NO_MATERIAL_RISKS

    dpia.risk_conclusion = RISKS_IDENTIFIED
    dpia.risk_conclusion_rationale = None
    dpia.risk_reviewed_by = actor_user_id
    dpia.risk_reviewed_at = _now()

    # A risk arriving after somebody concluded there were none overturns
    # that conclusion, which is a decision worth its own audit line —
    # silently dropping the rationale would erase why they had concluded
    # otherwise.
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=(
            "compliance.dpia.risk_conclusion_changed"
            if overturning
            else "compliance.dpia.risks_identified"
        ),
        object_type="dpia",
        object_id=str(dpia.id),
        before_state=before if overturning else None,
        after_state={"conclusion": RISKS_IDENTIFIED},
    )
    await db.flush()
    return dpia


# --- recording that a person read a section -----------------------------


def approve_section(
    dpia: DPIA,
    *,
    section: str,
    actor_user_id: uuid.UUID | None,
    context_digest_at_approval: str | None = None,
) -> None:
    """Record that somebody signed off one Article 35(7) section.

    Held separately from the text because agreeing with a draft is a
    decision, not an edit. Inferring review from "the wording changed"
    would mean a reviewer who agrees verbatim has to alter the words
    before the product believes them.
    """
    if section == "consultation_notes":
        raise DpiaRefused(
            "The consultation record is resolved by recording the "
            "consultation decision, not by approving it separately."
        )
    if section not in SECTIONS:
        raise DpiaRefused(f"Unknown section: {section}")
    # A reviewer pressing Approve on Veyntra's own prompt is the failure
    # this exists to stop: it produced a formal-looking DPIA whose
    # necessity argument was the instruction to write one.
    problem = dpia_quality.section_problem(section, getattr(dpia, section))
    if problem is not None:
        raise DpiaRefused(problem)

    reviews = dict(dpia.section_reviews or {})
    reviews[section] = {
        "approved_by": str(actor_user_id) if actor_user_id else None,
        "approved_at": _now().isoformat(),
        # What the processing looked like when this was approved. A
        # sign-off is a statement about particular words *about
        # particular facts*; when the facts move, the words may no longer
        # hold, and §12 wants that surfaced rather than silently kept.
        "context_digest": context_digest_at_approval,
    }
    dpia.section_reviews = reviews


def unreview_changed_sections(dpia: DPIA, changed: Iterable[str]) -> list[str]:
    """Drop the sign-off from sections whose text has just been rewritten.

    An approval is a statement about particular words. Editing them
    afterwards and keeping the tick would leave the record saying
    somebody approved text they never saw.
    """
    reviews = dict(dpia.section_reviews or {})
    dropped = [section for section in changed if section in reviews]
    for section in dropped:
        reviews.pop(section, None)
    dpia.section_reviews = reviews
    return dropped


# --- has anything underneath moved since this was assessed? -------------


def context_digest(context: ProcessingContext) -> str:
    """A fingerprint of the processing an assessment was written against.

    Compared later to notice that the ROPA, the vendor or the transfers
    have moved, without diffing two snapshots on every page load.
    """
    payload = json.dumps(
        {
            "purpose": context.purpose,
            "data_subjects": context.data_subjects,
            "data_categories": sorted(context.data_categories),
            "special_category": context.special_category,
            "retention": context.retention,
            "ai_systems": sorted(context.ai_systems),
            "vendors": sorted(
                f"{name}:{country or ''}" for name, country in context.vendors
            ),
            "transfers": sorted(context.transfers),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def describe_drift(before: ProcessingContext, after: ProcessingContext) -> list[str]:
    """What changed, in the words a reviewer needs to judge whether it
    matters. Never applied to the assessment itself."""
    changes: list[str] = []
    if before.purpose != after.purpose:
        changes.append("The recorded purpose changed.")
    if before.data_subjects != after.data_subjects:
        changes.append("The data subjects changed.")
    added = sorted(set(after.data_categories) - set(before.data_categories))
    if added:
        changes.append(f"New personal-data categories: {_sentence(added)}.")
    if after.special_category and not before.special_category:
        changes.append(
            "Special-category data is now recorded against this processing."
        )
    if before.retention != after.retention:
        changes.append("The retention period changed.")
    new_systems = sorted(set(after.ai_systems) - set(before.ai_systems))
    if new_systems:
        changes.append(f"New AI system: {_sentence(new_systems)}.")
    before_vendors = {name: country for name, country in before.vendors}
    for name, country in after.vendors:
        if name not in before_vendors:
            changes.append(f"New processor: {name}.")
        elif before_vendors[name] != country:
            changes.append(
                f"{name} moved from {before_vendors[name] or 'an unrecorded country'} "
                f"to {country or 'an unrecorded country'}."
            )
    new_transfers = sorted(set(after.transfers) - set(before.transfers))
    if new_transfers:
        changes.append(f"New transfer: {_sentence(new_transfers)}.")
    return changes


__all__ = [
    "APPROVED",
    "COMPLETED",
    "DECISION_NOT_REQUIRED",
    "DECISION_REQUIRED",
    "DRAFT",
    "DRAFT_MARKER",
    "IN_REVIEW",
    "LIFECYCLE",
    "NOT_REQUIRED",
    "REJECTED",
    "CONSULTATION_NONE",
    "CONSULTATION_NOT_DECIDED",
    "CONSULTATION_PERFORMED",
    "NARRATIVE_SECTIONS",
    "NO_MATERIAL_RISKS",
    "RISKS_IDENTIFIED",
    "RISK_NOT_REVIEWED",
    "SCREENING",
    "SECTIONS",
    "TRANSITIONS",
    "Blocker",
    "DpiaRefused",
    "ProcessingContext",
    "RiskState",
    "SuggestedRisk",
    "approve_section",
    "completion_blockers",
    "conclude_no_material_risks",
    "content_gaps",
    "consultation_resolved",
    "consultation_state",
    "context_digest",
    "context_for",
    "decide_screening",
    "describe_drift",
    "draft_sections",
    "existing_for",
    "note_risks_identified",
    "pending_risk_suggestions",
    "record_consultation",
    "record_screening",
    "risk_conclusion_of",
    "risk_review_complete",
    "risk_state",
    "suggest_risks",
    "suggested_answers",
    "transition_refusal",
    "unreview_changed_sections",
]
