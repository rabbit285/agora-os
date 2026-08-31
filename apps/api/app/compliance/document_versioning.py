"""Deciding whether an upload is a new version of something you have.

Nobody should have to name a file `AI_Governance_Policy_v2.docx`. The
product knows what its documents are about, so it can work out that
`Updated AI Policy August.docx` is the next version of the AI Governance
Policy — and, just as importantly, that `Employee_Travel_Policy.docx` is
not.

Three outcomes, and the difference between them matters:

- **Exact duplicate** — the same bytes. Settled by the content hash, not
  by anything here; there is nothing to decide.
- **A new version** — different bytes, confidently the same document.
- **A new document** — everything else.

The middle case is a judgement, so it is made from several independent
signals and reported with the reasons that produced it. A single strong
one is not enough: two policies from the same template share most of
their headings, and two documents by the same author share an owner.
Silently merging unrelated documents destroys evidence lineage in a way
nobody notices until an auditor asks.

**Confidence decides who decides.** High proposes the link and says why.
Medium asks. Low creates a new document and does not mention it. The
product never merges on a guess.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import Policy
from app.core.models import File
from app.knowledge.documents import readable_title

# --- how sure we are --------------------------------------------------

CONFIDENCE_LEVELS = ("high", "medium", "low")

# Scores are the sum of the signals below. The thresholds are set so that
# no single signal can reach `high` on its own — a shared title or a
# shared filename is a coincidence two documents from one template will
# produce all day.
HIGH_CONFIDENCE = 0.70
MEDIUM_CONFIDENCE = 0.40

# What each signal is worth. Content overlap is the heaviest because it
# is the hardest to fake: two documents that share most of their
# distinctive sentences are the same document, whatever they are called.
WEIGHTS = {
    "content": 0.45,
    "title": 0.25,
    "headings": 0.15,
    "policy": 0.15,
    "document_type": 0.10,
    "filename": 0.10,
    "version_metadata": 0.10,
}

# Below this, shared content is unremarkable — boilerplate, headers, the
# organization's name on every page. Calibrated against a real revision
# that rewrites half its sections: that scores around 0.3, and two
# unrelated policies from the same template score under 0.05.
CONTENT_FLOOR = 0.15

# Where the content signal reaches full weight. A revision sharing half
# its distinctive sentences is as much evidence as one sharing all of
# them; past this point the extra overlap says nothing new.
CONTENT_FULL = 0.5


@dataclass
class VersionSignal:
    """One reason to believe, or not believe, this is the same document."""

    name: str
    matched: bool
    weight: float
    detail: str


@dataclass
class VersionCandidate:
    """An existing document this upload might be a new version of."""

    file_id: uuid.UUID
    title: str
    confidence: str
    score: float
    signals: list[VersionSignal] = field(default_factory=list)
    policy_id: uuid.UUID | None = None
    current_version: str | None = None
    detected_version: str | None = None

    @property
    def reasons(self) -> list[str]:
        """Why Veyntra thinks so, in the reader's words."""
        return [signal.detail for signal in self.signals if signal.matched]


# --- reading what a document says about itself ------------------------

_VERSION_PATTERNS = (
    re.compile(r"\bversion\s*[:\-]?\s*(\d+(?:\.\d+)*)\b", re.IGNORECASE),
    re.compile(r"\bv(\d+(?:\.\d+)+)\b", re.IGNORECASE),
    re.compile(r"\brevision\s*[:\-]?\s*(\d+(?:\.\d+)*)\b", re.IGNORECASE),
)

_EFFECTIVE_PATTERNS = (
    re.compile(
        r"\b(?:effective|effective\s+date|in\s+force)\s*[:\-]?\s*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Z][a-z]+\s+\d{4}|[A-Z][a-z]+\s+\d{4}|\d{4}-\d{2}-\d{2})",
        re.IGNORECASE,
    ),
)

# Words that say nothing about which document this is. Stripped before
# comparing titles, so "Updated AI Policy August" and "AI Governance
# Policy" are compared on the words that identify them.
_NOISE_WORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "for",
        "our",
        "draft",
        "final",
        "updated",
        "update",
        "revised",
        "revision",
        "new",
        "latest",
        "current",
        "copy",
        "version",
        "v",
        "policy",
        "document",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)


