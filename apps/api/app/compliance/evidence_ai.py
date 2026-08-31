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
import logging
import re
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.exceptions import AiProviderUnavailable
from app.ai.gateway import GenerateRequest, ModelGateway
from app.audit.service import record_event
from app.compliance.assessment import note_evidence_on_control
from app.compliance.models import Control, ControlMapping, Evidence, EvidenceSuggestion, Requirement
from app.core.dedupe import content_fingerprint, get_or_create, text_fingerprint
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
logger = logging.getLogger("agora.compliance.evidence")

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
    requirement_code: str | None = Field(
        default=None,
        description=(
            "Which ONE of that control's mapped requirements this passage evidences, "
            "copied exactly as written in the brackets after the control (for example "
            "'Art. 15' or '9.1'). Name one whenever the passage is about a specific "
            "obligation. Leave null only when the passage genuinely speaks to the "
            "control as a whole and no single requirement fits better than the others."
        ),
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

    The mapping prompt asks the model what the document is as well,
    because a model that knows it is reading a retention schedule maps it
    better than one that does not. That answer is context for this call
    only — `app.compliance.classification` owns the record.

    They were once one call, on the reasoning that classification and
    mapping are one reading of one document. True, and it held until a
    customer's first upload: with no controls there is no mapping
    question, the call returned early, and the classification went with
    it.
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
        "  - requirement_code: which ONE of that control's mapped requirements this",
        "    passage evidences. Copy it exactly as written in the brackets after the",
        "    control above. Name one whenever the passage is about a specific",
        "    obligation — most passages are. Leave it null only when the passage really",
        "    does speak to the control as a whole.",
        "  - quoted_passage: a passage copied VERBATIM from that section",
        "",
        "Rules:",
        "  - The quoted passage must appear word-for-word in the section you name. Do not",
        "    paraphrase, summarise, correct, or reflow it. Passages that do not appear in",
        "    the document are checked and discarded.",
        "  - Only propose a control where the document really does say something that supports",
        "    it. Returning no mappings is a valid and useful answer.",
        "  - Do not propose a control merely because its subject is related to the document's.",
        "  - The requirement_code must be one of the codes in brackets after the control",
        "    you chose. A code from a different control, or one you have inferred rather",
        "    than read, is discarded.",
        "  - If a document evidences two requirements on the same control, return two",
        "    mappings for that control, each naming its own requirement_code and quoting",
        "    the passage that supports it.",
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
    # By reference code, so a proposal naming one can be checked against
    # the requirements that control actually serves.
    requirements_by_control: dict[uuid.UUID, dict[str, Requirement]] = {}
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
            requirements_by_control[control.id] = {
                requirement.reference_code: requirement for requirement in mapped
            }

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

    # Deliberately not recorded here. `classify_document` owns what a
    # document is, and runs before this whether or not the organization
    # has controls — this function used to be the only thing that set it,
    # which is why a new customer's first upload came back unclassified.
    #
    # The mapping prompt still asks: knowing what it is reading makes the
    # model map better. Its answer is context for this call, not the
    # record.

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
    evidenced_controls: set[uuid.UUID] = set()
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

        # Routing is decided by the most sensitive requirement the control
        # serves, never by whichever one the model happened to name — a
        # lenient path for a control that also serves Article 33 is the
        # mistake this gate exists to prevent.
        requirement = requirement_by_control.get(control.id)
        # What the passage was cited *against*, if the model named one
        # and it really is on this control. An invented code is dropped
        # rather than trusted: unattributed evidence goes to a person,
        # wrongly attributed evidence becomes coverage nobody has.
        cited_requirement = None
        if proposal.requirement_code:
            cited_requirement = requirements_by_control.get(control.id, {}).get(
                proposal.requirement_code.strip()
            )
        decision = route_suggestion(
            quote_verified=verified,
            confidence=proposal.confidence,
            requirement_sensitivity=requirement.sensitivity if requirement else None,
        )
        if decision.status == "unverifiable":
            unverifiable += 1

        # The logical identity of this proposal. Reprocessing the same
        # document produces the same passage against the same control,
        # and that is one suggestion however many times it is extracted.
        passage_hash = text_fingerprint(
            section.label if section else None, proposal.quoted_passage
        )
        # The same document, control and requirement is the same mapping,
        # however many times the document is analysed. The requirement is
        # part of the identity because it is part of the claim — one
        # policy can evidence one control for two different obligations.
        requirement_id = cited_requirement.id if cited_requirement else None
        existing = (
            await db.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.organization_id == organization_id,
                    EvidenceSuggestion.file_id == file_record.id,
                    EvidenceSuggestion.control_id == control.id,
                    EvidenceSuggestion.requirement_id == requirement_id,
                )
            )
        ).scalars().first()

        if existing is not None:
            # Already known. A decision somebody made about it is the one
            # thing here that cannot be regenerated, so re-extraction
            # refreshes the model's own output and leaves the verdict
            # alone — an approved mapping must never return to the review
            # queue because a job ran twice.
            if existing.status == "proposed":
                # Refresh what the model said this time; the quote can
                # legitimately differ between runs and the newest reading
                # is the one to keep.
                existing.confidence = proposal.confidence
                existing.rationale = proposal.rationale
                existing.routing_reason = decision.reason
                existing.status = decision.status
                existing.passage_hash = passage_hash
                existing.quoted_passage = proposal.quoted_passage
                existing.source_location = section.label if section else None
            suggestions.append(existing)
            if existing.status in ("approved", "auto_approved"):
                evidenced_controls.add(control.id)
            continue

        suggestion = EvidenceSuggestion(
            organization_id=organization_id,
            passage_hash=passage_hash,
            file_id=file_record.id,
            control_id=control.id,
            requirement_id=cited_requirement.id if cited_requirement else None,
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
            # One document supporting one control is one piece of
            # evidence. This used to insert blindly, so five reprocessing
            # runs left five identical rows and the control's evidence
            # count counted our retries.
            evidence, _ = await get_or_create(
                db,
                Evidence,
                match={
                    "organization_id": organization_id,
                    "file_id": file_record.id,
                    "control_id": control.id,
                },
                defaults={
                    "title": file_record.original_filename,
                    "created_by": None,
                },
            )
            suggestion.evidence_id = evidence.id
            suggestion.decided_at = datetime.now(UTC)
            control.needs_reassessment = True
            evidenced_controls.add(control.id)
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

    # Announced once per control, not once per mapping. One document that
    # evidences a control in three places is still one document arriving,
    # and three identical lines in the gap's activity feed read as three
    # separate uploads.
    for evidenced_control_id in evidenced_controls:
        await note_evidence_on_control(
            db,
            organization_id=organization_id,
            control_id=evidenced_control_id,
            filename=file_record.original_filename,
            actor_user_id=actor_user_id,
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
    from app.compliance.classification import classify_document
    from app.compliance.copilot_index import index_for_copilot
    from app.compliance.policy_governance import ensure_policy_for_document
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

        # Already analysed, or being analysed right now. A user who
        # refreshes mid-processing, a queue that redelivers, or a
        # BackgroundTask scheduled twice all land here — and running the
        # pipeline again would re-extract, re-map and re-notify for work
        # that is already done or in flight.
        if file_record.processing_status in ("parsing", "analyzing"):
            return

        try:
            await _stage(db, file_record, "parsing")
            file_bytes = await asyncio.to_thread(download_object, file_record.storage_key)

            # The document's real identity, computed from the bytes
            # themselves. Uploads are presigned, so the API never saw the
            # content before now: whatever hash the client claimed at
            # upload time is a hint, and this is the fact.
            fingerprint = content_fingerprint(file_bytes)
            duplicate_of = await _already_analysed(
                db,
                organization_id=organization_id,
                fingerprint=fingerprint,
                size_bytes=file_record.size_bytes,
                excluding=file_record.id,
            )
            if duplicate_of is not None:
                # The same bytes are already a fully analysed document.
                # Running the pipeline again would produce a second set
                # of evidence, mappings and gaps for one real-world
                # policy, so this row is marked as what it is and the
                # original stands.
                file_record.processing_status = "duplicate"
                file_record.duplicate_of_id = duplicate_of.id
                file_record.processing_error = None
                file_record.processed_at = datetime.now(UTC)
                await db.commit()
                return

            file_record.content_hash = fingerprint
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

            # --- understanding the document ---------------------------
            #
            # Everything from here to the mapping call answers "what is
            # this document?", and none of it depends on the
            # organization having controls, frameworks or anything else
            # set up. A new customer's first upload has to work, and it
            # did not: classification used to be a by-product of the
            # mapping call, so an organization with no controls got a
            # document with no type, which meant no Managed Policy.
            await classify_document(
                db,
                organization_id=organization_id,
                file_record=file_record,
                document_text=document_text,
                actor_user_id=actor_user_id,
            )

            # What the document says about itself — version, effective
            # date — and whether it looks like a newer version of
            # something already here. Recorded as a *proposal*, never
            # acted on: silently merging two documents that turn out to
            # be unrelated destroys evidence lineage in a way nobody
            # notices until an auditor asks.
            await _detect_version_relationship(
                db,
                organization_id=organization_id,
                file_record=file_record,
                document_text=document_text,
            )

            # A policy document gets its governance record here rather
            # than waiting for someone to retype the title on another
            # screen. Detection only — no owner, no approval, no review
            # date, because the product cannot know those and a guess
            # would be a fabricated compliance record.
            await ensure_policy_for_document(
                db,
                organization_id=organization_id,
                file_record=file_record,
                document_text=document_text,
                actor_user_id=actor_user_id,
            )
            await db.commit()

            # The other half of "processed". Document Intelligence has
            # read the document; the Copilot cannot answer a question
            # about it until it is chunked and embedded. Its own failure
            # is recorded on the file rather than raised: an embedding
            # provider being down must not discard a classification that
            # succeeded.
            await index_for_copilot(
                db,
                organization_id=organization_id,
                file_record=file_record,
                file_bytes=file_bytes,
            )

            # --- mapping it to controls -------------------------------
            #
            # The only stage that needs controls to exist. When none do,
            # it returns an empty result and the document is still
            # analysed — "we have nothing to map this to yet" is a state,
            # not a failure.

            # Reprocessing an unchanged document is a reconciliation, not
            # a second opinion. The bytes are immutable once stored, so
            # running extraction again asks a non-deterministic model the
            # same question and takes whatever it says this time — which
            # is how three reprocesses turned two evidence items into
            # four. None of those were duplicates; they were the model
            # noticing different things on different readings, and a
            # customer watching their evidence count climb while nothing
            # changed has no way to tell the difference.
            #
            # Extraction runs when there is something new to read: a
            # document analysed for the first time, or one whose control
            # set has grown since — which is how a document uploaded
            # before any framework was adopted gets mapped once controls
            # appear, without anybody re-uploading it. Understanding the
            # document, above, runs every time regardless.
            reextract = await _should_extract(
                db, organization_id=organization_id, file_record=file_record
            )
            if not reextract:
                outcome = SuggestionOutcome(
                    suggestions=[], unverifiable_count=0, considered_controls=0
                )
                logger.info(
                    "Skipping re-extraction for %s: unchanged content and no new controls",
                    file_record.id,
                )
            else:
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

            # An upload the person made *as* a new version is linked
            # here, now that there is evidence on both sides to
            # reconcile. Detection never reaches this branch: it
            # proposes, and a proposal waits on a person.
            await _link_confirmed_version(
                db,
                organization_id=organization_id,
                file_record=file_record,
                actor_user_id=actor_user_id,
            )
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
            #
            # Logged server-side, because the message the customer sees is
            # deliberately just a class name and a failure nobody can
            # diagnose is a failure nobody fixes. Database errors are
            # logged with their detail — they are ours. Anything that
            # might have come from a model provider is logged by class
            # alone: provider exceptions carry request payloads, and a
            # log is not a safe place for them.
            if isinstance(exc, SQLAlchemyError):
                logger.exception("Document processing failed for %s", file_id)
            else:
                logger.error(
                    "Document processing failed for %s (%s)",
                    file_id,
                    type(exc).__name__,
                )
            await db.rollback()
            file_record = await db.get(File, file_id)
            if file_record is not None:
                file_record.processing_status = "failed"
                file_record.processing_error = _safe_error_message(exc)
                file_record.processed_at = datetime.now(UTC)
                await db.commit()


async def _should_extract(
    db: AsyncSession, *, organization_id: uuid.UUID, file_record: File
) -> bool:
    """Whether there is anything new for the extractor to find.

    True the first time a document is read. True again once controls
    exist that were not considered last time — a framework adopted after
    the upload is a real reason to look at the document again.

    False for a reprocess of an unchanged document against an unchanged
    control set: the inputs are identical, so the output should be too,
    and the only thing another extraction run can produce is a different
    answer to the same question.
    """
    from app.compliance.models import Control

    if file_record.processed_at is None:
        return True

    considered = (
        await db.execute(
            select(func.count(EvidenceSuggestion.id)).where(
                EvidenceSuggestion.organization_id == organization_id,
                EvidenceSuggestion.file_id == file_record.id,
            )
        )
    ).scalar_one()
    if not considered:
        # Analysed before but produced nothing — worth another look, and
        # there is no prior result to disturb.
        return True

    newer_controls = (
        await db.execute(
            select(func.count(Control.id)).where(
                Control.organization_id == organization_id,
                Control.created_at > file_record.processed_at,
            )
        )
    ).scalar_one()
    return bool(newer_controls)


async def _already_analysed(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    fingerprint: str,
    size_bytes: int,
    excluding: uuid.UUID,
) -> File | None:
    """Another document in this organization with exactly these bytes.

    Only a `ready` one counts. A previous attempt that failed, or one
    still parsing, is not a result to adopt — deduplicating against it
    would strand the customer with a document that never produced
    anything and no way to retry.
    """
    already = (
        await db.execute(
            select(File)
            .where(
                File.organization_id == organization_id,
                File.content_hash == fingerprint,
                File.id != excluding,
                File.processing_status == "ready",
            )
            .order_by(File.created_at)
            .limit(1)
        )
    ).scalars().first()
    if already is not None:
        return already

    # Nothing matched by hash — but a file uploaded before hashes existed
    # has none, so the identical document may be sitting right there
    # unrecognised. Candidates are narrowed by size first (a cheap,
    # exact necessary condition) and only those few are read and hashed,
    # which also records what they are so the next upload matches
    # immediately.
    from app.core.storage import download_object

    unhashed = list(
        (
            await db.execute(
                select(File).where(
                    File.organization_id == organization_id,
                    File.content_hash.is_(None),
                    File.id != excluding,
                    File.processing_status == "ready",
                    File.size_bytes == size_bytes,
                )
                .order_by(File.created_at)
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    for candidate in unhashed:
        try:
            candidate.content_hash = content_fingerprint(
                await asyncio.to_thread(download_object, candidate.storage_key)
            )
        except Exception:  # noqa: BLE001 - a missing object is not a crash
            continue
        if candidate.content_hash == fingerprint:
            return candidate
    return None


async def _link_confirmed_version(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_record: File,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Complete an explicit "upload new version", now that it can be.

    Only ever runs for `version_confidence == "confirmed"`, which the
    endpoint sets when the person names the document being replaced. A
    detected candidate never reaches here — the difference between a
    guess and a decision is exactly what this is guarding.

    If the target moved while this was processing, the upload is left as
    an ordinary document with the proposal still on it, for a person to
    settle from the banner. Worse than success; far better than a
    half-linked chain.
    """
    if file_record.version_confidence != "confirmed":
        return
    target_id = file_record.version_candidate_id
    if target_id is None:
        return

    previous = await db.get(File, target_id)
    if (
        previous is None
        or previous.organization_id != organization_id
        or previous.superseded_by_id is not None
    ):
        file_record.version_confidence = "medium"
        return

    from app.compliance.version_promotion import accept_new_version

    try:
        await accept_new_version(
            db,
            organization_id=organization_id,
            previous=previous,
            current=file_record,
            actor_user_id=actor_user_id,
            version_label=file_record.version_label,
        )
    except Exception:  # noqa: BLE001 - the document itself read fine
        # The document was read, classified and mapped successfully; only
        # the link failed. Marking the whole upload `failed` would tell
        # the customer their policy could not be processed, which is not
        # what happened. Left as a proposal for them to accept from the
        # banner instead.
        logger.exception("Linking a confirmed version failed for %s", file_record.id)
        file_record.version_confidence = "high"
        # A proposal with no reasons is one nobody can check. Detection
        # never ran here — the person said so themselves — so that is
        # what the banner says.
        file_record.version_reasons = [
            f"You uploaded this as a new version of {previous.original_filename}."
        ]
        return

    file_record.version_candidate_id = None
    file_record.version_confidence = None
    file_record.version_reasons = []


async def _detect_version_relationship(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_record: File,
    document_text: str,
) -> None:
    """Record whether this upload looks like a newer version of a document
    the organization already has.

    Never links anything. High confidence gets proposed prominently,
    medium gets asked about, low is not mentioned at all — prompting on
    every upload teaches people to dismiss the prompt.

    Skipped entirely when the person uploaded this *as* a new version of
    a document they named: they answered the question before it was
    asked, and a detector that overrode them would be worse than one that
    never ran.
    """
    if file_record.version_confidence == "confirmed" and file_record.version_candidate_id:
        from app.compliance.document_versioning import (
            detect_effective_date as _effective,
        )
        from app.compliance.document_versioning import detect_version_label as _label

        file_record.version_label = _label(document_text)
        file_record.version_effective_date = _effective(document_text)
        return
    from app.compliance.document_versioning import (
        detect_effective_date,
        detect_version_label,
        find_version_candidate,
    )
    from app.core.storage import download_object

    # What the document says about itself, recorded whether or not it
    # turns out to be a version of anything: the reader comparing two
    # documents needs both dates, and the one they are replacing was
    # read long before this upload existed.
    file_record.version_label = detect_version_label(document_text)
    file_record.version_effective_date = detect_effective_date(document_text)

    def read_text(other: File) -> str:
        try:
            return extract_text(other.content_type, download_object(other.storage_key))
        except Exception:  # noqa: BLE001 - an unreadable neighbour is not a failure
            return ""

    try:
        candidate = await find_version_candidate(
            db,
            organization_id=organization_id,
            file_record=file_record,
            document_text=document_text,
            read_text=read_text,
        )
    except Exception:  # noqa: BLE001 - detection is a convenience
        logger.warning("Version detection failed for %s", file_record.id)
        return

    if candidate is None:
        return

    file_record.version_candidate_id = candidate.file_id
    file_record.version_confidence = candidate.confidence
    file_record.version_reasons = candidate.reasons[:4]
    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=None,
        action="core.file.version_candidate_detected",
        object_type="file",
        object_id=str(file_record.id),
        after_state={
            "candidate": candidate.title,
            "confidence": candidate.confidence,
            "score": candidate.score,
            "reasons": candidate.reasons[:4],
        },
    )


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

    # Reuses the row if this document already evidences this control —
    # approving a second proposal from the same document must strengthen
    # the existing evidence, not shadow it with a copy.
    evidence, _ = await get_or_create(
        db,
        Evidence,
        match={
            "organization_id": organization_id,
            "file_id": suggestion.file_id,
            "control_id": suggestion.control_id,
        },
        defaults={
            "title": title or file_record.original_filename,
            "created_by": actor_user_id,
        },
    )

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
        await note_evidence_on_control(
            db,
            organization_id=organization_id,
            control_id=control.id,
            filename=file_record.original_filename,
            actor_user_id=actor_user_id,
        )

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
