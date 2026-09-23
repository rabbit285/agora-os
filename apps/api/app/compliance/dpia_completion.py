"""Finishing a DPIA, and what stops it being quietly un-finished later.

Two things live here.

**Completion is a gate, not a status change.** `complete()` refuses
while `dpia_workflow.completion_blockers` returns anything, so a DPIA
cannot reach "completed" with an unreviewed section, an unresolved
consultation, suggested risks nobody ruled on, an uncalculated residual
rating, or an unapproved high residual risk. The blockers are returned
together rather than one at a time, so somebody can finish the work in a
single pass instead of discovering the next missing thing on each press.

**A completed DPIA is frozen.** The snapshot records what was assessed:
the processing as it stood, the screening and who decided it, the
sections as approved, every risk with its rating and safeguards, the
residual position, the approvals, and the evidence referenced. Stored
rather than re-derived, because re-deriving it next quarter answers
"what is true now" and a completed DPIA is a statement about what was
true then.

That matters most when the ROPA moves underneath it. A vendor changing
country, an AI system taking on a new data category, special-category
data appearing — none of that edits the completed record. It raises a
flag saying the assessment should be looked at again, which is a
different claim, made by a different party, at a different time.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance import dpia_quality, dpia_workflow
from app.compliance.dpia_workflow import (
    COMPLETED,
    SECTIONS,
    DpiaRefused,
    context_digest,
    context_for,
    describe_drift,
)
from app.compliance.models import (
    DPIA,
    DpiaRiskSuggestion,
    Evidence,
    ProcessingActivity,
    Risk,
)
from app.core.models import Approval
from app.db.base import utcnow
from app.identity.models import User


async def _actor_label(db: AsyncSession, user_id: uuid.UUID | None) -> str | None:
    """A person's name for the frozen record.

    Resolved at completion and stored, because a snapshot that holds a
    user id reads as an internal identifier years later, and one that
    re-resolves the name shows the name they have now rather than the
    name that signed.
    """
    if user_id is None:
        return None
    user = await db.get(User, user_id)
    if user is None:
        return None
    return (user.full_name or "").strip() or user.email


async def build_snapshot(
    db: AsyncSession, *, organization_id: uuid.UUID, dpia: DPIA
) -> dict:
    """Everything the completed assessment concluded, as it stands now."""
    activity = (
        await db.get(ProcessingActivity, dpia.processing_activity_id)
        if dpia.processing_activity_id
        else None
    )
    context = (
        await context_for(db, activity=activity) if activity is not None else None
    )

    risks = list(
        (
            await db.execute(
                select(Risk)
                .where(
                    Risk.dpia_id == dpia.id,
                    Risk.organization_id == organization_id,
                )
                .order_by(Risk.created_at)
            )
        )
        .scalars()
        .all()
    )
    suggestions = list(
        (
            await db.execute(
                select(DpiaRiskSuggestion).where(
                    DpiaRiskSuggestion.dpia_id == dpia.id,
                    DpiaRiskSuggestion.organization_id == organization_id,
                )
            )
        )
        .scalars()
        .all()
    )
    # Evidence reachable from this assessment: what the risks' controls
    # are evidenced by. Referenced by id and title rather than copied —
    # the snapshot records which documents the conclusion rested on, and
    # a reader who needs the document itself follows the reference.
    control_ids = [risk.control_id for risk in risks if risk.control_id]
    evidence = (
        [
            {"id": str(row.id), "title": row.title, "control_id": str(row.control_id)}
            for row in (
                await db.execute(
                    select(Evidence).where(
                        Evidence.organization_id == organization_id,
                        Evidence.control_id.in_(control_ids),
                    )
                )
            )
            .scalars()
            .all()
        ]
        if control_ids
        else []
    )

    approval = (
        await db.get(Approval, dpia.approval_id) if dpia.approval_id else None
    )

    sections: dict[str, dict] = {}
    reviews = dpia.section_reviews or {}
    for key in SECTIONS:
        review = reviews.get(key) or {}
        sections[key] = {
            "text": getattr(dpia, key),
            "approved_by": await _actor_label(
                db,
                uuid.UUID(review["approved_by"])
                if review.get("approved_by")
                else None,
            ),
            "approved_at": review.get("approved_at"),
        }

    return {
        "processing": {
            "title": context.title if context else dpia.title,
            "purpose": context.purpose if context else None,
            "data_subjects": context.data_subjects if context else None,
            "data_categories": list(context.data_categories) if context else [],
            "special_category": context.special_category if context else False,
            "retention": context.retention if context else None,
            "ai_systems": list(context.ai_systems) if context else [],
            "vendors": [
                {"name": name, "country": country}
                for name, country in (context.vendors if context else [])
            ],
            "transfers": list(context.transfers) if context else [],
        },
        "screening": {
            "outcome": dpia.screening_outcome,
            "findings": dpia.screening_findings,
            "decision": dpia.screening_decision,
            "decided_by": await _actor_label(db, dpia.screening_decided_by),
            "decided_at": (
                dpia.screening_decided_at.isoformat()
                if dpia.screening_decided_at
                else None
            ),
            "rationale": dpia.screening_rationale,
        },
        "assessment": sections,
        "consultation": {
            "state": dpia_workflow.consultation_state(dpia),
            "performed": dpia.consultation_performed,
            "party": dpia.consulted_party,
            "role": dpia.consulted_role,
            "at": dpia.consulted_at.isoformat() if dpia.consulted_at else None,
            # The advice when one happened; the reason when none did.
            "notes": dpia.consultation_notes,
            "recorded_by": await _actor_label(db, dpia.consultation_recorded_by),
            "recorded_at": (
                dpia.consultation_recorded_at.isoformat()
                if dpia.consultation_recorded_at
                else None
            ),
        },
        # What the risk review concluded, which is not recoverable from
        # the risk list: an empty register means "reviewed and found
        # nothing material" here, and that is a claim somebody made.
        "risk_review": {
            "conclusion": dpia_workflow.risk_conclusion_of(dpia),
            "rationale": dpia.risk_conclusion_rationale,
            "reviewed_by": await _actor_label(db, dpia.risk_reviewed_by),
            "reviewed_at": (
                dpia.risk_reviewed_at.isoformat() if dpia.risk_reviewed_at else None
            ),
        },
        # §15: a completed DPIA has to answer "were special categories
        # involved?" — and "nobody recorded any categories" is not that
        # answer.
        "special_category": {
            "confirmed": dpia.special_category_confirmed,
            "rationale": dpia.special_category_rationale,
            "decided_by": await _actor_label(db, dpia.special_category_decided_by),
            "decided_at": (
                dpia.special_category_decided_at.isoformat()
                if dpia.special_category_decided_at
                else None
            ),
        },
        "risks": [
            {
                "id": str(risk.id),
                "title": risk.title,
                "description": risk.description,
                "affected_data_subjects": risk.affected_data_subjects,
                "likelihood": risk.likelihood,
                "impact": risk.impact,
                "existing_safeguards": risk.existing_safeguards,
                "additional_mitigations": risk.additional_mitigations,
                "residual_likelihood": risk.residual_likelihood,
                "residual_impact": risk.residual_impact,
                "status": risk.status,
            }
            for risk in risks
        ],
        # Kept because "we considered this and decided it was not a risk
        # here" is part of what an assessment concluded, and an auditor
        # asking why something is absent should find the answer in the
        # record rather than in nobody's memory.
        "dismissed_risks": [
            {"title": row.title, "reason": row.reason}
            for row in suggestions
            if row.status == "dismissed"
        ],
        "residual_risk": dpia.residual_risk_level,
        "inherent_risk": dpia.risk_level,
        "approval": (
            {
                "action_type": approval.action_type,
                "status": approval.status,
                "decided_by": await _actor_label(db, approval.decided_by),
                "decided_at": (
                    approval.decided_at.isoformat() if approval.decided_at else None
                ),
            }
            if approval
            else None
        ),
        "evidence": evidence,
    }


async def complete(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dpia: DPIA,
    actor_user_id: uuid.UUID | None,
) -> DPIA:
    """Finish the assessment, or refuse and say what is missing."""
    if dpia.status == COMPLETED:
        raise DpiaRefused("This DPIA is already complete.")

    blockers = await dpia_workflow.completion_blockers(
        db, organization_id=organization_id, dpia=dpia
    )
    if blockers:
        raise DpiaRefused(
            "This DPIA cannot be completed yet: "
            + " ".join(blocker.message for blocker in blockers)
        )

    dpia.snapshot = await build_snapshot(
        db, organization_id=organization_id, dpia=dpia
    )
    dpia.status = COMPLETED
    dpia.completed_at = utcnow()
    dpia.completed_by = actor_user_id
    # Completing clears any outstanding flag: this assessment now
    # accounts for whatever had drifted.
    dpia.review_reason = None
    dpia.review_flagged_at = None

    if dpia.processing_activity_id:
        activity = await db.get(ProcessingActivity, dpia.processing_activity_id)
        if activity is not None:
            dpia.source_digest = context_digest(
                await context_for(db, activity=activity)
            )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dpia.completed",
        object_type="dpia",
        object_id=str(dpia.id),
        after_state={
            "residual_risk": dpia.residual_risk_level,
            "risks": len(dpia.snapshot.get("risks") or []),
        },
    )
    await db.flush()
    return dpia


# --- §16: DPIAs completed before the quality gates existed --------------


def snapshot_quality_problems(dpia: DPIA) -> list[str]:
    """What a completed DPIA would fail on if it were assessed today.

    Read from the frozen snapshot, never from the live record, because
    the question is what this document says — not what the processing
    looks like now.
    """
    snapshot = dpia.snapshot or {}
    problems: list[str] = []

    sections = snapshot.get("assessment") or {}
    for key in dpia_workflow.NARRATIVE_SECTIONS:
        entry = sections.get(key) or {}
        problem = dpia_quality.section_problem(key, entry.get("text"))
        if problem is not None:
            problems.append(problem)

    review = snapshot.get("risk_review") or {}
    if review.get("conclusion") == dpia_workflow.NO_MATERIAL_RISKS:
        weak = dpia_quality.rationale_problem(review.get("rationale"))
        if weak is not None:
            problems.append(
                "The conclusion that no material risks exist rests on a "
                "rationale that would not be accepted now."
            )

    processing = snapshot.get("processing") or {}
    if not processing.get("data_categories"):
        problems.append(
            "No personal-data categories were recorded, so the assessment "
            "does not say what data it covered."
        )
    special = snapshot.get("special_category") or {}
    if special.get("confirmed") is None and not processing.get("special_category"):
        # Only worth raising where the record actually looks sensitive.
        context = dpia_workflow.ProcessingContext(
            title=processing.get("title") or dpia.title,
            purpose=processing.get("purpose"),
            data_subjects=processing.get("data_subjects"),
            data_categories=list(processing.get("data_categories") or []),
            ai_systems=list(processing.get("ai_systems") or []),
        )
        signals = dpia_quality.special_category_signals(context)
        if signals:
            kinds = ", ".join(signal.kind for signal in signals)
            problems.append(
                f"Possible special-category data ({kinds}) was never "
                "confirmed or ruled out."
            )
    return problems


async def flag_weak_completed_dpias(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[DPIA]:
    """Mark completed DPIAs whose content would not pass today's gates.

    Deliberately a flag and not a repair. The snapshot is what the
    organization concluded on the day it concluded it; rewriting it to
    satisfy a rule introduced afterwards would replace the record with a
    better-looking one that nobody actually signed. So the document
    stands, and the flag says a person should look at it again.
    """
    rows = list(
        (
            await db.execute(
                select(DPIA).where(
                    DPIA.organization_id == organization_id,
                    DPIA.status == COMPLETED,
                )
            )
        )
        .scalars()
        .all()
    )
    flagged: list[DPIA] = []
    for dpia in rows:
        problems = snapshot_quality_problems(dpia)
        reason = (
            "This DPIA was completed before Veyntra checked assessment "
            "quality, and its record would not pass those checks now: "
            + " ".join(problems)
        )[:2000] if problems else None

        if reason == dpia.quality_review_reason:
            continue
        dpia.quality_review_reason = reason
        if reason:
            await record_event(
                db,
                organization_id=organization_id,
                actor_user_id=None,
                action="compliance.dpia.quality_review_recommended",
                object_type="dpia",
                object_id=str(dpia.id),
                after_state={"problems": problems},
            )
            flagged.append(dpia)
    await db.flush()
    return flagged


# --- §24: noticing that the ground moved --------------------------------


async def check_for_drift(
    db: AsyncSession, *, organization_id: uuid.UUID, dpia: DPIA
) -> list[str]:
    """What has changed under this DPIA since it was assessed.

    Never rewrites the assessment. A completed DPIA that silently
    absorbed a new vendor country would be claiming somebody assessed a
    transfer they never saw.
    """
    if not dpia.processing_activity_id or not dpia.snapshot:
        return []
    activity = await db.get(ProcessingActivity, dpia.processing_activity_id)
    if activity is None:
        return []
    current = await context_for(db, activity=activity)
    if dpia.source_digest and context_digest(current) == dpia.source_digest:
        return []

    frozen = dpia.snapshot.get("processing") or {}
    before = dpia_workflow.ProcessingContext(
        title=frozen.get("title") or dpia.title,
        purpose=frozen.get("purpose"),
        data_subjects=frozen.get("data_subjects"),
        data_categories=list(frozen.get("data_categories") or []),
        special_category=bool(frozen.get("special_category")),
        retention=frozen.get("retention"),
        ai_systems=list(frozen.get("ai_systems") or []),
        vendors=[
            (entry.get("name"), entry.get("country"))
            for entry in (frozen.get("vendors") or [])
        ],
        transfers=list(frozen.get("transfers") or []),
    )
    return describe_drift(before, current)


async def flag_for_review(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dpia: DPIA,
    changes: list[str],
    actor_user_id: uuid.UUID | None = None,
) -> DPIA:
    """Record that a completed DPIA should be looked at again."""
    if not changes:
        return dpia
    reason = " ".join(changes)[:1000]
    if dpia.review_reason == reason:
        # Already flagged for exactly this. Re-flagging would produce a
        # second notification for one change.
        return dpia
    dpia.review_reason = reason
    dpia.review_flagged_at = utcnow()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dpia.review_recommended",
        object_type="dpia",
        object_id=str(dpia.id),
        after_state={"changes": changes},
    )
    await db.flush()
    return dpia


async def review_completed_dpias(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[DPIA]:
    """Flag every completed DPIA whose processing has moved on."""
    rows = list(
        (
            await db.execute(
                select(DPIA).where(
                    DPIA.organization_id == organization_id,
                    DPIA.status == COMPLETED,
                )
            )
        )
        .scalars()
        .all()
    )
    flagged: list[DPIA] = []
    for dpia in rows:
        changes = await check_for_drift(
            db, organization_id=organization_id, dpia=dpia
        )
        if changes:
            await flag_for_review(
                db, organization_id=organization_id, dpia=dpia, changes=changes
            )
            flagged.append(dpia)
    return flagged


__all__ = [
    "build_snapshot",
    "flag_weak_completed_dpias",
    "snapshot_quality_problems",
    "check_for_drift",
    "complete",
    "flag_for_review",
    "review_completed_dpias",
]
