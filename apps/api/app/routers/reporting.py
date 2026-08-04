from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Pagination, paginate, pagination_params
from app.db.session import get_db
from app.dependencies import OrgContext, require_permission
from app.reporting.models import Report
from app.reporting.schemas import (
    REPORT_TYPES,
    ReportCreate,
    ReportDownloadOut,
    ReportOut,
    ReportTypeOut,
)
from app.reporting.service import generate_report, get_download_url, get_report, reports_query

router = APIRouter(prefix="/api/v1/reports", tags=["reporting"])


@router.get("/types", response_model=list[ReportTypeOut])
async def list_report_types(
    _: OrgContext = Depends(require_permission("reports.generate")),
) -> list[ReportTypeOut]:
    """Catalog of spec §65's 14 named report types, for the frontend to
    render a picker without hardcoding the list."""
    return [ReportTypeOut(key=key, label=label) for key, label in REPORT_TYPES.items()]


@router.get("", response_model=list[ReportOut])
async def list_organization_reports(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("reports.generate")),
    pagination: Pagination = Depends(pagination_params),
) -> list[Report]:
    stmt = reports_query(organization_id=context.organization_id)
    return await paginate(db, stmt, pagination, response)


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("reports.generate")),
) -> Report:
    """Generation is synchronous: every report type is a set of real,
    fast aggregate queries plus an in-process render (no AI call), so
    there is no async job to poll for — the response's `status` is
    already terminal (`completed` or `failed`)."""
    return await generate_report(
        db,
        organization_id=context.organization_id,
        requested_by=context.user.id,
        report_type=payload.report_type,
        format=payload.format,
    )


@router.get("/{report_id}", response_model=ReportOut)
async def get_organization_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("reports.generate")),
) -> Report:
    report = await get_report(db, organization_id=context.organization_id, report_id=report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


@router.get("/{report_id}/download", response_model=ReportDownloadOut)
async def download_organization_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("reports.generate")),
) -> ReportDownloadOut:
    report = await get_report(db, organization_id=context.organization_id, report_id=report_id)
    if report is None or report.status != "completed":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return ReportDownloadOut(download_url=get_download_url(report))
