"""Privacy facts read out of a document, and the passage each came from.

The privacy module could draft a processing activity from a registered
AI system, and could not read a word of the documents the organization
had uploaded. So a privacy policy or a processing description could be
analysed, mapped to nine controls and indexed for the Copilot, while
Privacy → Processing activities still said "Review suggestions (0)".
Evidence mapping and the RoPA are different pipelines, and only one of
them was connected to documents.

This is the connection. It reads the extracted text the Copilot already
has — the same `DocumentChunk` rows, no re-parsing, no second upload —
and pulls out the fields a processing activity is made of.

**Every fact carries the passage it came from.** Extraction that cannot
show its source is indistinguishable from invention, and a RoPA entry a
reviewer cannot check against the document is not worth having. The
quote is verified against the text before the fact is offered, the same
discipline `evidence_ai` uses for control mappings.

**Nothing legal is extracted.** A document saying "we rely on legitimate
interests" is the organization's own claim about a judgement, not the
judgement; the lawful basis, the Article 9 condition and the transfer
mechanism all come back needing confirmation however plainly the
document states them. What is extracted is the shape of the processing:
what it is for, whose data, which categories, which systems and
processors, where it goes, how long it is kept.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import File
from app.knowledge.models import Document, DocumentChunk

# Documents worth reading for privacy facts. A contract or an invoice is
# analysed for evidence too, and mining it for a processing activity
# produces noise a reviewer has to clear.
#
# Matched as words within the label rather than by equality, because the
# classifier writes for a person: it produces "Privacy / GDPR", not
# "privacy". Testing `label in DOMAINS` silently excluded every real
# privacy document in the library.
PRIVACY_DOMAINS = frozenset({"privacy", "gdpr", "data protection", "dpia", "ropa"})


def is_privacy_domain(label: str | None) -> bool:
    """Whether a classifier's domain label names privacy."""
    text = (label or "").lower()
    return any(domain in text for domain in PRIVACY_DOMAINS)

# How a labelled field is written in the documents people actually
# produce: "Purpose:", "Purpose —", "Purpose -". The value runs to the
# end of the line.
_LABEL = r"^[ \t\-\*•]*{label}[ \t]*[:–—-][ \t]*(?P<value>.+)$"

# The fields a processing activity is made of, and the labels each is
# written under. Order within a tuple is preference order.
_FIELDS: dict[str, tuple[str, ...]] = {
    "name": ("processing activity", "activity name", "activity"),
    "purpose": (
        "business purpose",
        "primary purpose",
        "purpose of processing",
        "processing purpose",
        "purpose",
    ),
    "data_subjects": ("data subjects", "categories of data subjects"),
    "data_categories": (
        "categories of personal data",
        "personal data categories",
        "data categories",
        "personal data",
    ),
    "ai_system": ("ai system", "ai systems"),
    "vendor": (
        "third-party processor",
        "third party processor",
        "vendor/processor",
        "sub-processor",
        "subprocessor",
        "processor",
        "vendor",
        "vendors",
        "processors",
    ),
    "destination": (
        "primary processing location",
        "processing location",
        "storage location",
        "destination",
        "country",
    ),
    "systems": ("primary systems", "systems", "systems involved"),
    "retention": ("retention period", "retention"),
    "owner": ("processing owner", "responsible team", "owner"),
    "special_category": ("special category data", "special-category data"),
}

# Sub-labels that describe a category of personal data inside a
# "Personal data processed" section. A document that lists its data this
# way — "Identity and contact data: name, business email…" — is naming
# the categories in its headings, not in a single labelled field.
_CATEGORY_SECTION = re.compile(
    r"^\s*\d+[.)]?\s*(personal data(?: processed)?|categories of personal data|"
    r"data (?:categories|processed))\s*$",
    re.IGNORECASE,
)
# The next numbered heading ends the section.
_HEADING = re.compile(r"^\s*\d+[.)]\s+\S")

# Wording that indicates a DPIA screening is worth running. Reported as
# an indicator with its passage, never as a conclusion — whether a DPIA
# is required is a decision, and this only says the question is live.
_DPIA_INDICATORS: tuple[tuple[str, str], ...] = (
    (r"\bautomated decision", "Automated decision-making"),
    (r"\bprofiling\b", "Profiling"),
    (r"\bsystematic (monitoring|analysis|observation)", "Systematic monitoring or analysis"),
    (r"\blarge[- ]scale\b", "Large-scale processing"),
    (r"\bspecial[- ]categor", "Special-category data"),
    (r"\b(biometric|health data|genetic)\b", "Special-category data"),
    (r"\b(children|minors|vulnerable)\b", "Vulnerable data subjects"),
    (r"\b(machine learning|artificial intelligence|llm|large language model)",
     "Innovative technology"),
    (r"\bcombin(e|ing|ation) (of )?(datasets|data sets|data sources)",
     "Combining datasets"),
)

