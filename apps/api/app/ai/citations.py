"""Turning a retrieved chunk into something a customer can act on.

A citation used to render as `Document da7966ef · chunk 5`. Both halves
of that are ours, not the reader's: the UUID is a primary key and the
chunk number is an artefact of slicing the file into 1000-character
windows. Neither can be looked up in the customer's own copy of the
document, which is the only thing a citation is for.

So every citation is resolved here into what the document actually calls
itself — its title, the heading in force where the passage sits, the page
it fell on, and the passage itself — before it leaves the API.

**The identifiers do not disappear.** `ResolvedCitation` still carries
`document_id`, `chunk_id` and `chunk_index`, and the AI request record
still logs every retrieved chunk by id, because an auditor asking "what
exactly did the model read" needs the exact chunk. They are simply not
serialized into the customer-facing payload: `document_id` survives as a
link target and nothing else, and the schema in app.ai.schemas has no
field a chunk id could be rendered from.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import File
from app.core.routes import DOCUMENT_ROUTE, RETIRED_ROUTE_PREFIXES, document_detail_href
from app.knowledge.documents import readable_title
from app.knowledge.models import Document
from app.knowledge.retrieval import RetrievedChunk

# Long enough to be worth reading, short enough that five of them do not
# bury the answer they support.
PASSAGE_MAX_CHARS = 320

# DOCUMENT_ROUTE and RETIRED_ROUTE_PREFIXES live in app.core.routes and
# are re-exported here, because a citation is only one of the things that
# links to a document: the library, the evidence list, a control's
# evidence and a search hit all open the same page. One route, named
# once, so they cannot drift apart.

# Categories rather than names. The classifier calls some documents just
# "document", which as a source-type chip beside the title is noise.
_GENERIC_TYPES = {
    "document",
    "file",
    "other",
    "unknown",
    "uncategorized",
}

# The kinds of document a compliance library actually holds. A chip is a
# category, so it is reduced to one of these rather than printed as the
# classifier phrased it — that gave chips like "AI Support Assistant
# Processing Description (Internal Record/Assessment)", which is longer
# than the title it sits beside and tells the reader less.
_TYPE_WORDS = (
    "policy",
    "procedure",
    "standard",
    "guideline",
    "runbook",
    "notice",
    "charter",
    "register",
    "assessment",
    "record",
    "report",
    "agreement",
    "contract",
)

# Above this a chip has stopped being a label. Anything longer with no
# recognizable type word in it is dropped rather than truncated into
# something that reads like a mistake.
_MAX_TYPE_CHARS = 24


@dataclass(frozen=True)
class ResolvedCitation:
    """One place in one document, in the terms the document uses.

    `document_id` is here to open the document when the citation is
    clicked. `chunk_id` and `chunk_index` are here for traceability and
    are deliberately absent from the API schema — see the module
    docstring.
    """

    document_id: uuid.UUID
    chunk_id: uuid.UUID
    chunk_index: int
    document_title: str
    section: str | None
    page: int | None
    passage: str
    source_type: str | None

    @property
    def reference(self) -> str:
        """What the citation reads as: "AI Governance Policy — §7 Monitoring".

        Falls back through what is actually known. A document with no
        headings and no pages cites as its title alone, which is honest;
        appending "§1" to make it look precise would send the reader
        looking for a section that does not exist.
        """
        if self.section:
            return f"{self.document_title} — {_section_display(self.section)}"
        if self.page:
            return f"{self.document_title} — page {self.page}"
        return self.document_title

    @property
    def href(self) -> str:
        """Where clicking this citation goes: the document, at the passage.

        The same route the document library opens, from the same helper —
        a citation and a library row are two ways to the one page.

        The passage travels in the query string so the reader can find it
        in the text and highlight it. A fragment would need an anchor we
        invented, and inventing anchors is how "chunk 5" reached the UI in
        the first place.
        """
        return document_detail_href(
            self.document_id, passage=self.passage, section=self.section
        )


def _section_display(section: str) -> str:
    """Prefix a numbered heading with the section sign, leave a worded one.

    "3. Authentication" reads as "§3 Authentication"; "Access review" does
    not become a numbered section it never was. The full stop the document
    puts after its number is dropped, since the § already says the number
    is a reference.
    """
    trimmed = section.strip()
    if not re.match(r"^\d", trimmed):
        return trimmed
    return "§" + re.sub(r"^(\d+(?:\.\d+)*)\.(?=\s|$)", r"\1", trimmed)


def _title_of(document: Document, file_record: File | None) -> str:
    """What to call this document.

    `Document.title` wins over the filename. For a compliance upload the
    two are the same string, but where somebody gave the document a real
    title it is the better name — and a citation reading "Gdpr overview"
    that opens a page headed "GDPR Compliance Overview" is the kind of
    disagreement a reader has to stop and resolve.

    Either way it is cleaned by `readable_title` — the same function the
    document library and the detail page use, so a citation and the page
    it opens cannot disagree about what the document is called.
    """
    return readable_title(
        document.title or (file_record.original_filename if file_record else "")
    )


def _source_type_of(file_record: File | None, title: str) -> str | None:
    """The kind of document this is, when saying so adds anything.

    Reduced to one word where the classifier's phrasing contains one, so
    every chip in a list is the same size and means the same kind of
    thing: "Special-Category Personal Data Processing Policy" is a chip
    longer than the title it sits beside, and reads as "Policy". Anything
    that is neither a recognizable kind nor short enough to be a label is
    dropped, as is one that merely restates the title.
    """
    described = ((file_record.document_type if file_record else None) or "").strip()
    if not described or described.lower() in _GENERIC_TYPES:
        return None

    lowered = described.lower()
    # The earliest recognizable type word, so "Internal Record/Assessment"
    # reads as "Record" rather than as the whole parenthetical.
    positions = [(lowered.find(word), word) for word in _TYPE_WORDS if word in lowered]
    if positions:
        return min(positions)[1].capitalize()

    if len(described) > _MAX_TYPE_CHARS:
        return None
    if _comparable(described) == _comparable(title):
        return None
    return described[:1].upper() + described[1:]


def _comparable(text: str) -> str:
    """Letters and digits only, lower case — for asking whether two names
    are the same name written differently."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def passage_from(content: str) -> str:
    """The quotable part of a chunk.

    Chunks are fixed-size windows, so one routinely begins and ends
    mid-sentence. Both ends are marked with an ellipsis rather than
    presented as though the document said exactly this and stopped —
    a passage that looks complete but is not is a quiet misquote.
    """
    text = " ".join(content.split())
    if not text:
        return ""

    opens_mid_sentence = bool(text[0].islower() or text[0] in ",;:")
    if len(text) > PASSAGE_MAX_CHARS:
        window = text[:PASSAGE_MAX_CHARS]
        # Prefer a sentence end, then a word boundary, then a hard cut.
        sentence = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
        if sentence > PASSAGE_MAX_CHARS // 2:
            text = window[: sentence + 1]
        else:
            space = window.rfind(" ")
            text = (window[:space] if space > 0 else window).rstrip(",;: ") + "…"

    if opens_mid_sentence:
        text = f"…{text}"
    return text


