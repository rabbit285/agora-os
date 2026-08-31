"""What a customer would receive, assembled before anything is generated.

The compliance team must always know what they are about to send outside
the organization. That sentence is the whole design: this module builds
the complete contents of a customer-facing package as data, so a person
can read it, remove things from it, and only then ask for a file.

Nothing here writes. Preview is a pure function of the review's current
state, which is what lets it be opened, refreshed and closed without
leaving a record of packages nobody sent. The immutable
`ReviewExport` row is written by the generation step, from a snapshot of
exactly this.

Three rules the rest of the module exists to hold:

- **Approved answers only.** A customer-facing document quotes what
  somebody signed off, never a draft, a rejected suggestion, or an
  approved answer that has been edited since. An answer that moved after
  its approval is reported and blocks the export rather than being
  quietly sent in whichever state it happens to be in.
- **Nothing leaves that nobody cleared.** A document's `disclosure` is
  the gate, and an unclassified document is not a shareable one.
  `restricted` is refused outright — a vulnerability report is not
  something to offer an override for.
- **Qualified answers stay qualified.** "We maintain a procedure;
  however, the most recent tabletop exercise is not evidenced" goes out
  as written. Summarising that into "Yes" is the failure mode that makes
  assurance documents worthless, and it is easy to do by accident.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.customer_review import ReviewProgress, label_for, progress_for
from app.compliance.models import (
    Evidence,
    Policy,
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    ReviewExport,
    SecurityReview,
)
from app.core.models import File

logger = logging.getLogger("agora.compliance.review_export")

# --- disclosure -------------------------------------------------------
#
# internal           — not classified, or classified as ours. The default,
#                      and the reason the default matters: "nobody has
#                      decided" and "nobody has approved this for sharing"
#                      are the same answer to the question export asks.
# customer_shareable — somebody decided this may go to a customer.
# restricted         — somebody decided this must not leave. Not an
#                      override candidate; the point of the state is that
#                      it is not a matter of permission.
DISCLOSURES = ("internal", "customer_shareable", "restricted")

DISCLOSURE_LABELS = {
    "internal": "Internal",
    "customer_shareable": "Customer-shareable",
    "restricted": "Restricted",
}

OUTPUT_TYPES = ("summary", "questionnaire", "evidence_pack")

OUTPUT_LABELS = {
    "summary": "Security Review Summary",
    "questionnaire": "Completed questionnaire",
    "evidence_pack": "Evidence / Assurance Pack",
}

OUTPUT_FORMATS = {
    "summary": "pdf",
    "questionnaire": "xlsx",
    "evidence_pack": "zip",
}

# The sections of the summary a person can turn off. Facts, not opinions:
# turning one off removes it from the document, and none of them can be
# edited into saying something the record does not.
SUMMARY_SECTIONS = (
    "executive_summary",
    "completion",
    "responses",
    "evidence",
    "disclosures",
    "reviewer",
)

SECTION_LABELS = {
    "executive_summary": "Executive summary",
    "completion": "Completion summary",
    "responses": "Approved responses",
    "evidence": "Supporting evidence",
    "disclosures": "Known disclosures and limitations",
    "reviewer": "Reviewer information",
}

DISCLAIMER = (
    "This report summarizes the security review and supporting information "
    "recorded in Veyntra. It is not an independent certification, legal "
    "opinion, or audit attestation."
)

# Words that mark an answer as qualified. An answer containing one is
# surfaced as a disclosure so the limitation travels with the document
# instead of being lost in a summary that reads "fully implemented".
_QUALIFIERS = re.compile(
    r"\b(however|although|except|excluding|but not|not yet|"
    r"in progress|planned|partial(?:ly)?|does not|is not|no evidence|"
    r"pending|limitation|caveat|with the exception)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExportBlocker:
    """One reason a customer-facing package should not be generated."""

    code: str
    message: str


@dataclass
class AnswerLine:
    """One question and the answer that was approved for it."""

    question_id: uuid.UUID
    question: str
    category: str | None
    answer: str
    approved_at: datetime | None
    # Documents cited in support. Titles only — the customer gets the
    # name of a policy, not a chunk identifier.
    sources: list[str] = field(default_factory=list)
    # The answer carries a limitation, and the limitation goes out with
    # it. See `_QUALIFIERS`.
    qualified: bool = False


@dataclass
class DocumentLine:
    """One document that could go in the package, and whether it may.

    `eligible` is the product's answer; `included` is the person's. They
    are separate so the preview can show a document, say why it is not
    proposed, and let somebody with the standing to do so include it
    anyway — without an ineligible document ever being on by default.
    """

    file_id: uuid.UUID
    title: str
    kind: str
    disclosure: str
    eligible: bool
    reason: str | None = None
    version: str | None = None
    status: str | None = None
    superseded: bool = False
    supports: list[str] = field(default_factory=list)
    included: bool = False


@dataclass
class ExportPreview:
    """Everything the customer would receive, before any file exists."""

    output_type: str
    output_label: str
    file_format: str
    title: str
    customer_name: str | None
    review_title: str
    review_status: str
    review_status_label: str
    review_archived: bool
    review_date: datetime
    progress: ReviewProgress
    answers: list[AnswerLine] = field(default_factory=list)
    documents: list[DocumentLine] = field(default_factory=list)
    disclosures: list[str] = field(default_factory=list)
    blockers: list[ExportBlocker] = field(default_factory=list)
    # The whole document unless somebody turns a section off. Defaulting
    # this to empty renders a cover page and a disclaimer and nothing
    # else — which still looks like a report, which is the dangerous
    # part. A missing section should be a decision, never an oversight.
    sections: list[str] = field(default_factory=lambda: list(SUMMARY_SECTIONS))
    introduction: str | None = None
    disclaimer: str = DISCLAIMER
    # A fingerprint of the review state behind this. Stored on the
    # generated export so a later page load can say "the review has
    # changed since this was generated" without diffing two snapshots.
    digest: str = ""
    # Only meaningful for the questionnaire output: what the customer's
    # own spreadsheet called its columns, and what we put where.
    column_mapping: dict[str, str] = field(default_factory=dict)
    source_filename: str | None = None

    @property
    def ready(self) -> bool:
        return not self.blockers

    @property
    def included_documents(self) -> list[DocumentLine]:
        return [document for document in self.documents if document.included]


def _now() -> datetime:
    return datetime.now(UTC)


def is_qualified(text: str | None) -> bool:
    """Does this answer carry a limitation the customer must see?"""
    return bool(text and _QUALIFIERS.search(text))


async def _answers_for(
    db: AsyncSession, *, review_id: uuid.UUID
) -> tuple[list[AnswerLine], list[ExportBlocker], list[Questionnaire]]:
    """The approved answers, and everything wrong with sending them.

    An answer is quoted only when a person approved it. Anything else —
    a draft, an unanswered question, an approval that has been edited
    since — is reported rather than silently included or silently
    dropped. Both of those are ways of sending a customer a document
    that does not say what the organization decided it says.
    """
    questionnaires = list(
        (
            await db.execute(
                select(Questionnaire)
                .where(Questionnaire.security_review_id == review_id)
                .order_by(Questionnaire.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    if not questionnaires:
        return [], [ExportBlocker("no_questionnaires", "This review has no questionnaires in it.")], []

    rows = (
        await db.execute(
            select(QuestionnaireQuestion, QuestionnaireAnswer)
            .outerjoin(
                QuestionnaireAnswer,
                QuestionnaireAnswer.question_id == QuestionnaireQuestion.id,
            )
            .where(
                QuestionnaireQuestion.questionnaire_id.in_(
                    [questionnaire.id for questionnaire in questionnaires]
                )
            )
            .order_by(QuestionnaireQuestion.order_index.asc())
        )
    ).all()

    answers: list[AnswerLine] = []
    unanswered = 0
    needs_review = 0
    changed = 0

    for question, answer in rows:
        if answer is None or answer.status != "approved":
            if answer is not None and answer.status == "needs_review":
                needs_review += 1
            else:
                unanswered += 1
            continue

        # An approved answer that moved afterwards is neither the old one
        # nor a new approval. Sending either state would be asserting
        # something nobody signed.
        #
        # Compared against the text that was approved, not against
        # timestamps: `updated_at` moves on the same flush that records
        # the approval, so a clock comparison flags every freshly
        # approved answer as changed. Null `approved_text` means the row
        # predates the column and we cannot tell — treated as unchanged
        # rather than as a discrepancy nobody can act on.
        if (
            answer.approved_text is not None
            and (answer.answer_text or "") != answer.approved_text
        ):
            changed += 1

        answers.append(
            AnswerLine(
                question_id=question.id,
                question=question.text,
                category=question.category,
                answer=answer.answer_text or "",
                approved_at=answer.approved_at,
                sources=_citation_titles(answer),
                qualified=is_qualified(answer.answer_text),
            )
        )

    blockers: list[ExportBlocker] = []
    if unanswered:
        blockers.append(
            ExportBlocker(
                "unanswered",
                f"{unanswered} question{'' if unanswered == 1 else 's'} "
                f"{'has' if unanswered == 1 else 'have'} no approved answer.",
            )
        )
    if needs_review:
        blockers.append(
            ExportBlocker(
                "needs_review",
                f"{needs_review} answer{'' if needs_review == 1 else 's'} "
                f"need{'s' if needs_review == 1 else ''} review.",
            )
        )
    if changed:
        blockers.append(
            ExportBlocker(
                "changed_since_approval",
                f"{changed} answer{'' if changed == 1 else 's'} "
                f"{'has' if changed == 1 else 'have'} changed since approval. "
                "Re-approve before sending this to a customer.",
            )
        )

    return answers, blockers, questionnaires


def _citation_titles(answer: QuestionnaireAnswer) -> list[str]:
    """The documents behind an answer, by name.

    Titles only. A customer reading "supported by the Information
    Security Policy" learns something; a chunk id tells them about our
    storage layer, and confidence scores tell them how sure a model was,
    which is an internal number about our process rather than a fact
    about their security.
    """
    titles: list[str] = []
    for citation in answer.citations or []:
        if not isinstance(citation, dict):
            continue
        title = (
            citation.get("document_title")
            or citation.get("title")
            or citation.get("filename")
        )
        if title and title not in titles:
            titles.append(str(title))
    return titles


async def _documents_for(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> list[DocumentLine]:
    """Every document that could be offered, with why it may or may not.

    Policies first — they are what a customer actually asks for — then
    other evidence. Each carries its disclosure state and, where it is
    not eligible, the sentence explaining that.
    """
    lines: list[DocumentLine] = []
    seen: set[uuid.UUID] = set()

    policies = list(
        (
            await db.execute(
                select(Policy, File)
                .join(File, File.id == Policy.file_id)
                .where(
                    Policy.organization_id == organization_id,
                    Policy.file_id.is_not(None),
                )
                .order_by(Policy.title.asc())
            )
        ).all()
    )
    for policy, file_record in policies:
        seen.add(file_record.id)
        lines.append(_document_line(file_record, kind="Policy", policy=policy))

    evidence = list(
        (
            await db.execute(
                select(Evidence, File)
                .join(File, File.id == Evidence.file_id)
                .where(Evidence.organization_id == organization_id)
                .order_by(Evidence.title.asc())
            )
        ).all()
    )
    for item, file_record in evidence:
        if file_record.id in seen:
            continue
        seen.add(file_record.id)
        lines.append(
            _document_line(file_record, kind="Evidence", title=item.title)
        )

    return lines


def _document_line(
    file_record: File,
    *,
    kind: str,
    policy: Policy | None = None,
    title: str | None = None,
) -> DocumentLine:
    disclosure = file_record.disclosure or "internal"
    superseded = file_record.superseded_by_id is not None

    eligible = True
    reason: str | None = None

    if disclosure == "restricted":
        eligible = False
        reason = "Restricted. This document cannot be shared externally."
    elif disclosure != "customer_shareable":
        eligible = False
        reason = "This document is not currently approved for external sharing."
    elif superseded:
        # §12: a superseded version is not the current policy, and
        # sending one as though it were is worse than sending nothing.
        eligible = False
        reason = "Superseded by a newer version. Share the current version instead."
    elif policy is not None and policy.status != "approved":
        eligible = False
        reason = "This policy has not been approved yet."

    return DocumentLine(
        file_id=file_record.id,
        title=(policy.title if policy else title) or file_record.original_filename,
        kind=kind,
        disclosure=disclosure,
        eligible=eligible,
        reason=reason,
        version=policy.version if policy else None,
        status=policy.status if policy else None,
        superseded=superseded,
    )


def _digest(
    *, answers: list[AnswerLine], documents: list[DocumentLine], status: str
) -> str:
    """A fingerprint of what this package would contain.

    Compared later against the review as it stands, to say "changed since
    generated" without keeping two snapshots side by side. Built from the
    answers and included documents rather than from timestamps, so an
    unrelated edit elsewhere in the review does not read as a change to
    what the customer was sent.
    """
    payload = json.dumps(
        {
            "status": status,
            "answers": [
                [str(line.question_id), line.answer] for line in answers
            ],
            "documents": sorted(
                str(document.file_id)
                for document in documents
                if document.included
            ),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def build_preview(
    db: AsyncSession,
    *,
    review: SecurityReview,
    output_type: str,
    include_documents: list[uuid.UUID] | None = None,
    sections: list[str] | None = None,
    title: str | None = None,
    introduction: str | None = None,
) -> ExportPreview:
    """Assemble exactly what the customer would receive. Writes nothing.

    Called on every preview open and refresh, which is why it has to stay
    free of side effects: a preview that left a record behind would turn
    the export history into a log of packages considered rather than
    packages sent.
    """
    if output_type not in OUTPUT_TYPES:
        raise ValueError(f"Unknown output type: {output_type}")

    answers, blockers, questionnaires = await _answers_for(db, review_id=review.id)
    progress = await progress_for(
        db, review_id=review.id, include_archived=review.archived_at is not None
    )

    documents = await _documents_for(db, organization_id=review.organization_id)

    # What is proposed. Eligible documents are on by default; nothing
    # else ever is, whatever the caller asks for — an ineligible document
    # reaches a package only through an explicit inclusion, and even then
    # only when the rules allow one.
    chosen = set(include_documents or [])
    for document in documents:
        if include_documents is None:
            document.included = document.eligible
        else:
            document.included = document.file_id in chosen and document.eligible

    if review.status not in ("ready_to_share", "completed"):
        blockers.append(
            ExportBlocker(
                "not_ready",
                f"This review is {label_for(review.status).lower()}, not ready to share.",
            )
        )

    preview = ExportPreview(
        output_type=output_type,
        output_label=OUTPUT_LABELS[output_type],
        file_format=OUTPUT_FORMATS[output_type],
        title=(title or "").strip() or _default_title(review, output_type),
        customer_name=review.customer_name,
        review_title=review.title or "Customer security review",
        review_status=review.status,
        review_status_label=label_for(review.status),
        review_archived=review.archived_at is not None,
        review_date=_now(),
        progress=progress,
        answers=answers,
        documents=documents,
        disclosures=[line.answer for line in answers if line.qualified],
        blockers=blockers,
        sections=list(sections or SUMMARY_SECTIONS),
        introduction=(introduction or "").strip() or None,
    )

    if output_type == "questionnaire" and questionnaires:
        source = questionnaires[0]
        preview.column_mapping = dict(source.source_columns or {})
        if source.source_file_id is not None:
            source_file = await db.get(File, source.source_file_id)
            preview.source_filename = (
                source_file.original_filename if source_file else None
            )

    preview.digest = _digest(
        answers=answers, documents=documents, status=review.status
    )
    return preview


def _default_title(review: SecurityReview, output_type: str) -> str:
    customer = review.customer_name or "Customer"
    match output_type:
        case "summary":
            return f"{customer} Security Review Summary"
        case "questionnaire":
            return f"{customer} Security Questionnaire — Completed"
        case _:
            return f"{customer} Assurance Pack"


async def next_version(
    db: AsyncSession, *, review_id: uuid.UUID, output_type: str
) -> int:
    """The version number this generation would take.

    Per review and output type, so "version 2 of the summary" is
    something a person can ask for and point at.
    """
    rows = (
        await db.execute(
            select(ReviewExport.version).where(
                ReviewExport.security_review_id == review_id,
                ReviewExport.output_type == output_type,
            )
        )
    ).scalars().all()
    return (max(rows) + 1) if rows else 1


async def is_stale(
    db: AsyncSession, *, export: ReviewExport, review: SecurityReview
) -> bool:
    """Has the review moved since this package was generated?

    The old package stays exactly as it is either way. This only decides
    whether the screen says so.
    """
    if not export.source_digest:
        return False
    current = await build_preview(
        db, review=review, output_type=export.output_type
    )
    return current.digest != export.source_digest


__all__ = [
    "DISCLAIMER",
    "DISCLOSURES",
    "DISCLOSURE_LABELS",
    "OUTPUT_FORMATS",
    "OUTPUT_LABELS",
    "OUTPUT_TYPES",
    "SECTION_LABELS",
    "SUMMARY_SECTIONS",
    "AnswerLine",
    "DocumentLine",
    "ExportBlocker",
    "ExportPreview",
    "build_preview",
    "is_qualified",
    "is_stale",
    "next_version",
]
