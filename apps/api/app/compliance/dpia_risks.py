"""Risks Veyntra proposes, and the decision that turns one into a risk.

`dpia_workflow.suggest_risks` computes candidates from what the records
say. Those used to be recomputed on every read and never stored, which
made them impossible to act on: there was nothing to approve, nothing to
dismiss, and no way to stop the same proposal reappearing after somebody
had already decided it was not a real risk.

So proposals are persisted here, and the boundary is strict:

**A suggestion is not a risk.** The residual-risk arithmetic in
`dpia_workflow.risk_state` ignores this table completely. A DPIA's risk
register is the controller's statement of what threatens data subjects;
a list assembled from what a record happens to mention is not that.
Approving one is what creates the `Risk` row.

**Nothing here carries a likelihood or an impact.** Those are the
judgement the review exists to make. A proposal arriving pre-rated would
answer the one question the reviewer was brought in for, and the rating
would then flow into an inherent level nobody chose.

**Identity comes from what a proposal is about, never its wording.**
`source_key` is derived from the fact that produced it — an AI system is
involved, a processor is named, no retention is recorded. Re-running the
analysis reconciles against that key, so a copy edit to the description
does not turn one reviewed proposal into two unreviewed ones, and a
dismissed proposal stays dismissed.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.dpia_workflow import (
    ProcessingContext,
    SuggestedRisk,
    suggest_risks,
)
from app.compliance.models import DPIA, DpiaRiskSuggestion, Risk
from app.db.base import utcnow

SUGGESTED = "suggested"
APPROVED = "approved"
DISMISSED = "dismissed"


class RiskSuggestionRefused(Exception):
    """A suggestion cannot be acted on the way it was asked."""


def source_key_for(risk: SuggestedRisk) -> str:
    """The stable identity of a proposal.

    Derived from the title, which names the *kind* of risk rather than
    the particular phrasing of its description, and normalised so
    punctuation and case changes do not fork the identity. The
    descriptions interpolate vendor and system names and would fork on
    every rename; the titles are fixed strings in `suggest_risks`.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", risk.title.lower()).strip("-")
    return slug[:200]


def _safeguards_hint(context: ProcessingContext) -> str | None:
    """Safeguards the record already shows, as a starting point.

    Facts, not an argument that they are sufficient — that judgement is
    the reviewer's, and stating it here would put Veyntra's name on a
    conclusion about adequacy it has no basis for.
    """
    noted: list[str] = []
    if context.retention:
        noted.append(f"a recorded retention period of {context.retention}")
    if context.vendors:
        noted.append("a named processor with a vendor record")
    if not noted:
        return None
    return (
        "On record: " + ", and ".join(noted) + ". "
        "Whether that is sufficient is your assessment, not Veyntra's."
    )


