"""Fixed-size character chunking with overlap.

Deliberately simple for Phase 2 (spec's document-intelligence pipeline
needs *a* chunking strategy before embeddings can exist at all). Token-
aware / semantic chunking is a later improvement, not a Phase 2 blocker.
"""

from __future__ import annotations

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def chunk_text(
    text: str, *, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    text = text.strip()
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap
    while start < len(text):
        chunk = text[start : start + chunk_size].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def estimate_token_count(text: str) -> int:
    """Rough heuristic (~4 chars/token for English), not a real tokenizer.
    Good enough for Phase 2 bookkeeping; replace if a model's exact token
    count ever becomes load-bearing (e.g. context-window budgeting)."""
    return max(1, len(text) // 4)
