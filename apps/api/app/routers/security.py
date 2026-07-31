from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import Evidence, Risk
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.secops.cloud_scanner import run_cloud_security_scan
from app.secops.models import (
    SecurityAlert,
    SecurityAsset,
    SecurityFinding,
    SecurityIncident,
    SecurityIncidentAsset,
    SecurityIncidentTimelineEntry,
)
from app.secops.schemas import (
    AffectedAssetLink,
    AlertCreate,
    AlertDetailOut,
    AlertOut,
    AlertUpdate,
    AssetCreate,
    AssetDetailOut,
    AssetOut,
    CloudScanResultOut,
    FindingCreate,
    FindingOut,
    FindingUpdate,
    IncidentCreate,
    IncidentDetailOut,
    IncidentOut,
    IncidentPostmortemUpdate,
    IncidentUpdate,
    SecurityOverviewOut,
    TimelineEntryCreate,
    TimelineEntryOut,
)
from app.secops.service import compute_security_score, create_incident

router = APIRouter(prefix="/api/v1/security", tags=["security"])


@router.get("/overview", response_model=SecurityOverviewOut)
async def get_security_overview(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> SecurityOverviewOut:
    """Security Overview dashboard (spec §13). Every number is a live
    aggregate query over this org's own rows — there is no cached or
    precomputed rollup to go stale."""
    org_id = context.organization_id

    async def _count(stmt: Any) -> int:
        result = await db.execute(select(func.count()).select_from(stmt.subquery()))
        return int(result.scalar_one())

    critical_alerts = await _count(
        select(SecurityAlert.id).where(
            SecurityAlert.organization_id == org_id,
            SecurityAlert.severity == "critical",
            SecurityAlert.status.notin_(["resolved", "false_positive"]),
        )
    )
    high_risks = await _count(
        select(Risk.id).where(
            Risk.organization_id == org_id,
            Risk.impact == "high",
            Risk.status == "open",
        )
    )
    assets_monitored = await _count(
        select(SecurityAsset.id).where(SecurityAsset.organization_id == org_id)
    )
    vulnerabilities_open = await _count(
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == org_id,
            SecurityFinding.category == "vulnerability",
            SecurityFinding.status == "open",
        )
    )
    identity_issues_open = await _count(
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == org_id,
            SecurityFinding.category == "identity",
            SecurityFinding.status == "open",
        )
    )
    cloud_misconfigurations_open = await _count(
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == org_id,
            SecurityFinding.category == "cloud_misconfiguration",
            SecurityFinding.status == "open",
        )
    )
    open_incidents = await _count(
        select(SecurityIncident.id).where(
            SecurityIncident.organization_id == org_id,
            SecurityIncident.status != "closed",
        )
    )
    total_incidents = await _count(
        select(SecurityIncident.id).where(SecurityIncident.organization_id == org_id)
    )
    incidents_with_evidence = await _count(
        select(SecurityIncident.id)
        .join(Evidence, Evidence.incident_id == SecurityIncident.id)
        .where(SecurityIncident.organization_id == org_id)
        .distinct()
    )
    evidence_coverage_percent = (
        round(100 * incidents_with_evidence / total_incidents, 1) if total_incidents else 0.0
    )

    # Simple, transparent deduction model (spec §13) — shared with the
    # Onboarding readiness score (spec §68), see app.secops.service.
    security_score = await compute_security_score(db, organization_id=org_id)

    return SecurityOverviewOut(
        security_score=security_score,
        critical_alerts=critical_alerts,
        high_risks=high_risks,
        assets_monitored=assets_monitored,
        vulnerabilities_open=vulnerabilities_open,
        identity_issues_open=identity_issues_open,
        cloud_misconfigurations_open=cloud_misconfigurations_open,
        open_incidents=open_incidents,
        evidence_coverage_percent=evidence_coverage_percent,
    )


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


@router.get("/assets/{asset_id}", response_model=AssetDetailOut)
async def get_asset(
    asset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> AssetDetailOut:
    asset = await db.get(SecurityAsset, asset_id)
    if asset is None or asset.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    findings_result = await db.execute(
        select(SecurityFinding)
        .where(SecurityFinding.asset_id == asset.id)
        .order_by(SecurityFinding.created_at.desc())
    )
    incidents_result = await db.execute(
        select(SecurityIncident)
        .join(SecurityIncidentAsset, SecurityIncidentAsset.incident_id == SecurityIncident.id)
        .where(SecurityIncidentAsset.asset_id == asset.id)
        .order_by(SecurityIncident.created_at.desc())
    )
    return AssetDetailOut(
        **AssetOut.model_validate(asset).model_dump(),
        findings=[FindingOut.model_validate(f) for f in findings_result.scalars().all()],
        incidents=[IncidentOut.model_validate(i) for i in incidents_result.scalars().all()],
    )


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
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="security.alert.created",
        object_type="security_alert",
        object_id=str(alert.id),
        after_state={"title": alert.title, "severity": alert.severity},
    )

    from app.automation.triggers import dispatch_event

    await dispatch_event(
        db,
        organization_id=context.organization_id,
        trigger_type="security_alert",
        payload={"alert_id": str(alert.id), "title": alert.title, "severity": alert.severity},
        actor_user_id=context.user.id,
    )

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
    before_status = alert.status
    alert.status = payload.status
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="security.alert.status_changed",
        object_type="security_alert",
        object_id=str(alert.id),
        before_state={"status": before_status},
        after_state={"status": alert.status},
    )
    await db.commit()
    await db.refresh(alert)
    return alert


