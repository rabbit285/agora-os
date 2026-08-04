from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.audit.service import record_event
from app.core.storage import build_storage_key, presign_download, upload_object
from app.reporting.content import REPORT_BUILDERS
from app.reporting.models import Report
from app.reporting.rendering import RENDERERS
from app.reporting.schemas import REPORT_FORMATS


async def generate_report(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    requested_by: uuid.UUID,
    report_type: str,
    format: str,
) -> Report:
    report = Report(
        organization_id=organization_id,
        requested_by=requested_by,
        report_type=report_type,
        format=format,
        status="generating",
    )
    db.add(report)
    await db.flush()

    try:
        content = await REPORT_BUILDERS[report_type](db, organization_id)
        file_bytes = RENDERERS[format](content)
        storage_key = build_storage_key(organization_id, f"{report_type}.{format}")
        upload_object(storage_key, file_bytes, REPORT_FORMATS[format])
        report.status = "completed"
        report.storage_key = storage_key
    except Exception as exc:  # noqa: BLE001 - a real, persisted failure (storage/render errors), not swallowed
        report.status = "failed"
        report.error_message = str(exc)[:2000]

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=requested_by,
        action="report.generated",
        object_type="report",
        object_id=str(report.id),
        after_state={"report_type": report_type, "format": format, "status": report.status},
    )
    await db.commit()
    await db.refresh(report)
    return report


def reports_query(*, organization_id: uuid.UUID) -> Select[Any]:
    return (
        select(Report)
        .where(Report.organization_id == organization_id)
        .order_by(Report.created_at.desc())
    )


async def get_report(
    db: AsyncSession, *, organization_id: uuid.UUID, report_id: uuid.UUID
) -> Report | None:
    result = await db.execute(
        select(Report).where(Report.id == report_id, Report.organization_id == organization_id)
    )
    return result.scalar_one_or_none()


def get_download_url(report: Report) -> str:
    """The "Secure link" export option (spec §65) — a short-lived signed
    URL, the same `presign_download` primitive `app.routers.files` uses,
    minted fresh per request rather than a permanently-stored link."""
    assert report.storage_key is not None
    return presign_download(report.storage_key)