def detect_version_label(text: str | None) -> str | None:
    """The version the document gives itself, or None.

    Never invented. A document with no version number has no version
    number, and writing "1.0" on it would be putting words in its mouth —
    `app.compliance.policy_governance.detect_version` makes the same
    promise.
    """
    head = (text or "")[:3000]
    for pattern in _VERSION_PATTERNS:
        match = pattern.search(head)
        if match:
            return match.group(1)[:40]
    return None


def detect_effective_date(text: str | None) -> str | None:
    """The date the document says it takes effect, as written."""
    head = (text or "")[:3000]
    for pattern in _EFFECTIVE_PATTERNS:
        match = pattern.search(head)
        if match:
            return match.group(1).strip()[:60]
    return None


def _significant_words(value: str) -> set[str]:
    """The words that identify a document, not the ones that decorate it.

    Two-letter tokens are kept: "AI" is the single most identifying word
    in "AI Governance Policy", and discarding it as short made that
    document look like every other policy in the library.
    """
    words = re.findall(r"[a-z0-9]+", (value or "").lower())
    return {word for word in words if len(word) >= 2 and word not in _NOISE_WORDS}


def title_similarity(left: str, right: str) -> float:
    """How much two names have in common, ignoring the words that decorate
    every document a company owns."""
    a, b = _significant_words(left), _significant_words(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _shingles(text: str, size: int = 5) -> set[str]:
    """Overlapping word runs — long enough that a shared run means shared
    writing rather than shared vocabulary.

    Five words, not eight. A version that rewrites two sections of four
    still shares most of its sentences, but eight-word runs are strict
    enough that a genuine revision scored below an unrelated document's
    boilerplate.
    """
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    if len(words) < size:
        return set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def content_similarity(left: str, right: str) -> float:
    """Jaccard overlap of distinctive word runs.

    Deliberately not an embedding comparison: two documents about the
    same subject are semantically close and are still different
    documents. What identifies a *version* is that most of the actual
    sentences survived the edit.
    """
    a, b = _shingles(left), _shingles(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _headings(text: str) -> set[str]:
    from app.knowledge.headings import heading_of

    found = set()
    for line in (text or "").splitlines():
        label = heading_of(line)
        if label:
            found.add(" ".join(label.lower().split()))
    return found


def heading_similarity(left: str, right: str) -> float:
    a, b = _headings(left), _headings(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _grade(score: float) -> str:
    if score >= HIGH_CONFIDENCE:
        return "high"
    if score >= MEDIUM_CONFIDENCE:
        return "medium"
    return "low"


def score_candidate(
    *,
    uploaded_title: str,
    uploaded_filename: str,
    uploaded_text: str,
    uploaded_type: str | None,
    existing_title: str,
    existing_filename: str,
    existing_text: str,
    existing_type: str | None,
    shares_policy: bool = False,
    uploaded_version: str | None = None,
    existing_version: str | None = None,
) -> tuple[float, list[VersionSignal]]:
    """Weigh every signal, and say what each one concluded.

    Pure, so the rules can be read and tested without a database or an
    upload behind them.
    """
    signals: list[VersionSignal] = []

    content = content_similarity(uploaded_text, existing_text)
    signals.append(
        VersionSignal(
            "content",
            content >= CONTENT_FLOOR,
            WEIGHTS["content"] * min(content / CONTENT_FULL, 1.0)
            if content >= CONTENT_FLOOR
            else 0.0,
            f"{round(content * 100)}% of the wording is shared with the existing document",
        )
    )

    title = title_similarity(uploaded_title, existing_title)
    signals.append(
        VersionSignal(
            "title",
            title >= 0.5,
            WEIGHTS["title"] * title if title >= 0.5 else 0.0,
            f"The document calls itself “{uploaded_title}”, close to “{existing_title}”",
        )
    )

    headings = heading_similarity(uploaded_text, existing_text)
    signals.append(
        VersionSignal(
            "headings",
            headings >= 0.4,
            WEIGHTS["headings"] * headings if headings >= 0.4 else 0.0,
            f"{round(headings * 100)}% of the section headings match",
        )
    )

    signals.append(
        VersionSignal(
            "policy",
            shares_policy,
            WEIGHTS["policy"] if shares_policy else 0.0,
            "Both are governed by the same policy record",
        )
    )

    same_type = bool(
        uploaded_type and existing_type and uploaded_type.strip().lower() == existing_type.strip().lower()
    )
    signals.append(
        VersionSignal(
            "document_type",
            same_type,
            WEIGHTS["document_type"] if same_type else 0.0,
            f"Both are classified as {existing_type}",
        )
    )

    filename = title_similarity(uploaded_filename, existing_filename)
    signals.append(
        VersionSignal(
            "filename",
            filename >= 0.5,
            WEIGHTS["filename"] * filename if filename >= 0.5 else 0.0,
            "The filenames are similar",
        )
    )

    # A document that names a version *later* than the one on file is
    # saying outright what it is.
    newer = bool(
        uploaded_version
        and existing_version
        and _version_tuple(uploaded_version) > _version_tuple(existing_version)
    )
    signals.append(
        VersionSignal(
            "version_metadata",
            newer,
            WEIGHTS["version_metadata"] if newer else 0.0,
            f"The document states version {uploaded_version}, newer than {existing_version}",
        )
    )

    return (sum(signal.weight for signal in signals), signals)


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in re.findall(r"\d+", value))
    except ValueError:  # pragma: no cover
        return ()


async def find_version_candidate(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    file_record: File,
    document_text: str,
    read_text,
    limit: int = 25,
) -> VersionCandidate | None:
    """The document this upload is most likely a newer version of.

    `read_text` is injected rather than imported so this can be tested
    without object storage, and so the caller controls how many documents
    are actually read — comparing against a whole library is a lot of
    parsing for something that is usually a new document.

    Returns None when nothing scores above `low`: the honest answer for
    an unrelated upload, and the one that keeps `Employee_Travel_Policy`
    from being attached to the AI Governance Policy.
    """
    uploaded_title = readable_title(file_record.original_filename)
    uploaded_version = detect_version_label(document_text)

    existing_files = list(
        (
            await db.execute(
                select(File)
                .where(
                    File.organization_id == organization_id,
                    File.id != file_record.id,
                    File.processing_status == "ready",
                    File.superseded_by_id.is_(None),
                    # A version replaces something that came before it.
                    # For a live upload this is every other document, so
                    # it costs nothing; for the backfill, which walks a
                    # library oldest-first, it is what stops the pass
                    # proposing that the original is a new version of its
                    # own revision.
                    File.created_at < file_record.created_at,
                )
                .order_by(File.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not existing_files:
        return None

    policies = {
        row.file_id: row
        for row in (
            await db.execute(
                select(Policy).where(
                    Policy.organization_id == organization_id, Policy.file_id.is_not(None)
                )
            )
        )
        .scalars()
        .all()
    }

    best: VersionCandidate | None = None
    for existing in existing_files:
        existing_text = read_text(existing)
        if not existing_text:
            continue

        policy = policies.get(existing.id)
        score, signals = score_candidate(
            uploaded_title=uploaded_title,
            uploaded_filename=file_record.original_filename,
            uploaded_text=document_text,
            uploaded_type=file_record.document_type,
            existing_title=readable_title(existing.original_filename),
            existing_filename=existing.original_filename,
            existing_text=existing_text,
            existing_type=existing.document_type,
            shares_policy=False,
            uploaded_version=uploaded_version,
            existing_version=policy.version if policy else None,
        )
        if best is None or score > best.score:
            best = VersionCandidate(
                file_id=existing.id,
                title=readable_title(existing.original_filename),
                confidence=_grade(score),
                score=round(score, 3),
                signals=signals,
                policy_id=policy.id if policy else None,
                current_version=policy.version if policy else None,
                detected_version=uploaded_version,
            )

    if best is None or best.confidence == "low":
        # Nothing convincing. A new document, and no question asked —
        # prompting on every upload teaches people to dismiss the prompt.
        return None
    return best


__all__ = [
    "CONFIDENCE_LEVELS",
    "CONTENT_FLOOR",
    "CONTENT_FULL",
    "HIGH_CONFIDENCE",
    "MEDIUM_CONFIDENCE",
    "WEIGHTS",
    "VersionCandidate",
    "VersionSignal",
    "content_similarity",
    "detect_effective_date",
    "detect_version_label",
    "find_version_candidate",
    "heading_similarity",
    "score_candidate",
    "title_similarity",
]