@router.get("/alerts/{alert_id}", response_model=AlertDetailOut)
async def get_alert(
    alert_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> AlertDetailOut:
    alert = await db.get(SecurityAlert, alert_id)
    if alert is None or alert.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    finding = await db.get(SecurityFinding, alert.finding_id) if alert.finding_id else None
    return AlertDetailOut(
        **AlertOut.model_validate(alert).model_dump(),
        finding=FindingOut.model_validate(finding) if finding else None,
    )


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


async def _get_org_incident(
    db: AsyncSession, incident_id: uuid.UUID, organization_id: uuid.UUID
) -> SecurityIncident:
    incident = await db.get(SecurityIncident, incident_id)
    if incident is None or incident.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident


@router.get("/incidents/{incident_id}", response_model=IncidentDetailOut)
async def get_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> IncidentDetailOut:
    """Incident workspace (spec §19): Timeline, Communication (both the
    same chronological log, discriminated by entry_type), Affected Assets,
    and Evidence/Root-Cause/Lessons-Learned are all part of this detail
    view, not a bare status enum."""
    incident = await _get_org_incident(db, incident_id, context.organization_id)

    timeline_result = await db.execute(
        select(SecurityIncidentTimelineEntry)
        .where(SecurityIncidentTimelineEntry.incident_id == incident.id)
        .order_by(SecurityIncidentTimelineEntry.created_at.asc())
    )
    assets_result = await db.execute(
        select(SecurityAsset)
        .join(SecurityIncidentAsset, SecurityIncidentAsset.asset_id == SecurityAsset.id)
        .where(SecurityIncidentAsset.incident_id == incident.id)
    )

    return IncidentDetailOut(
        **IncidentOut.model_validate(incident).model_dump(),
        timeline=[TimelineEntryOut.model_validate(e) for e in timeline_result.scalars().all()],
        affected_assets=[AssetOut.model_validate(a) for a in assets_result.scalars().all()],
    )


@router.post(
    "/incidents/{incident_id}/timeline",
    response_model=TimelineEntryOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_timeline_entry(
    incident_id: uuid.UUID,
    payload: TimelineEntryCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.incidents.manage")),
) -> SecurityIncidentTimelineEntry:
    incident = await _get_org_incident(db, incident_id, context.organization_id)
    entry = SecurityIncidentTimelineEntry(
        organization_id=context.organization_id,
        incident_id=incident.id,
        entry_type=payload.entry_type,
        body=payload.body,
        author_id=context.user.id,
    )
    db.add(entry)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="security.incident.timeline_entry_added",
        object_type="security_incident",
        object_id=str(incident.id),
        after_state={"entry_type": entry.entry_type},
    )
    await db.commit()
    await db.refresh(entry)
    return entry


@router.post(
    "/incidents/{incident_id}/assets",
    response_model=IncidentDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def link_affected_asset(
    incident_id: uuid.UUID,
    payload: AffectedAssetLink,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.incidents.manage")),
) -> IncidentDetailOut:
    incident = await _get_org_incident(db, incident_id, context.organization_id)
    asset = await db.get(SecurityAsset, payload.asset_id)
    if asset is None or asset.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    existing = await db.get(SecurityIncidentAsset, (incident.id, asset.id))
    if existing is None:
        db.add(SecurityIncidentAsset(incident_id=incident.id, asset_id=asset.id))
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="security.incident.asset_linked",
            object_type="security_incident",
            object_id=str(incident.id),
            after_state={"asset_id": str(asset.id)},
        )
        await db.commit()

    return await get_incident(incident_id, db, context)


@router.patch("/incidents/{incident_id}/postmortem", response_model=IncidentOut)
async def update_incident_postmortem(
    incident_id: uuid.UUID,
    payload: IncidentPostmortemUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.incidents.manage")),
) -> SecurityIncident:
    incident = await _get_org_incident(db, incident_id, context.organization_id)
    if payload.root_cause is not None:
        incident.root_cause = payload.root_cause
    if payload.lessons_learned is not None:
        incident.lessons_learned = payload.lessons_learned
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="security.incident.postmortem_updated",
        object_type="security_incident",
        object_id=str(incident.id),
    )
    await db.commit()
    await db.refresh(incident)
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


@router.post("/cloud-scan", response_model=CloudScanResultOut)
async def trigger_cloud_scan(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("security.assets.manage")),
) -> CloudScanResultOut:
    """Cloud Security / Identity Security scan (spec §15-16): runs real
    checks against the org's configured AWS account and creates
    `SecurityFinding` rows for anything found. Returns
    `configured=False` (creates nothing) rather than a fake result when
    no AWS credentials are set — see app.secops.cloud_scanner."""
    result = await run_cloud_security_scan(
        db, organization_id=context.organization_id, actor_user_id=context.user.id
    )
    await db.commit()
    return CloudScanResultOut(
        configured=result.configured,
        checks_run=result.checks_run,
        findings_created=result.findings_created,
    )
