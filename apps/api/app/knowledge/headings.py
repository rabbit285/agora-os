"""Where in a document a piece of text came from.

A citation is only useful if the person reading it can find the passage
in their own copy. "chunk 5" is not something anyone can look up — it is
an artefact of how we happened to slice the file. A heading the document
gives itself ("7. Monitoring", "Article 12", "## Access review") is, and
so is a page number.

So chunking records the heading in force where each chunk starts, and
the page it fell on. Both are resolved here, from the document's own
text, before anything is embedded.
"""

from __future__ import annotations

import bisect
import re

# Numbered or keyword headings — "Section 4.2", "Article 12", "7.1 Access
# control", "3." — the forms policies and regulations actually use.
NUMBERED_HEADING = re.compile(
    r"^\s*((?:section|clause|article|part|appendix|annex)\s+[\w.]+|\d+(?:\.\d+)*\.?)\s*[-–—:.]?\s*(.*)$",
    re.IGNORECASE,
)

# Markdown, which is what an exported policy or a README arrives as.
MARKDOWN_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")

# A heading is short. A paragraph that happens to open with a number is
# not, and treating one as a heading fragments the body into nonsense.
MAX_HEADING_LENGTH = 90


def heading_of(line: str) -> str | None:
    """The heading this line declares, or None if it is body text."""
    stripped = line.strip()
    if not stripped or len(stripped) > MAX_HEADING_LENGTH:
        return None

    markdown = MARKDOWN_HEADING.match(line)
    if markdown:
        return markdown.group(2).strip() or None

    numbered = NUMBERED_HEADING.match(line)
    if numbered:
        number = numbered.group(1).strip()
        title = numbered.group(2).strip()
        return f"{number} {title}".strip() if title else number

    return None


def heading_index(text: str) -> list[tuple[int, str]]:
    """Every heading in the document, as (character offset, label).

    Sorted by offset so a chunk's heading is a binary search rather than a
    rescan of the document per chunk.
    """
    index: list[tuple[int, str]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        label = heading_of(line)
        if label:
            index.append((offset, label))
        offset += len(line)
    return index


def heading_at(index: list[tuple[int, str]], offset: int) -> str | None:
    """The heading in force at `offset` — the last one at or before it.

    Text before the first heading has none, and says so rather than being
    attributed to a section it does not belong to.
    """
    if not index:
        return None
    position = bisect.bisect_right([entry[0] for entry in index], offset)
    if position == 0:
        return None
    return index[position - 1][1]


def page_at(page_starts: object, offset: int) -> int | None:
    """The 1-based page `offset` falls on, or None when the format has no
    pages. A .docx or a Markdown file genuinely has no page numbers, and
    inventing one would send the reader to a page that does not exist."""
    starts = list(page_starts or ())
    if not starts:
        return None
    return max(1, bisect.bisect_right(starts, offset))


__all__ = [
    "MARKDOWN_HEADING",
    "MAX_HEADING_LENGTH",
    "NUMBERED_HEADING",
    "heading_at",
    "heading_index",
    "heading_of",
    "page_at",
]