async def reconcile(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dpia: DPIA,
    context: ProcessingContext,
    actor_user_id: uuid.UUID | None = None,
) -> list[DpiaRiskSuggestion]:
    """Persist the proposals the current facts imply, without duplicating.

    Re-running this is safe and is expected to happen — on screening, on
    a document being re-analysed, on an AI system changing. Existing rows
    are matched by `source_key`:

    * a proposal a person already decided is left exactly as it is, in
      both directions. A dismissed risk does not come back because the
      analysis ran again, and an approved one is not re-proposed.
    * an undecided proposal has its wording refreshed, since nobody has
      relied on it yet.
    * a proposal the facts no longer support is withdrawn only while it
      is still undecided.
    """
    proposals = suggest_risks(context)
    by_key = {source_key_for(risk): risk for risk in proposals}

    existing = list(
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
    seen = {row.source_key: row for row in existing}
    hint = _safeguards_hint(context)
    created = 0

    for key, proposal in by_key.items():
        row = seen.get(key)
        if row is None:
            row = DpiaRiskSuggestion(
                organization_id=organization_id,
                dpia_id=dpia.id,
                source_key=key,
                status=SUGGESTED,
                title=proposal.title,
                description=proposal.description,
                reason=proposal.reason,
                suggested_safeguards=hint,
            )
            db.add(row)
            created += 1
        elif row.status == SUGGESTED:
            # Nobody has relied on this yet, so refreshing the wording
            # costs nothing. A decided row is never rewritten.
            row.title = proposal.title
            row.description = proposal.description
            row.reason = proposal.reason
            row.suggested_safeguards = hint

    for key, row in seen.items():
        if key not in by_key and row.status == SUGGESTED:
            # The fact behind it is gone. Withdrawing an undecided
            # proposal is housekeeping; withdrawing a decided one would
            # erase somebody's decision.
            await db.delete(row)

    await db.flush()

    if created:
        await record_event(
            db,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="compliance.dpia.risks_suggested",
            object_type="dpia",
            object_id=str(dpia.id),
            after_state={"proposed": created},
        )

    return await for_dpia(db, organization_id=organization_id, dpia_id=dpia.id)


async def withdraw_undecided(
    db: AsyncSession, *, organization_id: uuid.UUID, dpia_id: uuid.UUID
) -> int:
    """Drop proposals for an assessment that is not going to happen.

    Used when a screening concludes no DPIA is required. Only
    undecided rows go: a proposal somebody approved or dismissed is a
    record of a decision, and removing it would erase the decision
    along with the proposal.
    """
    rows = list(
        (
            await db.execute(
                select(DpiaRiskSuggestion).where(
                    DpiaRiskSuggestion.dpia_id == dpia_id,
                    DpiaRiskSuggestion.organization_id == organization_id,
                    DpiaRiskSuggestion.status == SUGGESTED,
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        await db.delete(row)
    await db.flush()
    return len(rows)


async def for_dpia(
    db: AsyncSession, *, organization_id: uuid.UUID, dpia_id: uuid.UUID
) -> list[DpiaRiskSuggestion]:
    return list(
        (
            await db.execute(
                select(DpiaRiskSuggestion)
                .where(
                    DpiaRiskSuggestion.dpia_id == dpia_id,
                    DpiaRiskSuggestion.organization_id == organization_id,
                )
                .order_by(DpiaRiskSuggestion.created_at)
            )
        )
        .scalars()
        .all()
    )


async def approve(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    suggestion: DpiaRiskSuggestion,
    likelihood: str,
    impact: str,
    title: str | None = None,
    description: str | None = None,
    affected_data_subjects: str | None = None,
    existing_safeguards: str | None = None,
    owner_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> Risk:
    """Turn a proposal into a real risk, with the rating a person chose.

    The likelihood and impact are required arguments rather than
    defaulted, because this is the moment the DPIA acquires a risk
    position and there is no honest value to fall back on. `title` and
    `description` are optional overrides — §13's "Edit" is the same
    decision as "Approve", made about different words.
    """
    if suggestion.status != SUGGESTED:
        raise RiskSuggestionRefused(
            f"This suggestion was already {suggestion.status}."
        )
    if likelihood not in ("low", "medium", "high") or impact not in (
        "low",
        "medium",
        "high",
    ):
        raise RiskSuggestionRefused(
            "A risk needs a likelihood and an impact of low, medium or high."
        )

    risk = Risk(
        organization_id=organization_id,
        title=(title or suggestion.title).strip(),
        description=(description or suggestion.description).strip(),
        category="privacy",
        likelihood=likelihood,
        impact=impact,
        status="open",
        dpia_id=suggestion.dpia_id,
        affected_data_subjects=(affected_data_subjects or "").strip() or None,
        existing_safeguards=(existing_safeguards or "").strip() or None,
        owner_id=owner_id,
    )
    db.add(risk)
    await db.flush()

    suggestion.status = APPROVED
    suggestion.created_risk_id = risk.id
    suggestion.decided_by = actor_user_id
    suggestion.decided_at = utcnow()

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dpia.risk_approved",
        object_type="dpia",
        object_id=str(suggestion.dpia_id),
        after_state={
            "risk_id": str(risk.id),
            "title": risk.title,
            "likelihood": likelihood,
            "impact": impact,
        },
    )
    await db.flush()
    return risk


async def dismiss(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    suggestion: DpiaRiskSuggestion,
    reason: str,
    actor_user_id: uuid.UUID | None = None,
) -> DpiaRiskSuggestion:
    """Record that this is not a risk here, and why.

    A reason is required for the same argument that makes "DPIA not
    required" need one: an unexplained dismissal is indistinguishable
    from nobody having looked, and it is the record the organization
    would have to stand behind if the risk later materialised.
    """
    if suggestion.status != SUGGESTED:
        raise RiskSuggestionRefused(
            f"This suggestion was already {suggestion.status}."
        )
    if not (reason or "").strip():
        raise RiskSuggestionRefused(
            "Dismissing a suggested risk needs a reason. That reason is the "
            "record you would rely on if the risk were ever questioned."
        )

    suggestion.status = DISMISSED
    suggestion.decided_by = actor_user_id
    suggestion.decided_at = utcnow()
    suggestion.reason = (
        f"{suggestion.reason}\n\nDismissed: {reason.strip()}"
    )[:1000]

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.dpia.risk_dismissed",
        object_type="dpia",
        object_id=str(suggestion.dpia_id),
        after_state={"title": suggestion.title, "reason": reason.strip()},
    )
    await db.flush()
    return suggestion


__all__ = [
    "APPROVED",
    "DISMISSED",
    "SUGGESTED",
    "RiskSuggestionRefused",
    "approve",
    "dismiss",
    "for_dpia",
    "reconcile",
    "source_key_for",
    "withdraw_undecided",
]
