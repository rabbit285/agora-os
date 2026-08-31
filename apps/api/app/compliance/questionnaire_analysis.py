"""Looking at an import before doing it.

Creating a hundred questions the moment somebody pastes something is
fast and unsafe. They cannot see what was found, what was thrown away,
or what already existed — and by the time they can, it is a hundred rows
they have to unpick by hand.

So the import happens in two halves. This module is the first: read the
input, decide what each line is, and describe the result. It writes
nothing. The caller shows that description to a person, and only what
that person confirms is created.

Three kinds of duplicate, and the difference matters:

- **The same question, written the same way.** Normalized text matches.
  Not created again, not offered as a choice — there is nothing to
  decide.
- **The same question, written differently.** "Do you encrypt customer
  data at rest?" against "Is customer data encrypted while stored?" These
  are flagged and left to the reader. Merging them automatically would
  silently drop a question a customer asked, which is the one thing a
  questionnaire tool must never do.
- **Repeated within the same paste.** A spreadsheet that asks the same
  thing on three tabs is asking once.

Rejected lines are reported rather than dropped. A questionnaire where
eight rows vanished without comment is a questionnaire nobody can trust
they have answered.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import QuestionnaireQuestion
from app.compliance.questionnaire_import import (
    MAX_QUESTION_CHARS,
    MIN_QUESTION_CHARS,
    categorize,
    clean_line,
    looks_like_a_question,
)

# Above this share of shared words, two questions are close enough that a
# person should look. Deliberately not a merge threshold — nothing is
# merged on this number, it only decides what gets pointed at.
#
# Measured, not guessed. Across realistic pairs, the same question with a
# qualifier added scores 0.67-1.00 ("...at rest" against "...at rest
# across all environments"; "a policy" against "a written policy"), while
# genuinely different questions top out at 0.60 ("at rest" against "in
# transit"). The gap between those is where this sits.
#
# What it cannot reach: a paraphrase built from synonyms. "Do you encrypt
# customer data at rest?" against "Is customer data encrypted while
# stored?" shares almost no vocabulary and scores 0.29 — indistinguishable
# from two unrelated questions by any lexical measure. Catching that needs
# an embedding per line, which is a model call per row of a customer's
# spreadsheet; the duplicate is then caught by the person reading the
# preview, which is why there is a preview.
NEAR_DUPLICATE_RATIO = 0.65

# Words that appear in most questionnaire questions and so carry no
# signal about which question this is. Left in, two questions about
# entirely different subjects look 40% alike purely on scaffolding.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "do", "does", "did", "you", "your",
        "we", "our", "have", "has", "any", "all", "and", "or", "of", "to",
        "in", "on", "for", "with", "at", "by", "be", "been", "as", "that",
        "this", "it", "its", "if", "how", "what", "which", "please",
        "provide", "describe", "explain", "confirm", "list", "detail",
        "company", "organization", "organisation",
    }
)

_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """What makes two questions the same question.

    Case, punctuation and spacing are how a question was typed, not what
    it asks. "Do you encrypt customer data at rest?" and "do you encrypt
    customer data at rest" are one question asked twice, and creating
    both is the duplicate bug this normalization exists to prevent.
    """
    lowered = (text or "").strip().lower()
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", lowered)).strip()


def _significant_words(text: str) -> set[str]:
    return {word for word in normalize(text).split() if word not in _STOPWORDS}


def similarity(left: str, right: str) -> float:
    """How alike two questions are, on the words that identify them.

    Jaccard over the words that survive the stopword list. Not a semantic
    model: this decides what to *ask about*, and a number a reader can
    reason about is worth more here than one they cannot.
    """
    a, b = _significant_words(left), _significant_words(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class AnalyzedLine:
    """One line of the input, and what Veyntra made of it."""

    text: str
    # new | duplicate | possible_duplicate | unparsed
    outcome: str
    category: str = "compliance"
    # The question already on the questionnaire this one resembles.
    matches: str | None = None
    similarity: float = 0.0
    # Why a line was not read as a question, in the reader's words.
    reason: str | None = None

    @property
    def importable(self) -> bool:
        """Whether importing this would create something.

        A possible duplicate is importable — it is a question the reader
        may well want, and the whole point of flagging rather than
        merging is that they decide.
        """
        return self.outcome in ("new", "possible_duplicate")


@dataclass
class ImportAnalysis:
    """What an import would do, before it does it."""

    lines: list[AnalyzedLine] = field(default_factory=list)

    @property
    def detected(self) -> int:
        """Lines that read as questions, whatever became of them."""
        return sum(1 for line in self.lines if line.outcome != "unparsed")

    @property
    def new(self) -> int:
        return sum(1 for line in self.lines if line.outcome == "new")

    @property
    def duplicates(self) -> int:
        return sum(1 for line in self.lines if line.outcome == "duplicate")

    @property
    def possible_duplicates(self) -> int:
        return sum(1 for line in self.lines if line.outcome == "possible_duplicate")

    @property
    def unparsed(self) -> int:
        return sum(1 for line in self.lines if line.outcome == "unparsed")

    @property
    def headline(self) -> str:
        """One sentence, so somebody can decide without reading the list."""
        if not self.lines:
            return "Nothing was found to import."
        parts = [f"{self.detected} question{'' if self.detected == 1 else 's'} detected"]
        if self.new:
            parts.append(f"{self.new} new")
        if self.duplicates:
            parts.append(f"{self.duplicates} already here")
        if self.possible_duplicates:
            parts.append(
                f"{self.possible_duplicates} possibly already here"
            )
        if self.unparsed:
            parts.append(
                f"{self.unparsed} line{'' if self.unparsed == 1 else 's'} not recognised"
            )
        return ", ".join(parts) + "."


def _rejection_reason(cleaned: str, raw: str) -> str:
    """Why this line was not read as a question.

    Specific enough to act on. "Could not parse" tells somebody nothing
    about whether they should paste it again, edit it, or ignore it.
    """
    if not cleaned:
        return "This line is empty."
    if len(cleaned) < MIN_QUESTION_CHARS:
        return "Too short to be a question."
    if len(cleaned) > MAX_QUESTION_CHARS:
        return "Too long to be a single question — it may be a paragraph or several rows joined together."
    if cleaned.isupper():
        return "Reads as a section heading rather than a question."
    if raw.count(",") >= 2 or raw.count("\t") >= 1:
        return "Looks like a spreadsheet row with several columns. Veyntra could not tell which cell is the question."
    return "Does not read as a question. Veyntra looks for a question mark, or an opening like \"Do you\" or \"Describe\"."


async def analyse_import(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    questionnaire_id: uuid.UUID,
    raw_lines: list[str],
) -> ImportAnalysis:
    """Decide what each line is, against what the questionnaire already has."""
    existing_rows = list(
        (
            await db.execute(
                select(QuestionnaireQuestion.text).where(
                    QuestionnaireQuestion.organization_id == organization_id,
                    QuestionnaireQuestion.questionnaire_id == questionnaire_id,
                )
            )
        )
        .scalars()
        .all()
    )
    existing_normalized = {normalize(text): text for text in existing_rows}

    analysis = ImportAnalysis()
    # Repeats inside one paste. A spreadsheet asking the same thing on
    # three tabs is asking once, and reporting it three times as "new"
    # would make the preview lie about what is about to be created.
    seen_in_input: set[str] = set()

    for raw in raw_lines:
        if not raw.strip():
            continue
        cleaned = clean_line(raw)

        if not looks_like_a_question(cleaned):
            analysis.lines.append(
                AnalyzedLine(
                    text=cleaned or raw.strip(),
                    outcome="unparsed",
                    reason=_rejection_reason(cleaned, raw),
                )
            )
            continue

        key = normalize(cleaned)
        if key in seen_in_input:
            continue
        seen_in_input.add(key)

        if key in existing_normalized:
            analysis.lines.append(
                AnalyzedLine(
                    text=cleaned,
                    outcome="duplicate",
                    category=categorize(cleaned),
                    matches=existing_normalized[key],
                    similarity=1.0,
                )
            )
            continue

        closest, score = None, 0.0
        for existing_key, original in existing_normalized.items():
            candidate = similarity(existing_key, key)
            if candidate > score:
                closest, score = original, candidate

        if closest is not None and score >= NEAR_DUPLICATE_RATIO:
            analysis.lines.append(
                AnalyzedLine(
                    text=cleaned,
                    outcome="possible_duplicate",
                    category=categorize(cleaned),
                    matches=closest,
                    similarity=round(score, 2),
                )
            )
            continue

        analysis.lines.append(
            AnalyzedLine(text=cleaned, outcome="new", category=categorize(cleaned))
        )

    return analysis


__all__ = [
    "NEAR_DUPLICATE_RATIO",
    "AnalyzedLine",
    "ImportAnalysis",
    "analyse_import",
    "normalize",
    "similarity",
]
