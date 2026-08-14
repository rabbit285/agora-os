"""Vendor privacy and security review, and the approval decision.

Both reviews read the vendor's actual state — DPA status, evidence on
file, questionnaire answers — and report what is missing. Neither judges
the vendor. "We have not received a transfer mechanism" is a fact about
our file; "this vendor is unsafe" is a conclusion we have no basis for
and no standing to publish.

The approval decision is the part worth arguing for. Real vendor reviews
end in "yes, but" far more often than in a clean yes, and a tool offering
only approve/reject forces the reviewer to either block a vendor the
business needs or wave through the caveat they were worried about.
`conditionally_approved` exists so the caveat is recorded as a condition
on the decision, in required text, where it outlives the person who made
it and can be found again when the condition comes due.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import (
    Evidence,
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    Vendor,
    VendorAssessment,
)

APPROVAL_STATES = (
    "not_submitted",
    "pending",
    "approved",
    "conditionally_approved",
    "rejected",
)

# Words that indicate a questionnaire question is asking about the thing
# each review needs. Matching on the question text keeps the review
# working with customer-supplied questionnaires, which never use our
# field names.
_TRANSFER_TERMS = ("transfer", "international", "third country", "adequacy", "scc")
_RETENTION_TERMS = ("retention", "retain", "deletion", "delete", "erasure")
_SUBPROCESSOR_TERMS = ("subprocessor", "sub-processor", "subcontractor")


@dataclass(frozen=True)
class ReviewFinding:
    check: str
    outcome: str  # satisfied | missing | unanswered
    detail: str


def _severity_from(findings: list[ReviewFinding]) -> str:
    unmet = [f for f in findings if f.outcome != "satisfied"]
    if not unmet:
        return "low"
    if len(unmet) >= 3:
        return "high"
    return "medium"


async def _questionnaire_state(
    db: AsyncSession, *, organization_id: uuid.UUID, vendor_id: uuid.UUID
) -> tuple[int, int, list[str]]:
    """Returns (total questions, answered, unanswered question texts) across
    every questionnaire attached to this vendor."""
    questionnaire_ids = list(
        (
            await db.execute(
                select(Questionnaire.id).where(
                    Questionnaire.organization_id == organization_id,
                    Questionnaire.vendor_id == vendor_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not questionnaire_ids:
        return 0, 0, []

    rows = list(
        (
            await db.execute(
                select(QuestionnaireQuestion.text, QuestionnaireAnswer.answer_text)
                .select_from(QuestionnaireQuestion)
                .outerjoin(
                    QuestionnaireAnswer,
                    QuestionnaireAnswer.question_id == QuestionnaireQuestion.id,
                )
                .where(QuestionnaireQuestion.questionnaire_id.in_(questionnaire_ids))
            )
        ).all()
    )
    unanswered = [text for text, answer in rows if not (answer or "").strip()]
    return len(rows), len(rows) - len(unanswered), unanswered


def _covers(question_text: str, terms: tuple[str, ...]) -> bool:
    lowered = question_text.lower()
    return any(term in lowered for term in terms)


async def run_privacy_review(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    vendor: Vendor,
    actor_user_id: uuid.UUID | None,
) -> VendorAssessment:
    """Check the privacy position: is there a DPA, is the transfer basis
    documented, has retention been confirmed."""
    _, _, unanswered = await _questionnaire_state(
        db, organization_id=organization_id, vendor_id=vendor.id
    )

    findings: list[ReviewFinding] = []

    if vendor.dpa_status == "signed":
        findings.append(
            ReviewFinding("Data processing agreement", "satisfied", "A DPA is recorded as signed.")
        )
    elif vendor.dpa_status == "not_required":
        findings.append(
            ReviewFinding(
                "Data processing agreement",
                "satisfied",
                "Marked not required. This is a human judgement recorded here, not a "
                "determination by Veyntra.",
            )
        )
    else:
        findings.append(
            ReviewFinding(
                "Data processing agreement",
                "missing",
                "No signed DPA is recorded. Article 28 requires one wherever this vendor "
                "processes personal data on the organization's behalf.",
            )
        )

    transfer_gaps = [q for q in unanswered if _covers(q, _TRANSFER_TERMS)]
    findings.append(
        ReviewFinding(
            "International transfer basis",
            "unanswered" if transfer_gaps else "satisfied",
            f"{len(transfer_gaps)} questionnaire question(s) about transfers are unanswered."
            if transfer_gaps
            else "No outstanding questions about international transfers.",
        )
    )

    retention_gaps = [q for q in unanswered if _covers(q, _RETENTION_TERMS)]
    findings.append(
        ReviewFinding(
            "Retention and deletion",
            "unanswered" if retention_gaps else "satisfied",
            f"{len(retention_gaps)} questionnaire question(s) about retention or deletion are "
            "unanswered."
            if retention_gaps
            else "No outstanding questions about retention or deletion.",
        )
    )

    subprocessor_gaps = [q for q in unanswered if _covers(q, _SUBPROCESSOR_TERMS)]
    findings.append(
        ReviewFinding(
            "Subprocessors",
            "unanswered" if subprocessor_gaps else "satisfied",
            f"{len(subprocessor_gaps)} questionnaire question(s) about subprocessors are "
            "unanswered."
            if subprocessor_gaps
            else "No outstanding questions about subprocessors.",
        )
    )

    return await _record(
        db,
        organization_id=organization_id,
        vendor=vendor,
        assessment_type="privacy",
        findings=findings,
        actor_user_id=actor_user_id,
    )


async def run_security_review(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    vendor: Vendor,
    actor_user_id: uuid.UUID | None,
) -> VendorAssessment:
    """Check the security position: is there evidence on file, and has the
    questionnaire actually been completed."""
    total, answered, unanswered = await _questionnaire_state(
        db, organization_id=organization_id, vendor_id=vendor.id
    )
    evidence_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Evidence)
                .where(
                    Evidence.vendor_id == vendor.id,
                    Evidence.organization_id == organization_id,
                )
            )
        ).scalar_one()
    )

    findings = [
        ReviewFinding(
            "Supporting evidence",
            "satisfied" if evidence_count else "missing",
            f"{evidence_count} document(s) attached to this vendor."
            if evidence_count
            else "No documents are attached to this vendor, so nothing supports its answers.",
        ),
        ReviewFinding(
            "Questionnaire completion",
            "satisfied" if total and not unanswered else "unanswered" if total else "missing",
            f"{answered} of {total} questions answered."
            if total
            else "No security questionnaire has been attached to this vendor.",
        ),
    ]

    return await _record(
        db,
        organization_id=organization_id,
        vendor=vendor,
        assessment_type="security",
        findings=findings,
        actor_user_id=actor_user_id,
    )


async def _record(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    vendor: Vendor,
    assessment_type: str,
    findings: list[ReviewFinding],
    actor_user_id: uuid.UUID | None,
) -> VendorAssessment:
    severity = _severity_from(findings)
    unmet = [f for f in findings if f.outcome != "satisfied"]

    assessment = VendorAssessment(
        organization_id=organization_id,
        vendor_id=vendor.id,
        assessment_type=assessment_type,
        risk_conclusion=severity,
        notes=(
            f"{len(unmet)} of {len(findings)} checks are outstanding."
            if unmet
            else "All checks in this review are satisfied on the information on file."
        ),
        findings={
            "checks": [
                {"check": f.check, "outcome": f.outcome, "detail": f.detail} for f in findings
            ],
            "outstanding": len(unmet),
            # Said plainly, because a green review is the moment someone
            # stops looking.
            "coverage_note": (
                "Based on the DPA status, attached evidence and questionnaire answers held in "
                "Veyntra. It is not an independent audit of the vendor."
            ),
        },
        assessed_by=actor_user_id,
    )
    db.add(assessment)
    await db.flush()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=f"compliance.vendor.{assessment_type}_reviewed",
        object_type="vendor",
        object_id=str(vendor.id),
        after_state={"risk_conclusion": severity, "outstanding": len(unmet)},
    )
    return assessment


class VendorApprovalError(Exception):
    """A decision that cannot be recorded as stated."""


async def decide_vendor_approval(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    vendor: Vendor,
    decision: str,
    conditions: str | None,
    actor_user_id: uuid.UUID | None,
) -> Vendor:
    """Record an approval decision.

    A conditional approval must state its conditions. Allowing one without
    them would produce exactly the record that makes conditional approval
    worthless six months later — a vendor marked "conditionally approved"
    with nobody able to say what the condition was.
    """
    if decision not in APPROVAL_STATES:
        raise VendorApprovalError(f"Unknown approval state: {decision}")
    if decision == "conditionally_approved" and not (conditions or "").strip():
        raise VendorApprovalError(
            "A conditional approval must record its conditions — what is permitted, and what "
            "must be completed before full approval."
        )

    before = vendor.approval_state
    vendor.approval_state = decision
    vendor.approval_conditions = conditions if decision == "conditionally_approved" else None
    vendor.approval_decided_at = datetime.now(UTC)
    vendor.approval_decided_by = actor_user_id

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.vendor.approval_decided",
        object_type="vendor",
        object_id=str(vendor.id),
        before_state={"approval_state": before},
        after_state={"approval_state": decision, "conditions": vendor.approval_conditions},
    )
    return vendor


def latest_by_type(assessments: list[VendorAssessment]) -> dict[str, Any]:
    """Newest privacy and security review, keyed by type — the two are
    separate positions and neither stands in for the other."""
    result: dict[str, Any] = {}
    for assessment in sorted(assessments, key=lambda a: a.created_at, reverse=True):
        result.setdefault(assessment.assessment_type, assessment)
    return result
