"""Security domain services.

`create_incident` ships all 9 of spec §69's "Security Incident" chain
steps, all gated on `severity == "critical"` and all firing from the same
event ("Creates incident -> Security AI summarizes -> Finds affected
assets -> Checks personal-data impact -> Compliance module assesses GDPR
breach obligations -> Creates incident response tasks -> Notifies
responsible team -> Generates draft communications -> Preserves
evidence"):

1. (Phase 4, ADR-0018) Auto-creates a linked Compliance `Risk` so the
   GDPR breach-notification obligation is tracked somewhere real.
2. (Phase 8, ADR-0023) Auto-creates a `core.Task` ("Investigate and
   contain: ...") and, if the incident has an `owner_id`, a
   `core.Notification` to that owner — reusing the Phase 1 Task and
   Notification primitives rather than inventing incident-specific
   response-tracking types.
3. (ADR-0043) "Security AI summarizes" — a real `ModelGateway.generate`
   call (honest demo-mode text when uncredentialed, like every other AI
   call in this build), stored as `ai_summary`.
4. (ADR-0043) "Finds affected assets" — a disclosed heuristic, not a
   forensic claim: every existing `SecurityAsset` already flagged
   `at_risk`/`compromised` elsewhere in the inventory is linked via the
   pre-existing `SecurityIncidentAsset` workspace join (spec §19
   "Affected Assets" — reused, not duplicated).
5. (ADR-0043) "Checks personal-data impact" — `personal_data_impact` is
   true if any auto-linked asset is classified `confidential`/
   `restricted`; a disclosed heuristic a human still confirms via the
   linked Risk, not a legal determination this code makes for real.
6. (ADR-0043) "Generates draft communications" — a real AI-drafted
   stakeholder update stored as a `SecurityIncidentTimelineEntry`
   (`entry_type="communication"`), the pre-existing workspace Timeline
   reused for its intended purpose rather than a new communications
   table.
7. (ADR-0043) "Preserves evidence" — a real point-in-time JSON snapshot
   of the incident's known facts, uploaded via the same `File`/storage
   primitive the Enterprise Sales Security Review's trust package
   already uses, attached via the pre-existing `Evidence.incident_id`
   link (spec §19 "Evidence" — reused, not duplicated).

All of this extends the same hook rather than adding a second one, since
spec §69's chain is a single event with multiple shared-primitive
consequences, not several separate triggers.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway import GenerateRequest, ModelGateway
from app.audit.service import record_event
from app.compliance.models import Evidence, Risk
from app.core.models import File, Task
from app.core.notifications import notify
from app.core.storage import ensure_bucket, upload_object
from app.secops.models import (
    SecurityAlert,
    SecurityAsset,
    SecurityFinding,
    SecurityIncident,
    SecurityIncidentAsset,
    SecurityIncidentTimelineEntry,
)
from app.secops.schemas import SecurityOverviewOut

_PERSONAL_DATA_CLASSIFICATIONS = {"confidential", "restricted"}


async def create_incident(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    title: str,
    description: str | None,
    severity: str,
    owner_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    gateway: ModelGateway | None = None,
) -> SecurityIncident:
    gateway = gateway or ModelGateway()
    incident = SecurityIncident(
        organization_id=organization_id,
        title=title,
        description=description,
        severity=severity,
        owner_id=owner_id,
    )
    db.add(incident)
    await db.flush()

    response_task_id: uuid.UUID | None = None
    if severity == "critical":
        summary_result = await gateway.generate(
            db,
            organization_id=organization_id,
            requested_by=actor_user_id,
            request=GenerateRequest(
                task_type="security.incident_summary",
                prompt=(
                    "Summarize this security incident in 2-3 sentences for a responder "
                    f"who has not seen it yet.\n\nTitle: {title}\n"
                    f"Description: {description or '(none provided)'}"
                ),
            ),
        )
        incident.ai_summary = summary_result.text

        affected_assets_result = await db.execute(
            select(SecurityAsset).where(
                SecurityAsset.organization_id == organization_id,
                SecurityAsset.status.in_(("at_risk", "compromised")),
            )
        )
        affected_assets = list(affected_assets_result.scalars().all())
        for asset in affected_assets:
            db.add(SecurityIncidentAsset(incident_id=incident.id, asset_id=asset.id))
        incident.personal_data_impact = any(
            asset.data_classification in _PERSONAL_DATA_CLASSIFICATIONS for asset in affected_assets
        )

        risk = Risk(
            organization_id=organization_id,
            title=f"Security incident: {title}",
            description=(
                "Auto-created from a critical security incident. Assess GDPR breach "
                "notification obligations (spec section 19)."
            ),
            category="security",
            likelihood="high",
            impact="high",
            owner_id=owner_id,
        )
        db.add(risk)
        await db.flush()
        incident.related_risk_id = risk.id

        response_task = Task(
            organization_id=organization_id,
            title=f"Investigate and contain: {title}",
            description=description,
            module="security",
            priority="urgent",
            assignee_id=owner_id,
        )
        db.add(response_task)
        await db.flush()
        incident.related_task_id = response_task.id
        response_task_id = response_task.id

        if owner_id is not None:
            await notify(
                db,
                organization_id=organization_id,
                user_id=owner_id,
                title="Critical security incident assigned to you",
                body=f'"{title}" was just declared critical and needs immediate '
                "investigation and containment.",
                link="/security",
                channels=["email"],
            )

        communication_result = await gateway.generate(
            db,
            organization_id=organization_id,
            requested_by=actor_user_id,
            request=GenerateRequest(
                task_type="security.incident_communication_draft",
                prompt=(
                    "Draft a brief, factual stakeholder update about this security "
                    f"incident. Do not speculate about cause or impact beyond what's "
                    f"given.\n\nTitle: {title}\nSeverity: {severity}\n"
                    f"Description: {description or '(none provided)'}"
                ),
            ),
        )
        db.add(
            SecurityIncidentTimelineEntry(
                organization_id=organization_id,
                incident_id=incident.id,
                entry_type="communication",
                body=communication_result.text,
                author_id=actor_user_id,
            )
        )

        snapshot = {
            "incident_id": str(incident.id),
            "title": title,
            "description": description,
            "severity": severity,
            "ai_summary": incident.ai_summary,
            "personal_data_impact": incident.personal_data_impact,
            "affected_asset_ids": [str(asset.id) for asset in affected_assets],
            "related_risk_id": str(risk.id),
        }
        ensure_bucket()
        snapshot_bytes = json.dumps(snapshot, indent=2).encode("utf-8")
        storage_key = f"org/{organization_id}/security-incidents/{incident.id}/snapshot.json"
        upload_object(storage_key, snapshot_bytes, "application/json")
        snapshot_file = File(
            organization_id=organization_id,
            storage_key=storage_key,
            original_filename="snapshot.json",
            content_type="application/json",
            size_bytes=len(snapshot_bytes),
            uploaded_by=actor_user_id,
        )
        db.add(snapshot_file)
        await db.flush()
        db.add(
            Evidence(
                organization_id=organization_id,
                incident_id=incident.id,
                file_id=snapshot_file.id,
                title=f"Point-in-time snapshot: {title}",
                created_by=actor_user_id,
            )
        )

    await record_event(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="security.incident.created",
        object_type="security_incident",
        object_id=str(incident.id),
        after_state={
            "title": incident.title,
            "severity": incident.severity,
            "response_task_id": str(response_task_id) if response_task_id else None,
        },
    )
    return incident


async def compute_security_score(db: AsyncSession, *, organization_id: uuid.UUID) -> int:
    """The same simple, transparent deduction model `GET /security/overview`
    computes (spec §13) — extracted here so it has one real implementation
    used by both that dashboard and the Onboarding readiness score
    (spec §68), rather than two independently-drifting copies."""

    async def _count(stmt: Any) -> int:
        result = await db.execute(select(func.count()).select_from(stmt.subquery()))
        return int(result.scalar_one())

    critical_alerts = await _count(
        select(SecurityAlert.id).where(
            SecurityAlert.organization_id == organization_id,
            SecurityAlert.severity == "critical",
            SecurityAlert.status.notin_(["resolved", "false_positive"]),
        )
    )
    open_critical_findings = await _count(
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == organization_id,
            SecurityFinding.severity == "critical",
            SecurityFinding.status.notin_(["resolved", "false_positive", "risk_accepted"]),
        )
    )
    open_high_findings = await _count(
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == organization_id,
            SecurityFinding.severity == "high",
            SecurityFinding.status.notin_(["resolved", "false_positive", "risk_accepted"]),
        )
    )
    open_incidents = await _count(
        select(SecurityIncident.id).where(
            SecurityIncident.organization_id == organization_id,
            SecurityIncident.status != "closed",
        )
    )
    deductions = (
        critical_alerts * 10
        + open_critical_findings * 8
        + open_high_findings * 4
        + open_incidents * 6
    )
    return max(0, 100 - deductions)


async def get_security_overview(
    db: AsyncSession, *, organization_id: uuid.UUID
) -> SecurityOverviewOut:
    """The exact aggregate `GET /security/overview` returns (spec §13) —
    extracted here so the Reporting module's Security Posture Report
    (spec §65) reuses the same live queries rather than a second,
    independently-drifting copy of this dashboard."""

    async def _count(stmt: Any) -> int:
        result = await db.execute(select(func.count()).select_from(stmt.subquery()))
        return int(result.scalar_one())

    critical_alerts = await _count(
        select(SecurityAlert.id).where(
            SecurityAlert.organization_id == organization_id,
            SecurityAlert.severity == "critical",
            SecurityAlert.status.notin_(["resolved", "false_positive"]),
        )
    )
    high_risks = await _count(
        select(Risk.id).where(
            Risk.organization_id == organization_id,
            Risk.impact == "high",
            Risk.status == "open",
        )
    )
    assets_monitored = await _count(
        select(SecurityAsset.id).where(SecurityAsset.organization_id == organization_id)
    )
    vulnerabilities_open = await _count(
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == organization_id,
            SecurityFinding.category == "vulnerability",
            SecurityFinding.status == "open",
        )
    )
    identity_issues_open = await _count(
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == organization_id,
            SecurityFinding.category == "identity",
            SecurityFinding.status == "open",
        )
    )
    cloud_misconfigurations_open = await _count(
        select(SecurityFinding.id).where(
            SecurityFinding.organization_id == organization_id,
            SecurityFinding.category == "cloud_misconfiguration",
            SecurityFinding.status == "open",
        )
    )
    open_incidents = await _count(
        select(SecurityIncident.id).where(
            SecurityIncident.organization_id == organization_id,
            SecurityIncident.status != "closed",
        )
    )
    total_incidents = await _count(
        select(SecurityIncident.id).where(SecurityIncident.organization_id == organization_id)
    )
    incidents_with_evidence = await _count(
        select(SecurityIncident.id)
        .join(Evidence, Evidence.incident_id == SecurityIncident.id)
        .where(SecurityIncident.organization_id == organization_id)
        .distinct()
    )
    evidence_coverage_percent = (
        round(100 * incidents_with_evidence / total_incidents, 1) if total_incidents else 0.0
    )
    security_score = await compute_security_score(db, organization_id=organization_id)

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
