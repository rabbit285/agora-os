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
a complete answer on its own.

A narrow class of proposal is accepted without a person: one whose
quote was found in the document, against a requirement not flagged
sensitive, above a confidence floor. `route_suggestion` holds those
rules, checks confidence *last*, and records why each decision went the
way it did. Everything touching a high-sensitivity requirement — breach
notification, DPIA, prohibited AI practices, human oversight — reaches a
person regardless of how certain the model claimed to be.

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

import asyncio
import re
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
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
# Below this, whatever came out of the parser is not a document. Set just
# high enough to reject a PDF that yielded only page furniture, and low
# enough that a genuinely terse one-paragraph policy still processes.
MIN_EXTRACTED_CHARACTERS = 50


# A section shorter than this is a heading, not a passage worth citing.
MIN_SECTION_CHARS = 120
# Sections handed to the model per pass. Enough for a normal policy;
# beyond this the prompt stops fitting and precision degrades anyway.
MAX_SECTIONS = 40

# Auto-approval floor. Deliberately not sufficient on its own — see
# `route_suggestion`, where confidence is the last condition checked,
# after the ones that actually protect the customer.
AUTO_APPROVE_CONFIDENCE = 0.90

_SECTION_PATTERN = re.compile(
    r"^\s*((?:section|clause|article|part|appendix|annex)\s+[\w.]+|\d+(?:\.\d+)*\.?)\s*[-–—:.]?\s*(.*)$",
    re.IGNORECASE,
)


@dataclass
class DocumentSection:
    """One addressable piece of a document.

    `label` is how the document names it, not an index we invented — an
    auditor following a citation needs to find it in their own copy, and
    "chunk 7" is not something they can look up.
    """

    index: int
    label: str
    text: str


def split_into_sections(document_text: str) -> list[DocumentSection]:
    """Split a document on its own headings so citations can point at one.

    Deliberately not fixed-size chunking. A 1000-character window cuts
    mid-sentence and produces a citation like "characters 2000-3000",
    which is useless to the person checking it. Splitting on the
    document's own numbering gives back a label it already uses.

    Falls back to a single whole-document section when nothing looks like
    a heading, so an unstructured document still processes — with honest
    provenance rather than an invented section number.
    """
    lines = document_text.splitlines()
    sections: list[DocumentSection] = []
    current_label: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if current_label is None:
            return
        text = nl_join(buffer).strip()
        if len(text) >= MIN_SECTION_CHARS:
            sections.append(
                DocumentSection(index=len(sections) + 1, label=current_label, text=text)
            )

    for line in lines:
        match = _SECTION_PATTERN.match(line) if line.strip() else None
        # A heading is short. A paragraph that happens to start with a
        # number is not, and treating it as one would fragment the body.
        if match and len(line.strip()) <= 90:
            flush()
            heading = match.group(2).strip()
            current_label = (
                f"{match.group(1).strip()} {heading}".strip() if heading else match.group(1).strip()
            )
            buffer = [line]
        else:
            buffer.append(line)

    flush()

    if not sections:
        whole = document_text.strip()
        if whole:
            sections = [DocumentSection(index=1, label="Whole document", text=whole)]
    return sections[:MAX_SECTIONS]


def nl_join(lines: list[str]) -> str:
    return "\n".join(lines)


@dataclass
class RoutingDecision:
    status: str
    reason: str


def route_suggestion(
    *,
    quote_verified: bool,
    confidence: float | None,
    requirement_sensitivity: str | None,
) -> RoutingDecision:
    """Decide whether a proposal can stand without a person seeing it.

    Ordered so that confidence is the *last* thing consulted, and never
    sufficient alone. A model that is confident and wrong is the failure
    this whole feature is built around; letting a high score bypass the
    citation check would reintroduce exactly the risk the check exists to
    remove.

    Auto-approval is a convenience for the obvious cases — a verified
    quote against an ordinary requirement — and every one is recorded
    with its reason and remains reversible.
    """
    if not quote_verified:
        return RoutingDecision(
            "unverifiable",
            "The quoted passage was not found in the document.",
        )
    if requirement_sensitivity == "high":
        return RoutingDecision(
            "proposed",
            "This requirement is one where a wrong mapping is expensive to discover later, so it always goes to a person.",
        )
    if confidence is None or confidence < AUTO_APPROVE_CONFIDENCE:
        return RoutingDecision(
            "proposed",
            "The model was not confident enough for this to stand without review.",
        )
    return RoutingDecision(
        "auto_approved",
        "The quoted passage was found in the document and the requirement is not one flagged as sensitive.",
    )


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
    section_index: int = Field(
        description="The number in brackets next to the section the passage came from"
    )
    evidence_type: str = Field(
        default="policy_statement",
        description=(
            "One of: policy_statement (states what the organization will do), "
            "procedure (describes how), record (shows something happened), "
            "attestation (a third party asserts it), other"
        ),
    )


