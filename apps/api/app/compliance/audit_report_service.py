"""Turning a confirmed preview into an issued audit report.

The split is the whole point. `audit_report.build_preview` assembles what
the report will say and writes nothing; this renders it and writes the
immutable record of having issued it. Two steps, because an audit report
is a statement somebody signs their name to, and they have to be able to
read it before it exists as a document.

`confirm_digest` joins them. The preview returns a fingerprint of its own
contents; generation requires it back and refuses if the audit has moved
in between. Without that, "generate what I just read" and "generate
whatever is true now" are the same call — and the gap between them is
exactly where a colleague closes a finding.

Nothing here ever edits an existing report. If remediation moves, version
1 keeps saying what it said and somebody generates version 2.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.audit_render import render_audit_report_pdf
from app.compliance.audit_report import AuditReportPreview, next_version
from app.compliance.models import Audit, AuditReport
from app.core.models import File
from app.identity.models import User
from app.core.storage import build_storage_key, upload_object

logger = logging.getLogger("agora.compliance.audit_report_service")

CONTENT_TYPE = "application/pdf"


class ReportRefused(Exception):
    """The report must not be issued as asked."""


def _now() -> datetime:
    return datetime.now(UTC)


def _safe_filename(title: str, version: int) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in " -_" else " "
        for character in title
    )
    return f"{' '.join(cleaned.split())} v{version}.pdf"


def _snapshot(preview: AuditReportPreview) -> dict:
    """The contents, frozen.

    Everything §5 asks to be kept: the audit's own state, the conclusions
    as decided, the finding states and remediation states at generation,
    and the document versions cited. Stored rather than re-derived,
    because re-deriving it next month answers a different question than
    "what did this report say".
    """
    return {
        "audit_id": str(preview.audit_id),
        "audit_title": preview.audit_title,
        "title": preview.title,
        "organization_name": preview.organization_name,
        "framework_name": preview.framework_name,
        "framework_basis": preview.framework_basis,
        "classification": preview.classification,
        "executive_summary": list(preview.executive_summary),
        "methodology": list(preview.methodology),
        "metrics": [
            {"label": m.label, "value": m.value} for m in preview.metrics
        ],
        "auditor_name": preview.auditor_name,
        # The auditor as recorded, not as inferred. Kept structured in
        # the snapshot so a reissue a year from now says the same thing.
        "auditor": {
            "name": preview.auditor.name,
            "auditor_type": preview.auditor.auditor_type,
            "organization": preview.auditor.organization,
            "unresolved": preview.auditor.unresolved,
        },
        "organization_name_configured": preview.organization_name_configured,
        "scope": preview.scope,
        "status": preview.status,
        "started_at": (
            preview.started_at.isoformat() if preview.started_at else None
        ),
        "completed_at": (
            preview.completed_at.isoformat() if preview.completed_at else None
        ),
        "prepared_at": (
            preview.prepared_at.isoformat() if preview.prepared_at else None
        ),
        "progress": {
            "scoped": preview.progress.scoped,
            "reviewed": preview.progress.reviewed,
            "percent_reviewed": preview.progress.percent_reviewed,
            "excluded": preview.progress.excluded,
            "findings": preview.progress.findings,
            "superseded": preview.progress.superseded,
        },
        "conclusion_counts": dict(preview.conclusion_counts),
        "conclusions": [
            {
                "reference_code": line.reference_code,
                "requirement_title": line.requirement_title,
                "control_title": line.control_title,
                "evidence_state": line.evidence_state,
                "decision": line.decision,
                "decision_label": line.decision_label,
                "decision_note": line.decision_note,
                "decided_at": (
                    line.decided_at.isoformat() if line.decided_at else None
                ),
                "decided_by": line.decided_by,
                "evidence_count": line.evidence_count,
                # The live half, frozen at generation and labelled as
                # such. A reader comparing two versions can see exactly
                # what moved between them.
                "current_remediation": line.current_remediation,
            }
            for line in preview.conclusions
        ],
        "findings": [
            {
                "id": str(line.id),
                "reference_code": line.reference_code,
                "requirement_title": line.requirement_title,
                "title": line.title,
                "severity": line.severity,
                "conclusion_label": line.conclusion_label,
                "evidence_state": line.evidence_state,
                "assessment": line.assessment,
                "not_evidenced": line.not_evidenced,
                "auditor_note": line.auditor_note,
                "status_at_generation": line.current_status,
                "remediation_owner": line.remediation_owner,
                "remediation_due": (
                    line.remediation_due.isoformat() if line.remediation_due else None
                ),
                "verified_at": (
                    line.verified_at.isoformat() if line.verified_at else None
                ),
                "verified_by": line.verified_by,
                "verification_note": line.verification_note,
                "remediation_task": line.remediation_task,
            }
            for line in preview.findings
        ],
        "superseded_findings": [
            {
                "id": str(line.id),
                "reference_code": line.reference_code,
                "title": line.title,
                "severity": line.severity,
                "superseded_at": (
                    line.superseded_at.isoformat() if line.superseded_at else None
                ),
                "superseded_reason": line.superseded_reason,
            }
            for line in preview.superseded_findings
        ],
        "remediation": [
            {"status": group.status, "label": group.label, "count": group.count}
            for group in preview.remediation
        ],
        # §17: the exact document version relied on, kept with the row.
        # An index that records a title and no version cannot be checked
        # a year later, because the document will have moved on.
        "evidence_index": [
            {
                "title": line.title,
                "filename": line.filename,
                "version": line.version,
                "version_label": line.version_label,
                "version_source": line.version_source,
                "evidence_states": list(line.evidence_states),
                "requirement_codes": list(line.requirement_codes),
            }
            for line in preview.evidence_index
        ],
        "limitations": list(preview.limitations),
        "disclaimer": preview.disclaimer,
        "sign_off": {
            "auditor_name": preview.sign_off.auditor.name,
            "auditor_type": preview.sign_off.auditor.auditor_type,
            "auditor_organization": preview.sign_off.auditor.organization,
            "completed_at": (
                preview.sign_off.completed_at.isoformat()
                if preview.sign_off.completed_at
                else None
            ),
            "generated_by": preview.sign_off.generated_by,
            "report_version": preview.sign_off.report_version,
            # Null because the product records no formal approval on an
            # audit. Stored explicitly so the record says "nobody
            # approved this" rather than "we did not look".
            "approved_by": preview.sign_off.approved_by,
            "approved_at": (
                preview.sign_off.approved_at.isoformat()
                if preview.sign_off.approved_at
                else None
            ),
        },
    }


async def generate(
    db: AsyncSession,
    *,
    audit: Audit,
    preview: AuditReportPreview,
    confirm_digest: str,
    actor_user_id: uuid.UUID | None,
) -> AuditReport:
    """Render the previewed report and record having issued it.

    Refuses on two grounds, in the order a person meets them: the audit
    has moved since the preview, or the audit is not in a state that can
    be reported on at all.
    """
    if preview.digest != confirm_digest:
        raise ReportRefused(
            "This audit has changed since the preview was prepared. Open the "
            "preview again to see what the report would say now."
        )
    if preview.blockers:
        raise ReportRefused(
            "This report cannot be generated yet: "
            + " ".join(blocker.message for blocker in preview.blockers)
        )

    version = await next_version(db, audit_id=audit.id)
    # The preview was built before anybody clicked generate, so it does
    # not know who did. Stamped here rather than re-derived, so the
    # sign-off in the PDF and the record agree by construction.
    preview.sign_off.report_version = version
    if actor_user_id is not None:
        person = await db.get(User, actor_user_id)
        if person is not None:
            preview.sign_off.generated_by = person.full_name or person.email
    file_bytes = render_audit_report_pdf(preview)
    filename = _safe_filename(preview.audit_title, version)
    storage_key = build_storage_key(audit.organization_id, filename)
    upload_object(storage_key, file_bytes, CONTENT_TYPE)

    file_record = File(
        organization_id=audit.organization_id,
        storage_key=storage_key,
        original_filename=filename,
        content_type=CONTENT_TYPE,
        size_bytes=len(file_bytes),
        uploaded_by=actor_user_id,
        # An internal audit report is an internal document. It goes to a
        # customer only if somebody decides that deliberately, on the
        # document itself, rather than by default because it exists.
        disclosure="internal",
    )
    db.add(file_record)
    await db.flush()

    report = AuditReport(
        organization_id=audit.organization_id,
        audit_id=audit.id,
        title=preview.title,
        version=version,
        file_format="pdf",
        file_id=file_record.id,
        contents=_snapshot(preview),
        source_digest=preview.digest,
        generated_by=actor_user_id,
        generated_at=_now(),
    )
    db.add(report)
    await db.flush()

    await record_event(
        db,
        organization_id=audit.organization_id,
        actor_user_id=actor_user_id,
        action="compliance.audit_report.generated",
        object_type="audit_report",
        object_id=str(report.id),
        after_state={
            "audit": audit.title,
            "framework": audit.framework_name,
            "version": version,
            "requirements_reviewed": preview.progress.reviewed,
            "requirements_in_scope": preview.progress.scoped,
            "findings": preview.progress.findings,
            # The severities that went out, by name. A trail recording
            # "4 findings" cannot answer the question somebody asks a
            # year from now.
            "findings_by_severity": {
                group.label: group.count for group in preview.findings_by_severity
            },
        },
    )

    logger.info("Generated audit report v%d for audit %s", version, audit.id)
    return report


async def history(db: AsyncSession, *, audit_id: uuid.UUID) -> list[AuditReport]:
    """Every report issued for this audit, newest first.

    Nothing is ever replaced. Regenerating adds a version; the earlier
    one stays downloadable, because somebody may have already circulated
    it and our record of what it said has to match their copy.
    """
    return list(
        (
            await db.execute(
                select(AuditReport)
                .where(AuditReport.audit_id == audit_id)
                .order_by(AuditReport.version.desc())
            )
        )
        .scalars()
        .all()
    )


__all__ = ["CONTENT_TYPE", "ReportRefused", "generate", "history"]