# Country wording → ISO 3166-1 alpha-2, for the destinations that
# actually turn up in processing descriptions. Deliberately small: a
# country this does not know is reported as text for a person to read,
# not guessed at.
_COUNTRIES: tuple[tuple[str, str], ...] = (
    (r"\bunited states\b|\bu\.?s\.?a?\b", "US"),
    (r"\bunited kingdom\b|\bu\.?k\.?\b", "GB"),
    (r"\bireland\b", "IE"),
    (r"\bgermany\b", "DE"),
    (r"\bfrance\b", "FR"),
    (r"\bnetherlands\b", "NL"),
    (r"\bindia\b", "IN"),
    (r"\bcanada\b", "CA"),
    (r"\baustralia\b", "AU"),
    (r"\bsingapore\b", "SG"),
    (r"\bjapan\b", "JP"),
    (r"\bbrazil\b", "BR"),
)


@dataclass
class ExtractedFact:
    """One field, its value, and the line it was read from."""

    field: str
    value: str
    # The passage, verbatim, so a reviewer checks rather than trusts.
    quote: str
    # label — read from an explicit "Purpose: …" field
    # keyword — inferred from wording in the prose
    basis: str = "label"


@dataclass
class DocumentPrivacyFacts:
    """What one document says about one processing activity."""

    file_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    facts: dict[str, ExtractedFact] = field(default_factory=dict)
    data_categories: list[str] = field(default_factory=list)
    dpia_indicators: list[ExtractedFact] = field(default_factory=list)
    destination_country: str | None = None

    @property
    def usable(self) -> bool:
        """Whether this is enough to propose an activity at all.

        A name or a purpose, plus something about whose data it is. Less
        than that is a document mentioning privacy, not a description of
        processing, and proposing from it fills the queue with things
        nobody can act on.
        """
        has_subject = "name" in self.facts or "purpose" in self.facts
        has_scope = "data_subjects" in self.facts or bool(self.data_categories)
        return has_subject and has_scope


def _split_values(value: str) -> list[str]:
    """A labelled list, as written: commas, semicolons, or "and"."""
    parts = re.split(r"\s*[;,]\s*|\s+and\s+", value)
    seen: list[str] = []
    for part in parts:
        cleaned = part.strip().strip(".").strip()
        if cleaned and cleaned.lower() not in {p.lower() for p in seen}:
            seen.append(cleaned)
    return seen


def _find_label(text: str, labels: tuple[str, ...]) -> tuple[str, str] | None:
    """The first labelled field matching any of these labels."""
    for label in labels:
        pattern = _LABEL.format(label=re.escape(label))
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group("value").strip().strip(".").strip()
            if value:
                return value, match.group(0).strip()
    return None


def _categories_from_section(
    text: str, found: "DocumentPrivacyFacts"
) -> list[str]:
    """Categories named as sub-labels under a "Personal data" heading.

    A document that writes "Identity and contact data: name, business
    email address…" is naming the category in the label and giving
    examples after it. The label is the category; taking the whole line
    would put a sentence where a category belongs.
    """
    lines = text.splitlines()
    inside = False
    categories: list[str] = []
    for line in lines:
        if _CATEGORY_SECTION.match(line):
            inside = True
            continue
        if inside and _HEADING.match(line):
            break
        if not inside:
            continue
        # "Identity and contact data: name, business email address…"
        match = re.match(r"^\s*([A-Z][^:]{2,60}?)\s*:\s+\S", line)
        if match:
            label = match.group(1).strip()
            if label and label not in categories:
                categories.append(label)
                found.facts.setdefault(
                    f"category:{label}",
                    ExtractedFact(
                        field="data_category",
                        value=label,
                        quote=line.strip(),
                        basis="section",
                    ),
                )
    return categories


def country_from(text: str) -> str | None:
    for pattern, code in _COUNTRIES:
        if re.search(pattern, text, re.IGNORECASE):
            return code
    return None