async def resolve_citations(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    chunks: list[RetrievedChunk],
) -> list[ResolvedCitation]:
    """Resolve retrieved chunks into customer-facing citations.

    One per chunk, in the order given. Collapsing repeats is a display
    decision and belongs to `dedupe_for_display` — the prompt still needs
    a reference for every chunk it is shown.
    """
    if not chunks:
        return []

    document_ids = {chunk.document_id for chunk in chunks}
    documents = {
        document.id: document
        for document in (
            await db.execute(
                select(Document).where(
                    Document.id.in_(document_ids),
                    Document.organization_id == organization_id,
                )
            )
        )
        .scalars()
        .all()
    }
    file_ids = {document.file_id for document in documents.values()}
    files = {
        file_record.id: file_record
        for file_record in (await db.execute(select(File).where(File.id.in_(file_ids))))
        .scalars()
        .all()
    }

    resolved: list[ResolvedCitation] = []
    for chunk in chunks:
        document = documents.get(chunk.document_id)
        if document is None:
            # Retrieval is already tenant-scoped; a chunk whose document
            # is not in this organization is a bug, not something to
            # render. Dropped rather than shown with a placeholder title.
            continue

        file_record = files.get(document.file_id)
        title = _title_of(document, file_record)
        resolved.append(
            ResolvedCitation(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                document_title=title,
                section=chunk.section_label,
                page=chunk.page_number,
                passage=passage_from(chunk.content),
                source_type=_source_type_of(file_record, title),
            )
        )
    return resolved


def dedupe_for_display(resolved: list[ResolvedCitation]) -> list[ResolvedCitation]:
    """Collapse citations that point at the same place in the same document.

    A section longer than one chunk window retrieves as two or three
    chunks, and listing "AI Governance Policy — 7 Monitoring" three times
    is our slicing showing through. The reader is being pointed at a
    location; the location appears once. Nothing is hidden — the AI
    request record still holds every chunk that was retrieved.
    """
    seen: set[tuple[uuid.UUID, str | None, int | None]] = set()
    display: list[ResolvedCitation] = []
    for citation in resolved:
        place = (citation.document_id, citation.section, citation.page)
        if place in seen:
            continue
        seen.add(place)
        display.append(citation)
    return display


__all__ = [
    "DOCUMENT_ROUTE",
    "PASSAGE_MAX_CHARS",
    "RETIRED_ROUTE_PREFIXES",
    "ResolvedCitation",
    "dedupe_for_display",
    "passage_from",
    "resolve_citations",
]
