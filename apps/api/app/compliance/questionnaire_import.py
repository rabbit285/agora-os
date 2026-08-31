"""Getting the customer's questions out of the customer's file.

A security questionnaire arrives as a spreadsheet, a Word document, a PDF
or an email someone pasted. Requiring a person to retype a hundred
questions into a form is the reason this screen felt like a form builder:
the work the product should be doing was being done by hand before the
product was involved at all.

Extraction is deliberately conservative. A line that is not a question is
better left out than imported as one — a questionnaire padded with
section headings and instructions makes the reviewer's job worse, and
they cannot tell which rows Veyntra invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.knowledge.parsing import UnsupportedFormatError, extract_text

# The formats a questionnaire actually arrives in, limited to the ones
# this product can already read. Anything else is refused by name rather
# than parsed into nonsense.
SUPPORTED_CONTENT_TYPES = {
    "text/csv": "CSV",
    "text/plain": "Text",
    "text/markdown": "Markdown",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
    "application/pdf": "PDF",
}

# A question is short enough to be one and long enough to mean something.
MIN_QUESTION_CHARS = 12
MAX_QUESTION_CHARS = 600
MAX_QUESTIONS = 500

# Numbering the customer's own document uses, stripped so the question
# reads as a question rather than as row 4.7 of somebody's spreadsheet.
_LEADING_NUMBER = re.compile(r"^\s*(?:[A-Z]{1,3}[-.]?)?\d+(?:[.)]\d+)*[.)]?\s+")
_LEADING_BULLET = re.compile(r"^\s*[-*•‣◦]\s+")

# Lines that are structure, not content.
_HEADING_WORDS = (
    "section",
    "part ",
    "appendix",
    "annex",
    "instructions",
    "please complete",
    "vendor response",
    "response",
    "answer",
    "comments",
    "n/a",
)

# What the question is about, from its own words. Used only to group the
# review queue — never to decide an answer.
_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "privacy",
        ("gdpr", "personal data", "data subject", "dpia", "privacy", "dpo", "retention"),
    ),
    (
        "ai_governance",
        ("ai ", "artificial intelligence", "model", "machine learning", "llm"),
    ),
    (
        "security",
        (
            "encrypt",
            "access control",
            "incident",
            "vulnerability",
            "penetration",
            "mfa",
            "password",
            "backup",
            "firewall",
            "logging",
            "malware",
        ),
    ),
)


@dataclass(frozen=True)
class ExtractedQuestion:
    text: str
    category: str
    order_index: int


def categorize(text: str) -> str:
    lowered = text.lower()
    for category, words in _CATEGORIES:
        if any(word in lowered for word in words):
            return category
    return "compliance"


def clean_line(line: str) -> str:
    """Strip the customer's own formatting off a line.

    Public because the analysis step has to clean a line exactly the way
    extraction does. Two copies of this logic would mean the preview
    describing something other than what gets created.
    """
    stripped = _LEADING_BULLET.sub("", _LEADING_NUMBER.sub("", line.strip()))
    # A spreadsheet row arrives as "question, answer, comments" — the
    # question is the first cell, and the rest is the form we are filling
    # in rather than part of what was asked.
    if "," in stripped and stripped.count(",") >= 1 and stripped.endswith(","):
        stripped = stripped.rstrip(", ")
    return " ".join(stripped.split())


def looks_like_a_question(text: str) -> bool:
    """Whether this line is something a customer is asking.

    A question mark is the strongest signal and not the only one:
    questionnaires are full of imperatives — "Describe your incident
    response process" — which are questions in every sense that matters.
    """
    if not (MIN_QUESTION_CHARS <= len(text) <= MAX_QUESTION_CHARS):
        return False

    lowered = text.lower()
    if any(lowered.startswith(word) for word in _HEADING_WORDS):
        return False
    # A line with no lowercase at all is a heading shouting at us.
    if text.isupper():
        return False

    if text.endswith("?"):
        return True

    openers = (
        "do you",
        "does your",
        "are you",
        "is your",
        "have you",
        "has your",
        "can you",
        "will you",
        "describe",
        "explain",
        "provide",
        "list ",
        "how do",
        "how does",
        "what ",
        "which ",
        "who ",
        "where ",
        "when ",
        "confirm",
        "specify",
        "detail ",
        "outline",
    )
    return lowered.startswith(openers)


def extract_questions(text: str) -> list[ExtractedQuestion]:
    """Every question in this document, in the order it was asked.

    Duplicates collapse: a spreadsheet that repeats a question across
    tabs is asking it once.
    """
    seen: set[str] = set()
    questions: list[ExtractedQuestion] = []

    for raw_line in (text or "").splitlines():
        cleaned = clean_line(raw_line)
        if not looks_like_a_question(cleaned):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        questions.append(
            ExtractedQuestion(
                text=cleaned,
                category=categorize(cleaned),
                order_index=len(questions),
            )
        )
        if len(questions) >= MAX_QUESTIONS:
            break

    return questions


def extract_questions_from_file(content_type: str, data: bytes) -> list[ExtractedQuestion]:
    """Read a questionnaire file and pull the questions out of it.

    Raises `UnsupportedFormatError` for a format this product cannot read,
    so the caller can name the formats it can — which is more use than an
    empty question list that looks like a document with no questions in
    it.
    """
    if content_type not in SUPPORTED_CONTENT_TYPES:
        raise UnsupportedFormatError(content_type)
    return extract_questions(extract_text(content_type, data))


__all__ = [
    "clean_line",
    "MAX_QUESTIONS",
    "SUPPORTED_CONTENT_TYPES",
    "ExtractedQuestion",
    "categorize",
    "extract_questions",
    "extract_questions_from_file",
    "looks_like_a_question",
]
