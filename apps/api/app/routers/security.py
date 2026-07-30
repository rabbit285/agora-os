from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.secops.models import SecurityAlert, SecurityAsset, SecurityFinding, SecurityIncident
from app.secops.schemas import (
    AlertCreate,
    AlertOut,
    AlertUpdate,
    AssetCreate,
    AssetOut,
    FindingCreate,
    FindingOut,
    FindingUpdate,
    IncidentCreate,
    IncidentOut,
    IncidentUpdate,
)
from app.secops.service import create_incident

router = APIRouter(prefix="/api/v1/security", tags=["security"])


@router.get("/assets", response_model=list[AssetOut])
async def list_assets(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[SecurityAsset]:
    result = await db.execute(
        select(SecurityAsset)
        .where(SecurityAsset.organization_id == context.organization_id)
        .order_by(SecurityAsset.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.assets.manage")),
) -> SecurityAsset:
    asset = SecurityAsset(
        organization_id=context.organization_id,
        last_observed_at=datetime.now(UTC),
        **payload.model_dump(),
    )
    db.add(asset)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="security.asset.created",
        object_type="security_asset",
        object_id=str(asset.id),
        after_state={"name": asset.name, "asset_type": asset.asset_type},
    )
    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("/findings", response_model=list[FindingOut])
async def list_findings(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[SecurityFinding]:
    result = await db.execute(
        select(SecurityFinding)
        .where(SecurityFinding.organization_id == context.organization_id)
        .order_by(SecurityFinding.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/findings", response_model=FindingOut, status_code=status.HTTP_201_CREATED)
async def create_finding(
    payload: FindingCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.findings.manage")),
) -> SecurityFinding:
    if payload.asset_id is not None:
        asset = await db.get(SecurityAsset, payload.asset_id)
        if asset is None or asset.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    finding = SecurityFinding(organization_id=context.organization_id, **payload.model_dump())
    db.add(finding)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="security.finding.created",
        object_type="security_finding",
        object_id=str(finding.id),
        after_state={"title": finding.title, "severity": finding.severity},
    )
    await db.commit()
    await db.refresh(finding)
    return finding


@router.patch("/findings/{finding_id}", response_model=FindingOut)
async def update_finding(
    finding_id: uuid.UUID,
    payload: FindingUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.findings.manage")),
) -> SecurityFinding:
    finding = await db.get(SecurityFinding, finding_id)
    if finding is None or finding.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    before_status = finding.status
    finding.status = payload.status
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="security.finding.status_changed",
        object_type="security_finding",
        object_id=str(finding.id),
        before_state={"status": before_status},
        after_state={"status": finding.status},
    )
    await db.commit()
    await db.refresh(finding)
    return finding


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[SecurityAlert]:
    result = await db.execute(
        select(SecurityAlert)
        .where(SecurityAlert.organization_id == context.organization_id)
        .order_by(SecurityAlert.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/alerts", response_model=AlertOut, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: AlertCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.alerts.manage")),
) -> SecurityAlert:
    if payload.finding_id is not None:
        finding = await db.get(SecurityFinding, payload.finding_id)
        if finding is None or finding.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")

    alert = SecurityAlert(organization_id=context.organization_id, **payload.model_dump())
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: uuid.UUID,
    payload: AlertUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.alerts.manage")),
) -> SecurityAlert:
    alert = await db.get(SecurityAlert, alert_id)
    if alert is None or alert.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    alert.status = payload.status
    await db.commit()
    await db.refresh(alert)
    return alert


@router.get("/incidents", response_model=list[IncidentOut])
async def list_incidents(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[SecurityIncident]:
    result = await db.execute(
        select(SecurityIncident)
        .where(SecurityIncident.organization_id == context.organization_id)
        .order_by(SecurityIncident.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/incidents", response_model=IncidentOut, status_code=status.HTTP_201_CREATED)
async def create_incident_endpoint(
    payload: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.incidents.manage")),
) -> SecurityIncident:
    incident = await create_incident(
        db,
        organization_id=context.organization_id,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        owner_id=payload.owner_id,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(incident)
    return incident


@router.get("/incidents/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> SecurityIncident:
    incident = await db.get(SecurityIncident, incident_id)
    if incident is None or incident.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


@router.patch("/incidents/{incident_id}", response_model=IncidentOut)
async def update_incident(
    incident_id: uuid.UUID,
    payload: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.incidents.manage")),
) -> SecurityIncident:
    incident = await db.get(SecurityIncident, incident_id)
    if incident is None or incident.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    before_status = incident.status
    incident.status = payload.status
    if payload.status == "closed":
        incident.closed_at = datetime.now(UTC)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="security.incident.status_changed",
        object_type="security_incident",
        object_id=str(incident.id),
        before_state={"status": before_status},
        after_state={"status": incident.status},
    )
    await db.commit()
    await db.refresh(incident)
    return incident