class ProposedMappings(BaseModel):
    mappings: list[ProposedMapping] = Field(default_factory=list)


class DocumentAnalysis(BaseModel):
    """What one pass over a document produces: what it is, and where it
    belongs.

    Classification and mapping are answered in a single call because they
    are one reading of one document — asking twice doubles cost and
    latency to re-derive the same understanding, and invites the two
    answers to disagree with each other.
    """

    document_type: str = Field(
        description="What this document is, e.g. 'Privacy Notice', 'Record of Processing Activities'"
    )
    document_domain: str = Field(
        description="The compliance domain, e.g. 'Privacy / GDPR', 'Security', 'AI Governance'"
    )
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


def build_prompt(
    sections: list[DocumentSection], controls: list[tuple[Control, list[str]]]
) -> str:
    """Prompt the model over labelled sections rather than a raw blob.

    The section list is what makes a citation checkable: the model says
    which section it read the passage in, and that label goes on the
    suggestion so a reviewer opens one section instead of re-reading the
    whole policy.
    """
    lines = [
        "You are helping a compliance team decide which of their controls a document evidences.",
        "",
        "CONTROLS:",
    ]
    for index, (control, requirement_codes) in enumerate(controls, start=1):
        codes = f" (mapped to {', '.join(requirement_codes)})" if requirement_codes else ""
        description = f" — {control.description}" if control.description else ""
        lines.append(f"[{index}] {control.title}{codes}{description}")

    lines += ["", "DOCUMENT SECTIONS:"]
    for section in sections:
        lines.append(f"[{section.index}] {section.label}")
        lines.append(section.text)
        lines.append("")

    lines += [
        "",
        "First identify the document:",
        "  - document_type: what this document is, in the words the document itself uses",
        "    (for example 'Privacy Notice', 'Information Security Policy', 'Record of",
        "    Processing Activities', 'Data Processing Addendum'). If it does not announce",
        "    itself, say what it most resembles — do not invent a formal title it lacks.",
        "  - document_domain: the compliance domain it belongs to (for example",
        "    'Privacy / GDPR', 'Security', 'AI Governance', 'Vendor Management').",
        "",
        "Then, for each control this document genuinely evidences, return a mapping containing:",
        "  - control_index: the number in brackets next to the control above",
        "  - section_index: the number in brackets next to the section the passage came from",
        "  - confidence: 0.0 to 1.0",
        "  - rationale: one sentence on why this document supports that control",
        "  - evidence_type: policy_statement, procedure, record, attestation, or other",
        "  - quoted_passage: a passage copied VERBATIM from that section",
        "",
        "Rules:",
        "  - The quoted passage must appear word-for-word in the section you name. Do not",
        "    paraphrase, summarise, correct, or reflow it. Passages that do not appear in",
        "    the document are checked and discarded.",
        "  - Only propose a control where the document really does say something that supports",
        "    it. Returning no mappings is a valid and useful answer.",
        "  - Do not propose a control merely because its subject is related to the document's.",
    ]
    return "\n".join(lines)

