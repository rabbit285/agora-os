from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.ai_governance import (
    indicator_catalog,
    record_eu_ai_act_assessment,
    record_privacy_assessment,
)
from app.compliance.assessment import (
    create_task_from_gap,
    generate_remediation,
    run_framework_assessment,
    set_framework_activation,
)
from app.compliance.dpia_screening import (
    EDPB_CRITERIA,
    MANDATORY_CRITERIA,
    recalculate_residual_risk,
    record_dpia_screening,
)
from app.compliance.dsar import (
    DsarVerificationRequired,
    generate_export,
    run_data_discovery,
    verify_identity,
)
from app.compliance.models import (
    DPIA,
    DSAR,
    AIAssessment,
    AIIncident,
    AISystem,
    Audit,
    AuditFinding,
    ComplianceGap,
    Control,
    ControlAssessment,
    ControlMapping,
    DataTransfer,
    Evidence,
    Framework,
    FrameworkActivation,
    Policy,
    ProcessingActivity,
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    Requirement,
    Risk,
    SecurityReview,
    Vendor,
    VendorAssessment,
)
from app.compliance.schemas import (
    AIAssessmentCreate,
    AIAssessmentDetailOut,
    AIAssessmentOut,
    AIIncidentCreate,
    AIIncidentOut,
    AIIncidentStatusUpdate,
    AISystemCreate,
    AISystemDetailOut,
    AISystemOut,
    AISystemProfileUpdate,
    AISystemStatusUpdate,
    AuditCreate,
    AuditDetailOut,
    AuditFindingCreate,
    AuditFindingOut,
    AuditFindingStatusUpdate,
    AuditOut,
    AuditStatusUpdate,
    ComplianceGapOut,
    ControlAssessmentCreate,
    ControlAssessmentOut,
    ControlCreate,
    ControlDetailOut,
    ControlOut,
    CreateGapTaskRequest,
    DataTransferCreate,
    DataTransferOut,
    DataTransferStatusUpdate,
    DPIACreate,
    DPIAOut,
    DpiaScreeningRequest,
    DpiaScreeningResultOut,
    DPIASectionsUpdate,
    DPIAStatusUpdate,
    DSARCreate,
    DsarDiscoveryOut,
    DSAROut,
    DSARStatusUpdate,
    DsarVerificationRequest,
    EuAiActScreeningRequest,
    EvidenceCreate,
    EvidenceOut,
    FrameworkActivationOut,
    FrameworkAssessmentResultOut,
    FrameworkCreate,
    FrameworkDashboardControlOut,
    FrameworkDashboardOut,
    FrameworkDashboardRequirementOut,
    FrameworkOut,
    PolicyCreate,
    PolicyOut,
    PolicyStatusUpdate,
    PrivacyAssessmentRequest,
    ProcessingActivityCreate,
    ProcessingActivityOut,
    QuestionnaireAnswerOut,
    QuestionnaireAnswerUpdate,
    QuestionnaireCreate,
    QuestionnaireDetailOut,
    QuestionnaireOut,
    QuestionnaireQuestionCreate,
    QuestionnaireQuestionDetailOut,
    QuestionnaireQuestionOut,
    QuestionnaireStatusUpdate,
    RequirementEvaluationOut,
    RequirementOut,
    RiskCreate,
    RiskOut,
    RiskResidualUpdate,
    RiskUpdate,
    SecurityReviewCreate,
    SecurityReviewDetailOut,
    SecurityReviewOut,
    SecurityReviewStatusUpdate,
    SecurityReviewSyncResult,
    SetFrameworkActivationRequest,
    VendorAssessmentCreate,
    VendorAssessmentOut,
    VendorCreate,
    VendorDetailOut,
    VendorDpaStatusUpdate,
    VendorOut,
    VendorStatusUpdate,
)
from app.compliance.service import (
    add_questionnaire_question,
    clear_security_review,
    create_ai_incident,
    create_data_transfer,
    create_dpia,
    create_dsar,
    decide_ai_system_status,
    decide_dpia_status,
    list_security_review_gaps,
    record_assessment,
    record_audit_finding,
    record_vendor_assessment,
    register_ai_system,
    start_security_review,
    suggest_questionnaire_answer,
    sync_security_review,
    update_ai_incident_status,
    update_audit_finding_status,
    update_data_transfer_status,
    update_dsar_status,
    update_questionnaire_answer,
    update_security_review_status,
)
from app.core.models import Approval, File, Task
from app.core.pagination import Pagination, paginate, pagination_params
from app.core.schemas import TaskOut
from app.db.base import utcnow
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.sales.models import Opportunity

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


@router.get("/frameworks", response_model=list[FrameworkOut])
async def list_frameworks(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Framework]:
    result = await db.execute(
        select(Framework)
        .where(
            (Framework.organization_id.is_(None))
            | (Framework.organization_id == context.organization_id)
        )
        .order_by(Framework.name)
    )
    return list(result.scalars().all())


@router.post("/frameworks", response_model=FrameworkOut, status_code=status.HTTP_201_CREATED)
async def create_framework(
    payload: FrameworkCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.frameworks.manage")),
) -> Framework:
    """spec §12's own named "Custom Frameworks" item — private to this
    organization, never visible to any other tenant."""
    framework = Framework(
        organization_id=context.organization_id,
        key=f"custom-{uuid.uuid4().hex[:12]}",
        name=payload.name,
        description=payload.description,
    )
    db.add(framework)
    await db.flush()

    for requirement in payload.requirements:
        db.add(
            Requirement(
                framework_id=framework.id,
                reference_code=requirement.reference_code,
                title=requirement.title,
                description=requirement.description,
            )
        )

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.framework.created",
        object_type="framework",
        object_id=str(framework.id),
        after_state={"name": framework.name},
    )
    await db.commit()
    await db.refresh(framework)
    return framework


