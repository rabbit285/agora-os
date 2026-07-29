from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import (
    DPIA,
    DSAR,
    AIAssessment,
    AIIncident,
    AISystem,
    Control,
    ControlAssessment,
    ControlMapping,
    Evidence,
    Framework,
    Policy,
    ProcessingActivity,
    Requirement,
    Risk,
)
from app.compliance.schemas import (
    AIAssessmentCreate,
    AIAssessmentOut,
    AIIncidentCreate,
    AIIncidentOut,
    AIIncidentStatusUpdate,
    AISystemCreate,
    AISystemDetailOut,
    AISystemOut,
    AISystemStatusUpdate,
    ControlAssessmentCreate,
    ControlAssessmentOut,
    ControlCreate,
    ControlDetailOut,
    ControlOut,
    DPIACreate,
    DPIAOut,
    DPIAStatusUpdate,
    DSARCreate,
    DSAROut,
    DSARStatusUpdate,
    EvidenceCreate,
    EvidenceOut,
    FrameworkOut,
    PolicyCreate,
    PolicyOut,
    ProcessingActivityCreate,
    ProcessingActivityOut,
    RequirementOut,
    RiskCreate,
    RiskOut,
    RiskUpdate,
)
from app.compliance.service import (
    create_ai_incident,
    create_dpia,
    create_dsar,
    decide_ai_system_status,
    decide_dpia_status,
    record_assessment,
    register_ai_system,
    update_ai_incident_status,
    update_dsar_status,
)
from app.core.models import File
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


@router.get("/frameworks", response_model=list[FrameworkOut])
async def list_frameworks(
    db: AsyncSession = Depends(get_db), _: OrgContext = Depends(get_org_context)
) -> list[Framework]:
    result = await db.execute(select(Framework).order_by(Framework.name))
    return list(result.scalars().all())


@router.get("/frameworks/{framework_id}/requirements", response_model=list[RequirementOut])
async def list_requirements(
    framework_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: OrgContext = Depends(get_org_context),
) -> list[Requirement]:
    framework = await db.get(Framework, framework_id)
    if framework is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
    result = await db.execute(
        select(Requirement)
        .where(Requirement.framework_id == framework_id)
        .order_by(Requirement.reference_code)
    )
    return list(result.scalars().all())


@router.get("/controls", response_model=list[ControlOut])
async def list_controls(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Control]:
    result = await db.execute(
        select(Control)
        .where(Control.organization_id == context.organization_id)
        .order_by(Control.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/controls", response_model=ControlOut, status_code=status.HTTP_201_CREATED)
async def create_control(
    payload: ControlCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.controls.manage")),
) -> Control:
    control = Control(
        organization_id=context.organization_id,
        title=payload.title,
        description=payload.description,
        owner_id=payload.owner_id,
    )
    db.add(control)
    await db.flush()

    for requirement_id in payload.requirement_ids:
        requirement = await db.get(Requirement, requirement_id)
        if requirement is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Requirement {requirement_id} not found",
            )
        db.add(ControlMapping(control_id=control.id, requirement_id=requirement_id))

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.control.created",
        object_type="control",
        object_id=str(control.id),
        after_state={"title": control.title},
    )
    await db.commit()
    await db.refresh(control)
    return control


async def _get_org_control(
    db: AsyncSession, control_id: uuid.UUID, organization_id: uuid.UUID
) -> Control:
    control = await db.get(Control, control_id)
    if control is None or control.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
    return control