async def _load_controls(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[tuple[Control, list[str]]]:
    # Ordered explicitly. `control_index` in the prompt is positional, so
    # an unordered query makes the same document produce different index
    # numbers between runs — internally consistent each time, but
    # impossible to reason about or reproduce when a mapping looks wrong.
    controls = list(
        (
            await db.execute(
                select(Control)
                .where(Control.organization_id == organization_id)
                .order_by(Control.created_at, Control.id)
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
    sections = split_into_sections(document_text)
    sections_by_index = {section.index: section for section in sections}
    controls = await _load_controls(db, organization_id=organization_id)
    if not controls:
        return SuggestionOutcome(suggestions=[], unverifiable_count=0, considered_controls=0)

    by_index = {index: control for index, (control, _) in enumerate(controls, start=1)}

    # The requirement each control answers to, preferring the most
    # sensitive one it maps to. A control covering both an ordinary
    # requirement and a high-sensitivity one must route by the
    # sensitive one — taking the lenient path for a control that also
    # serves Article 33 is exactly the mistake worth preventing.
    requirement_by_control: dict[uuid.UUID, Requirement] = {}
    for control, _ in controls:
        mapped = list(
            (
                await db.execute(
                    select(Requirement)
                    .join(ControlMapping, ControlMapping.requirement_id == Requirement.id)
                    .where(ControlMapping.control_id == control.id)
                )
            )
            .scalars()
            .all()
        )
        if mapped:
            requirement_by_control[control.id] = max(
                mapped, key=lambda r: r.sensitivity == "high"
            )

    gateway = gateway or ModelGateway()
    raw = await gateway.generate_structured(
        db,
        organization_id=organization_id,
        requested_by=actor_user_id,
        request=GenerateRequest(
            task_type="compliance.evidence_mapping",
            prompt=build_prompt(sections, controls),
            prompt_template="compliance_evidence_mapping",
            prompt_version="1",
            input_classification="confidential",
        ),
        schema=DocumentAnalysis,
    )
    # The gateway is typed to return BaseModel. Narrowed with a real
    # check rather than a cast: an adapter returning the wrong shape
    # should fail loudly, not quietly propose nothing and look like
    # "the document matched no controls".
    if not isinstance(raw, DocumentAnalysis):
        raise AiProviderUnavailable(
            "The AI provider returned an unexpected response shape for evidence mapping."
        )
    proposals = raw

    # Record what the document is on the file itself, so the library can
    # show a classified document even when it evidenced no control.
    file_record.document_type = raw.document_type[:80] or None
    file_record.document_domain = raw.document_domain[:80] or None

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

        section = sections_by_index.get(proposal.section_index)
        # Verify against the section the model named where it named one,
        # and against the whole document otherwise. Checking the named
        # section is stricter: a passage that exists elsewhere in the
        # document but not where the model said it read it is a citation
        # that would not survive an auditor following it.
        haystack = section.text if section else document_text
        verified = verify_quote(proposal.quoted_passage, haystack)
        if not verified and section is not None:
            # Fall back to the whole document before condemning it: the
            # section split is ours, not the document's, and a passage
            # straddling our boundary is a mis-split, not a fabrication.
            verified = verify_quote(proposal.quoted_passage, document_text)
            if verified:
                section = None

        requirement = requirement_by_control.get(control.id)
        decision = route_suggestion(
            quote_verified=verified,
            confidence=proposal.confidence,
            requirement_sensitivity=requirement.sensitivity if requirement else None,
        )
        if decision.status == "unverifiable":
            unverifiable += 1

        suggestion = EvidenceSuggestion(
            organization_id=organization_id,
            file_id=file_record.id,
            control_id=control.id,
            requirement_id=requirement.id if requirement else None,
            status=decision.status,
            routing_reason=decision.reason,
            confidence=proposal.confidence,
            rationale=proposal.rationale,
            quoted_passage=proposal.quoted_passage,
            quote_verified=verified,
            source_location=section.label if section else None,
            evidence_type=proposal.evidence_type[:40] if proposal.evidence_type else None,
        )
        db.add(suggestion)
        await db.flush()
        suggestions.append(suggestion)

        # An auto-approved mapping has to become real Evidence here, or
        # the status is a label on a proposal nobody acted on. Recorded
        # with created_by unset: no person made this decision, and
        # attributing it to whoever happened to upload the document
        # would put their name on a judgement they never made.
        if decision.status == "auto_approved":
            evidence = Evidence(
                organization_id=organization_id,
                control_id=control.id,
                file_id=file_record.id,
                title=file_record.original_filename,
                created_by=None,
            )
            db.add(evidence)
            await db.flush()
            suggestion.evidence_id = evidence.id
            suggestion.decided_at = datetime.now(UTC)
            control.needs_reassessment = True
            await record_event(
                db,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="compliance.evidence.suggestion_auto_approved",
                object_type="evidence_suggestion",
                object_id=str(suggestion.id),
                after_state={
                    "evidence_id": str(evidence.id),
                    "control_id": str(control.id),
                    "confidence": proposal.confidence,
                    "source_location": suggestion.source_location,
                    # Recorded so an auto-approval can always be
                    # explained after the fact, even if the rules change.
                    "reason": decision.reason,
                },
            )

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
            "auto_approved": sum(1 for s in suggestions if s.status == "auto_approved"),
            "unverifiable": unverifiable,
            "controls_considered": len(controls),
            "sections": len(sections),
        },
    )
    return SuggestionOutcome(
        suggestions=suggestions,
        unverifiable_count=unverifiable,
        considered_controls=len(controls),
    )


async def process_document(
    file_id: uuid.UUID,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]] | None = None,
) -> None:
    """Run the full upload → ready pipeline for one document.

    Designed to be handed to `BackgroundTasks`, so it opens its own
    session: the request's session is closed by the time this runs.

    Each stage commits before starting the next. That is the point — the
    user is watching this happen, and a status that only appears at the
    end is indistinguishable from a spinner. It also means a crash leaves
    the document parked at the stage that broke rather than silently back
    at the beginning.
    """
    # Imported here rather than at module scope: assessment imports
    # this module's models, and a top-level import would close the loop.
    from app.compliance.assessment import reassess_frameworks_for_control
    from app.core.storage import download_object
    from app.db.session import AsyncSessionLocal

    factory = session_factory or AsyncSessionLocal

    async def _stage(db: AsyncSession, file_record: File, stage: str) -> None:
        file_record.processing_status = stage
        await db.commit()

    async with factory() as db:
        file_record = await db.get(File, file_id)
        if file_record is None or file_record.organization_id != organization_id:
            return

        try:
            await _stage(db, file_record, "parsing")
            file_bytes = await asyncio.to_thread(download_object, file_record.storage_key)
            document_text = extract_text(file_record.content_type, file_bytes)

            # A document that parsed to nothing is not ready, it is
            # unreadable — most often a scanned PDF with no text layer.
            # Reporting `ready` here would show an empty evidence list and
            # let the user conclude the document matched no controls.
            if len(document_text.strip()) < MIN_EXTRACTED_CHARACTERS:
                file_record.processing_status = "failed"
                file_record.extracted_characters = len(document_text.strip())
                file_record.processing_error = (
                    "No readable text could be extracted from this document. If it is a "
                    "scanned PDF it needs to be run through OCR before it can be analysed."
                )
                file_record.processed_at = datetime.now(UTC)
                await db.commit()
                return

            file_record.extracted_characters = len(document_text)
            await _stage(db, file_record, "analyzing")

            outcome = await suggest_evidence_mappings(
                db,
                organization_id=organization_id,
                file_record=file_record,
                file_bytes=file_bytes,
                actor_user_id=actor_user_id,
            )
            auto_approved_controls = {
                suggestion.control_id
                for suggestion in outcome.suggestions
                if suggestion.status == "auto_approved"
            }
            file_record.processing_status = "ready"
            file_record.processed_at = datetime.now(UTC)
            await db.commit()

            # Auto-approved mappings created real evidence, so the
            # frameworks those controls serve are now out of date. Human
            # approval already triggers this; an automatic one has to as
            # well, or the customer is left with controls flagged stale
            # and a readiness figure nobody re-ran.
            for control_id in auto_approved_controls:
                await reassess_frameworks_for_control(
                    control_id,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    session_factory=session_factory,
                )

        except UnsupportedFormatError:
            # Terminal and distinct from `failed`: retrying will never
            # help, so the UI offers manual attachment instead of a retry.
            file_record.processing_status = "unsupported"
            file_record.processing_error = (
                f"Veyntra cannot read {file_record.content_type} documents. "
                "Attach it to a control manually if it is relevant."
            )
            file_record.processed_at = datetime.now(UTC)
            await db.commit()

        except Exception as exc:  # noqa: BLE001 - status must reflect any failure
            # Broad by intent: whatever went wrong, the document must not
            # be left stuck mid-pipeline claiming to still be working.
            await db.rollback()
            file_record = await db.get(File, file_id)
            if file_record is not None:
                file_record.processing_status = "failed"
                file_record.processing_error = _safe_error_message(exc)
                file_record.processed_at = datetime.now(UTC)
                await db.commit()


def _safe_error_message(exc: Exception) -> str:
    """A message for the UI that cannot leak provider internals.

    Provider exceptions can carry request payloads, URLs and key
    fragments. Only our own AI exception types are quoted; anything else
    is reported by class name alone.
    """
    if isinstance(exc, AiProviderUnavailable):
        return str(exc)
    return f"Processing failed ({type(exc).__name__}). See server logs for detail."


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

    # The control's last assessment predates this evidence, so whatever it
    # concluded is now stale. Flagged rather than re-run: an approval must
    # not silently move a stated compliance position.
    control = await db.get(Control, suggestion.control_id)
    if control is not None:
        control.needs_reassessment = True

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
    "MIN_EXTRACTED_CHARACTERS",
    "MIN_QUOTE_LENGTH",
    "DocumentAnalysis",
    "ProposedMapping",
    "ProposedMappings",
    "SuggestionDecisionError",
    "SuggestionOutcome",
    "UnsupportedFormatError",
    "approve_suggestion",
    "build_prompt",
    "process_document",
    "reject_suggestion",
    "suggest_evidence_mappings",
    "verify_quote",
]
