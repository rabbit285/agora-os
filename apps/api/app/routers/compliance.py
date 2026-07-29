from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.models import (
    Control,
    ControlAssessment,
    ControlMapping,
    Evidence,
    Framework,
    Policy,
    Requirement,
    Risk,
)
from app.compliance.schemas import (
    ControlAssessmentCreate,
    ControlAssessmentOut,
    ControlCreate,
    ControlDetailOut,
    ControlOut,
    EvidenceCreate,
    EvidenceOut,
    FrameworkOut,
    PolicyCreate,
    PolicyOut,
    RequirementOut,
    RiskCreate,
    RiskOut,
    RiskUpdate,
)
from app.compliance.service import record_assessment
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
