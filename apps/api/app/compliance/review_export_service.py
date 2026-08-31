"""Turning a confirmed preview into a package that leaves the building.

The split is the point. `review_export.build_preview` assembles what the
customer would receive and writes nothing; this generates the file and
writes the immutable record of having done so. Two steps, because the
compliance team must be able to read the contents before the contents
exist as something sendable.

`confirm_digest` is what joins them. The preview returns a fingerprint of
its own contents; generation requires it back and refuses if the review
has moved in between. Without that, "generate what I just looked at" and
"generate whatever is true now" are the same call, and the gap between
them is exactly where somebody else approves an answer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import ReviewExport, SecurityReview
from app.compliance.review_export import (
    OUTPUT_FORMATS,
    OUTPUT_LABELS,
    ExportPreview,
    build_preview,
    next_version,
)
from app.compliance.review_render import (
    render_evidence_pack,
    render_questionnaire_xlsx,
    render_summary_pdf,
)
from app.core.models import File
from app.core.storage import build_storage_key, download_object, upload_object

logger = logging.getLogger("agora.compliance.review_export_service")

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}


class ExportRefused(Exception):
    """The package must not be generated as asked."""


def _now() -> datetime:
    return datetime.now(UTC)


def _safe_filename(title: str, extension: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in " -_" else " "
        for character in title
    )
    return f"{' '.join(cleaned.split())}.{extension}"


def _snapshot(preview: ExportPreview) -> dict:
    """The contents, frozen.

    Stored rather than re-derived because re-deriving it tomorrow answers
    a different question than "what did we send". Everything a person
    would need to see what went out, without the internal identifiers a
    customer never sees.
    """
    return {
        "title": preview.title,
        "customer_name": preview.customer_name,
        "review_title": preview.review_title,
        "review_status": preview.review_status,
        "review_archived": preview.review_archived,
        "generated_for": preview.review_date.isoformat(),
        "sections": list(preview.sections),
        "introduction": preview.introduction,
        "disclaimer": preview.disclaimer,
        "progress": {
            "questionnaires": preview.progress.questionnaires,
            "total": preview.progress.total,
            "approved": preview.progress.approved,
            "percent_complete": preview.progress.percent_complete,
        },
        "answers": [
            {
                "question": line.question,
                "answer": line.answer,
                "category": line.category,
                "sources": list(line.sources),
                "qualified": line.qualified,
                "approved_at": (
                    line.approved_at.isoformat() if line.approved_at else None
                ),
            }
            for line in preview.answers
        ],
        "documents": [
            {
                "file_id": str(document.file_id),
                "title": document.title,
                "kind": document.kind,
                "version": document.version,
                "status": document.status,
                "disclosure": document.disclosure,
            }
            for document in preview.included_documents
        ],
        "disclosures": list(preview.disclosures),
        "column_mapping": dict(preview.column_mapping),
        "source_filename": preview.source_filename,
    }


async def generate(
    db: AsyncSession,
    *,
    review: SecurityReview,
    preview: ExportPreview,
    confirm_digest: str,
    actor_user_id: uuid.UUID | None,
    may_override_disclosure: bool = False,
) -> ReviewExport:
    """Render the previewed contents and record having sent them.

    Refuses on three grounds, in the order a person would meet them: the
    review has moved since the preview, something in it is not fit to
    send, or the selection includes a document nobody cleared.
    """
    if preview.digest != confirm_digest:
        raise ExportRefused(
            "The review has changed since this preview was prepared. Open the "
            "preview again to see what would be sent now."
        )

    if preview.blockers:
        raise ExportRefused(
            "This review cannot be exported yet: "
            + " ".join(blocker.message for blocker in preview.blockers)
        )

    # Nothing ineligible reaches a package by accident. `build_preview`
    # already refuses to mark one included; this is the second check, at
    # the boundary where the file gets made, because an export is the one
    # place where being wrong is irreversible.
    ineligible = [
        document
        for document in preview.included_documents
        if not document.eligible
    ]
    if ineligible:
        restricted = [d for d in ineligible if d.disclosure == "restricted"]
        if restricted or not may_override_disclosure:
            names = ", ".join(document.title for document in ineligible)
            raise ExportRefused(
                f"These documents are not approved for external sharing: {names}."
            )

    file_bytes, extension = await _render(db, preview)
    storage_key = build_storage_key(
        review.organization_id, _safe_filename(preview.title, extension)
    )
    upload_object(storage_key, file_bytes, CONTENT_TYPES[extension])

    file_record = File(
        organization_id=review.organization_id,
        storage_key=storage_key,
        original_filename=_safe_filename(preview.title, extension),
        content_type=CONTENT_TYPES[extension],
        size_bytes=len(file_bytes),
        uploaded_by=actor_user_id,
        # The generated package is itself a document the organization
        # decided to send, so it is shareable by construction — unlike
        # everything uploaded, which starts internal.
        disclosure="customer_shareable",
    )
    db.add(file_record)
    await db.flush()

    export = ReviewExport(
        organization_id=review.organization_id,
        security_review_id=review.id,
        output_type=preview.output_type,
        file_format=extension,
        title=preview.title,
        version=await next_version(
            db, review_id=review.id, output_type=preview.output_type
        ),
        file_id=file_record.id,
        contents=_snapshot(preview),
        source_digest=preview.digest,
        generated_by=actor_user_id,
        generated_at=_now(),
    )
    db.add(export)
    await db.flush()

    await record_event(
        db,
        organization_id=review.organization_id,
        actor_user_id=actor_user_id,
        action=f"compliance.review_export.{preview.output_type}_generated",
        object_type="review_export",
        object_id=str(export.id),
        after_state={
            "review": review.title or "Customer security review",
            "customer": review.customer_name,
            "output": OUTPUT_LABELS[preview.output_type],
            "format": extension,
            "version": export.version,
            "answers": len(preview.answers),
            # The document versions that went out, by name. An audit
            # trail that records "3 documents" cannot answer the question
            # somebody will actually ask a year from now.
            "documents": [
                f"{document.title}"
                + (f" v{document.version}" if document.version else "")
                for document in preview.included_documents
            ],
            "overridden": [
                document.title
                for document in preview.included_documents
                if not document.eligible
            ],
        },
    )

    logger.info(
        "Generated %s v%d for review %s",
        preview.output_type,
        export.version,
        review.id,
    )
    return export


async def _render(
    db: AsyncSession, preview: ExportPreview
) -> tuple[bytes, str]:
    """The bytes, from the preview and nothing else."""
    match preview.output_type:
        case "summary":
            return render_summary_pdf(preview), "pdf"
        case "questionnaire":
            return render_questionnaire_xlsx(preview), "xlsx"
        case _:
            documents: list[tuple[str, bytes]] = []
            for document in preview.included_documents:
                file_record = await db.get(File, document.file_id)
                if file_record is None:  # pragma: no cover - it was just listed
                    continue
                try:
                    payload = download_object(file_record.storage_key)
                except Exception:  # noqa: BLE001 - one missing file is not a failed pack
                    logger.warning(
                        "Evidence pack: could not read %s", file_record.storage_key
                    )
                    continue
                documents.append((file_record.original_filename, payload))
            return (
                render_evidence_pack(
                    preview,
                    summary_pdf=render_summary_pdf(preview),
                    questionnaire_xlsx=(
                        render_questionnaire_xlsx(preview) if preview.answers else None
                    ),
                    documents=documents,
                ),
                "zip",
            )


async def mark_shared(
    db: AsyncSession,
    *,
    export: ReviewExport,
    actor_user_id: uuid.UUID | None,
) -> bool:
    """Record that a generated package actually went to the customer.

    Deliberately a separate act. Generating a PDF is not sending it, and
    a product that marks something shared because a file exists is
    telling its user a delivery happened that nobody performed.
    """
    if export.shared_at is not None:
        return False
    export.shared_at = _now()
    export.shared_by = actor_user_id
    await record_event(
        db,
        organization_id=export.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.review_export.shared",
        object_type="review_export",
        object_id=str(export.id),
        after_state={"title": export.title, "version": export.version},
    )
    await db.flush()
    return True


async def history(
    db: AsyncSession, *, review_id: uuid.UUID
) -> list[ReviewExport]:
    return list(
        (
            await db.execute(
                select(ReviewExport)
                .where(ReviewExport.security_review_id == review_id)
                .order_by(ReviewExport.generated_at.desc())
            )
        )
        .scalars()
        .all()
    )


__all__ = ["CONTENT_TYPES", "ExportRefused", "generate", "history", "mark_shared"]
