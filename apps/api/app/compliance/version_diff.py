"""What actually changed between two versions of a document.

"Version 2 is current" is not an answer to the question a compliance
reviewer is asking. They want to know which paragraph moved, because
that is what decides whether the control that relied on it still holds
and whether the approval on it can stand.

Compared section by section rather than line by line. A policy that gets
re-flowed by a word processor changes every line and says nothing new;
what matters is that §7 Monitoring now requires monthly review where it
used to say "should be monitored". Sections are the unit people argue
about, cite, and approve, so they are the unit this reports.

Nothing here writes. It reads two versions and describes the difference —
the decisions that follow from it live in `version_promotion`.
"""

from __future__ import annotations

import difflib
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import File
from app.knowledge.headings import heading_of
from app.knowledge.models import Document, DocumentChunk

# Below this, two versions of a section are the same section reworded
# rather than rewritten. Above it, somebody changed what it requires.
REWRITTEN_BELOW = 0.75

# A section shorter than this is a heading, a page number or a stray
# line, and reporting it as a change is noise that hides the real ones.
MIN_SECTION_CHARS = 20


@dataclass
class SectionChange:
    """One section, and what happened to it."""

    # added | removed | rewritten | reworded | unchanged
    change: str
    section: str | None
    previous_text: str | None = None
    current_text: str | None = None
    similarity: float = 0.0

    @property
    def summary(self) -> str:
        """What to say about it, in the reader's words."""
        # Text before the first heading is the title block and whatever
        # precedes §1. It is still part of the document, so it is still
        # reported — just named as what it is.
        name = self.section or "The opening section"
        return {
            "added": f"{name} is new in this version.",
            "removed": f"{name} is no longer in the document.",
            "rewritten": f"{name} has been substantially rewritten.",
            "reworded": f"{name} has been edited.",
            "unchanged": f"{name} is unchanged.",
        }[self.change]


@dataclass
class VersionDiff:
    """The difference between two versions, as a person would describe it."""

    previous_file_id: uuid.UUID
    current_file_id: uuid.UUID
    previous_label: str | None = None
    current_label: str | None = None
    changes: list[SectionChange] = field(default_factory=list)

    @property
    def added(self) -> int:
        return sum(1 for change in self.changes if change.change == "added")

    @property
    def removed(self) -> int:
        return sum(1 for change in self.changes if change.change == "removed")

    @property
    def modified(self) -> int:
        return sum(1 for change in self.changes if change.change in ("rewritten", "reworded"))

    @property
    def unchanged(self) -> int:
        return sum(1 for change in self.changes if change.change == "unchanged")

    @property
    def headline(self) -> str:
        """One sentence, so the reader knows whether to look further."""
        parts = []
        if self.modified:
            parts.append(f"{self.modified} section{'' if self.modified == 1 else 's'} changed")
        if self.added:
            parts.append(f"{self.added} added")
        if self.removed:
            parts.append(f"{self.removed} removed")
        if not parts:
            return "The text of this document did not change between these versions."
        return f"{', '.join(parts)}."


def _normalize(text: str) -> str:
    """Whitespace is formatting, not meaning."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def split_sections(text: str) -> dict[str | None, str]:
    """The document as its own headings divide it.

    Keyed by heading, so two versions line up on what the sections *are*
    rather than on where they happen to fall — inserting §8 must not
    report every following section as changed.
    """
    sections: dict[str | None, list[str]] = {}
    order: list[str | None] = []
    current: str | None = None
    for line in (text or "").splitlines():
        heading = heading_of(line)
        if heading:
            current = heading
            if current not in sections:
                sections[current] = []
                order.append(current)
            # The heading names the section; it is not part of its body,
            # so renaming "7. Monitoring" to "7. Monitoring and review"
            # reads as a new section rather than as a reworded one.
            continue
        if current not in sections:
            sections[current] = []
            order.append(current)
        sections[current].append(line)

    return {
        key: _normalize("\n".join(body))
        for key in order
        for body in [sections[key]]
        if _normalize("\n".join(body))
    }


def diff_text(previous: str, current: str) -> list[SectionChange]:
    """Compare two documents section by section.

    Sections present in both are compared on their words; the rest are
    reported as added or removed. Order is the current document's, with
    removals appended — a reader is looking at what the document says
    now, and what is missing from it.
    """
    before = split_sections(previous)
    after = split_sections(current)

    changes: list[SectionChange] = []
    for section, text in after.items():
        old = before.get(section)
        if old is None:
            if len(text) < MIN_SECTION_CHARS:
                continue
            changes.append(
                SectionChange(change="added", section=section, current_text=text)
            )
            continue

        similarity = difflib.SequenceMatcher(None, old, text).ratio()
        if old == text:
            change = "unchanged"
        elif similarity < REWRITTEN_BELOW:
            change = "rewritten"
        else:
            change = "reworded"
        changes.append(
            SectionChange(
                change=change,
                section=section,
                previous_text=old,
                current_text=text,
                similarity=similarity,
            )
        )

    for section, text in before.items():
        if section not in after and len(text) >= MIN_SECTION_CHARS:
            changes.append(
                SectionChange(change="removed", section=section, previous_text=text)
            )

    return changes


async def _text_of(
    db: AsyncSession, *, organization_id: uuid.UUID, file_record: File
) -> str:
    """A version's text, reassembled from the chunks that were indexed.

    Read from the index rather than from storage: it is what the Copilot
    quoted and what the citations point into, so a diff built from it
    describes the same document the rest of the product is talking about.
    """
    rows = (
        await db.execute(
            select(DocumentChunk.content)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.organization_id == organization_id,
                Document.file_id == file_record.id,
            )
            .order_by(DocumentChunk.chunk_index.asc())
        )
    ).scalars().all()
    return "\n".join(rows)


async def compare_versions(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    previous: File,
    current: File,
) -> VersionDiff:
    """Describe the difference between two versions of one document."""
    before = await _text_of(db, organization_id=organization_id, file_record=previous)
    after = await _text_of(db, organization_id=organization_id, file_record=current)

    return VersionDiff(
        previous_file_id=previous.id,
        current_file_id=current.id,
        previous_label=previous.version_label,
        current_label=current.version_label,
        changes=diff_text(before, after),
    )


__all__ = [
    "MIN_SECTION_CHARS",
    "REWRITTEN_BELOW",
    "SectionChange",
    "VersionDiff",
    "compare_versions",
    "diff_text",
    "split_sections",
]