async def _get_visible_framework(
    db: AsyncSession, framework_id: uuid.UUID, organization_id: uuid.UUID
) -> Framework:
    """A framework is visible if it's global catalog data (organization_id
    is null) or a custom framework belonging to this exact org — a custom
    framework from another org must 404, same as any other tenant-scoped
    row, even though `Framework` itself predates per-tenant scoping."""
    framework = await db.get(Framework, framework_id)
    if framework is None or (
        framework.organization_id is not None and framework.organization_id != organization_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
    return framework


@router.get("/frameworks/{framework_id}/requirements", response_model=list[RequirementOut])
async def list_requirements(
    framework_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[Requirement]:
    await _get_visible_framework(db, framework_id, context.organization_id)
    result = await db.execute(
        select(Requirement)
        .where(Requirement.framework_id == framework_id)
        .order_by(Requirement.reference_code)
    )
    return list(result.scalars().all())


@router.get("/frameworks/activations", response_model=list[FrameworkActivationOut])
async def list_framework_activations(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[FrameworkActivation]:
    """Which frameworks this organization has adopted.

    Declared before `/frameworks/{framework_id}/...` so the literal path
    is matched first — FastAPI resolves routes in definition order, and a
    UUID path parameter would otherwise swallow "activations".
    """
    result = await db.execute(
        select(FrameworkActivation).where(
            FrameworkActivation.organization_id == context.organization_id
        )
    )
    return list(result.scalars().all())


@router.put("/frameworks/{framework_id}/activation", response_model=FrameworkActivationOut)
async def set_activation(
    framework_id: uuid.UUID,
    payload: SetFrameworkActivationRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.frameworks.manage")),
) -> FrameworkActivation:
    """Adopt a framework, or stand it down.

    Deactivating keeps every control, evidence item, assessment and gap
    built against the framework — switching GDPR off and on again must
    not discard the organization's own work.
    """
    framework = await _get_visible_framework(db, framework_id, context.organization_id)
    activation = await set_framework_activation(
        db,
        organization_id=context.organization_id,
        framework=framework,
        active=payload.active,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(activation)
    return activation


@router.post("/frameworks/{framework_id}/assess", response_model=FrameworkAssessmentResultOut)
async def assess_framework(
    framework_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.controls.manage")),
) -> FrameworkAssessmentResultOut:
    """Run (or re-run) the assessment for a whole framework.

    Deterministic: every status is computed from mapped controls,
    attached evidence and recorded assessments — see
    `app.compliance.assessment` for why this must not be a model call.
    Re-running reconciles gaps rather than duplicating them, which is what
    makes remediate-then-reassess a real loop.
    """
    framework = await _get_visible_framework(db, framework_id, context.organization_id)
    evaluations = await run_framework_assessment(
        db,
        organization_id=context.organization_id,
        framework=framework,
        actor_user_id=context.user.id,
    )
    await db.commit()

    gaps = {
        gap.requirement_id: gap
        for gap in (
            await db.execute(
                select(ComplianceGap).where(
                    ComplianceGap.organization_id == context.organization_id,
                    ComplianceGap.framework_id == framework_id,
                    ComplianceGap.status != "resolved",
                )
            )
        )
        .scalars()
        .all()
    }

    rows = [
        RequirementEvaluationOut(
            requirement_id=e.requirement.id,
            reference_code=e.requirement.reference_code,
            title=e.requirement.title,
            status=e.status,
            control_ids=e.control_ids,
            evidence_count=e.evidence_count,
            latest_assessment_status=e.latest_assessment_status,
            summary=e.summary,
            gap_id=gaps[e.requirement.id].id if e.requirement.id in gaps else None,
        )
        for e in evaluations
    ]
    satisfied = sum(1 for e in evaluations if e.status == "satisfied")
    # Distinct from the dashboard's control coverage: this counts
    # requirements actually backed by evidence, which is the number that
    # must not move when an unrelated document is uploaded.
    with_evidence = sum(1 for e in evaluations if e.evidence_count > 0)
    return FrameworkAssessmentResultOut(
        framework_id=framework_id,
        assessed_at=datetime.now(UTC),
        requirements=rows,
        satisfied_count=satisfied,
        gap_count=len(gaps),
        evidence_coverage_percent=(
            round(100 * with_evidence / len(evaluations), 1) if evaluations else 0.0
        ),
    )


@router.get("/gaps", response_model=list[ComplianceGapOut])
async def list_gaps(
    framework_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[ComplianceGap]:
    stmt = select(ComplianceGap).where(
        ComplianceGap.organization_id == context.organization_id
    )
    if framework_id is not None:
        stmt = stmt.where(ComplianceGap.framework_id == framework_id)
    if status_filter is not None:
        stmt = stmt.where(ComplianceGap.status == status_filter)
    result = await db.execute(stmt.order_by(ComplianceGap.created_at.desc()))
    return list(result.scalars().all())


async def _get_gap(db: AsyncSession, gap_id: uuid.UUID, organization_id: uuid.UUID) -> ComplianceGap:
    gap = await db.get(ComplianceGap, gap_id)
    if gap is None or gap.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gap not found")
    return gap


@router.get("/gaps/{gap_id}", response_model=ComplianceGapOut)
async def get_gap(
    gap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> ComplianceGap:
    return await _get_gap(db, gap_id, context.organization_id)


@router.post("/gaps/{gap_id}/remediation", response_model=ComplianceGapOut)
async def generate_gap_remediation(
    gap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.controls.manage")),
) -> ComplianceGap:
    """Write a concrete recommendation onto the gap, drawn from the
    regulation's own text rather than generated."""
    gap = await _get_gap(db, gap_id, context.organization_id)
    await generate_remediation(
        db, organization_id=context.organization_id, gap=gap, actor_user_id=context.user.id
    )
    await db.commit()
    await db.refresh(gap)
    return gap


@router.post("/gaps/{gap_id}/task", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_gap_task(
    gap_id: uuid.UUID,
    payload: CreateGapTaskRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.controls.manage")),
) -> Task:
    """Raise a remediation Task pointing back at this gap, so the Tasks
    module can answer "why does this exist?" without re-reading the
    title."""
    gap = await _get_gap(db, gap_id, context.organization_id)
    task = await create_task_from_gap(
        db,
        organization_id=context.organization_id,
        gap=gap,
        actor_user_id=context.user.id,
        title=payload.title,
        assignee_id=payload.assignee_id,
        priority=payload.priority,
        due_in_days=payload.due_in_days,
    )
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/frameworks/{framework_id}/dashboard", response_model=FrameworkDashboardOut)
async def get_framework_dashboard(
    framework_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> FrameworkDashboardOut:
    """Framework-specific compliance dashboard (spec §67 "Compliance" screen
    group): for each of this framework's requirements, which of this org's
    own Controls map to it and their current assessment status — makes gaps
    (a requirement with zero mapped controls) and unfinished work (mapped
    but not yet `implemented`) visible per-framework, not just as one flat
    control list."""
    framework = await _get_visible_framework(db, framework_id, context.organization_id)

    requirements = list(
        (
            await db.execute(
                select(Requirement)
                .where(Requirement.framework_id == framework_id)
                .order_by(Requirement.reference_code)
            )
        )
        .scalars()
        .all()
    )

    requirement_rows: list[FrameworkDashboardRequirementOut] = []
    covered_count = 0
    for requirement in requirements:
        controls = list(
            (
                await db.execute(
                    select(Control)
                    .join(ControlMapping, ControlMapping.control_id == Control.id)
                    .where(
                        ControlMapping.requirement_id == requirement.id,
                        Control.organization_id == context.organization_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        if any(c.status == "implemented" for c in controls):
            covered_count += 1
        requirement_rows.append(
            FrameworkDashboardRequirementOut(
                id=requirement.id,
                reference_code=requirement.reference_code,
                title=requirement.title,
                controls=[
                    FrameworkDashboardControlOut(id=c.id, title=c.title, status=c.status)
                    for c in controls
                ],
            )
        )

    coverage_percent = round(100 * covered_count / len(requirements), 1) if requirements else 0.0
    return FrameworkDashboardOut(
        framework=FrameworkOut.model_validate(framework),
        requirements=requirement_rows,
        coverage_percent=coverage_percent,
    )


@router.get("/controls", response_model=list[ControlOut])
async def list_controls(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Control]:
    stmt = (
        select(Control)
        .where(Control.organization_id == context.organization_id)
        .order_by(Control.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


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
    evidence_result = await db.execute(
        select(Evidence)
        .where(
            Evidence.control_id == control.id,
            Evidence.organization_id == context.organization_id,
        )
        .order_by(Evidence.created_at.desc())
    )

    return ControlDetailOut(
        **ControlOut.model_validate(control).model_dump(),
        requirements=[
            RequirementOut.model_validate(r) for r in requirements_result.scalars().all()
        ],
        assessments=[
            ControlAssessmentOut.model_validate(a) for a in assessments_result.scalars().all()
        ],
        evidence=[EvidenceOut.model_validate(e) for e in evidence_result.scalars().all()],
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

    if payload.status == "fail":
        from app.automation.triggers import dispatch_event

        await dispatch_event(
            db,
            organization_id=context.organization_id,
            trigger_type="control_failed",
            payload={"control_id": str(control.id), "assessment_id": str(assessment.id)},
            actor_user_id=context.user.id,
        )

    await db.commit()
    await db.refresh(assessment)
    return assessment


@router.get("/evidence", response_model=list[EvidenceOut])
async def list_evidence(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Evidence]:
    stmt = (
        select(Evidence)
        .where(Evidence.organization_id == context.organization_id)
        .order_by(Evidence.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


async def _get_org_evidence(
    db: AsyncSession, evidence_id: uuid.UUID, organization_id: uuid.UUID
) -> Evidence:
    evidence = await db.get(Evidence, evidence_id)
    if evidence is None or evidence.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
    return evidence


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
    if payload.vendor_id is not None:
        await _get_org_vendor(db, payload.vendor_id, context.organization_id)
    if payload.incident_id is not None:
        from app.secops.models import SecurityIncident

        incident = await db.get(SecurityIncident, payload.incident_id)
        if incident is None or incident.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")

    evidence = Evidence(
        organization_id=context.organization_id,
        control_id=payload.control_id,
        vendor_id=payload.vendor_id,
        incident_id=payload.incident_id,
        file_id=payload.file_id,
        title=payload.title,
        valid_until=payload.valid_until,
        created_by=context.user.id,
    )
    db.add(evidence)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.evidence.created",
        object_type="evidence",
        object_id=str(evidence.id),
        # What it was attached to, not just that it exists — an auditor
        # tracing a requirement needs the mapping, and "evidence created"
        # alone does not say which control it now supports.
        after_state={
            "title": evidence.title,
            "control_id": str(evidence.control_id) if evidence.control_id else None,
            "vendor_id": str(evidence.vendor_id) if evidence.vendor_id else None,
        },
    )
    await db.commit()
    await db.refresh(evidence)
    return evidence


@router.get("/risks", response_model=list[RiskOut])
async def list_risks(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Risk]:
    stmt = (
        select(Risk)
        .where(Risk.organization_id == context.organization_id)
        .order_by(Risk.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


@router.post("/risks", response_model=RiskOut, status_code=status.HTTP_201_CREATED)
async def create_risk(
    payload: RiskCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.risks.manage")),
) -> Risk:
    if payload.control_id is not None:
        await _get_org_control(db, payload.control_id, context.organization_id)
    # Validated here rather than left to the foreign key. An unknown id
    # reaching the database surfaces as an opaque 500, which tells the
    # caller nothing and looks like a server fault rather than their typo.
    # The org check also stops a risk being attached to another tenant's
    # AI system or DPIA by guessing an id.
    if payload.ai_system_id is not None:
        await _get_org_ai_system(db, payload.ai_system_id, context.organization_id)
    if payload.dpia_id is not None:
        dpia = await db.get(DPIA, payload.dpia_id)
        if dpia is None or dpia.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DPIA not found")

    risk = Risk(organization_id=context.organization_id, **payload.model_dump())
    db.add(risk)
    await db.flush()
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
    await db.flush()
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


async def _get_org_policy(
    db: AsyncSession, policy_id: uuid.UUID, organization_id: uuid.UUID
) -> Policy:
    policy = await db.get(Policy, policy_id)
    if policy is None or policy.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return policy


@router.patch("/policies/{policy_id}/status", response_model=PolicyOut)
async def update_policy_status(
    policy_id: uuid.UUID,
    payload: PolicyStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.policies.manage")),
) -> Policy:
    policy = await _get_org_policy(db, policy_id, context.organization_id)
    before_status = policy.status
    policy.status = payload.status
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.policy.status_changed",
        object_type="policy",
        object_id=str(policy.id),
        before_state={"status": before_status},
        after_state={"status": policy.status},
    )
    if payload.status == "published" and before_status != "published":
        from app.memory.service import record_policy_published_memory

        await record_policy_published_memory(
            db,
            organization_id=context.organization_id,
            policy_id=policy.id,
            policy_title=policy.title,
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

    from app.automation.triggers import dispatch_event

    await dispatch_event(
        db,
        organization_id=context.organization_id,
        trigger_type="ai_system_registered",
        payload={"ai_system_id": str(system.id), "risk_classification": system.risk_classification},
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


@router.get("/ai-systems/indicator-catalog")
async def get_indicator_catalog(
    context: OrgContext = Depends(get_org_context),
) -> dict[str, object]:
    """The EU AI Act indicator list and privacy questions.

    Served rather than duplicated in the form component, so the questions
    and the rules that read them cannot drift apart. Declared before the
    `{ai_system_id}` routes so the literal path wins.
    """
    return indicator_catalog()


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


@router.patch("/ai-systems/{ai_system_id}/profile", response_model=AISystemOut)
async def update_ai_system_profile(
    ai_system_id: uuid.UUID,
    payload: AISystemProfileUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.ai_systems.manage")),
) -> AISystem:
    """Fill in the inventory detail — users, affected people, data
    categories, and the three accountable owners."""
    system = await _get_org_ai_system(db, ai_system_id, context.organization_id)
    before = {
        "internal_users": list(system.internal_users or []),
        "affected_users": list(system.affected_users or []),
    }
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(system, field, value)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.ai_system.profile_updated",
        object_type="ai_system",
        object_id=str(system.id),
        before_state=before,
        after_state={
            "internal_users": list(system.internal_users or []),
            "affected_users": list(system.affected_users or []),
        },
    )
    await db.commit()
    await db.refresh(system)
    return system


@router.post(
    "/ai-systems/{ai_system_id}/eu-ai-act-screening",
    response_model=AIAssessmentDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def screen_ai_system(
    ai_system_id: uuid.UUID,
    payload: EuAiActScreeningRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.ai_systems.manage")),
) -> AIAssessment:
    """Screen a system against the EU AI Act's own indicators.

    The tier always arrives with the facts it was drawn from, what remains
    uncertain, and whether a human must confirm — see
    `app.compliance.ai_governance` for why this must not be a model call.
    """
    system = await _get_org_ai_system(db, ai_system_id, context.organization_id)
    assessment, _ = await record_eu_ai_act_assessment(
        db,
        organization_id=context.organization_id,
        ai_system=system,
        indicators=payload.indicators,
        assessed_by=context.user.id,
    )
    await db.commit()
    await db.refresh(assessment)
    return assessment


@router.post(
    "/ai-systems/{ai_system_id}/privacy-assessment",
    response_model=AIAssessmentDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def assess_ai_system_privacy(
    ai_system_id: uuid.UUID,
    payload: PrivacyAssessmentRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> AIAssessment:
    """Record the privacy assessment, including which questions nobody
    answered — "no transfer happens" and "nobody checked" are different
    answers and a DPO needs to tell them apart."""
    system = await _get_org_ai_system(db, ai_system_id, context.organization_id)
    assessment = await record_privacy_assessment(
        db,
        organization_id=context.organization_id,
        ai_system=system,
        answers=payload.answers,
        assessed_by=context.user.id,
    )
    await db.commit()
    await db.refresh(assessment)
    return assessment


@router.patch("/risks/{risk_id}/residual", response_model=RiskOut)
async def update_risk_residual(
    risk_id: uuid.UUID,
    payload: RiskResidualUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.risks.manage")),
) -> Risk:
    """Record the risk remaining after mitigation.

    Kept distinct from the inherent rating rather than overwriting it: the
    point of a residual rating is the comparison, and a register that only
    stores the current number cannot show that a control did anything.
    """
    risk = await db.get(Risk, risk_id)
    if risk is None or risk.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
    before = {"likelihood": risk.likelihood, "impact": risk.impact}
    risk.residual_likelihood = payload.residual_likelihood
    risk.residual_impact = payload.residual_impact
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.risk.residual_recorded",
        object_type="risk",
        object_id=str(risk.id),
        before_state=before,
        after_state={
            "residual_likelihood": payload.residual_likelihood,
            "residual_impact": payload.residual_impact,
        },
    )
    await db.commit()
    await db.refresh(risk)
    return risk


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


@router.get("/dpias/screening-criteria")
async def get_dpia_screening_criteria(
    context: OrgContext = Depends(get_org_context),
) -> dict[str, object]:
    """Article 35(3)'s named cases and the EDPB's nine criteria.

    Declared before `/dpias/{dpia_id}` so the literal path wins — FastAPI
    matches in definition order and a UUID parameter would swallow it.
    """
    return {"mandatory": MANDATORY_CRITERIA, "edpb": EDPB_CRITERIA}


@router.post("/dpias/screening", response_model=DpiaScreeningResultOut)
async def run_dpia_screening(
    payload: DpiaScreeningRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DpiaScreeningResultOut:
    """Decide whether a processing activity needs a DPIA.

    Counts the criteria the controller reported; it does not judge the
    processing. Two or more EDPB criteria, or any Article 35(3) case,
    indicates one is required — see `app.compliance.dpia_screening`.
    """
    activity = await db.get(ProcessingActivity, payload.processing_activity_id)
    if activity is None or activity.organization_id != context.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Processing activity not found"
        )
    result = await record_dpia_screening(
        db,
        organization_id=context.organization_id,
        activity=activity,
        answers=payload.answers,
        actor_user_id=context.user.id,
    )
    await db.commit()
    return DpiaScreeningResultOut(
        outcome=result.outcome,
        rationale=result.rationale,
        criteria_met=result.criteria_met,
        mandatory_triggers=result.mandatory_triggers,
        unanswered=result.unanswered,
    )


@router.patch("/dpias/{dpia_id}/sections", response_model=DPIAOut)
async def update_dpia_sections(
    dpia_id: uuid.UUID,
    payload: DPIASectionsUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DPIA:
    """Fill in Article 35(7)'s required content."""
    dpia = await db.get(DPIA, dpia_id)
    if dpia is None or dpia.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DPIA not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dpia, field, value)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.dpia.sections_updated",
        object_type="dpia",
        object_id=str(dpia.id),
        after_state={"sections": sorted(payload.model_dump(exclude_unset=True).keys())},
    )
    await db.commit()
    await db.refresh(dpia)
    return dpia


@router.post("/dpias/{dpia_id}/recalculate-residual", response_model=DPIAOut)
async def recalculate_dpia_residual(
    dpia_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DPIA:
    """Recompute the residual level from the risks raised against this DPIA.

    A risk with no residual rating counts at its inherent level, so the
    DPIA cannot improve merely because nobody reassessed it.
    """
    dpia = await db.get(DPIA, dpia_id)
    if dpia is None or dpia.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DPIA not found")
    before = dpia.residual_risk_level
    level = await recalculate_residual_risk(
        db, organization_id=context.organization_id, dpia=dpia
    )
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.dpia.residual_recalculated",
        object_type="dpia",
        object_id=str(dpia.id),
        before_state={"residual_risk_level": before},
        after_state={"residual_risk_level": level},
    )
    await db.commit()
    await db.refresh(dpia)
    return dpia


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


async def _get_org_dsar(db: AsyncSession, dsar_id: uuid.UUID, organization_id: uuid.UUID) -> DSAR:
    dsar = await db.get(DSAR, dsar_id)
    if dsar is None or dsar.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DSAR not found")
    return dsar


@router.post("/dsars/{dsar_id}/verify-identity", response_model=DSAROut)
async def verify_dsar_identity(
    dsar_id: uuid.UUID,
    payload: DsarVerificationRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DSAR:
    """Record whether the requester's identity was established.

    A failed verification is recorded too — "we refused this one, and
    why" is as important to be able to show as a completed response.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    await verify_identity(
        db,
        organization_id=context.organization_id,
        dsar=dsar,
        method=payload.method,
        verified=payload.verified,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(dsar)
    return dsar


@router.post("/dsars/{dsar_id}/discover", response_model=DsarDiscoveryOut)
async def discover_dsar_data(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DsarDiscoveryOut:
    """Search this organization's own records for the requester.

    Returns a map of where the person appears — counts and record ids,
    not the records themselves — which is what a case worker needs to
    decide what belongs in the response, and stops the discovery result
    from becoming a second uncontrolled copy of the data.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    findings = await run_data_discovery(
        db, organization_id=context.organization_id, dsar=dsar, actor_user_id=context.user.id
    )
    await db.commit()
    return DsarDiscoveryOut(**findings)


@router.post("/dsars/{dsar_id}/export")
async def export_dsar(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> Response:
    """Produce the response package.

    Blocked until the requester is verified. The guard lives in
    `app.compliance.dsar.generate_export`, not here, so a second caller
    added later cannot skip it — see that module's docstring for why this
    direction of risk is the one that matters.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    try:
        payload, filename = await generate_export(
            db, organization_id=context.organization_id, dsar=dsar, actor_user_id=context.user.id
        )
    except DsarVerificationRequired as exc:
        # 409, not 403: the caller has permission, the request is not in a
        # state where this action is allowed yet.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()
    return Response(
        content=payload,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


@router.get("/data-transfers", response_model=list[DataTransferOut])
async def list_data_transfers(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[DataTransfer]:
    result = await db.execute(
        select(DataTransfer)
        .where(DataTransfer.organization_id == context.organization_id)
        .order_by(DataTransfer.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/data-transfers", response_model=DataTransferOut, status_code=status.HTTP_201_CREATED)
async def create_data_transfer_endpoint(
    payload: DataTransferCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DataTransfer:
    if payload.processing_activity_id is not None:
        await _get_org_processing_activity(
            db, payload.processing_activity_id, context.organization_id
        )
    transfer = await create_data_transfer(
        db,
        organization_id=context.organization_id,
        processing_activity_id=payload.processing_activity_id,
        recipient_name=payload.recipient_name,
        destination_country=payload.destination_country,
        transfer_mechanism=payload.transfer_mechanism,
        safeguards_description=payload.safeguards_description,
        owner_id=payload.owner_id,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(transfer)
    return transfer


async def _get_org_data_transfer(
    db: AsyncSession, transfer_id: uuid.UUID, organization_id: uuid.UUID
) -> DataTransfer:
    transfer = await db.get(DataTransfer, transfer_id)
    if transfer is None or transfer.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data transfer not found")
    return transfer


@router.get("/data-transfers/{transfer_id}", response_model=DataTransferOut)
async def get_data_transfer(
    transfer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DataTransfer:
    return await _get_org_data_transfer(db, transfer_id, context.organization_id)


@router.patch("/data-transfers/{transfer_id}/status", response_model=DataTransferOut)
async def update_data_transfer_status_endpoint(
    transfer_id: uuid.UUID,
    payload: DataTransferStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DataTransfer:
    transfer = await _get_org_data_transfer(db, transfer_id, context.organization_id)
    transfer = await update_data_transfer_status(
        db, transfer=transfer, new_status=payload.status, actor_user_id=context.user.id
    )
    await db.commit()
    await db.refresh(transfer)
    return transfer


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


@router.get("/vendors", response_model=list[VendorOut])
async def list_vendors(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Vendor]:
    stmt = (
        select(Vendor)
        .where(Vendor.organization_id == context.organization_id)
        .order_by(Vendor.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


@router.post("/vendors", response_model=VendorOut, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    payload: VendorCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.vendors.manage")),
) -> Vendor:
    vendor = Vendor(organization_id=context.organization_id, **payload.model_dump())
    db.add(vendor)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.vendor.created",
        object_type="vendor",
        object_id=str(vendor.id),
        after_state={"name": vendor.name, "category": vendor.category},
    )

    from app.automation.triggers import dispatch_event

    await dispatch_event(
        db,
        organization_id=context.organization_id,
        trigger_type="new_vendor",
        payload={"vendor_id": str(vendor.id), "name": vendor.name},
        actor_user_id=context.user.id,
    )

    await db.commit()
    await db.refresh(vendor)
    return vendor


async def _get_org_vendor(
    db: AsyncSession, vendor_id: uuid.UUID, organization_id: uuid.UUID
) -> Vendor:
    vendor = await db.get(Vendor, vendor_id)
    if vendor is None or vendor.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
    return vendor


@router.get("/vendors/{vendor_id}", response_model=VendorDetailOut)
async def get_vendor(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> VendorDetailOut:
    vendor = await _get_org_vendor(db, vendor_id, context.organization_id)
    assessments_result = await db.execute(
        select(VendorAssessment)
        .where(VendorAssessment.vendor_id == vendor.id)
        .order_by(VendorAssessment.created_at.desc())
    )
    evidence_result = await db.execute(
        select(Evidence).where(Evidence.vendor_id == vendor.id).order_by(Evidence.created_at.desc())
    )
    return VendorDetailOut(
        **VendorOut.model_validate(vendor).model_dump(),
        assessments=[
            VendorAssessmentOut.model_validate(a) for a in assessments_result.scalars().all()
        ],
        evidence=[EvidenceOut.model_validate(e) for e in evidence_result.scalars().all()],
    )


@router.patch("/vendors/{vendor_id}/status", response_model=VendorOut)
async def update_vendor_status(
    vendor_id: uuid.UUID,
    payload: VendorStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.vendors.manage")),
) -> Vendor:
    vendor = await _get_org_vendor(db, vendor_id, context.organization_id)
    before_status = vendor.status
    vendor.status = payload.status
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.vendor.status_changed",
        object_type="vendor",
        object_id=str(vendor.id),
        before_state={"status": before_status},
        after_state={"status": vendor.status},
    )
    await db.commit()
    await db.refresh(vendor)
    return vendor


@router.patch("/vendors/{vendor_id}/dpa-status", response_model=VendorOut)
async def update_vendor_dpa_status(
    vendor_id: uuid.UUID,
    payload: VendorDpaStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.vendors.manage")),
) -> Vendor:
    """spec §69 "New AI Tool Adoption" step "DPA review" — a real,
    human-reviewed state, never auto-flipped to "signed"."""
    vendor = await _get_org_vendor(db, vendor_id, context.organization_id)
    before_status = vendor.dpa_status
    vendor.dpa_status = payload.dpa_status
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.vendor.dpa_status_changed",
        object_type="vendor",
        object_id=str(vendor.id),
        before_state={"dpa_status": before_status},
        after_state={"dpa_status": vendor.dpa_status},
    )
    await db.commit()
    await db.refresh(vendor)
    return vendor


@router.post(
    "/vendors/{vendor_id}/assessments",
    response_model=VendorAssessmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_vendor_assessment(
    vendor_id: uuid.UUID,
    payload: VendorAssessmentCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.vendors.manage")),
) -> VendorAssessment:
    vendor = await _get_org_vendor(db, vendor_id, context.organization_id)
    assessment = await record_vendor_assessment(
        db,
        organization_id=context.organization_id,
        vendor=vendor,
        risk_conclusion=payload.risk_conclusion,
        notes=payload.notes,
        assessed_by=context.user.id,
    )
    await db.commit()
    await db.refresh(assessment)
    return assessment


@router.get("/questionnaires", response_model=list[QuestionnaireOut])
async def list_questionnaires(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[Questionnaire]:
    result = await db.execute(
        select(Questionnaire)
        .where(Questionnaire.organization_id == context.organization_id)
        .order_by(Questionnaire.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/questionnaires", response_model=QuestionnaireOut, status_code=status.HTTP_201_CREATED
)
async def create_questionnaire(
    payload: QuestionnaireCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> Questionnaire:
    if payload.opportunity_id is not None:
        from app.sales.models import Opportunity

        opportunity = await db.get(Opportunity, payload.opportunity_id)
        if opportunity is None or opportunity.organization_id != context.organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found"
            )

    questionnaire = Questionnaire(organization_id=context.organization_id, **payload.model_dump())
    db.add(questionnaire)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.questionnaire.created",
        object_type="questionnaire",
        object_id=str(questionnaire.id),
        after_state={"title": questionnaire.title, "source": questionnaire.source},
    )
    await db.commit()
    await db.refresh(questionnaire)
    return questionnaire


async def _get_org_questionnaire(
    db: AsyncSession, questionnaire_id: uuid.UUID, organization_id: uuid.UUID
) -> Questionnaire:
    questionnaire = await db.get(Questionnaire, questionnaire_id)
    if questionnaire is None or questionnaire.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire not found")
    return questionnaire


async def _build_questionnaire_detail(
    db: AsyncSession, questionnaire: Questionnaire
) -> QuestionnaireDetailOut:
    questions_result = await db.execute(
        select(QuestionnaireQuestion)
        .where(QuestionnaireQuestion.questionnaire_id == questionnaire.id)
        .order_by(QuestionnaireQuestion.order_index)
    )
    questions = list(questions_result.scalars().all())

    question_details: list[QuestionnaireQuestionDetailOut] = []
    for question in questions:
        answer_result = await db.execute(
            select(QuestionnaireAnswer).where(QuestionnaireAnswer.question_id == question.id)
        )
        answer = answer_result.scalar_one_or_none()
        question_details.append(
            QuestionnaireQuestionDetailOut(
                **QuestionnaireQuestionOut.model_validate(question).model_dump(),
                answer=QuestionnaireAnswerOut.model_validate(answer) if answer else None,
            )
        )

    return QuestionnaireDetailOut(
        **QuestionnaireOut.model_validate(questionnaire).model_dump(),
        questions=question_details,
    )


@router.get("/questionnaires/{questionnaire_id}", response_model=QuestionnaireDetailOut)
async def get_questionnaire(
    questionnaire_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> QuestionnaireDetailOut:
    questionnaire = await _get_org_questionnaire(db, questionnaire_id, context.organization_id)
    return await _build_questionnaire_detail(db, questionnaire)


@router.patch("/questionnaires/{questionnaire_id}/status", response_model=QuestionnaireOut)
async def update_questionnaire_status(
    questionnaire_id: uuid.UUID,
    payload: QuestionnaireStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> Questionnaire:
    questionnaire = await _get_org_questionnaire(db, questionnaire_id, context.organization_id)
    before_status = questionnaire.status
    questionnaire.status = payload.status
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.questionnaire.status_changed",
        object_type="questionnaire",
        object_id=str(questionnaire.id),
        before_state={"status": before_status},
        after_state={"status": questionnaire.status},
    )
    await db.commit()
    await db.refresh(questionnaire)
    return questionnaire


@router.post(
    "/questionnaires/{questionnaire_id}/questions",
    response_model=QuestionnaireQuestionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_questionnaire_question(
    questionnaire_id: uuid.UUID,
    payload: QuestionnaireQuestionCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> QuestionnaireQuestion:
    questionnaire = await _get_org_questionnaire(db, questionnaire_id, context.organization_id)
    question = await add_questionnaire_question(
        db,
        organization_id=context.organization_id,
        questionnaire=questionnaire,
        text=payload.text,
        category=payload.category,
        order_index=payload.order_index,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(question)
    return question


async def _get_org_question_and_answer(
    db: AsyncSession,
    questionnaire_id: uuid.UUID,
    question_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> tuple[QuestionnaireQuestion, QuestionnaireAnswer]:
    question = await db.get(QuestionnaireQuestion, question_id)
    if (
        question is None
        or question.organization_id != organization_id
        or question.questionnaire_id != questionnaire_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    answer_result = await db.execute(
        select(QuestionnaireAnswer).where(QuestionnaireAnswer.question_id == question.id)
    )
    answer = answer_result.scalar_one_or_none()
    if answer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer not found")
    return question, answer


@router.post(
    "/questionnaires/{questionnaire_id}/questions/{question_id}/suggest-answer",
    response_model=QuestionnaireAnswerOut,
)
async def suggest_answer(
    questionnaire_id: uuid.UUID,
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> QuestionnaireAnswer:
    question, answer = await _get_org_question_and_answer(
        db, questionnaire_id, question_id, context.organization_id
    )
    answer = await suggest_questionnaire_answer(
        db,
        organization_id=context.organization_id,
        question=question,
        answer=answer,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(answer)
    return answer


@router.patch(
    "/questionnaires/{questionnaire_id}/questions/{question_id}/answer",
    response_model=QuestionnaireAnswerOut,
)
async def update_answer(
    questionnaire_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: QuestionnaireAnswerUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> QuestionnaireAnswer:
    _, answer = await _get_org_question_and_answer(
        db, questionnaire_id, question_id, context.organization_id
    )
    if payload.evidence_id is not None:
        await _get_org_evidence(db, payload.evidence_id, context.organization_id)
    if payload.control_id is not None:
        await _get_org_control(db, payload.control_id, context.organization_id)
    answer = await update_questionnaire_answer(
        db,
        answer=answer,
        answer_text=payload.answer_text,
        status=payload.status,
        evidence_id=payload.evidence_id,
        control_id=payload.control_id,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(answer)
    return answer


@router.get("/audits", response_model=list[AuditOut])
async def list_audits(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[Audit]:
    stmt = (
        select(Audit)
        .where(Audit.organization_id == context.organization_id)
        .order_by(Audit.created_at.desc())
    )
    return await paginate(db, stmt, pagination, response)


@router.post("/audits", response_model=AuditOut, status_code=status.HTTP_201_CREATED)
async def create_audit(
    payload: AuditCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> Audit:
    if payload.framework_id is not None:
        framework = await db.get(Framework, payload.framework_id)
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
    audit = Audit(organization_id=context.organization_id, **payload.model_dump())
    db.add(audit)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.audit.created",
        object_type="audit",
        object_id=str(audit.id),
        after_state={"title": audit.title, "status": audit.status},
    )
    await db.commit()
    await db.refresh(audit)
    return audit


async def _get_org_audit(
    db: AsyncSession, audit_id: uuid.UUID, organization_id: uuid.UUID
) -> Audit:
    audit = await db.get(Audit, audit_id)
    if audit is None or audit.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return audit


@router.get("/audits/{audit_id}", response_model=AuditDetailOut)
async def get_audit(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> AuditDetailOut:
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    findings_result = await db.execute(
        select(AuditFinding)
        .where(AuditFinding.audit_id == audit.id)
        .order_by(AuditFinding.created_at.desc())
    )
    return AuditDetailOut(
        **AuditOut.model_validate(audit).model_dump(),
        findings=[AuditFindingOut.model_validate(f) for f in findings_result.scalars().all()],
    )


@router.patch("/audits/{audit_id}/status", response_model=AuditOut)
async def update_audit_status(
    audit_id: uuid.UUID,
    payload: AuditStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> Audit:
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    before_status = audit.status
    audit.status = payload.status
    if payload.status == "completed":
        audit.completed_at = utcnow()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.audit.status_changed",
        object_type="audit",
        object_id=str(audit.id),
        before_state={"status": before_status},
        after_state={"status": audit.status},
    )
    await db.commit()
    await db.refresh(audit)
    return audit


@router.post(
    "/audits/{audit_id}/findings",
    response_model=AuditFindingOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_audit_finding(
    audit_id: uuid.UUID,
    payload: AuditFindingCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditFinding:
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    if payload.control_id is not None:
        await _get_org_control(db, payload.control_id, context.organization_id)
    finding = await record_audit_finding(
        db,
        organization_id=context.organization_id,
        audit=audit,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        control_id=payload.control_id,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(finding)
    return finding


@router.patch(
    "/audits/{audit_id}/findings/{finding_id}/status",
    response_model=AuditFindingOut,
)
async def update_finding_status(
    audit_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: AuditFindingStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditFinding:
    finding = await db.get(AuditFinding, finding_id)
    if (
        finding is None
        or finding.organization_id != context.organization_id
        or finding.audit_id != audit_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    finding = await update_audit_finding_status(
        db, finding=finding, new_status=payload.status, actor_user_id=context.user.id
    )
    await db.commit()
    await db.refresh(finding)
    return finding


async def _get_org_security_review(
    db: AsyncSession, review_id: uuid.UUID, organization_id: uuid.UUID
) -> SecurityReview:
    review = await db.get(SecurityReview, review_id)
    if review is None or review.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Security review not found"
        )
    return review


async def _build_security_review_detail(
    db: AsyncSession, review: SecurityReview
) -> SecurityReviewDetailOut:
    opportunity = await db.get(Opportunity, review.opportunity_id)
    questionnaire = await db.get(Questionnaire, review.questionnaire_id)
    assert opportunity is not None
    assert questionnaire is not None
    gaps = await list_security_review_gaps(db, questionnaire_id=review.questionnaire_id)
    approval_status = None
    if review.approval_id is not None:
        approval = await db.get(Approval, review.approval_id)
        approval_status = approval.status if approval else None
    return SecurityReviewDetailOut(
        **SecurityReviewOut.model_validate(review).model_dump(),
        opportunity_title=opportunity.title,
        approval_status=approval_status,
        gap_count=len(gaps),
        questionnaire=await _build_questionnaire_detail(db, questionnaire),
    )


@router.get("/security-reviews", response_model=list[SecurityReviewOut])
async def list_security_reviews(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[SecurityReview]:
    result = await db.execute(
        select(SecurityReview)
        .where(SecurityReview.organization_id == context.organization_id)
        .order_by(SecurityReview.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/security-reviews", response_model=SecurityReviewDetailOut, status_code=status.HTTP_201_CREATED
)
async def create_security_review(
    payload: SecurityReviewCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.security_reviews.manage")),
) -> SecurityReviewDetailOut:
    opportunity = await db.get(Opportunity, payload.opportunity_id)
    if opportunity is None or opportunity.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    existing = (
        await db.execute(
            select(SecurityReview).where(SecurityReview.opportunity_id == opportunity.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A security review already exists for this opportunity",
        )
    try:
        review = await start_security_review(
            db,
            organization_id=context.organization_id,
            opportunity=opportunity,
            questionnaire_id=payload.questionnaire_id,
            actor_user_id=context.user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(review)
    return await _build_security_review_detail(db, review)


@router.get("/security-reviews/{review_id}", response_model=SecurityReviewDetailOut)
async def get_security_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> SecurityReviewDetailOut:
    review = await _get_org_security_review(db, review_id, context.organization_id)
    return await _build_security_review_detail(db, review)


@router.patch("/security-reviews/{review_id}/status", response_model=SecurityReviewOut)
async def update_security_review_status_route(
    review_id: uuid.UUID,
    payload: SecurityReviewStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.security_reviews.manage")),
) -> SecurityReview:
    review = await _get_org_security_review(db, review_id, context.organization_id)
    review = await update_security_review_status(
        db, review=review, new_status=payload.status, actor_user_id=context.user.id
    )
    await db.commit()
    await db.refresh(review)
    return review


@router.post("/security-reviews/{review_id}/sync", response_model=SecurityReviewSyncResult)
async def sync_security_review_route(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.security_reviews.manage")),
) -> SecurityReviewSyncResult:
    review = await _get_org_security_review(db, review_id, context.organization_id)
    review, tasks_created = await sync_security_review(
        db, review=review, actor_user_id=context.user.id
    )
    await db.commit()
    await db.refresh(review)
    detail = await _build_security_review_detail(db, review)
    return SecurityReviewSyncResult(review=detail, tasks_created=tasks_created)


@router.post("/security-reviews/{review_id}/clear", response_model=SecurityReviewDetailOut)
async def clear_security_review_route(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.security_reviews.manage")),
) -> SecurityReviewDetailOut:
    review = await _get_org_security_review(db, review_id, context.organization_id)
    try:
        review = await clear_security_review(db, review=review, actor_user_id=context.user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(review)
    return await _build_security_review_detail(db, review)
