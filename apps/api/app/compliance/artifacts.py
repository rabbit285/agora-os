"""What Veyntra produced, kept apart from what it was given.

A generated report is a **result** of compliance work, not an
independent source of it. That distinction was missing, and the
consequence was a loop the product could walk on its own:

    evidence → assessment → audit → audit report → Documents →
    "Analyze for evidence" → evidence → assessment …

Once round that circle, the compliance state is partly supported by a
document Veyntra wrote from the compliance state. Nothing in the record
says so, and an auditor pulling the thread finds the product citing
itself.

So the type is stored on the file, and everything downstream keys on it:
evidence analysis refuses a generated output, the copilot index skips
it, and the library lists it apart. Hiding it in the UI would have left
every one of those paths open.

**The exception is deliberate and narrow.** An audit report genuinely
can evidence that an audit took place — "perform internal audits" is a
requirement, and the report is the artefact proving it was done. That
route exists here, but it is an explicit act with a reason attached, and
it refuses the one case that would close the loop: a report cannot
evidence the requirements its own audit assessed.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compliance.models import (
    Audit,
    AuditItem,
    AuditReport,
    ReviewExport,
    SecurityReview,
)
from app.core.models import File

logger = logging.getLogger("agora.compliance.artifacts")

SOURCE = "source"
GENERATED = "generated_output"

# What a person is told these are, rather than the column value. "Source
# document" and "Generated output" are the words; `artifact_type` is
# plumbing and never appears on screen.
ARTIFACT_LABELS = {
    SOURCE: "Source document",
    GENERATED: "Generated output",
}

ORIGIN_LABELS = {
    "audit_report": "Audit",
    "review_export": "Security review",
}

# Where a person goes to see the record a generated output came from.
ORIGIN_ROUTES = {
    "audit_report": "/compliance/audits/{id}",
    "review_export": "/compliance/security-reviews/{id}",
}


class EvidenceRefused(Exception):
    """This document must not become evidence in the way asked."""


def is_generated(file_record: File) -> bool:
    return (file_record.artifact_type or SOURCE) == GENERATED


def origin_href(file_record: File) -> str | None:
    template = ORIGIN_ROUTES.get(file_record.origin_type or "")
    if not template or file_record.origin_id is None:
        return None
    return template.format(id=file_record.origin_id)


def mark_generated(
    file_record: File,
    *,
    origin_type: str,
    origin_id: uuid.UUID,
    origin_label: str | None,
) -> File:
    """Record that Veyntra produced this, and out of what.

    Called at generation rather than inferred afterwards, because the
    generator is the only place that knows for certain — and a
    classification derived from a filename is one a customer can break
    by naming an upload "Audit Report v2".
    """
    file_record.artifact_type = GENERATED
    file_record.origin_type = origin_type
    file_record.origin_id = origin_id
    file_record.origin_label = (origin_label or "")[:300] or None
    # A generated output is not waiting to be analysed. Leaving it at
    # "not_analyzed" is what put "Not analyzed yet · Analyze for
    # evidence" on every report the product wrote.
    file_record.processing_status = "generated"
    return file_record


@dataclass
class CircularityCheck:
    """Whether using this document as evidence would close a loop."""

    circular: bool
    reason: str | None = None


async def check_circularity(
    db: AsyncSession,
    *,
    file_record: File,
    control_id: uuid.UUID | None = None,
    requirement_id: uuid.UUID | None = None,
) -> CircularityCheck:
    """Would this generated output evidence its own conclusions?

    An audit report may prove an audit happened. It may not prove that
    the requirements that audit assessed are met — the report says they
    are *because the auditor concluded so*, and feeding that back in as
    independent evidence launders a conclusion into a fact.

    So the check is specific rather than blanket: the report is refused
    against the requirements its own audit scoped, and allowed
    elsewhere.
    """
    if not is_generated(file_record):
        return CircularityCheck(circular=False)
    if file_record.origin_type != "audit_report" or file_record.origin_id is None:
        # A security-review export has no requirement conclusions of its
        # own to feed back, so there is no loop to detect here. It is
        # still excluded from automatic analysis; this is only about the
        # explicit route.
        return CircularityCheck(circular=False)
    if requirement_id is None:
        return CircularityCheck(circular=False)

    # `origin_id` is the audit itself, which is both what a person
    # opens and what the loop is about.
    scoped = (
        await db.execute(
            select(AuditItem.id).where(
                AuditItem.audit_id == file_record.origin_id,
                AuditItem.requirement_id == requirement_id,
            )
        )
    ).first()
    if scoped is None:
        return CircularityCheck(circular=False)

    return CircularityCheck(
        circular=True,
        reason=(
            "This report was generated from the audit that assessed this "
            "requirement. Using it as evidence here would mean the "
            "requirement is supported by a document written from the "
            "conclusion about it."
        ),
    )


async def guard_analysis(file_record: File) -> None:
    """Refuse to run evidence analysis over something Veyntra wrote.

    Raised at the endpoint rather than filtered in the query, so the
    person who asked gets told why instead of watching a request return
    nothing.
    """
    if is_generated(file_record):
        raise EvidenceRefused(
            "This file was generated by Veyntra from your compliance records, "
            "so it is not analysed for evidence. Analysing it would let the "
            "compliance state be supported by a document written from that "
            "same state."
        )


async def backfill(db: AsyncSession) -> dict[str, int]:
    """Classify generated files that predate the column.

    Driven off the **generation records** — `audit_reports.file_id` and
    `review_exports.file_id` — which are authoritative about what
    produced a file. Deliberately not off filenames: a customer can
    upload something called "Audit Report v2", and a migration that
    reclassified it would quietly remove a real document from the
    evidence library.
    """
    counts = {"audit_reports": 0, "review_exports": 0}

    reports = (
        await db.execute(
            select(AuditReport).where(AuditReport.file_id.is_not(None))
        )
    ).scalars().all()
    for report in reports:
        file_record = await db.get(File, report.file_id)
        if file_record is None or is_generated(file_record):
            continue
        audit = await db.get(Audit, report.audit_id)
        mark_generated(
            file_record,
            origin_type="audit_report",
            origin_id=report.audit_id,
            origin_label=(audit.title if audit else None) or report.title,
        )
        counts["audit_reports"] += 1

    exports = (
        await db.execute(
            select(ReviewExport).where(ReviewExport.file_id.is_not(None))
        )
    ).scalars().all()
    for export in exports:
        file_record = await db.get(File, export.file_id)
        if file_record is None or is_generated(file_record):
            continue
        review = await db.get(SecurityReview, export.security_review_id)
        mark_generated(
            file_record,
            origin_type="review_export",
            origin_id=export.security_review_id,
            origin_label=(review.title if review else None) or export.title,
        )
        counts["review_exports"] += 1

    if counts["audit_reports"] or counts["review_exports"]:
        await db.flush()
    logger.info("Artifact backfill: %s", counts)
    return counts


__all__ = [
    "ARTIFACT_LABELS",
    "GENERATED",
    "ORIGIN_LABELS",
    "SOURCE",
    "CircularityCheck",
    "EvidenceRefused",
    "backfill",
    "check_circularity",
    "guard_analysis",
    "is_generated",
    "mark_generated",
    "origin_href",
]
