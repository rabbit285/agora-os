"""Document intelligence: propose evidence mappings, verify the citations.

The workflow this enables is "upload once, review the proposals" rather
than "map every document to every control by hand". The model reads an
uploaded document alongside the organization's controls and proposes
which controls it evidences.

Three rules make that safe enough to build.

**A suggestion is not evidence.** Proposals land in `EvidenceSuggestion`,
the assessment ignores that table completely, and approving one is what
creates the real `Evidence` row. An auditor's question is "who decided
this document demonstrates that control", and "the software did" is not
an answer. Nothing here auto-approves, at any confidence.

**Every proposal must quote the document, and the quote is checked.**
The model returns the passage it relied on, and `verify_quote` looks for
that passage in the extracted text before the suggestion is ever offered.
A quote that is not in the source is recorded as `unverifiable` and never
shown as approvable. This is the one place a hallucination would do real
damage — a fabricated citation under a compliance claim — and it is
cheap to check, so it is checked rather than trusted.

**No provider, no proposals.** With AI unconfigured this raises rather
than falling back to keyword matching dressed up as intelligence.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.exceptions import AiProviderUnavailable
from app.ai.gateway import GenerateRequest, ModelGateway
from app.audit.service import record_event
from app.compliance.models import Control, ControlMapping, Evidence, EvidenceSuggestion, Requirement
from app.core.models import File
from app.knowledge.parsing import UnsupportedFormatError, extract_text

# Long enough that a match is meaningful, short enough that a model
# quoting a fragment of a sentence still verifies.
MIN_QUOTE_LENGTH = 25
# Documents are truncated before prompting. Compliance documents are
# mostly front-loaded with their statements of intent, and sending an
# unbounded policy costs tokens without improving the proposal.
MAX_DOCUMENT_CHARS = 24_000


class ProposedMapping(BaseModel):
    # An index into the numbered list in the prompt, not a title. Asking
    # for the title invited the model to echo back the whole formatted
    # line — name, requirement codes and description — which then matched
    # nothing. An integer cannot be garbled by formatting.
    control_index: int = Field(description="The number in brackets next to the control")
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(description="Why this document evidences that control")
    quoted_passage: str = Field(
        description="A passage copied verbatim from the document that supports this mapping"
    )


class ProposedMappings(BaseModel):
    mappings: list[ProposedMapping] = Field(default_factory=list)


@dataclass
class SuggestionOutcome:
    suggestions: list[EvidenceSuggestion]
    unverifiable_count: int
    considered_controls: int


def _normalize(text: str) -> str:
    """Collapse whitespace and case so a quote still matches when the
    model reflows line breaks — which every model does when copying out
    of a PDF."""
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_quote(quote: str, document_text: str) -> bool:
    """Is this passage actually in the document?

    Deliberately a plain containment check on normalized text rather than
    a fuzzy or semantic match. The question being asked is "did the model
    copy this out of the document, or invent it", and a similarity
    threshold answers a different, softer question — one that a
    confidently-worded fabrication can pass.
    """
    if not quote or len(quote.strip()) < MIN_QUOTE_LENGTH:
        return False
    return _normalize(quote) in _normalize(document_text)


def build_prompt(document_text: str, controls: list[tuple[Control, list[str]]]) -> str:
    lines = [
        "You are helping a compliance team decide which of their controls a document evidences.",
        "",
        "CONTROLS:",
    ]
    for index, (control, requirement_codes) in enumerate(controls, start=1):
        codes = f" (mapped to {', '.join(requirement_codes)})" if requirement_codes else ""
        description = f" — {control.description}" if control.description else ""
        lines.append(f"[{index}] {control.title}{codes}{description}")

    lines += [
        "",
        "DOCUMENT:",
        document_text[:MAX_DOCUMENT_CHARS],
        "",
        "For each control this document genuinely evidences, return a mapping containing:",
        "  - control_index: the number in brackets next to the control above",
        "  - confidence: 0.0 to 1.0",
        "  - rationale: one sentence on why this document supports that control",
        "  - quoted_passage: a passage copied VERBATIM from the document above",
        "",
        "Rules:",
        "  - The quoted passage must appear word-for-word in the document. Do not paraphrase,",
        "    summarise, correct, or reflow it. Passages that do not appear in the document are",
        "    checked and discarded.",
        "  - Only propose a control where the document really does say something that supports",
        "    it. Returning no mappings is a valid and useful answer.",
        "  - Do not propose a control merely because its subject is related to the document's.",
    ]
    return "\n".join(lines)


async def _load_controls(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[tuple[Control, list[str]]]:
    controls = list(
        (
            await db.execute(
                select(Control).where(Control.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    result: list[tuple[Control, list[str]]] = []
    for control in controls:
        codes = list(
            (
                await db.execute(
                    select(Requirement.reference_code)
                    .join(ControlMapping, ControlMapping.requirement_id == Requirement.id)
                    .where(ControlMapping.control_id == control.id)
                )
            )
            .scalars()
            .all()
        )
        result.append((control, codes))
    return result


async def suggest_evidence_mappings(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_record: File,
    file_bytes: bytes,
    actor_user_id: uuid.UUID | None,
    gateway: ModelGateway | None = None,
) -> SuggestionOutcome:
    """Read a document and propose which controls it evidences.

    Raises `UnsupportedFormatError` for a file type we cannot read, and
    the AI provider exceptions unchanged when generation fails — both are
    honest outcomes, and both are better than an empty suggestion list
    that looks like "nothing matched".
    """
    document_text = extract_text(file_record.content_type, file_bytes)
    controls = await _load_controls(db, organization_id=organization_id)
    if not controls:
        return SuggestionOutcome(suggestions=[], unverifiable_count=0, considered_controls=0)

    by_index = {index: control for index, (control, _) in enumerate(controls, start=1)}

    gateway = gateway or ModelGateway()
    raw = await gateway.generate_structured(
        db,
        organization_id=organization_id,
        requested_by=actor_user_id,
        request=GenerateRequest(
            task_type="compliance.evidence_mapping",
            prompt=build_prompt(document_text, controls),
            prompt_template="compliance_evidence_mapping",
            prompt_version="1",
            input_classification="confidential",
        ),
        schema=ProposedMappings,
    )
    # The gateway is typed to return BaseModel. Narrowed with a real
    # check rather than a cast: an adapter returning the wrong shape
    # should fail loudly, not quietly propose nothing and look like
    # "the document matched no controls".
    if not isinstance(raw, ProposedMappings):
        raise AiProviderUnavailable(
            "The AI provider returned an unexpected response shape for evidence mapping."
        )
    proposals = raw

    # Clear previous proposals for this document that nobody has acted on,
    # so re-analysing replaces them rather than stacking near-duplicates.
    stale = list(
        (
            await db.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.organization_id == organization_id,
                    EvidenceSuggestion.file_id == file_record.id,
                    EvidenceSuggestion.status.in_(("proposed", "unverifiable")),
                )
            )
        )
        .scalars()
        .all()
    )
    for row in stale:
        await db.delete(row)

    suggestions: list[EvidenceSuggestion] = []
    unverifiable = 0

    for proposal in proposals.mappings:
        control = by_index.get(proposal.control_index)
        if control is None:
            # The model referenced a control that is not on the list.
            # Dropped rather than matched to the nearest one — guessing
            # which control was meant is how the wrong document ends up
            # under the wrong requirement.
            unverifiable += 1
            continue

        verified = verify_quote(proposal.quoted_passage, document_text)
        if not verified:
            unverifiable += 1
        suggestion = EvidenceSuggestion(
            organization_id=organization_id,
            file_id=file_record.id,
            control_id=control.id,
            status="proposed" if verified else "unverifiable",
            confidence=proposal.confidence,
            rationale=proposal.rationale,
            quoted_passage=proposal.quoted_passage,
            quote_verified=verified,
        )
        db.add(suggestion)
        suggestions.append(suggestion)

    await db.flush()
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.evidence.suggestions_generated",
        object_type="file",
        object_id=str(file_record.id),
        after_state={
            "proposed": sum(1 for s in suggestions if s.status == "proposed"),
            "unverifiable": unverifiable,
            "controls_considered": len(controls),
        },
    )
    return SuggestionOutcome(
        suggestions=suggestions,
        unverifiable_count=unverifiable,
        considered_controls=len(controls),
    )


class SuggestionDecisionError(Exception):
    """A suggestion that cannot be acted on as asked."""


async def approve_suggestion(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    suggestion: EvidenceSuggestion,
    title: str | None,
    actor_user_id: uuid.UUID | None,
) -> Evidence:
    """Turn an approved proposal into real evidence.

    This is the moment a person takes responsibility for the link, which
    is why it is a separate, explicit action and why an unverifiable
    suggestion cannot reach it — approving a citation that is not in the
    document would put a fabricated quote into the evidence record under
    a human's name.
    """
    if suggestion.status == "unverifiable":
        raise SuggestionDecisionError(
            "This suggestion quoted a passage that does not appear in the document, so it "
            "cannot be approved. Attach the document manually if it is genuinely relevant."
        )
    if suggestion.status != "proposed":
        raise SuggestionDecisionError(f"This suggestion has already been {suggestion.status}.")

    file_record = await db.get(File, suggestion.file_id)
    assert file_record is not None

    evidence = Evidence(
        organization_id=organization_id,
        control_id=suggestion.control_id,
        file_id=suggestion.file_id,
        title=title or file_record.original_filename,
        created_by=actor_user_id,
    )
    db.add(evidence)
    await db.flush()

    suggestion.status = "approved"
    suggestion.evidence_id = evidence.id
    suggestion.decided_by = actor_user_id
    suggestion.decided_at = datetime.now(UTC)

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.evidence.suggestion_approved",
        object_type="evidence_suggestion",
        object_id=str(suggestion.id),
        after_state={
            "evidence_id": str(evidence.id),
            "control_id": str(suggestion.control_id),
            # Recorded so the trail shows a human accepted a *verified*
            # citation, not merely that they clicked approve.
            "quote_verified": suggestion.quote_verified,
        },
    )
    return evidence


async def reject_suggestion(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    suggestion: EvidenceSuggestion,
    actor_user_id: uuid.UUID | None,
) -> EvidenceSuggestion:
    suggestion.status = "rejected"
    suggestion.decided_by = actor_user_id
    suggestion.decided_at = datetime.now(UTC)
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="compliance.evidence.suggestion_rejected",
        object_type="evidence_suggestion",
        object_id=str(suggestion.id),
    )
    return suggestion


__all__ = [
    "MAX_DOCUMENT_CHARS",
    "MIN_QUOTE_LENGTH",
    "ProposedMapping",
    "ProposedMappings",
    "SuggestionDecisionError",
    "SuggestionOutcome",
    "UnsupportedFormatError",
    "approve_suggestion",
    "build_prompt",
    "reject_suggestion",
    "suggest_evidence_mappings",
    "verify_quote",
]