@router.get("/controls/{control_id}", response_model=ControlDetailOut)
async def get_control(
    control_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> ControlDetailOut:
    control = await _get_org_control(db, control_id, context.organization_id)

    requirements_result = await db.execute(
        select(Requirement)
        .join(ControlMapping, ControlMapping.requirement_id == Requirement.id)
        .where(ControlMapping.control_id == control.id)
    )
    assessments_result = await db.execute(
        select(ControlAssessment)
        .where(ControlAssessment.control_id == control.id)
        .order_by(ControlAssessment.created_at.desc())
    )

    return ControlDetailOut(
        **ControlOut.model_validate(control).model_dump(),
        requirements=[
            RequirementOut.model_validate(r) for r in requirements_result.scalars().all()
        ],
        assessments=[
            ControlAssessmentOut.model_validate(a) for a in assessments_result.scalars().all()
        ],
    )


@router.post(
    "/controls/{control_id}/assessments",
    response_model=ControlAssessmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_assessment(
    control_id: uuid.UUID,
    payload: ControlAssessmentCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.controls.manage")),
) -> ControlAssessment:
    control = await _get_org_control(db, control_id, context.organization_id)
    assessment = await record_assessment(
        db,
        organization_id=context.organization_id,
        control=control,
        status=payload.status,
        notes=payload.notes,
        assessed_by=context.user.id,
    )
    await db.commit()
    await db.refresh(assessment)
    return assessment


@router.get("/evidence", response_model=list[EvidenceOut])
async def list_evidence(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Evidence]:
    result = await db.execute(
        select(Evidence)
        .where(Evidence.organization_id == context.organization_id)
        .order_by(Evidence.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/evidence", response_model=EvidenceOut, status_code=status.HTTP_201_CREATED)
async def create_evidence(
    payload: EvidenceCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> Evidence:
    file_record = await db.get(File, payload.file_id)
    if file_record is None or file_record.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if payload.control_id is not None:
        await _get_org_control(db, payload.control_id, context.organization_id)

    evidence = Evidence(
        organization_id=context.organization_id,
        control_id=payload.control_id,
        file_id=payload.file_id,
        title=payload.title,
        valid_until=payload.valid_until,
        created_by=context.user.id,
    )
    db.add(evidence)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.evidence.created",
        object_type="evidence",
        object_id=str(evidence.id),
        after_state={"title": evidence.title},
    )
    await db.commit()
    await db.refresh(evidence)
    return evidence


@router.get("/risks", response_model=list[RiskOut])
async def list_risks(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Risk]:
    result = await db.execute(
        select(Risk)
        .where(Risk.organization_id == context.organization_id)
        .order_by(Risk.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/risks", response_model=RiskOut, status_code=status.HTTP_201_CREATED)
async def create_risk(
    payload: RiskCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.risks.manage")),
) -> Risk:
    if payload.control_id is not None:
        await _get_org_control(db, payload.control_id, context.organization_id)

    risk = Risk(organization_id=context.organization_id, **payload.model_dump())
    db.add(risk)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.risk.created",
        object_type="risk",
        object_id=str(risk.id),
        after_state={"title": risk.title, "likelihood": risk.likelihood, "impact": risk.impact},
    )
    await db.commit()
    await db.refresh(risk)
    return risk


@router.patch("/risks/{risk_id}", response_model=RiskOut)
async def update_risk(
    risk_id: uuid.UUID,
    payload: RiskUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.risks.manage")),
) -> Risk:
    risk = await db.get(Risk, risk_id)
    if risk is None or risk.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
    before_status = risk.status
    risk.status = payload.status
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.risk.status_changed",
        object_type="risk",
        object_id=str(risk.id),
        before_state={"status": before_status},
        after_state={"status": risk.status},
    )
    await db.commit()
    await db.refresh(risk)
    return risk


@router.get("/policies", response_model=list[PolicyOut])
async def list_policies(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Policy]:
    result = await db.execute(
        select(Policy)
        .where(Policy.organization_id == context.organization_id)
        .order_by(Policy.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/policies", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: PolicyCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.policies.manage")),
) -> Policy:
    if payload.file_id is not None:
        file_record = await db.get(File, payload.file_id)
        if file_record is None or file_record.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    policy = Policy(organization_id=context.organization_id, **payload.model_dump())
    db.add(policy)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.policy.created",
        object_type="policy",
        object_id=str(policy.id),
        after_state={"title": policy.title},
    )
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("/ai-systems", response_model=list[AISystemOut])
async def list_ai_systems(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[AISystem]:
    result = await db.execute(
        select(AISystem)
        .where(AISystem.organization_id == context.organization_id)
        .order_by(AISystem.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/ai-systems", response_model=AISystemOut, status_code=status.HTTP_201_CREATED)
async def create_ai_system(
    payload: AISystemCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.ai_systems.manage")),
) -> AISystem:
    system = await register_ai_system(
        db,
        organization_id=context.organization_id,
        name=payload.name,
        vendor=payload.vendor,
        purpose=payload.purpose,
        risk_classification=payload.risk_classification,
        owner_id=payload.owner_id,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(system)
    return system


async def _get_org_ai_system(
    db: AsyncSession, ai_system_id: uuid.UUID, organization_id: uuid.UUID
) -> AISystem:
    system = await db.get(AISystem, ai_system_id)
    if system is None or system.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
    return system


@router.get("/ai-systems/{ai_system_id}", response_model=AISystemDetailOut)
async def get_ai_system(
    ai_system_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> AISystemDetailOut:
    system = await _get_org_ai_system(db, ai_system_id, context.organization_id)
    assessments_result = await db.execute(
        select(AIAssessment)
        .where(AIAssessment.ai_system_id == system.id)
        .order_by(AIAssessment.created_at.desc())
    )
    return AISystemDetailOut(
        **AISystemOut.model_validate(system).model_dump(),
        assessments=[AIAssessmentOut.model_validate(a) for a in assessments_result.scalars().all()],
    )


@router.patch("/ai-systems/{ai_system_id}/status", response_model=AISystemOut)
async def update_ai_system_status(
    ai_system_id: uuid.UUID,
    payload: AISystemStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.ai_systems.manage")),
) -> AISystem:
    system = await _get_org_ai_system(db, ai_system_id, context.organization_id)
    try:
        system = await decide_ai_system_status(
            db, system=system, new_status=payload.status, actor_user_id=context.user.id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(system)
    return system


@router.post(
    "/ai-systems/{ai_system_id}/assessments",
    response_model=AIAssessmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_ai_assessment(
    ai_system_id: uuid.UUID,
    payload: AIAssessmentCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.ai_systems.manage")),
) -> AIAssessment:
    system = await _get_org_ai_system(db, ai_system_id, context.organization_id)
    assessment = AIAssessment(
        organization_id=context.organization_id,
        ai_system_id=system.id,
        status=payload.status,
        notes=payload.notes,
        assessed_by=context.user.id,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return assessment


@router.get("/processing-activities", response_model=list[ProcessingActivityOut])
async def list_processing_activities(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[ProcessingActivity]:
    result = await db.execute(
        select(ProcessingActivity)
        .where(ProcessingActivity.organization_id == context.organization_id)
        .order_by(ProcessingActivity.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/processing-activities",
    response_model=ProcessingActivityOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_processing_activity(
    payload: ProcessingActivityCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> ProcessingActivity:
    activity = ProcessingActivity(organization_id=context.organization_id, **payload.model_dump())
    db.add(activity)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.processing_activity.created",
        object_type="processing_activity",
        object_id=str(activity.id),
        after_state={"name": activity.name, "legal_basis": activity.legal_basis},
    )
    await db.commit()
    await db.refresh(activity)
    return activity


async def _get_org_processing_activity(
    db: AsyncSession, activity_id: uuid.UUID, organization_id: uuid.UUID
) -> ProcessingActivity:
    activity = await db.get(ProcessingActivity, activity_id)
    if activity is None or activity.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Processing activity not found"
        )
    return activity


@router.get("/dpias", response_model=list[DPIAOut])
async def list_dpias(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[DPIA]:
    result = await db.execute(
        select(DPIA)
        .where(DPIA.organization_id == context.organization_id)
        .order_by(DPIA.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/dpias", response_model=DPIAOut, status_code=status.HTTP_201_CREATED)
async def create_dpia_endpoint(
    payload: DPIACreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DPIA:
    if payload.processing_activity_id is not None:
        await _get_org_processing_activity(
            db, payload.processing_activity_id, context.organization_id
        )
    dpia = await create_dpia(
        db,
        organization_id=context.organization_id,
        title=payload.title,
        processing_activity_id=payload.processing_activity_id,
        risk_level=payload.risk_level,
        owner_id=payload.owner_id,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(dpia)
    return dpia


async def _get_org_dpia(db: AsyncSession, dpia_id: uuid.UUID, organization_id: uuid.UUID) -> DPIA:
    dpia = await db.get(DPIA, dpia_id)
    if dpia is None or dpia.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DPIA not found")
    return dpia


@router.get("/dpias/{dpia_id}", response_model=DPIAOut)
async def get_dpia(
    dpia_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DPIA:
    return await _get_org_dpia(db, dpia_id, context.organization_id)


@router.patch("/dpias/{dpia_id}/status", response_model=DPIAOut)
async def update_dpia_status(
    dpia_id: uuid.UUID,
    payload: DPIAStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DPIA:
    dpia = await _get_org_dpia(db, dpia_id, context.organization_id)
    if payload.findings is not None:
        dpia.findings = payload.findings
    try:
        dpia = await decide_dpia_status(
            db, dpia=dpia, new_status=payload.status, actor_user_id=context.user.id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(dpia)
    return dpia


@router.get("/dsars", response_model=list[DSAROut])
async def list_dsars(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[DSAR]:
    result = await db.execute(
        select(DSAR)
        .where(DSAR.organization_id == context.organization_id)
        .order_by(DSAR.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/dsars", response_model=DSAROut, status_code=status.HTTP_201_CREATED)
async def create_dsar_endpoint(
    payload: DSARCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DSAR:
    dsar = await create_dsar(
        db,
        organization_id=context.organization_id,
        requester_name=payload.requester_name,
        requester_email=payload.requester_email,
        request_type=payload.request_type,
        assigned_to=payload.assigned_to,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(dsar)
    return dsar


async def _get_org_dsar(db: AsyncSession, dsar_id: uuid.UUID, organization_id: uuid.UUID) -> DSAR:
    dsar = await db.get(DSAR, dsar_id)
    if dsar is None or dsar.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DSAR not found")
    return dsar


@router.get("/dsars/{dsar_id}", response_model=DSAROut)
async def get_dsar(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DSAR:
    return await _get_org_dsar(db, dsar_id, context.organization_id)


@router.patch("/dsars/{dsar_id}/status", response_model=DSAROut)
async def update_dsar_status_endpoint(
    dsar_id: uuid.UUID,
    payload: DSARStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DSAR:
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    dsar = await update_dsar_status(
        db,
        dsar=dsar,
        new_status=payload.status,
        notes=payload.notes,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(dsar)
    return dsar


@router.get("/ai-incidents", response_model=list[AIIncidentOut])
async def list_ai_incidents(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[AIIncident]:
    result = await db.execute(
        select(AIIncident)
        .where(AIIncident.organization_id == context.organization_id)
        .order_by(AIIncident.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/ai-incidents", response_model=AIIncidentOut, status_code=status.HTTP_201_CREATED)
async def create_ai_incident_endpoint(
    payload: AIIncidentCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.ai_systems.manage")),
) -> AIIncident:
    ai_system = await _get_org_ai_system(db, payload.ai_system_id, context.organization_id)
    incident = await create_ai_incident(
        db,
        organization_id=context.organization_id,
        ai_system=ai_system,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        owner_id=payload.owner_id,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(incident)
    return incident


async def _get_org_ai_incident(
    db: AsyncSession, incident_id: uuid.UUID, organization_id: uuid.UUID
) -> AIIncident:
    incident = await db.get(AIIncident, incident_id)
    if incident is None or incident.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI incident not found")
    return incident


@router.get("/ai-incidents/{incident_id}", response_model=AIIncidentOut)
async def get_ai_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> AIIncident:
    return await _get_org_ai_incident(db, incident_id, context.organization_id)


@router.patch("/ai-incidents/{incident_id}/status", response_model=AIIncidentOut)
async def update_ai_incident_status_endpoint(
    incident_id: uuid.UUID,
    payload: AIIncidentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.ai_systems.manage")),
) -> AIIncident:
    incident = await _get_org_ai_incident(db, incident_id, context.organization_id)
    incident = await update_ai_incident_status(
        db, incident=incident, new_status=payload.status, actor_user_id=context.user.id
    )
    await db.commit()
    await db.refresh(incident)
    return incident
