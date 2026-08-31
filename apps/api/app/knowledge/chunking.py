"""Fixed-size character chunking with overlap.

Deliberately simple for Phase 2 (spec's document-intelligence pipeline
needs *a* chunking strategy before embeddings can exist at all). Token-
aware / semantic chunking is a later improvement, not a Phase 2 blocker.

Each chunk carries where it came from — the heading in force at its start
and the page it fell on — because a citation has to be findable in the
customer's own copy of the document. The slice boundaries stay an
implementation detail; the heading and page are what a person can look
up.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.knowledge.headings import heading_at, heading_index, page_at

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


@dataclass(frozen=True)
class TextChunk:
    """One chunk and its provenance in the source document."""

    text: str
    section_label: str | None = None
    page_number: int | None = None


def chunk_document(
    text: str,
    *,
    page_starts: tuple[int, ...] | list[int] = (),
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[TextChunk]:
    """Chunk `text`, resolving each chunk's heading and page as it goes.

    Offsets are tracked against the original string, not the stripped one,
    so a document with leading whitespace does not shift every page number
    by a page.
    """
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    lead = len(text) - len(text.lstrip())
    body = text.strip()
    if not body:
        return []

    headings = heading_index(text)
    chunks: list[TextChunk] = []
    start = 0
    step = chunk_size - overlap
    while start < len(body):
        window = body[start : start + chunk_size]
        piece = window.strip()
        if piece:
            # Where the chunk's *content* begins, not where the window
            # does — a window opening on a blank line would otherwise be
            # attributed to whatever preceded it.
            offset = lead + start + (len(window) - len(window.lstrip()))
            chunks.append(
                TextChunk(
                    text=piece,
                    section_label=heading_at(headings, offset),
                    page_number=page_at(page_starts, offset),
                )
            )
        start += step
    return chunks


def chunk_text(
    text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    """The chunk strings alone, for callers that do not need provenance."""
    return [
        chunk.text
        for chunk in chunk_document(text, chunk_size=chunk_size, overlap=overlap)
    ]


def estimate_token_count(text: str) -> int:
    """Rough heuristic (~4 chars/token for English), not a real tokenizer.
    Good enough for Phase 2 bookkeeping; replace if a model's exact token
    count ever becomes load-bearing (e.g. context-window budgeting)."""
    return max(1, len(text) // 4)