def extract(text: str, *, file_id: uuid.UUID, document_id: uuid.UUID, title: str) -> DocumentPrivacyFacts:
    """Read the privacy facts a document states about its processing."""
    found = DocumentPrivacyFacts(
        file_id=file_id, document_id=document_id, document_title=title
    )

    for field_name, labels in _FIELDS.items():
        hit = _find_label(text, labels)
        if hit is None:
            continue
        value, quote = hit
        found.facts[field_name] = ExtractedFact(
            field=field_name, value=value, quote=quote
        )

    if "data_categories" in found.facts:
        found.data_categories = _split_values(found.facts["data_categories"].value)
    else:
        found.data_categories = _categories_from_section(text, found)

    # The destination as a country code, from the labelled field if there
    # is one and from the prose otherwise.
    destination_text = (
        found.facts["destination"].value if "destination" in found.facts else text
    )
    found.destination_country = country_from(destination_text)

    # Indicators, each with the sentence it was read from. Reported so a
    # person can decide whether a screening is worth running — never as
    # a conclusion that one is required.
    seen: set[str] = set()

    # A document that names an AI system evidences innovative technology
    # through that field, which has a real quote behind it — rather than
    # through a two-letter keyword that matches any heading.
    if "ai_system" in found.facts:
        seen.add("Innovative technology")
        found.dpia_indicators.append(
            ExtractedFact(
                field="dpia_indicator",
                value="Innovative technology",
                quote=found.facts["ai_system"].quote,
                basis="label",
            )
        )

    for pattern, label in _DPIA_INDICATORS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is None or label in seen:
            continue
        seen.add(label)
        start = max(0, text.rfind("\n", 0, match.start()) + 1)
        end = text.find("\n", match.end())
        line = text[start : end if end != -1 else len(text)].strip()
        found.dpia_indicators.append(
            ExtractedFact(
                field="dpia_indicator",
                value=label,
                quote=line[:400],
                basis="keyword",
            )
        )

    return found


def quote_is_present(quote: str, text: str) -> bool:
    """Whether a quoted passage really occurs in the document.

    The same containment check on normalized text that `evidence_ai`
    uses. A fact whose quote cannot be found is not offered — which
    turns "the extraction might be making it up" from a worry into
    something measured.
    """
    squash = lambda value: " ".join(value.split()).lower()  # noqa: E731
    return squash(quote) in squash(text)


async def document_text(
    db: AsyncSession, *, document_id: uuid.UUID
) -> str:
    """The document's extracted text, from the chunks already stored.

    Deliberately reuses what the Copilot ingest produced rather than
    re-reading the file: the text is already parsed, already scoped to
    the organization, and re-parsing would be a second answer to a
    question that already has one.
    """
    rows = (
        await db.execute(
            select(DocumentChunk.content)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
    ).all()
    return "\n".join(row[0] for row in rows)


async def privacy_documents(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[tuple[File, Document]]:
    """Analysed documents worth reading for privacy facts.

    Restricted to the privacy domains and to documents that finished
    processing — a half-ingested file has partial text, and facts read
    out of half a document are worse than none.
    """
    rows = (
        await db.execute(
            select(File, Document)
            .join(Document, Document.file_id == File.id)
            .where(
                File.organization_id == organization_id,
                File.processing_status == "ready",
                # A report Veyntra wrote is not a source of facts about
                # the organization; see app.compliance.artifacts.
                File.artifact_type == "source",
                Document.status == "ready",
            )
        )
    ).all()
    return [
        (file_record, document)
        for file_record, document in rows
        if is_privacy_domain(file_record.document_domain)
    ]


async def facts_from_documents(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[DocumentPrivacyFacts]:
    """Every privacy document's facts, verified against its own text."""
    results: list[DocumentPrivacyFacts] = []
    for file_record, document in await privacy_documents(
        db, organization_id=organization_id
    ):
        text = await document_text(db, document_id=document.id)
        if not text.strip():
            continue
        found = extract(
            text,
            file_id=file_record.id,
            document_id=document.id,
            title=document.title or file_record.original_filename,
        )
        # Anything whose quote cannot be found in the source is dropped
        # rather than shown.
        found.facts = {
            name: fact
            for name, fact in found.facts.items()
            if quote_is_present(fact.quote, text)
        }
        found.dpia_indicators = [
            fact
            for fact in found.dpia_indicators
            if quote_is_present(fact.quote, text)
        ]
        if found.usable:
            results.append(found)
    return results


__all__ = [
    "PRIVACY_DOMAINS",
    "DocumentPrivacyFacts",
    "ExtractedFact",
    "country_from",
    "document_text",
    "extract",
    "facts_from_documents",
    "privacy_documents",
    "quote_is_present",
]
