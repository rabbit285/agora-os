from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record_event
from app.compliance.ai_governance import (
    indicator_catalog,
    record_eu_ai_act_assessment,
    record_privacy_assessment,
)
from app.compliance.ai_system_governance import assess_ai_system
from app.compliance import audit_findings as audit_finding_service
from app.compliance import audit_state, audit_workspace
from app.compliance.audit_scope_text import suggested_scope as suggested_audit_scope
from app.compliance import artifacts
from app.compliance import audit_identity, audit_report, audit_report_service
from app.compliance import (
    dpia_approval,
    dsar_discovery,
    dsar_response,
    dsar_scope,
    dsar_workflow,
    transfer_drift,
    dpia_quality,
    dpia_completion,
    dpia_prefill,
    dpia_risks,
    dpia_workflow,
    ropa_titles,
)
from app.compliance import privacy_accept, privacy_deadlines, privacy_overview
from app.compliance import privacy_suggestions
from app.identity.models import User
from app.compliance import review_export, review_export_service
from app.compliance.assessment import (
    REQUIREMENT_STATUS_LABELS as ASSESSMENT_STATUS_LABELS,

    create_task_from_gap,
    evaluate_framework,
    generate_remediation,
    load_scoping_profile,
    reassess_frameworks_for_control,
    run_framework_assessment,
    set_framework_activation,
    summarize_readiness,
)
from app.compliance.connectors import CONNECTORS, list_evidence_events
from app.compliance.control_assessment import (
    ASSESSMENT_LABELS,
    assess_control,
    assess_controls,
)
from app.compliance.copilot_index import backfill_organization
from app.compliance.customer_review import (
    find_active_for_customer as find_active_customer_review,
)
from app.compliance.customer_review import (
    review_title_for as customer_review_title,
)
from app.compliance.customer_review import (
    label_for as customer_review_label,
)
from app.compliance.customer_review import (
    link_questionnaire as link_questionnaire_to_review,
)
from app.compliance.customer_review import (
    progress_for as customer_review_progress,
)
from app.compliance.customer_review import (
    recalculate as recalculate_customer_review,
)
from app.compliance.customer_review import (
    set_lifecycle as set_review_lifecycle,
)
from app.compliance.customer_review import (
    sync_lifecycle as sync_review_lifecycle,
)
from app.compliance.customer_identity import (
    reads_like_a_question as title_reads_like_a_question,
)
from app.compliance.customer_identity import suggest_customer_name
from app.compliance.dashboard import build_dashboard
from app.compliance.document_reconcile import (
    backfill_classification,
    map_documents_to_new_controls,
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
    verify_identity,
)
from app.compliance.evidence_ai import (
    SuggestionDecisionError,
    UnsupportedFormatError,
    approve_suggestion,
    process_document,
    reject_suggestion,
    suggest_evidence_mappings,
)
from app.compliance.framework_applicability import (
    CompanyFacts,
    applicable_framework_keys,
    recommend_frameworks,
)
from app.compliance.lifecycle import audit_eligibility, questionnaire_eligibility
from app.compliance.models import (
    DPIA,
    DSAR,
    AIAssessment,
    AIIncident,
    AISystem,
    Audit,
    AuditFinding,
    AuditItem,
    ComplianceGap,
    Control,
    ControlAssessment,
    ControlMapping,
    DataTransfer,
    DsarDiscoveredItem,
    DsarResponsePackage,
    DsarScopeSource,
    DpiaRiskSuggestion,
    Evidence,
    EvidenceEvent,
    EvidenceSuggestion,
    Framework,
    FrameworkActivation,
    Policy,
    PolicyVersion,
    ProcessingActivity,
    Questionnaire,
    QuestionnaireAnswer,
    QuestionnaireQuestion,
    AuditReport,
    PrivacySuggestion,
    ProcessingActivityAISystem,
    ProcessingActivityVendor,
    Requirement,
    ReviewExport,
    Risk,
    SecurityReview,
    Vendor,
    VendorAssessment,
)
from app.compliance.policy_governance import approve_policy as approve_policy_record
from app.compliance.policy_governance import backfill_organization as policy_backfill
from app.compliance.policy_governance import days_until_review as policy_days_until_review
from app.compliance.policy_governance import missing_governance as policy_missing_governance
from app.compliance.policy_governance import (
    promote_document_to_current_version as promote_policy_version,
)
from app.compliance.policy_governance import review_state as policy_review_state
from app.compliance.questionnaire_ai import ANSWER_LABELS
from app.compliance.questionnaire_analysis import analyse_import
from app.compliance.questionnaire_analysis import normalize as normalize_question
from app.compliance.questionnaire_import import (
    SUPPORTED_CONTENT_TYPES,
    ExtractedQuestion,
    categorize,
    clean_line,
    extract_questions,
    extract_questions_from_file,
)
from app.compliance.questionnaire_status import (
    LABELS as QUESTIONNAIRE_STATUS_LABELS,
)
from app.compliance.questionnaire_status import (
    readiness_for as questionnaire_readiness,
)
from app.compliance.questionnaire_status import (
    blockers as questionnaire_blockers,
)
from app.compliance.questionnaire_status import (
    recalculate_by_id as recalculate_questionnaire_status,
)
from app.compliance.questionnaire_status import (
    setup_blockers as questionnaire_setup_blockers,
)
from app.compliance.requirement_applicability import evaluate_applicability
from app.compliance.review_backfill import backfill_customer_reviews
from app.compliance.review_center import build_review_center
from app.compliance.schemas import (
    AcceptVersionRequest,
    AdoptRecommendedRequest,
    AIAssessmentCreate,
    AIAssessmentDetailOut,
    AIAssessmentOut,
    AIGovernanceOverviewOut,
    AIIncidentCreate,
    AIIncidentOut,
    AIIncidentStatusUpdate,
    AISystemCreate,
    AISystemDetailOut,
    AISystemGovernanceOut,
    AISystemGovernanceUpdate,
    AISystemOut,
    AISystemProfileUpdate,
    AISystemStatusUpdate,
    AnalyzedLineOut,
    AnalyzeDocumentRequest,
    AnalyzeDocumentResult,
    ApproveSuggestionRequest,
    ArchiveResultOut,
    AuditCompletionBlockerOut,
    AuditCreate,
    AuditDecisionIn,
    AuditDecisionResultOut,
    AuditExclusionIn,
    AuditScopeLineOut,
    AuditScopeOut,
    AuditEvidenceOut,
    AuditItemOut,
    AuditPreparationOut,
    AuditProgressOut,
    AuditReopenIn,
    AuditSectionOut,
    AuditUpdate,
    ExportAnswerOut,
    ExportBlockerOut,
    ExportDocumentOut,
    ExportGenerateRequest,
    ExportPreviewOut,
    ExportPreviewRequest,
    FileDisclosureUpdate,
    ReviewExportOut,
    AuditVerificationIn,
    AuditDetailOut,
    AuditReportBlockerOut,
    AuditReportConclusionOut,
    AuditReportEvidenceOut,
    AuditReportFindingOut,
    AuditReportGenerateRequest,
    AuditReportMetricOut,
    AuditReportOut,
    AuditReportPreviewOut,
    AuditReportProgressOut,
    AuditReportRemediationOut,
    AuditReportSeverityGroupOut,
    AuditReportSignOffOut,
    AuditorIdentityOut,
    DSARExtensionIn,
    PrivacyAttentionOut,
    PrivacyMetricOut,
    PrivacyOverviewOut,
    DpiaBlockerOut,
    DpiaConsultationIn,
    DpiaContextOut,
    DpiaScreeningDecisionIn,
    DpiaScreeningStartIn,
    DpiaMissingFactOut,
    DpiaRiskApproveIn,
    DpiaRiskConclusionIn,
    DpiaRiskDismissIn,
    DpiaSectionApproveIn,
    RiskRemediationIn,
    DpiaSectionReviewOut,
    DpiaSpecialCategoryIn,
    DsarBlockerOut,
    DsarCoverageOut,
    DsarDiscoveredItemOut,
    DsarDiscoveryPlanOut,
    DsarItemReviewIn,
    DsarManualSourceIn,
    DsarNextActionOut,
    DsarResponseApproveIn,
    DsarResponsePackageOut,
    DsarResponsePreviewOut,
    DsarScopeConfirmIn,
    DsarScopeSourceOut,
    DsarSourceLineOut,
    DsarWorkflowOut,
    DpiaSpecialSignalOut,
    DpiaSuggestedRiskOut,
    DpiaWorkflowOut,
    DpiaLinkedRecordOut,
    DpiaSuggestedAnswerOut,
    ProcessingActivityRelatedOut,
    RopaTitleProblemOut,
    RopaTitleRepairApply,
    RopaTitleRepairOut,
    ProcessingActivityReviewIn,
    PrivacyAnalysisOut,
    PrivacyDataLocationOut,
    PrivacySuggestionAcceptIn,
    PrivacySuggestionDismissIn,
    PrivacySuggestionOut,
    PrivacySuggestionSourceOut,
    RelatedRecordOut,
    AuditFindingCreate,
    AuditFindingOut,
    AuditFindingStatusUpdate,
    AuditOut,
    AuditStatusUpdate,
    ClassificationBackfillOut,
    CompanyFactsUpdate,
    ComplianceDashboardOut,
    ComplianceDocumentOut,
    ComplianceGapOut,
    ComplianceOverviewOut,
    ConnectorCatalogOut,
    ConnectorOut,
    ControlAssessmentCreate,
    ControlAssessmentOut,
    ControlAssessmentViewOut,
    ControlCreate,
    ControlDetailOut,
    ControlOut,
    ControlRequirementMapping,
    CopilotIndexBackfillOut,
    CreateGapTaskRequest,
    DataTransferCreate,
    DataTransferDetailOut,
    DataTransferOut,
    DataTransferStatusUpdate,
    DeleteResultOut,
    DocumentDetailOut,
    DocumentEvidenceOut,
    DocumentVersionOut,
    DPIACreate,
    DPIAOut,
    DpiaScreeningRequest,
    DpiaScreeningResultOut,
    DPIASectionsUpdate,
    DPIAStatusUpdate,
    DSARCreate,
    DSAROut,
    DSARStatusUpdate,
    DsarVerificationRequest,
    EuAiActScreeningRequest,
    EvidenceCreate,
    EvidenceEventOut,
    EvidenceMappingOut,
    EvidenceOut,
    EvidenceSuggestionOut,
    FrameworkActivationOut,
    FrameworkAssessmentResultOut,
    FrameworkCreate,
    FrameworkDashboardControlOut,
    FrameworkDashboardOut,
    FrameworkDashboardRequirementOut,
    FrameworkOut,
    FrameworkReadinessOut,
    FrameworkRecommendationOut,
    FrameworkRecommendationsOut,
    GroupedEvidenceOut,
    ImportAnalysisOut,
    ImportResultOut,
    PolicyApproveRequest,
    PolicyBackfillOut,
    PolicyControlOut,
    PolicyCreate,
    PolicyDetailOut,
    PolicyGovernanceUpdate,
    PolicyOut,
    PolicyStatusUpdate,
    PolicyVersionOut,
    PolicyVersionUploadRequest,
    PrivacyAssessmentRequest,
    ProcessDocumentRequest,
    ProcessingActivityCreate,
    ProcessingActivityOut,
    QuestionnaireAnswerOut,
    QuestionnaireAnswerUpdate,
    QuestionnaireCreate,
    QuestionnaireCustomerResultOut,
    QuestionnaireCustomerUpdate,
    QuestionnaireDetailOut,
    QuestionnaireImportConfirm,
    QuestionnaireImportRequest,
    QuestionnaireImportResult,
    QuestionnaireOut,
    QuestionnaireProgressOut,
    QuestionnaireReadinessOut,
    QuestionnaireRename,
    QuestionnaireQuestionCreate,
    QuestionnaireQuestionDetailOut,
    ReadinessBlockerOut,
    QuestionnaireQuestionOut,
    QuestionnaireStatusUpdate,
    ReadinessBreakdownOut,
    RequirementEvaluationOut,
    RequirementOut,
    ReviewBackfillOut,
    ReviewCategoryOut,
    ReviewCenterOut,
    ReviewItemOut,
    ReviewProgressOut,
    ReviewQuestionnaireOut,
    RiskCreate,
    RiskOut,
    RiskResidualUpdate,
    RiskUpdate,
    SectionChangeOut,
    SecurityReviewDetailOut,
    SecurityReviewOut,
    SecurityReviewStatusUpdate,
    SecurityReviewSyncResult,
    SetFrameworkActivationRequest,
    VendorApprovalRequest,
    VendorAssessmentCreate,
    VendorAssessmentDetailOut,
    VendorAssessmentOut,
    VendorCreate,
    VendorDetailOut,
    VendorDpaStatusUpdate,
    VendorOut,
    VendorStatusUpdate,
    VersionAcceptedOut,
    VersionBackfillOut,
    VersionCandidateOut,
    VersionDiffOut,
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
    suggest_questionnaire_answer,
    sync_security_review,
    update_ai_incident_status,
    update_audit_finding_status,
    update_data_transfer_status,
    update_dsar_status,
    update_questionnaire_answer,
    update_security_review_status,
)
from app.compliance.vendor_review import (
    VendorApprovalError,
    decide_vendor_approval,
    run_privacy_review,
    run_security_review,
)
from app.core.models import Approval, File, Membership, Organization, Task
from app.core.pagination import Pagination, paginate, pagination_params
from app.core.routes import document_detail_href
from app.core.schemas import TaskOut
from app.core.storage import presign_download  # noqa: F401
from app.core.storage import download_object
from app.db.base import utcnow
from app.db.session import get_db
from app.dependencies import OrgContext, get_org_context, require_permission
from app.knowledge.documents import (
    documents_for_files,
    file_for_document,
    readable_title,
)
from app.knowledge.parsing import extract_text
from app.onboarding.models import OnboardingProfile
from app.sales.models import Opportunity

logger = logging.getLogger("agora.compliance")

router = APIRouter(prefix="/api/v1/compliance", tags=["compliance"])


@router.get("/frameworks", response_model=list[FrameworkOut])
async def list_frameworks(
    db: AsyncSession = Depends(get_db), context: OrgContext = Depends(get_org_context)
) -> list[FrameworkOut]:
    result = await db.execute(
        select(Framework)
        .where(
            (Framework.organization_id.is_(None))
            | (Framework.organization_id == context.organization_id)
        )
        .order_by(Framework.name)
    )
    out: list[FrameworkOut] = []
    for framework in result.scalars().all():
        item = FrameworkOut.model_validate(framework)
        # Server-side so every surface offers the same wording, and so
        # adding a framework means adding its scope description in one
        # place rather than in each form that mentions it.
        item.suggested_audit_scope = suggested_audit_scope(framework.key)
        out.append(item)
    return out


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
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.frameworks.manage")),
) -> FrameworkActivation:
    """Adopt a framework, or stand it down.

    Deactivating keeps every control, evidence item, assessment and gap
    built against the framework — switching GDPR off and on again must
    not discard the organization's own work.

    Adopting scaffolds controls, and those controls are the first thing
    the organization's existing documents have ever had to map to. A
    policy uploaded on day one was read, classified and governed then;
    it simply had nothing to be evidence *for*. Reconsidering it here is
    what stops the customer being asked to re-upload a file the product
    already holds and already understands.
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

    if payload.active:
        # After the response. Re-reading a library against a new control
        # set is a series of model calls, and the adoption itself is
        # already done — holding the request open for it would make
        # adopting a framework look hung.
        background.add_task(
            map_documents_to_new_controls,
            context.organization_id,
            actor_user_id=context.user.id,
        )

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

    # This framework's controls have now been reassessed against whatever
    # evidence is currently attached, so the "stale" prompt is answered.
    assessed_control_ids = {cid for e in evaluations for cid in e.control_ids}
    if assessed_control_ids:
        await db.execute(
            update(Control)
            .where(
                Control.id.in_(assessed_control_ids),
                Control.organization_id == context.organization_id,
            )
            .values(needs_reassessment=False)
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
            missing_conditions=list(e.coverage.unmet) if e.coverage else [],
            uncertainty=e.coverage.uncertainty if e.coverage else None,
        )
        for e in evaluations
    ]
    satisfied = sum(1 for e in evaluations if e.status == "satisfied")
    # Distinct from the dashboard's control coverage: this counts
    # requirements actually backed by evidence, which is the number that
    # must not move when an unrelated document is uploaded.
    #
    # Scoped to what applies, like readiness. A requirement that does
    # not bind this organization is not evidence they are missing — a
    # company in scope of fewer articles reading as less covered was the
    # same denominator bug in a second place.
    in_scope = [e for e in evaluations if e.status != "not_applicable"]
    with_evidence = sum(1 for e in in_scope if e.evidence_count > 0)
    return FrameworkAssessmentResultOut(
        framework_id=framework_id,
        assessed_at=datetime.now(UTC),
        requirements=rows,
        satisfied_count=satisfied,
        gap_count=len(gaps),
        evidence_coverage_percent=(
            round(100 * with_evidence / len(in_scope), 1) if in_scope else 0.0
        ),
        readiness=ReadinessBreakdownOut.model_validate(summarize_readiness(evaluations)),
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
    # Gaps raised before the plan existed, or by a code path that
    # skipped it, would otherwise produce the empty task shell this
    # endpoint is supposed to have stopped producing.
    if not gap.remediation_plan:
        await generate_remediation(
            db,
            organization_id=context.organization_id,
            gap=gap,
            actor_user_id=context.user.id,
        )
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

    # Scoping, so this screen's coverage figure uses the same denominator
    # as readiness. A requirement that does not bind this organization is
    # not something they have failed to cover.
    # The assessment's own profile loader, not a second one. Two
    # definitions of "what applies here" is how a coverage figure and a
    # readiness figure end up disagreeing on the same screen.
    profile = await load_scoping_profile(db, organization_id=context.organization_id)
    applicable_codes = {
        requirement.reference_code
        for requirement in requirements
        if evaluate_applicability(
            profile,
            framework_key=framework.key,
            reference_code=requirement.reference_code,
        ).applies
    }

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
        if (
            requirement.reference_code in applicable_codes
            and any(c.status == "implemented" for c in controls)
        ):
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

    coverage_percent = (
        round(100 * covered_count / len(applicable_codes), 1) if applicable_codes else 0.0
    )
    return FrameworkDashboardOut(
        framework=FrameworkOut.model_validate(framework),
        requirements=requirement_rows,
        coverage_percent=coverage_percent,
    )


async def _controls_with_assessment(
    db: AsyncSession, controls: list[Control], organization_id: uuid.UUID
) -> list[ControlOut]:
    """Attach the derived assessment to a set of controls.

    The one place a `ControlOut` is built with its status. Anything that
    returns controls goes through here, so no screen can quietly grow a
    second opinion about what a control's status is.
    """
    if not controls:
        return []
    profile = await load_scoping_profile(db, organization_id=organization_id)
    views = await assess_controls(
        db,
        organization_id=organization_id,
        controls=controls,
        profile=profile,
    )
    out: list[ControlOut] = []
    for control in controls:
        view = views[control.id]
        out.append(
            ControlOut(
                **ControlOut.model_validate(control).model_dump(
                    exclude={
                        "assessment_status",
                        "assessment_label",
                        "ai_assessment_status",
                        "ai_assessment_label",
                        "human_assessment_status",
                        "human_assessment_label",
                        "human_reviewed_at",
                        "human_reviewed_by",
                        "review_required",
                        "coverage_percent",
                        "evidence_count",
                        "applicable_requirement_count",
                        "mapped_requirement_count",
                    }
                ),
                # Effective first — it is what the row shows.
                assessment_status=view.effective_status,
                assessment_label=view.label,
                ai_assessment_status=view.ai_status,
                ai_assessment_label=view.ai_label,
                human_assessment_status=view.human_status,
                human_assessment_label=(
                    ASSESSMENT_LABELS.get(view.human_status, view.human_status)
                    if view.human_status
                    else None
                ),
                human_reviewed_at=(
                    datetime.fromisoformat(view.recorded_at)
                    if view.recorded_at and view.human_status
                    else None
                ),
                human_reviewed_by=view.recorded_by if view.human_status else None,
                review_required=view.review_required,
                coverage_percent=view.confidence,
                evidence_count=len(view.evidence),
                applicable_requirement_count=view.applicable_count,
                mapped_requirement_count=len(view.requirements),
            )
        )
    return out


@router.get("/controls", response_model=list[ControlOut])
async def list_controls(
    response: Response,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
    pagination: Pagination = Depends(pagination_params),
) -> list[ControlOut]:
    """Controls with their derived assessment attached.

    The list used to return the stored `status` field alone, which is
    why a control could read "Partially evidenced, 33%" on its own page
    and "not started" here. Both now come from
    app.compliance.control_assessment, assessed in one batch for the
    page rather than one query per row.
    """
    stmt = (
        select(Control)
        .where(Control.organization_id == context.organization_id)
        .order_by(Control.created_at.desc())
    )
    controls = await paginate(db, stmt, pagination, response)
    return await _controls_with_assessment(db, controls, context.organization_id)


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
        category=payload.category,
        priority=payload.priority,
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


async def _control_detail(
    db: AsyncSession, control: Control, organization_id: uuid.UUID
) -> ControlDetailOut:
    """Assemble a control with its requirements, assessments and evidence.

    Shared by the detail route and the mapping route so a caller who has
    just mapped a requirement sees the same shape back, rather than
    having to re-fetch to find out what changed.
    """
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
            Evidence.organization_id == organization_id,
        )
        .order_by(Evidence.created_at.desc())
    )
    # The same service the list uses, so the two screens cannot disagree.
    profile = await load_scoping_profile(db, organization_id=organization_id)
    assessment = await assess_control(db, control=control, profile=profile)
    summary = (await _controls_with_assessment(db, [control], organization_id))[0]

    return ControlDetailOut(
        **summary.model_dump(),
        requirements=[
            RequirementOut.model_validate(r) for r in requirements_result.scalars().all()
        ],
        assessments=[
            ControlAssessmentOut.model_validate(a) for a in assessments_result.scalars().all()
        ],
        evidence=[EvidenceOut.model_validate(e) for e in evidence_result.scalars().all()],
        # What the evidence actually supports, so the screen can lead with
        # an assessment rather than an empty pass/fail form.
        assessment=ControlAssessmentViewOut(
            **ControlAssessmentViewOut.model_validate(assessment).model_dump(
                exclude={
                    "ai_status",
                    "ai_label",
                    "human_status",
                    "human_label",
                    "effective_status",
                    "review_required",
                }
            ),
            ai_status=assessment.ai_status,
            ai_label=assessment.ai_label,
            human_status=assessment.human_status,
            human_label=(
                ASSESSMENT_LABELS.get(assessment.human_status, assessment.human_status)
                if assessment.human_status
                else None
            ),
            effective_status=assessment.effective_status,
            review_required=assessment.review_required,
        ),
    )


@router.post(
    "/controls/{control_id}/requirements",
    response_model=ControlDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def map_control_to_requirements(
    control_id: uuid.UUID,
    payload: ControlRequirementMapping,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.controls.manage")),
) -> ControlDetailOut:
    """Map an existing control to one or more requirements.

    Mapping used to be possible only when the control was created, which
    forced a duplicate control every time the same measure answered a
    second requirement — and one control satisfying several requirements
    is the normal case. Re-mapping an existing pair is a no-op rather
    than an error, so the button is safe to press twice.
    """
    control = await _get_org_control(db, control_id, context.organization_id)

    existing = set(
        (
            await db.execute(
                select(ControlMapping.requirement_id).where(
                    ControlMapping.control_id == control.id
                )
            )
        )
        .scalars()
        .all()
    )

    added: list[str] = []
    for requirement_id in payload.requirement_ids:
        requirement = await db.get(Requirement, requirement_id)
        if requirement is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found"
            )
        # Catalog requirements are global, but a *custom* framework's are
        # not — mapping to another tenant's private requirement would leak
        # its existence.
        framework = await db.get(Framework, requirement.framework_id)
        if framework is None or (
            framework.organization_id is not None
            and framework.organization_id != context.organization_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found"
            )
        if requirement_id in existing:
            continue
        db.add(ControlMapping(control_id=control.id, requirement_id=requirement_id))
        added.append(requirement.reference_code)

    if added:
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="compliance.control.mapped",
            object_type="control",
            object_id=str(control.id),
            after_state={"requirements": added},
        )
    await db.commit()
    return await _control_detail(db, control, context.organization_id)


@router.delete(
    "/controls/{control_id}/requirements/{requirement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def unmap_control_from_requirement(
    control_id: uuid.UUID,
    requirement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.controls.manage")),
) -> Response:
    """Remove a mapping. The control itself survives — it may still answer
    other requirements, and deleting it would take its evidence and
    assessment history with it."""
    control = await _get_org_control(db, control_id, context.organization_id)
    mapping = (
        await db.execute(
            select(ControlMapping).where(
                ControlMapping.control_id == control.id,
                ControlMapping.requirement_id == requirement_id,
            )
        )
    ).scalar_one_or_none()
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found")
    await db.delete(mapping)
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.control.unmapped",
        object_type="control",
        object_id=str(control.id),
        before_state={"requirement_id": str(requirement_id)},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/controls/{control_id}", response_model=ControlDetailOut)
async def get_control(
    control_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> ControlDetailOut:
    control = await _get_org_control(db, control_id, context.organization_id)
    return await _control_detail(db, control, context.organization_id)


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


async def _company_facts(
    db: AsyncSession, organization_id: uuid.UUID
) -> tuple[CompanyFacts, bool]:
    """Load declared facts. Second value is whether anything was declared."""
    profile = (
        await db.execute(
            select(OnboardingProfile).where(
                OnboardingProfile.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if profile is None:
        return CompanyFacts(), False

    facts = CompanyFacts(
        operates_in_eu=profile.operates_in_eu,
        sells_to_eu_customers=profile.sells_to_eu_customers,
        processes_personal_data=profile.processes_personal_data,
        processes_special_category_data=profile.processes_special_category_data,
        uses_third_party_ai=profile.uses_third_party_ai,
        builds_ai_features=profile.builds_ai_features,
        is_data_processor=profile.is_data_processor,
        sells_to_enterprise=profile.sells_to_enterprise,
        sector=profile.sector,
        employee_count_range=profile.employee_count_range,
    )
    declared = any(
        [
            facts.operates_in_eu,
            facts.sells_to_eu_customers,
            facts.processes_personal_data,
            facts.uses_third_party_ai,
            facts.builds_ai_features,
            facts.is_data_processor,
            facts.sells_to_enterprise,
            facts.sector is not None,
        ]
    )
    return facts, declared


async def _build_recommendations(
    db: AsyncSession, organization_id: uuid.UUID
) -> FrameworkRecommendationsOut:
    facts, declared = await _company_facts(db, organization_id)
    recommendations = recommend_frameworks(facts)

    frameworks = {
        f.key: f
        for f in (
            await db.execute(
                select(Framework).where(Framework.organization_id.is_(None))
            )
        )
        .scalars()
        .all()
    }
    active_keys = set(
        (
            await db.execute(
                select(Framework.key)
                .join(FrameworkActivation, FrameworkActivation.framework_id == Framework.id)
                .where(
                    FrameworkActivation.organization_id == organization_id,
                    FrameworkActivation.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )

    rows: list[FrameworkRecommendationOut] = []
    for recommendation in recommendations:
        framework = frameworks.get(recommendation.framework_key)
        rows.append(
            FrameworkRecommendationOut(
                framework_key=recommendation.framework_key,
                framework_id=framework.id if framework else None,
                framework_name=framework.name if framework else None,
                applicability=recommendation.applicability,
                reasons=recommendation.reasons,
                uncertainties=recommendation.uncertainties,
                requires_legal_review=recommendation.requires_legal_review,
                already_active=recommendation.framework_key in active_keys,
            )
        )
    return FrameworkRecommendationsOut(recommendations=rows, facts_declared=declared)


@router.put("/company-facts", response_model=FrameworkRecommendationsOut)
async def declare_company_facts(
    payload: CompanyFactsUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.frameworks.manage")),
) -> FrameworkRecommendationsOut:
    """Record what the organization is, and answer what applies to it."""
    profile = (
        await db.execute(
            select(OnboardingProfile).where(
                OnboardingProfile.organization_id == context.organization_id
            )
        )
    ).scalar_one_or_none()
    if profile is None:
        profile = OnboardingProfile(organization_id=context.organization_id)
        db.add(profile)

    for field_name, value in payload.model_dump().items():
        setattr(profile, field_name, value)

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.company_facts.declared",
        object_type="organization",
        object_id=str(context.organization_id),
        after_state=payload.model_dump(),
    )
    await db.commit()
    return await _build_recommendations(db, context.organization_id)


@router.get("/framework-recommendations", response_model=FrameworkRecommendationsOut)
async def get_framework_recommendations(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> FrameworkRecommendationsOut:
    """Which frameworks this organization has to satisfy, and why.

    Computed from declared facts by rules, never by a model — see
    app.compliance.framework_applicability for why applicability in
    particular has to be arguable rather than generated.
    """
    return await _build_recommendations(db, context.organization_id)


@router.post("/frameworks/adopt-recommended", response_model=list[FrameworkActivationOut])
async def adopt_recommended_frameworks(
    payload: AdoptRecommendedRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.frameworks.manage")),
) -> list[FrameworkActivation]:
    """Adopt several frameworks at once, scaffolding each one controls.

    Takes an explicit list rather than adopting everything recommended:
    adopting a framework commits the organization to evidencing it, and
    that stays a decision they made rather than one the product made for
    them.
    """
    frameworks = list(
        (
            await db.execute(
                select(Framework).where(
                    Framework.key.in_(payload.framework_keys),
                    Framework.organization_id.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    found = {f.key for f in frameworks}
    missing = sorted(set(payload.framework_keys) - found)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown framework: " + ", ".join(missing),
        )

    activations: list[FrameworkActivation] = []
    for framework in frameworks:
        activations.append(
            await set_framework_activation(
                db,
                organization_id=context.organization_id,
                framework=framework,
                active=True,
                actor_user_id=context.user.id,
            )
        )
    await db.commit()
    for activation in activations:
        await db.refresh(activation)
    return activations

@router.get("/connectors", response_model=ConnectorCatalogOut)
async def list_connectors(
    context: OrgContext = Depends(get_org_context),
) -> ConnectorCatalogOut:
    """The monitoring sources, each reporting its real state.

    Everything reads `coming_soon` today. The OAuth plumbing for
    several of these exists elsewhere in the codebase, but none of it
    produces compliance evidence yet, and a catalog implying otherwise
    would be the most damaging thing this module could ship.
    """
    connectors = [ConnectorOut.model_validate(connector) for connector in CONNECTORS]
    return ConnectorCatalogOut(
        connectors=connectors,
        available_count=sum(1 for c in connectors if c.status == "available"),
        coming_soon_count=sum(1 for c in connectors if c.status == "coming_soon"),
    )


@router.get("/evidence-events", response_model=list[EvidenceEventOut])
async def get_evidence_events(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[EvidenceEvent]:
    """Observations recorded against this organization.

    Empty until a connector is live. Deliberately not seeded with
    examples: simulated monitoring data presented as a customer's own
    is the one thing that would make every real number here suspect.
    """
    return await list_evidence_events(db, organization_id=context.organization_id)

@router.get("/dashboard", response_model=ComplianceDashboardOut)
async def get_compliance_dashboard(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> ComplianceDashboardOut:
    """Everything the executive view needs, in one call.

    Aggregated server-side rather than assembled from five requests in
    the browser: the numbers have to agree with each other, and five
    independent fetches resolving at different moments is how a
    dashboard ends up contradicting itself on screen.
    """
    _, declared = await _company_facts(db, context.organization_id)
    dashboard = await build_dashboard(
        db, organization_id=context.organization_id, facts_declared=declared
    )
    return ComplianceDashboardOut.model_validate(dashboard)

@router.get("/review-center", response_model=ReviewCenterOut)
async def get_review_center(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> ReviewCenterOut:
    """Everything waiting on a human decision, in one queue.

    The product argues that AI does the repetitive work and people
    handle exceptions. That only holds if the exceptions are in one
    place — spread across six screens it becomes "go and look
    everywhere", which is the job the customer was trying to stop
    doing.
    """
    facts, declared = await _company_facts(db, context.organization_id)
    recommended = applicable_framework_keys(facts) if declared else []

    review = await build_review_center(
        db,
        organization_id=context.organization_id,
        recommended_framework_keys=recommended,
    )

    return ReviewCenterOut(
        categories=[
            ReviewCategoryOut(
                key=category.key,
                label=category.label,
                description=category.description,
                count=category.count,
                items=[ReviewItemOut.model_validate(item) for item in category.items],
            )
            for category in review.categories
        ],
        total_needing_review=review.total_needing_review,
        auto_accepted_recently=review.auto_accepted_recently,
        proposals_recently=review.proposals_recently,
    )

@router.get("/overview", response_model=ComplianceOverviewOut)
async def get_compliance_overview(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> ComplianceOverviewOut:
    """Where the organization stands, for the Compliance screen itself.

    Evaluates the active frameworks and summarises them, so the last two
    steps of the promise — "assessment runs" and "readiness and missing
    items appear" — are visible where the customer uploaded the document,
    rather than only on a framework detail page they have to go and find.
    """
    activations = list(
        (
            await db.execute(
                select(Framework)
                .join(FrameworkActivation, FrameworkActivation.framework_id == Framework.id)
                .where(
                    FrameworkActivation.organization_id == context.organization_id,
                    FrameworkActivation.status == "active",
                )
                .order_by(Framework.name)
            )
        )
        .scalars()
        .all()
    )

    open_gaps = list(
        (
            await db.execute(
                select(ComplianceGap).where(
                    ComplianceGap.organization_id == context.organization_id,
                    ComplianceGap.status != "resolved",
                )
            )
        )
        .scalars()
        .all()
    )
    gaps_by_framework: dict[uuid.UUID, int] = {}
    for gap in open_gaps:
        gaps_by_framework[gap.framework_id] = gaps_by_framework.get(gap.framework_id, 0) + 1

    rows: list[FrameworkReadinessOut] = []
    for framework in activations:
        evaluations = await evaluate_framework(
            db, organization_id=context.organization_id, framework=framework
        )
        rows.append(
            FrameworkReadinessOut(
                framework_id=framework.id,
                framework_key=framework.key,
                framework_name=framework.name,
                readiness=ReadinessBreakdownOut.model_validate(summarize_readiness(evaluations)),
                open_gap_count=gaps_by_framework.get(framework.id, 0),
            )
        )

    proposals = await db.scalar(
        select(func.count(EvidenceSuggestion.id)).where(
            EvidenceSuggestion.organization_id == context.organization_id,
            EvidenceSuggestion.status == "proposed",
        )
    )
    processing = await db.scalar(
        select(func.count(File.id)).where(
            File.organization_id == context.organization_id,
            File.processing_status.in_(("uploaded", "parsing", "analyzing")),
        )
    )
    stale = await db.scalar(
        select(func.count(Control.id)).where(
            Control.organization_id == context.organization_id,
            Control.needs_reassessment.is_(True),
        )
    )

    return ComplianceOverviewOut(
        frameworks=rows,
        total_open_gaps=len(open_gaps),
        proposals_awaiting_review=int(proposals or 0),
        documents_processing=int(processing or 0),
        controls_needing_reassessment=int(stale or 0),
    )

async def _backfill_copilot_index(organization_id: uuid.UUID) -> None:
    """Index the backlog in its own session, after the response is sent."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await backfill_organization(db, organization_id=organization_id)


def _mapping_state(
    *, processing_status: str, has_controls: bool, mapping_count: int
) -> str:
    """Why a document has the mappings it has — or none.

    Three different situations that all look like "0 controls mapped" on
    screen, and telling them apart is the difference between a customer
    who understands what is happening and one who thinks the product
    failed:

    - `no_controls` — nothing to map to yet. The normal state of every
      organization before it adopts a framework, and not a failure: the
      document is read, classified, governed and searchable regardless.
    - `no_matches` — there were controls and this document evidenced
      none of them. A real answer about the document.
    - `mapped` — it evidences something.
    """
    if processing_status != "ready":
        return "not_analyzed"
    if mapping_count:
        return "mapped"
    return "no_controls" if not has_controls else "no_matches"


@router.get("/documents", response_model=list[ComplianceDocumentOut])
async def list_compliance_documents(
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[ComplianceDocumentOut]:
    """The document library with live processing state.

    The per-document suggestion counts are aggregated in one grouped
    query rather than per row — this list is polled while documents are
    processing, so an N+1 here would be a self-inflicted load spike.

    Opening this list also backfills anything the Copilot cannot yet
    see. Indexing was added after documents were already being
    processed, so every existing organization has a library the Copilot
    is blind to — and a migration cannot fix it, because embedding
    requires calling a provider. Doing it here rather than in a script
    somebody has to remember means it happens for every customer, once,
    the first time they look at their documents.
    """
    unindexed = int(
        (
            await db.execute(
                select(func.count())
                .select_from(File)
                .where(
                    File.organization_id == context.organization_id,
                    File.processing_status == "ready",
                    File.index_status == "pending",
                )
            )
        ).scalar_one()
    )
    if unindexed:
        # After the response. Embedding a backlog takes seconds per
        # document and the list must not block on it; the next poll shows
        # the documents flipping to indexed.
        background.add_task(_backfill_copilot_index, context.organization_id)

    files = list(
        (
            await db.execute(
                select(File)
                .where(
                    File.organization_id == context.organization_id,
                    # A row marked `duplicate` is a record that somebody
                    # uploaded bytes the organization already had. It is
                    # kept for the audit trail and pointed at the
                    # canonical document — it is not a second document,
                    # and rendering it as one produced the half-empty
                    # card with no classification, no evidence and no
                    # policy.
                    File.processing_status != "duplicate",
                )
                .order_by(File.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    counts = (
        await db.execute(
            select(
                EvidenceSuggestion.file_id,
                EvidenceSuggestion.status,
                func.count(EvidenceSuggestion.id),
            )
            .where(EvidenceSuggestion.organization_id == context.organization_id)
            .group_by(EvidenceSuggestion.file_id, EvidenceSuggestion.status)
        )
    ).all()
    by_file: dict[uuid.UUID, dict[str, int]] = {}
    for file_id, suggestion_status, count in counts:
        by_file.setdefault(file_id, {})[suggestion_status] = count

    # The governance record for each policy document, in one query. The
    # document row links straight to it rather than making the reader go
    # and find it on another screen.
    policy_rows = list(
        (
            await db.execute(
                select(Policy.file_id, Policy.id, Policy.title, Policy.status).where(
                    Policy.organization_id == context.organization_id,
                    Policy.file_id.is_not(None),
                )
            )
        ).all()
    )
    policy_by_file = {
        row[0]: (row[1], row[2], row[3]) for row in policy_rows if row[0] is not None
    }

    # Where each row opens. Resolved in one query rather than per row:
    # this list is polled while documents process, and the whole point of
    # the aggregate above is that it does not do N+1s.
    resolved_documents = await documents_for_files(
        db,
        organization_id=context.organization_id,
        file_ids=[file_record.id for file_record in files],
    )

    # Whether this organization has anything to map evidence *to*. A new
    # organization has not adopted a framework yet, so it has no controls
    # — and a document with no mappings because there is nothing to map
    # to is a different thing from one that matched nothing. Asked once
    # for the whole list rather than per row.
    has_controls = bool(
        (
            await db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == context.organization_id
                )
            )
        ).scalar_one()
    )

    # One row per logical document. A superseded version is not a second
    # document — it is the same document as it used to read — so it folds
    # into the row for its current version and contributes a number to the
    # version count rather than a row of its own.
    by_id = {row.id: row for row in files}
    versions_of: dict[uuid.UUID, int] = {}
    pending_on: set[uuid.UUID] = set()
    for row in files:
        head, seen = row, {row.id}
        while head.superseded_by_id is not None and len(seen) < 50:
            nxt = by_id.get(head.superseded_by_id)
            if nxt is None or nxt.id in seen:
                break
            seen.add(nxt.id)
            head = nxt
        versions_of[head.id] = versions_of.get(head.id, 0) + 1
        if row.version_candidate_id is not None and row.superseded_by_id is None:
            candidate = by_id.get(row.version_candidate_id)
            if candidate is not None:
                # Both ends of the question are flagged: the upload that
                # might be a new version, and the document it might be a
                # new version of. Until somebody decides, the library
                # genuinely does contain two rows for one document, and
                # saying so is better than letting it look like a bug.
                pending_on.add(candidate.id)
                pending_on.add(row.id)

    documents: list[ComplianceDocumentOut] = []
    for file_record in files:
        if file_record.superseded_by_id is not None:
            # History. Reachable from the version history on the document
            # it became, and from any citation that points into it.
            continue
        tally = by_file.get(file_record.id, {})
        out = ComplianceDocumentOut.model_validate(file_record)
        # The document's own title where there is one, so this row and
        # the page it opens call the document the same thing.
        indexed = resolved_documents.get(file_record.id)
        out.title = readable_title(
            indexed[1] if indexed else file_record.original_filename
        )
        out.document_id = indexed[0] if indexed else None
        out.href = document_detail_href(indexed[0]) if indexed else None
        out.proposed_count = tally.get("proposed", 0)
        # Auto-approved mappings are approved evidence — counted with the
        # ones a person approved, because that is what they are. Keeping
        # them out would show "0 proposals" over a document that produced
        # four pieces of evidence.
        out.approved_count = tally.get("approved", 0) + tally.get("auto_approved", 0)
        out.unverifiable_count = tally.get("unverifiable", 0)
        linked = policy_by_file.get(file_record.id)
        if linked is not None:
            out.policy_id, out.policy_title, out.policy_status = linked
        out.version_count = versions_of.get(file_record.id, 1)
        out.has_pending_version = file_record.id in pending_on
        out.mapping_state = _mapping_state(
            processing_status=file_record.processing_status,
            has_controls=has_controls,
            mapping_count=out.proposed_count + out.approved_count,
        )
        # What Veyntra produced, labelled as such and pointed back at
        # the record it came out of. Without this the library showed a
        # report beside the policies it was written from, offering to
        # analyse it for evidence.
        out.artifact_label = artifacts.ARTIFACT_LABELS.get(
            file_record.artifact_type or artifacts.SOURCE, "Source document"
        )
        out.origin_href = artifacts.origin_href(file_record)
        documents.append(out)
    return documents


@router.get("/documents/{document_id}/detail", response_model=DocumentDetailOut)
async def get_document_detail(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DocumentDetailOut:
    """One document: what it is, what Veyntra found in it, and what that
    supports.

    Addressed by the knowledge Document id, which is the identifier a
    Copilot citation already carries — so the library and a citation open
    the same URL. The page reads the document's text from the chunks
    endpoint; this is everything else it shows.
    """
    resolved = await file_for_document(
        db, organization_id=context.organization_id, document_id=document_id
    )
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    document, file_record = resolved

    # The evidence chain, in one query: suggestion -> control ->
    # requirement -> framework. Outer joins throughout, because a
    # suggestion may name a control without resolving which of its
    # requirements it speaks to, and that is a real state rather than a
    # row to hide.
    rows = list(
        (
            await db.execute(
                select(EvidenceSuggestion, Control, Requirement, Framework)
                .outerjoin(Control, Control.id == EvidenceSuggestion.control_id)
                .outerjoin(Requirement, Requirement.id == EvidenceSuggestion.requirement_id)
                .outerjoin(Framework, Framework.id == Requirement.framework_id)
                .where(
                    EvidenceSuggestion.organization_id == context.organization_id,
                    EvidenceSuggestion.file_id == file_record.id,
                )
                .order_by(EvidenceSuggestion.source_location, EvidenceSuggestion.created_at)
            )
        ).all()
    )

    evidence = [
        DocumentEvidenceOut(
            id=suggestion.id,
            source_location=suggestion.source_location,
            quoted_passage=suggestion.quoted_passage,
            evidence_type=suggestion.evidence_type,
            status=suggestion.status,
            confidence=suggestion.confidence,
            control_id=control.id if control else None,
            control_title=control.title if control else None,
            requirement_id=requirement.id if requirement else None,
            requirement_reference=requirement.reference_code if requirement else None,
            requirement_title=requirement.title if requirement else None,
            framework_name=framework.name if framework else None,
        )
        for suggestion, control, requirement, framework in rows
    ]

    # Distinct things, not rows. Four passages supporting one control is
    # one control, and reporting "4 controls" over it would be a count of
    # our own bookkeeping.
    counted = [item for item in evidence if item.status != "unverifiable"]
    controls = {item.control_id for item in counted if item.control_id}
    requirements = {item.requirement_id for item in counted if item.requirement_id}

    policy = (
        await db.execute(
            select(Policy).where(
                Policy.organization_id == context.organization_id,
                Policy.file_id == file_record.id,
            )
        )
    ).scalars().first()

    # Every version of this document, and — while one is proposed and
    # nobody has decided — what Veyntra thinks it is a newer version of.
    from app.compliance.version_promotion import version_history

    chain = await version_history(
        db, organization_id=context.organization_id, file_record=file_record
    )
    chain_ids = [row.id for row in chain]
    chain_documents = await documents_for_files(
        db, organization_id=context.organization_id, file_ids=chain_ids
    )
    evidence_by_file = dict(
        (
            await db.execute(
                select(Evidence.file_id, func.count(Evidence.id))
                .where(Evidence.file_id.in_(chain_ids))
                .group_by(Evidence.file_id)
            )
        ).all()
    )
    versions = [
        DocumentVersionOut(
            file_id=row.id,
            document_id=(chain_documents.get(row.id) or (None, None))[0],
            href=(
                document_detail_href(chain_documents[row.id][0])
                if row.id in chain_documents
                else None
            ),
            filename=row.original_filename,
            version_label=row.version_label,
            status="superseded" if row.superseded_by_id else "current",
            uploaded_at=row.created_at,
            uploaded_by=row.uploaded_by,
            evidence_count=int(evidence_by_file.get(row.id, 0)),
        )
        for row in chain
    ]

    candidate_out = None
    if file_record.version_candidate_id and file_record.superseded_by_id is None:
        candidate_file = await db.get(File, file_record.version_candidate_id)
        if candidate_file is not None and candidate_file.superseded_by_id is None:
            candidate_policy = (
                await db.execute(
                    select(Policy).where(Policy.file_id == candidate_file.id)
                )
            ).scalars().first()
            candidate_out = VersionCandidateOut(
                file_id=candidate_file.id,
                title=readable_title(candidate_file.original_filename),
                confidence=file_record.version_confidence or "medium",
                reasons=list(file_record.version_reasons or []),
                current_version=(
                    candidate_policy.version
                    if candidate_policy
                    else candidate_file.version_label
                ),
                current_effective_date=candidate_file.version_effective_date,
                current_approved_at=(
                    candidate_policy.approved_at if candidate_policy else None
                ),
                current_filename=candidate_file.original_filename,
                detected_version=file_record.version_label,
                detected_effective_date=file_record.version_effective_date,
                uploaded_filename=file_record.original_filename,
            )

    has_controls = bool(
        (
            await db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == context.organization_id
                )
            )
        ).scalar_one()
    )

    return DocumentDetailOut(
        document_id=document.id,
        file_id=file_record.id,
        mapping_state=_mapping_state(
            processing_status=file_record.processing_status,
            has_controls=has_controls,
            mapping_count=len(counted),
        ),
        versions=versions,
        version_label=file_record.version_label,
        version_candidate=candidate_out,
        href=document_detail_href(document.id),
        title=readable_title(document.title or file_record.original_filename),
        filename=file_record.original_filename,
        document_type=file_record.document_type,
        document_domain=file_record.document_domain,
        classification=file_record.classification,
        processing_status=file_record.processing_status,
        processing_error=file_record.processing_error,
        content_status=document.status,
        content_error=document.error,
        index_status=file_record.index_status,
        index_error=file_record.index_error,
        extracted_characters=file_record.extracted_characters,
        size_bytes=file_record.size_bytes,
        created_at=file_record.created_at,
        processed_at=file_record.processed_at,
        policy_id=policy.id if policy else None,
        policy_title=policy.title if policy else None,
        policy_status=policy.status if policy else None,
        evidence_count=len(counted),
        control_count=len(controls),
        requirement_count=len(requirements),
        proposed_count=sum(1 for item in evidence if item.status == "proposed"),
        approved_count=sum(
            1 for item in evidence if item.status in ("approved", "auto_approved")
        ),
        unverifiable_count=sum(1 for item in evidence if item.status == "unverifiable"),
        evidence=evidence,
    )


@router.get(
    "/documents/{document_id}/compare",
    response_model=VersionDiffOut,
)
async def compare_document_versions(
    document_id: uuid.UUID,
    against: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> VersionDiffOut:
    """What changed between this version and another one of the same document.

    `against` is the file id of the other version — always one from this
    document's own chain, so a request cannot be used to diff two
    unrelated documents against each other, or somebody else's.
    """
    from app.compliance.version_diff import compare_versions
    from app.compliance.version_promotion import version_history

    resolved = await file_for_document(
        db, organization_id=context.organization_id, document_id=document_id
    )
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    _, current = resolved

    chain = await version_history(
        db, organization_id=context.organization_id, file_record=current
    )
    other = next((row for row in chain if row.id == against), None)
    if other is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That is not another version of this document",
        )
    if other.id == current.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A version cannot be compared with itself",
        )

    # Oldest first, whichever way round the caller asked, so "added" and
    # "removed" always mean what the reader expects them to.
    order = [row.id for row in chain]
    previous, latest = (
        (other, current) if order.index(other.id) < order.index(current.id) else (current, other)
    )

    diff = await compare_versions(
        db, organization_id=context.organization_id, previous=previous, current=latest
    )
    return VersionDiffOut(
        previous_file_id=diff.previous_file_id,
        current_file_id=diff.current_file_id,
        previous_label=diff.previous_label,
        current_label=diff.current_label,
        headline=diff.headline,
        added=diff.added,
        removed=diff.removed,
        modified=diff.modified,
        unchanged=diff.unchanged,
        changes=[
            SectionChangeOut(
                change=change.change,
                section=change.section,
                summary=change.summary,
                previous_text=change.previous_text,
                current_text=change.current_text,
            )
            for change in diff.changes
        ],
    )


@router.post(
    "/documents/{document_id}/accept-version",
    response_model=VersionAcceptedOut,
)
async def accept_document_version(
    document_id: uuid.UUID,
    payload: AcceptVersionRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> VersionAcceptedOut:
    """Accept this document as the next version of an existing one.

    The explicit decision Veyntra never makes on its own. Everything
    downstream follows from it: the old version is superseded and kept,
    evidence whose passage survived carries its approval forward, evidence
    whose passage changed loses it, and a policy keeps its identity while
    needing review again.
    """
    from app.compliance.version_promotion import (
        VersionAlreadySuperseded,
        accept_new_version,
    )

    resolved = await file_for_document(
        db, organization_id=context.organization_id, document_id=document_id
    )
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    _, current = resolved

    previous = await db.get(File, payload.supersedes_file_id)
    if previous is None or previous.organization_id != context.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document to supersede not found"
        )
    if previous.id == current.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A document cannot be a new version of itself.",
        )
    if previous.superseded_by_id is not None and previous.superseded_by_id != current.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "That document has already been superseded by a newer version. "
                "Upload this against the current version instead."
            ),
        )

    try:
        report = await accept_new_version(
            db,
            organization_id=context.organization_id,
            previous=previous,
            current=current,
            actor_user_id=context.user.id,
            version_label=payload.version_label,
        )
    except VersionAlreadySuperseded as exc:
        # Lost the race to another acceptance. The chain is intact and
        # nothing of this attempt was written.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    current.version_candidate_id = None
    current.version_confidence = None
    current.version_reasons = []
    await db.commit()

    return VersionAcceptedOut(
        file_id=current.id,
        supersedes_file_id=previous.id,
        version_label=current.version_label,
        **report.as_dict(),
    )


@router.post(
    "/documents/{document_id}/separate-document",
    response_model=DocumentDetailOut,
)
async def keep_as_separate_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> DocumentDetailOut:
    """Decline the proposed version relationship.

    The proposal is cleared rather than remembered as a rejection: it was
    a guess, the person answered it, and asking again on every page load
    is how a product becomes something people click past.
    """
    resolved = await file_for_document(
        db, organization_id=context.organization_id, document_id=document_id
    )
    if resolved is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    _, file_record = resolved

    file_record.version_candidate_id = None
    file_record.version_confidence = None
    file_record.version_reasons = []
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="core.file.kept_as_separate_document",
        object_type="file",
        object_id=str(file_record.id),
        after_state={"filename": file_record.original_filename},
    )
    await db.commit()
    # The detail endpoint is the one place that assembles this payload;
    # calling it keeps a second copy of that assembly from existing.
    return await get_document_detail(document_id, db=db, context=context)


@router.post(
    "/documents/process",
    response_model=ComplianceDocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def process_compliance_document(
    payload: ProcessDocumentRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> ComplianceDocumentOut:
    """Start the read → classify → propose pipeline for a just-uploaded file.

    Returns 202 immediately and works in the background. Reading a policy
    end to end is a slow model call, and holding the request open for it
    would make the browser look hung during the exact step the product is
    selling — the client polls `GET /documents` for the lifecycle instead.
    """
    file_record = await db.get(File, payload.file_id)
    if file_record is None or file_record.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if file_record.processing_status in ("parsing", "analyzing"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document is already being processed.",
        )

    if payload.supersedes_file_id is not None:
        target = await db.get(File, payload.supersedes_file_id)
        if target is None or target.organization_id != context.organization_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The document this replaces was not found",
            )
        if target.id == file_record.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A document cannot be a new version of itself",
            )
        if target.superseded_by_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "That document has already been superseded by a newer version. "
                    "Upload this against the current version instead."
                ),
            )
        # Recorded as intent, linked only once the analysis has produced
        # the evidence there is to reconcile.
        file_record.version_candidate_id = target.id
        file_record.version_confidence = "confirmed"

    file_record.processing_status = "uploaded"
    file_record.processing_error = None
    await db.commit()

    background.add_task(
        process_document,
        file_record.id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
    )
    return ComplianceDocumentOut.model_validate(file_record)


@router.post("/evidence/analyze", response_model=AnalyzeDocumentResult)
async def analyze_document_for_evidence(
    payload: AnalyzeDocumentRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> AnalyzeDocumentResult:
    """Read an uploaded document and propose which controls it evidences.

    Proposals are not evidence: they land in a review queue, the
    assessment ignores them, and approving one is what creates the
    evidence row. Every proposal must quote the document, and the quote
    is checked against the extracted text before it is offered — see
    `app.compliance.evidence_ai` for why that check is the load-bearing
    part of this feature.
    """
    file_record = await db.get(File, payload.file_id)
    if file_record is None or file_record.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # A report Veyntra wrote from the compliance record is not a source
    # of evidence for it. Refused here rather than filtered in a query,
    # so whoever asked is told why instead of watching a request come
    # back empty.
    try:
        await artifacts.guard_analysis(file_record)
    except artifacts.EvidenceRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    try:
        file_bytes = download_object(file_record.storage_key)
    except Exception as exc:  # noqa: BLE001 - storage faults must not read as AI faults
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The document could not be read from storage.",
        ) from exc

    try:
        outcome = await suggest_evidence_mappings(
            db,
            organization_id=context.organization_id,
            file_record=file_record,
            file_bytes=file_bytes,
            actor_user_id=context.user.id,
        )
    except UnsupportedFormatError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"This file type cannot be read for evidence analysis: {exc}",
        ) from exc
    # AI provider failures propagate untouched — app.main's handler turns
    # them into an actionable status rather than an opaque 500, and a
    # provider outage must never be reported as "no matches found".

    await db.commit()
    return AnalyzeDocumentResult(
        suggestions=[EvidenceSuggestionOut.model_validate(s) for s in outcome.suggestions],
        controls_considered=outcome.considered_controls,
        unverifiable_count=outcome.unverifiable_count,
    )


@router.get("/evidence/suggestions", response_model=list[EvidenceSuggestionOut])
async def list_evidence_suggestions(
    status_filter: str | None = None,
    file_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[EvidenceSuggestion]:
    stmt = select(EvidenceSuggestion).where(
        EvidenceSuggestion.organization_id == context.organization_id
    )
    if status_filter:
        stmt = stmt.where(EvidenceSuggestion.status == status_filter)
    if file_id:
        stmt = stmt.where(EvidenceSuggestion.file_id == file_id)
    result = await db.execute(stmt.order_by(EvidenceSuggestion.created_at.desc()))
    return list(result.scalars().all())


async def _get_org_suggestion(
    db: AsyncSession, suggestion_id: uuid.UUID, organization_id: uuid.UUID
) -> EvidenceSuggestion:
    suggestion = await db.get(EvidenceSuggestion, suggestion_id)
    if suggestion is None or suggestion.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found")
    return suggestion


@router.post(
    "/evidence/suggestions/{suggestion_id}/approve",
    response_model=EvidenceOut,
    status_code=status.HTTP_201_CREATED,
)
async def approve_evidence_suggestion(
    suggestion_id: uuid.UUID,
    payload: ApproveSuggestionRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> Evidence:
    """Accept a proposal and create the evidence.

    The moment a person takes responsibility for the link. An
    unverifiable suggestion cannot reach here — approving a citation that
    is not in the document would put a fabricated quote into the evidence
    record under a human's name.
    """
    suggestion = await _get_org_suggestion(db, suggestion_id, context.organization_id)
    try:
        evidence = await approve_suggestion(
            db,
            organization_id=context.organization_id,
            suggestion=suggestion,
            title=payload.title,
            actor_user_id=context.user.id,
        )
    except SuggestionDecisionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(evidence)

    # Close the loop the customer was promised: approving evidence
    # re-runs the assessment for the frameworks this control serves, so
    # readiness and the gap list reflect the decision without the user
    # having to find the framework screen and press a button. Runs in the
    # background because assessing a whole framework is slower than the
    # click that triggered it, and the approval itself is already durable.
    background.add_task(
        reassess_frameworks_for_control,
        suggestion.control_id,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
    )
    return evidence


@router.post(
    "/evidence/suggestions/{suggestion_id}/reject", response_model=EvidenceSuggestionOut
)
async def reject_evidence_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> EvidenceSuggestion:
    suggestion = await _get_org_suggestion(db, suggestion_id, context.organization_id)
    await reject_suggestion(
        db,
        organization_id=context.organization_id,
        suggestion=suggestion,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(suggestion)
    return suggestion


@router.get("/evidence/by-document", response_model=list[GroupedEvidenceOut])
async def list_evidence_by_document(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[GroupedEvidenceOut]:
    """Evidence grouped by the document it came from.

    A document mapped to six controls produced six evidence rows, and
    the library rendered one card each — six identical filenames, which
    reads as six documents. The mappings are untouched in the database;
    this is the same data shaped the way a person understands it: one
    document, several statements, several controls.
    """
    evidence_rows = list(
        (
            await db.execute(
                select(Evidence, File, Control)
                .join(File, File.id == Evidence.file_id)
                .outerjoin(Control, Control.id == Evidence.control_id)
                .where(Evidence.organization_id == context.organization_id)
                .order_by(Evidence.created_at.desc())
            )
        ).all()
    )

    # One query for provenance rather than one per evidence row: this
    # list is rendered whole, and an N+1 here scales with the customer's
    # document count.
    suggestions = {
        suggestion.evidence_id: suggestion
        for suggestion in (
            await db.execute(
                select(EvidenceSuggestion).where(
                    EvidenceSuggestion.organization_id == context.organization_id,
                    EvidenceSuggestion.evidence_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    }

    grouped: dict[uuid.UUID, GroupedEvidenceOut] = {}
    controls_seen: dict[uuid.UUID, set[uuid.UUID]] = {}

    for evidence, file_record, control in evidence_rows:
        group = grouped.get(file_record.id)
        if group is None:
            group = GroupedEvidenceOut(
                file_id=file_record.id,
                filename=file_record.original_filename,
                title=readable_title(file_record.original_filename),
                document_type=file_record.document_type,
                document_domain=file_record.document_domain,
                processing_status=file_record.processing_status,
                evidence_count=0,
                control_count=0,
                mappings=[],
            )
            grouped[file_record.id] = group
            controls_seen[file_record.id] = set()

        suggestion = suggestions.get(evidence.id)
        group.mappings.append(
            EvidenceMappingOut(
                evidence_id=evidence.id,
                control_id=evidence.control_id or uuid.UUID(int=0),
                control_title=control.title if control else evidence.title,
                source_location=suggestion.source_location if suggestion else None,
                evidence_type=suggestion.evidence_type if suggestion else None,
                quoted_passage=suggestion.quoted_passage if suggestion else None,
                confidence=suggestion.confidence if suggestion else None,
                mapped_by=(
                    "auto"
                    if suggestion and suggestion.status == "auto_approved"
                    else "human"
                    if suggestion
                    else "manual"
                ),
            )
        )
        group.evidence_count += 1
        if evidence.control_id:
            controls_seen[file_record.id].add(evidence.control_id)

    # Where each document opens — the same Document Detail route the
    # library and a Copilot citation use. One query for the whole list.
    resolved_documents = await documents_for_files(
        db, organization_id=context.organization_id, file_ids=list(grouped)
    )
    for file_id, group in grouped.items():
        group.control_count = len(controls_seen[file_id])
        indexed = resolved_documents.get(file_id)
        if indexed is not None:
            # Same name and same route as the library row and a Copilot
            # citation. One document, one identity.
            group.title = readable_title(indexed[1])
            group.document_href = document_detail_href(indexed[0])

    return list(grouped.values())


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
    dpia: DPIA | None = None
    if payload.dpia_id is not None:
        dpia = await db.get(DPIA, payload.dpia_id)
        if dpia is None or dpia.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DPIA not found")
        if dpia.status == dpia_workflow.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "This DPIA is complete and its record is frozen. Start a "
                    "reassessment rather than adding to what was concluded."
                ),
            )

    risk = Risk(organization_id=context.organization_id, **payload.model_dump())
    db.add(risk)
    await db.flush()
    if dpia is not None:
        # §10's "Add risk" is a completed risk review too: a risk on the
        # register is what "risks were identified" means, however it got
        # there.
        await dpia_workflow.note_risks_identified(
            db,
            organization_id=context.organization_id,
            dpia=dpia,
            actor_user_id=context.user.id,
        )
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


async def _policy_out(
    db: AsyncSession, policy: Policy, organization_id: uuid.UUID
) -> PolicyOut:
    """One policy with the counts its row shows.

    The control and framework figures come from the evidence the linked
    document already produced — not a second mapping table the customer
    would have to maintain by hand.
    """
    filename: str | None = None
    document_href: str | None = None
    evidence_count = 0
    control_ids: list[uuid.UUID] = []
    framework_names: list[str] = []

    if policy.file_id is not None:
        file_record = await db.get(File, policy.file_id)
        filename = file_record.original_filename if file_record else None
        # The same Document Detail route every other surface uses, so
        # "Current document" opens the document rather than describing it.
        linked = await documents_for_files(
            db, organization_id=policy.organization_id, file_ids=[policy.file_id]
        )
        indexed = linked.get(policy.file_id)
        document_href = document_detail_href(indexed[0]) if indexed else None

        rows = list(
            (
                await db.execute(
                    select(Evidence.control_id)
                    .where(
                        Evidence.organization_id == organization_id,
                        Evidence.file_id == policy.file_id,
                        Evidence.control_id.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        evidence_count = len(rows)
        control_ids = list({row for row in rows if row is not None})

        if control_ids:
            framework_names = [
                str(name)
                for name in (
                    await db.execute(
                        select(Framework.name)
                        .join(Requirement, Requirement.framework_id == Framework.id)
                        .join(
                            ControlMapping,
                            ControlMapping.requirement_id == Requirement.id,
                        )
                        .where(ControlMapping.control_id.in_(control_ids))
                        .distinct()
                    )
                )
                .scalars()
                .all()
            ]

    return PolicyOut(
        **PolicyOut.model_validate(policy).model_dump(
            exclude={
                "review_state",
                "days_until_review",
                "missing_governance",
                "document_filename",
                "document_href",
                "evidence_count",
                "control_count",
                "framework_names",
            }
        ),
        review_state=policy_review_state(policy),
        days_until_review=policy_days_until_review(policy),
        missing_governance=policy_missing_governance(policy),
        document_filename=filename,
        document_href=document_href,
        evidence_count=evidence_count,
        control_count=len(control_ids),
        framework_names=sorted(framework_names),
    )


@router.get("/policies", response_model=list[PolicyOut])
async def list_policies(
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[PolicyOut]:
    """Every policy, governed or not.

    Opening this list also creates governance records for policy
    documents uploaded before detection existed. Without it an existing
    customer sees "no policies" beside ten policy documents, which is
    the exact confusion this feature was built to remove — and a
    migration cannot do it, because it needs the classifier's output.
    """
    ungoverned = int(
        (
            await db.execute(
                select(func.count())
                .select_from(File)
                .outerjoin(Policy, Policy.file_id == File.id)
                .where(
                    File.organization_id == context.organization_id,
                    File.processing_status == "ready",
                    File.document_type.is_not(None),
                    Policy.id.is_(None),
                )
            )
        ).scalar_one()
    )
    if ungoverned:
        background.add_task(_backfill_policies, context.organization_id)

    policies = list(
        (
            await db.execute(
                select(Policy)
                .where(Policy.organization_id == context.organization_id)
                .order_by(Policy.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        await _policy_out(db, policy, context.organization_id) for policy in policies
    ]


async def _backfill_policies(organization_id: uuid.UUID) -> None:
    """Detect governance records for already-uploaded policies."""
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await policy_backfill(db, organization_id=organization_id)


@router.get("/policies/{policy_id}", response_model=PolicyDetailOut)
async def get_policy(
    policy_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> PolicyDetailOut:
    """One policy, its version history, and the controls its evidence
    supports."""
    policy = await _get_org_policy(db, policy_id, context.organization_id)
    base = await _policy_out(db, policy, context.organization_id)

    version_rows = list(
        (
            await db.execute(
                select(PolicyVersion, File.original_filename)
                .outerjoin(File, File.id == PolicyVersion.file_id)
                .where(PolicyVersion.policy_id == policy.id)
                .order_by(PolicyVersion.created_at.desc())
            )
        ).all()
    )
    versions = [
        PolicyVersionOut(
            **PolicyVersionOut.model_validate(row).model_dump(exclude={"filename"}),
            filename=filename,
        )
        for row, filename in version_rows
    ]

    controls: list[PolicyControlOut] = []
    index_status: str | None = None
    if policy.file_id is not None:
        file_record = await db.get(File, policy.file_id)
        index_status = file_record.index_status if file_record else None

        control_ids = list(
            {
                row
                for row in (
                    await db.execute(
                        select(Evidence.control_id).where(
                            Evidence.organization_id == context.organization_id,
                            Evidence.file_id == policy.file_id,
                            Evidence.control_id.is_not(None),
                        )
                    )
                )
                .scalars()
                .all()
                if row is not None
            }
        )
        if control_ids:
            control_rows = list(
                (
                    await db.execute(
                        select(Control)
                        .where(Control.id.in_(control_ids))
                        .order_by(Control.title)
                    )
                )
                .scalars()
                .all()
            )
            summaries = await _controls_with_assessment(
                db, control_rows, context.organization_id
            )
            controls = [
                PolicyControlOut(
                    id=summary.id,
                    title=summary.title,
                    assessment_status=summary.assessment_status,
                    assessment_label=summary.assessment_label,
                )
                for summary in summaries
            ]

    return PolicyDetailOut(
        **base.model_dump(),
        versions=versions,
        controls=controls,
        document_index_status=index_status,
    )


@router.patch("/policies/{policy_id}/governance", response_model=PolicyOut)
async def update_policy_governance(
    policy_id: uuid.UUID,
    payload: PolicyGovernanceUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.policies.manage")),
) -> PolicyOut:
    """Fill in what detection could not know.

    Only the fields sent are touched, so telling us the owner today does
    not clear the review date somebody set last week.
    """
    policy = await _get_org_policy(db, policy_id, context.organization_id)
    before = {
        "owner_id": str(policy.owner_id) if policy.owner_id else None,
        "version": policy.version,
        "next_review_at": policy.next_review_at.isoformat()
        if policy.next_review_at
        else None,
    }

    updates = payload.model_dump(exclude_unset=True)
    if "owner_id" in updates and updates["owner_id"] is not None:
        member = (
            await db.execute(
                select(Membership).where(
                    Membership.user_id == updates["owner_id"],
                    Membership.organization_id == context.organization_id,
                    Membership.status == "active",
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
    for field, value in updates.items():
        setattr(policy, field, value)

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.policy.governance_updated",
        object_type="policy",
        object_id=str(policy.id),
        before_state=before,
        after_state={key: str(value) for key, value in updates.items()},
    )
    await db.commit()
    await db.refresh(policy)
    return await _policy_out(db, policy, context.organization_id)


@router.post("/policies/{policy_id}/approve", response_model=PolicyOut)
async def approve_policy_endpoint(
    policy_id: uuid.UUID,
    payload: PolicyApproveRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.policies.manage")),
) -> PolicyOut:
    """A person approves this policy.

    Only a person reaches this. Automatic detection never sets
    `approved` — approval is an organizational act, and a product that
    performs it on the customer's behalf is forging a record.
    """
    policy = await _get_org_policy(db, policy_id, context.organization_id)
    await approve_policy_record(
        db,
        organization_id=context.organization_id,
        policy=policy,
        actor_user_id=context.user.id,
        note=payload.note,
    )
    await db.commit()
    await db.refresh(policy)
    return await _policy_out(db, policy, context.organization_id)


@router.post("/policies/{policy_id}/versions", response_model=PolicyDetailOut)
async def add_policy_version(
    policy_id: uuid.UUID,
    payload: PolicyVersionUploadRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.policies.manage")),
) -> PolicyDetailOut:
    """Make an uploaded document this policy's current version.

    The previous document is marked superseded, never deleted, and the
    approval does not carry over: a new document is a new thing to sign
    off.
    """
    policy = await _get_org_policy(db, policy_id, context.organization_id)
    file_record = await db.get(File, payload.file_id)
    if file_record is None or file_record.organization_id != context.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    await promote_policy_version(
        db,
        organization_id=context.organization_id,
        policy=policy,
        file_record=file_record,
        actor_user_id=context.user.id,
        version=payload.version,
    )
    await db.commit()
    return await get_policy(policy_id, db=db, context=context)


@router.post(
    "/documents/backfill-classification", response_model=ClassificationBackfillOut
)
async def backfill_document_classification(
    dry_run: bool = True,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> ClassificationBackfillOut:
    """Classify documents that were read before classification ran on its own.

    Classification used to be a by-product of the control-mapping call,
    so a document uploaded while the organization had no controls came
    back with no type — and without a type there is no Managed Policy.
    Those documents are still here, still readable, still indexed. This
    finishes the job on them rather than asking anybody to upload them
    again.

    Idempotent: a document that already has a classification is left
    alone. `dry_run` defaults to true.
    """
    report = await backfill_classification(
        context.organization_id,
        actor_user_id=context.user.id,
        dry_run=dry_run,
    )
    return ClassificationBackfillOut(
        examined=report.examined,
        classified=report.classified,
        policies_created=report.policies_created,
        failed=report.failed,
        dry_run=dry_run,
    )


@router.post("/documents/backfill-versions", response_model=VersionBackfillOut)
async def backfill_document_versions(
    dry_run: bool = True,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> VersionBackfillOut:
    """Find version relationships among documents uploaded before
    detection existed.

    Proposes; never links. Accepting a version supersedes a document,
    moves what counts as current evidence and reopens approvals — doing
    that in bulk, retroactively, on a similarity score would rewrite
    compliance history for documents nobody was looking at.

    `dry_run` defaults to true on purpose: the first thing anybody should
    do with a bulk pass over a customer's library is read what it would
    do. Idempotent either way.
    """
    from app.compliance.version_backfill import backfill_version_candidates

    report = await backfill_version_candidates(
        db, organization_id=context.organization_id, dry_run=dry_run
    )
    if not dry_run:
        await db.commit()
    return VersionBackfillOut(**report.as_dict(), dry_run=dry_run)


@router.post("/policies/backfill", response_model=PolicyBackfillOut)
async def backfill_policies(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.policies.manage")),
) -> PolicyBackfillOut:
    """Detect governance records for documents uploaded before detection
    existed. Idempotent — safe to run whenever."""
    counts = await policy_backfill(
        db, organization_id=context.organization_id, actor_user_id=context.user.id
    )
    return PolicyBackfillOut(**counts)


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
        description=payload.description,
        internal_users=payload.internal_users,
        affected_users=payload.affected_users,
        processed_data=payload.processed_data,
        actor_user_id=context.user.id,
    )

    # The privacy implications of a new AI system are knowable the moment
    # it is registered, so they are drafted then. Proposals only —
    # nothing here creates a RoPA entry or a transfer — and the same
    # `source_key` that makes re-analysis idempotent makes this safe to
    # run on every registration.
    await privacy_suggestions.analyse(db, organization_id=context.organization_id)

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


@router.get("/ai-systems/governance", response_model=AIGovernanceOverviewOut)
async def get_ai_governance_overview(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> AIGovernanceOverviewOut:
    """Every AI system with what is documented, missing and outstanding.

    Computed deterministically from declared facts and what is linked
    to each system — see app.compliance.ai_system_governance. The
    output is a checklist the customer will be held to, so it has to
    be the same checklist every time they look.
    """
    systems = list(
        (
            await db.execute(
                select(AISystem)
                .where(AISystem.organization_id == context.organization_id)
                .order_by(AISystem.name)
            )
        )
        .scalars()
        .all()
    )

    rows = [await assess_ai_system(db, system=system) for system in systems]

    return AIGovernanceOverviewOut(
        systems=[AISystemGovernanceOut.model_validate(row) for row in rows],
        total_systems=len(rows),
        high_risk_systems=sum(
            1 for row in rows if row.risk_classification in ("high", "unacceptable")
        ),
        systems_without_screening=sum(1 for row in rows if not row.has_current_screening),
        total_open_actions=sum(len(row.required_actions) for row in rows),
    )


@router.patch("/ai-systems/{ai_system_id}/governance", response_model=AISystemOut)
async def update_ai_system_governance(
    ai_system_id: uuid.UUID,
    payload: AISystemGovernanceUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.ai_systems.manage")),
) -> AISystem:
    """Record the governance facts for one system.

    Partial by design: an inventory entry is filled in over time by
    different people, and requiring the whole record on every edit
    would mean whoever knows the model name has to guess at oversight.
    """
    system = await db.get(AISystem, ai_system_id)
    if system is None or system.organization_id != context.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found"
        )

    before = {
        field_name: getattr(system, field_name)
        for field_name in payload.model_dump(exclude_unset=True)
    }
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        setattr(system, field_name, value)

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.ai_system.governance_updated",
        object_type="ai_system",
        object_id=str(system.id),
        before_state=before,
        after_state=payload.model_dump(exclude_unset=True),
    )
    await db.commit()
    await db.refresh(system)
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


@router.get(
    "/processing-activities/title-repairs",
    response_model=list[RopaTitleRepairOut],
)
async def list_ropa_title_repairs(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[RopaTitleRepairOut]:
    """Activities whose title names who rather than what.

    Declared before `/processing-activities/{activity_id}` so the
    literal path wins — FastAPI matches in definition order and a UUID
    parameter would swallow it.
    """
    repairs = await ropa_titles.find_title_repairs(
        db, organization_id=context.organization_id
    )
    return [
        RopaTitleRepairOut(
            activity_id=repair.activity_id,
            current_title=repair.current_title,
            problem=RopaTitleProblemOut(
                kind=repair.problem.kind, message=repair.problem.message
            ),
            suggested_title=repair.suggested_title,
            suggestion_reason=repair.suggestion_reason,
        )
        for repair in repairs
    ]


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
    # §2: the organization answers who is processing; the activity
    # answers what is being processed. A title that borrows the first
    # identity leaves the second unrecorded, which is the one Article 30
    # asks for.
    problem = await ropa_titles.identity_conflict(
        db, organization_id=context.organization_id, title=payload.name
    )
    if problem is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=problem.message
        )

    fields = payload.model_dump()
    # §7: an activity missing a decision only a person can make is a
    # draft. Recording it as active would put an incomplete claim into
    # the register and stop the overview asking about it.
    incomplete = not (fields.get("legal_basis") or "") or not (
        fields.get("retention_period") or ""
    ).strip()
    fields["legal_basis"] = fields.get("legal_basis") or ""
    fields["retention_period"] = (fields.get("retention_period") or "").strip()

    activity = ProcessingActivity(
        organization_id=context.organization_id, **fields
    )
    if incomplete:
        activity.status = "draft"
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


@router.get("/dpias/prefill", response_model=DpiaContextOut)
async def get_dpia_prefill(
    processing_activity_id: uuid.UUID | None = None,
    ai_system_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DpiaContextOut:
    """What is already known about the processing being assessed.

    The DPIA flow used to open on a title and a risk dropdown — which
    asks somebody to classify the risk before the screening that exists
    to establish it, and then to retype facts sitting in the record they
    are assessing. This returns those facts, plus the screening answers
    the record already supports, each with the reason it was proposed.

    Declared before `/dpias/{dpia_id}` so the literal path wins: FastAPI
    matches in definition order and a UUID parameter would swallow it.
    """
    if processing_activity_id is None and ai_system_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Name what is being assessed: a processing activity or an AI "
                "system."
            ),
        )
    built = await dpia_prefill.build_context(
        db,
        organization_id=context.organization_id,
        processing_activity_id=processing_activity_id,
        ai_system_id=ai_system_id,
    )
    if built is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Record not found"
        )

    def link(entry) -> DpiaLinkedRecordOut:
        return DpiaLinkedRecordOut(
            id=entry.id, label=entry.label, kind=entry.kind, detail=entry.detail
        )

    return DpiaContextOut(
        title=built.title,
        purpose=built.purpose,
        data_subjects=built.data_subjects,
        data_categories=list(built.data_categories),
        special_category=built.special_category,
        processing_activity_id=built.processing_activity_id,
        ai_system_id=built.ai_system_id,
        owner_id=built.owner_id,
        ai_systems=[link(entry) for entry in built.ai_systems],
        vendors=[link(entry) for entry in built.vendors],
        transfers=[link(entry) for entry in built.transfers],
        evidence_count=built.evidence_count,
        suggested_answers=[
            DpiaSuggestedAnswerOut(
                criterion=answer.criterion, value=answer.value, reason=answer.reason
            )
            for answer in built.suggested_answers
        ],
        unknown=list(built.unknown),
    )


@router.post("/dpias/screening/start", response_model=DpiaWorkflowOut)
async def start_dpia_screening(
    payload: DpiaScreeningStartIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DpiaWorkflowOut:
    """Open — or find — the DPIA for this processing, and screen it.

    Reuses the existing record rather than creating a second one.
    Screening the same activity twice must reach the same DPIA: two
    half-finished assessments for one activity is an auditor asking
    which is authoritative.

    The answers Veyntra can support from the record are applied first,
    then whatever the person supplied — so a reviewer's answer always
    wins over a suggestion.
    """
    activity: ProcessingActivity | None = None
    if payload.processing_activity_id is not None:
        activity = await _get_org_processing_activity(
            db, payload.processing_activity_id, context.organization_id
        )

    dpia = await dpia_workflow.existing_for(
        db,
        organization_id=context.organization_id,
        processing_activity_id=payload.processing_activity_id,
        ai_system_id=payload.ai_system_id,
    )
    reused = dpia is not None

    if dpia is None:
        title = (
            f"{activity.name} DPIA"
            if activity is not None
            else (payload.title or "DPIA")
        )
        dpia = DPIA(
            organization_id=context.organization_id,
            processing_activity_id=payload.processing_activity_id,
            ai_system_id=payload.ai_system_id,
            title=title,
            # No risk level. Nobody has assessed anything yet, and a
            # default here is the bug this endpoint exists to stop.
            risk_level=None,
            status=dpia_workflow.SCREENING,
            owner_id=context.user.id,
        )
        db.add(dpia)
        await db.flush()
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="compliance.dpia.created",
            object_type="dpia",
            object_id=str(dpia.id),
            after_state={"title": dpia.title, "status": dpia.status},
        )

    processing = (
        await dpia_workflow.context_for(db, activity=activity)
        if activity is not None
        else None
    )
    answers = dict(payload.answers or {})
    if processing is not None:
        merged = dpia_workflow.suggested_answers(processing)
        merged.update(answers)
        answers = merged

    await dpia_workflow.record_screening(
        db,
        organization_id=context.organization_id,
        dpia=dpia,
        answers=answers,
        actor_user_id=context.user.id,
    )
    # Propose the risks the record implies now, so they are waiting the
    # moment the assessment opens. Reconciling by source key means
    # screening the same activity again refreshes rather than duplicates.
    await _reconcile_dpia_risks(
        db,
        organization_id=context.organization_id,
        dpia=dpia,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(dpia)

    view = await _workflow_view(
        db, organization_id=context.organization_id, dpia=dpia
    )
    view.reused_existing = reused
    return view


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
    if dpia.status == dpia_workflow.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This DPIA is complete and its record is frozen. Start a "
                "reassessment rather than editing what was concluded."
            ),
        )
    supplied = payload.model_dump(exclude_unset=True)
    changed = [
        field
        for field, value in supplied.items()
        if (getattr(dpia, field) or "") != (value or "")
    ]
    for field, value in supplied.items():
        setattr(dpia, field, value)
    # An approval is a statement about particular words. Keeping the tick
    # after those words are rewritten would leave the record saying
    # somebody approved text they never saw.
    dpia_workflow.unreview_changed_sections(dpia, changed)
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
    # Article 36(1): a high residual rating is the case a controller
    # cannot sign off alone, so the approval is raised from the rating
    # itself rather than from somebody later trying to complete.
    await dpia_approval.sync_high_residual_approval(
        db,
        organization_id=context.organization_id,
        dpia=dpia,
        actor_user_id=context.user.id,
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
    # One lifecycle, and it is not a free-text field. Without this the
    # dropdown could move a DPIA straight from screening to approved,
    # skipping the decision the screening exists to capture.
    refusal = dpia_workflow.transition_refusal(dpia.status, payload.status)
    if refusal is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=refusal
        )
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
        notes=payload.notes,
        actor_user_id=context.user.id,
    )
    # Verifying moves the request on; the stored phase follows the record
    # rather than waiting for somebody to notice.
    await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    await db.refresh(dsar)
    return dsar


def _scope_out(row) -> DsarScopeSourceOut:
    return DsarScopeSourceOut(
        id=row.id,
        source_key=row.source_key,
        kind=row.kind,
        name=row.name,
        reason=row.reason,
        relevance=row.relevance,
        relevance_reason=row.relevance_reason,
        linked_systems=list(row.linked_systems or []),
        potential_sources=list(row.potential_sources or []),
        search_capability=row.search_capability,
        included=row.included,
        added_by_user=row.added_by_user,
        record_id=row.record_id,
    )


def _dsar_item_out(row) -> DsarDiscoveredItemOut:
    return DsarDiscoveredItemOut(
        id=row.id,
        source_key=row.source_key,
        source_name=row.source_name,
        search_state=row.search_state,
        matches=row.matches,
        record_ids=[str(value) for value in (row.record_ids or [])],
        state_detail=row.state_detail,
        review_decision=row.review_decision,
        review_reason=row.review_reason,
        reviewed_at=row.reviewed_at,
        sensitivity_flags=list(row.sensitivity_flags or []),
        task_id=row.task_id,
    )


def _workflow_out(state) -> DsarWorkflowOut:
    return DsarWorkflowOut(
        phase=state.phase,
        phase_label=state.phase_label,
        next_action=(
            DsarNextActionOut(
                label=state.next_action.label,
                detail=state.next_action.detail,
                anchor=state.next_action.anchor,
            )
            if state.next_action
            else None
        ),
        blockers=[
            DsarBlockerOut(code=b.code, message=b.message, anchor=b.anchor)
            for b in state.blockers
        ],
        scope_total=state.scope_total,
        scope_included=state.scope_included,
        scope_undecided=state.scope_undecided,
        discovered_total=state.discovered_total,
        needs_review=state.needs_review,
        manual_follow_ups=state.manual_follow_ups,
        open_follow_ups=state.open_follow_ups,
        package_status=state.package_status,
    )


@router.get("/dsars/{dsar_id}/workflow", response_model=DsarWorkflowOut)
async def get_dsar_workflow(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DsarWorkflowOut:
    """Where this request is, and the single next thing to do.

    Derived on read. A phase somebody could set by hand would stop
    describing reality the first time it was convenient.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    state = await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    return _workflow_out(state)


@router.get("/dsars/{dsar_id}/scope", response_model=list[DsarScopeSourceOut])
async def get_dsar_scope(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[DsarScopeSourceOut]:
    """The ranked candidate sources, and what has been decided about them.

    Suggestions are reconciled on read so the ranking reflects the
    current register. Decisions already made are preserved -- a source
    somebody excluded does not come back included because the register
    changed.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    rows = await dsar_scope.reconcile(
        db, organization_id=context.organization_id, dsar=dsar
    )
    await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    return [_scope_out(row) for row in sorted(rows, key=dsar_scope.sort_key)]


@router.post("/dsars/{dsar_id}/scope/confirm", response_model=list[DsarScopeSourceOut])
async def confirm_dsar_scope(
    dsar_id: uuid.UUID,
    payload: DsarScopeConfirmIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> list[DsarScopeSourceOut]:
    """Record the human decision about what to search.

    Refuses while anything is undecided. A scope confirmed with sources
    nobody looked at is not a confirmed scope, and discovery obeys this
    list exactly.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    rows = {
        row.source_key: row
        for row in (
            await db.execute(
                select(DsarScopeSource).where(DsarScopeSource.dsar_id == dsar.id)
            )
        )
        .scalars()
        .all()
    }
    for decision in payload.decisions:
        row = rows.get(decision.source_key)
        if row is not None:
            row.included = decision.included
            row.exclusion_reason = (
                (decision.exclusion_reason or "").strip() or None
                if decision.included is False
                else None
            )

    # Excluding something the product argued was likely relevant is a
    # judgement, and it has to be recorded as one. Excluding a source
    # ranked "probably unrelated" needs no explanation -- agreeing with
    # the reasoning already shown is not a decision that needs defending.
    unexplained = [
        row
        for row in rows.values()
        if row.included is False
        and row.relevance == dsar_scope.HIGH
        and not (row.exclusion_reason or "").strip()
    ]
    if unexplained:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Record why these likely-relevant source(s) are being left out: "
                + ", ".join(sorted(row.name for row in unexplained))
                + ". A narrowed scope has to carry its own justification."
            ),
        )

    undecided = [row for row in rows.values() if row.included is None]
    if undecided:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{len(undecided)} source(s) have no decision yet: "
                + ", ".join(sorted(row.name for row in undecided)[:5])
                + ". Include or exclude each one before confirming the scope."
            ),
        )

    dsar.scope_confirmed_at = datetime.now(UTC)
    dsar.scope_confirmed_by = context.user.id
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.dsar.scope_confirmed",
        object_type="dsar",
        object_id=str(dsar.id),
        after_state={
            "included": sum(1 for row in rows.values() if row.included),
            "excluded": sum(1 for row in rows.values() if row.included is False),
        },
    )
    await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    return [
        _scope_out(row) for row in sorted(rows.values(), key=dsar_scope.sort_key)
    ]


@router.post("/dsars/{dsar_id}/scope/sources", response_model=DsarScopeSourceOut)
async def add_dsar_scope_source(
    dsar_id: uuid.UUID,
    payload: DsarManualSourceIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DsarScopeSourceOut:
    """Add a source Veyntra did not propose.

    The register is never complete, and the person handling the request
    often knows about a system it does not list. Marked as manual, so
    discovery raises a follow-up rather than pretending to search it.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    key = dsar_scope.source_key_for("manual", payload.name)
    existing = (
        await db.execute(
            select(DsarScopeSource).where(
                DsarScopeSource.dsar_id == dsar.id,
                DsarScopeSource.source_key == key,
            )
        )
    ).scalars().first()
    if existing is not None:
        # §18: adding the same source twice is one source.
        return _scope_out(existing)

    row = DsarScopeSource(
        organization_id=context.organization_id,
        dsar_id=dsar.id,
        source_key=key,
        kind="manual",
        name=payload.name,
        reason=payload.reason,
        relevance=dsar_scope.HIGH,
        relevance_reason=(
            "Added by a person who knows this system holds data relevant to this "
            "request."
        ),
        linked_systems=[],
        potential_sources=[],
        # A source somebody typed in is one Veyntra has no way to reach.
        search_capability=dsar_scope.NOT_CONNECTED,
        included=True,
        added_by_user=True,
    )
    db.add(row)
    await db.flush()
    await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    await db.refresh(row)
    return _scope_out(row)


@router.get("/dsars/{dsar_id}/discovery-plan", response_model=DsarDiscoveryPlanOut)
async def get_dsar_discovery_plan(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DsarDiscoveryPlanOut:
    """§8: what the run will do, before it does it."""
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    plan = await dsar_discovery.build_plan(db, dsar=dsar)
    return DsarDiscoveryPlanOut(
        total=plan.total,
        connected=plan.connected,
        manual=plan.manual,
        excluded=plan.excluded,
        manual_sources=plan.manual_sources,
        connected_sources=plan.connected_sources,
    )


@router.get("/dsars/{dsar_id}/discovered", response_model=list[DsarDiscoveredItemOut])
async def list_dsar_discovered(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[DsarDiscoveredItemOut]:
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    rows = (
        await db.execute(
            select(DsarDiscoveredItem)
            .where(DsarDiscoveredItem.dsar_id == dsar.id)
            .order_by(DsarDiscoveredItem.source_name)
        )
    ).scalars().all()
    return [_dsar_item_out(row) for row in rows]


@router.post("/dsars/{dsar_id}/discovery/run", response_model=list[DsarDiscoveredItemOut])
async def run_dsar_discovery(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> list[DsarDiscoveredItemOut]:
    """Search the confirmed scope.

    Refuses before identity verification and before the scope is
    confirmed -- §5. Searching for somebody on the strength of an
    unverified claim is the same disclosure risk as answering them, one
    step earlier.

    Safe to re-run: rows are keyed by source, decisions are preserved,
    and follow-up tasks are raised once.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    if dsar.verification_status != "verified":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Verify the requester's identity before searching. Looking a person "
                "up on an unverified request is the same disclosure risk as answering "
                "it."
            ),
        )
    if dsar.scope_confirmed_at is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Confirm the search scope first. Discovery searches exactly what was "
                "confirmed, so an unconfirmed scope would either search too much or "
                "too little."
            ),
        )

    items = await dsar_discovery.run(
        db,
        organization_id=context.organization_id,
        dsar=dsar,
        actor_user_id=context.user.id,
    )
    await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    return [_dsar_item_out(item) for item in items]


@router.patch(
    "/dsars/{dsar_id}/discovered/{item_id}", response_model=DsarDiscoveredItemOut
)
async def review_dsar_discovered_item(
    dsar_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: DsarItemReviewIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DsarDiscoveredItemOut:
    """Record what to do with one discovered record set.

    A reason is required to exclude or redact. Withholding data from a
    data subject is a decision somebody has to be able to defend, and an
    unexplained exclusion is indistinguishable after the fact from an
    accident.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    item = (
        await db.execute(
            select(DsarDiscoveredItem).where(
                DsarDiscoveredItem.id == item_id,
                DsarDiscoveredItem.dsar_id == dsar.id,
            )
        )
    ).scalars().first()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if payload.review_decision in ("exclude", "redact") and not (
        payload.review_reason or ""
    ).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Record why this is being {payload.review_decision}d. Withholding "
                "data from a data subject is a decision that has to be defensible."
            ),
        )

    item.review_decision = payload.review_decision
    item.review_reason = (payload.review_reason or "").strip() or None
    item.reviewed_by = context.user.id
    item.reviewed_at = datetime.now(UTC)

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.dsar.item_reviewed",
        object_type="dsar",
        object_id=str(dsar.id),
        after_state={"source": item.source_name, "decision": item.review_decision},
    )
    await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    await db.refresh(item)
    return _dsar_item_out(item)


def _dsar_preview_out(preview) -> DsarResponsePreviewOut:
    def lines(rows) -> list[DsarSourceLineOut]:
        return [
            DsarSourceLineOut(
                name=row.name,
                state=row.state,
                state_label=row.state_label,
                matches=row.matches,
                decision=row.decision,
                decision_reason=row.decision_reason,
                flags=row.flags,
            )
            for row in rows
        ]

    return DsarResponsePreviewOut(
        dsar_id=preview.dsar_id,
        requester_name=preview.requester_name,
        requester_email=preview.requester_email,
        request_type=preview.request_type,
        received_at=preview.received_at,
        due_at=preview.due_at,
        identity_method=preview.identity_method,
        identity_notes=preview.identity_notes,
        identity_verified_at=preview.identity_verified_at,
        identity_verified_by=preview.identity_verified_by,
        letter=preview.letter,
        included=lines(preview.included),
        excluded=lines(preview.excluded),
        redacted=lines(preview.redacted),
        not_searched=lines(preview.not_searched),
        follow_ups=preview.follow_ups,
        blockers=preview.blockers,
        coverage=(
            DsarCoverageOut(**asdict(preview.coverage)) if preview.coverage else None
        ),
        digest=preview.digest,
    )


@router.get("/dsars/{dsar_id}/response/preview", response_model=DsarResponsePreviewOut)
async def preview_dsar_response(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DsarResponsePreviewOut:
    """The drafted response, before anybody approves it.

    Built from live records and stamped with a digest of them. Nothing
    is stored: a preview is a question, not a commitment.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    preview = await dsar_response.build_preview(
        db, organization_id=context.organization_id, dsar=dsar
    )
    return _dsar_preview_out(preview)


@router.post("/dsars/{dsar_id}/response/approve", response_model=DsarResponsePackageOut)
async def approve_dsar_response(
    dsar_id: uuid.UUID,
    payload: DsarResponseApproveIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DsarResponsePackage:
    """Freeze the previewed response as the approved one.

    What is approved is what gets sent. Rebuilding at send time would let
    the answer change between the moment somebody read it and the moment
    it went out.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    try:
        package = await dsar_response.approve(
            db,
            organization_id=context.organization_id,
            dsar=dsar,
            confirm_digest=payload.digest,
            actor_user_id=context.user.id,
            letter_override=payload.letter,
        )
    except dsar_response.ResponseRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    await db.refresh(package)
    return package


@router.post("/dsars/{dsar_id}/response/sent", response_model=DsarResponsePackageOut)
async def mark_dsar_response_sent(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DsarResponsePackage:
    """Record that the approved response reached the requester.

    Refuses while anything still blocks completion -- §13. An open manual
    follow-up is one of those: a response can be sent while a source is
    outstanding, but the request is not finished until it is closed.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    package = (
        await db.execute(
            select(DsarResponsePackage)
            .where(
                DsarResponsePackage.dsar_id == dsar.id,
                DsarResponsePackage.status == "approved",
            )
            .order_by(DsarResponsePackage.version.desc())
        )
    ).scalars().first()
    if package is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Approve the response package before recording it as sent.",
        )

    blockers = await dsar_workflow.completion_blockers(db, dsar=dsar)
    if blockers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=" ".join(blocker.message for blocker in blockers),
        )

    try:
        package = await dsar_response.mark_sent(
            db,
            organization_id=context.organization_id,
            dsar=dsar,
            package=package,
            actor_user_id=context.user.id,
        )
    except dsar_response.ResponseRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    await db.refresh(package)
    return package


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

    Where a package has been approved, this renders *that* snapshot
    rather than rebuilding from live records — §12. Rebuilding would let
    the exported answer differ from the one somebody read and signed off,
    and the thing that differed would be a person's personal data.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    approved = (
        await db.execute(
            select(DsarResponsePackage)
            .where(
                DsarResponsePackage.dsar_id == dsar.id,
                DsarResponsePackage.status.in_(("approved", "sent")),
            )
            .order_by(DsarResponsePackage.version.desc())
        )
    ).scalars().first()
    if approved is not None:
        if dsar.verification_status != "verified":
            # Belt and braces: a package cannot be approved unverified,
            # but the export is the disclosure, so it re-checks rather
            # than trusting an earlier state.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This request cannot be exported until the data subject's "
                    "identity has been verified."
                ),
            )
        rendered = dsar_response.render(approved).encode("utf-8")
        dsar.export_generated_at = datetime.now(UTC)
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="compliance.dsar.export_generated",
            object_type="dsar",
            object_id=str(dsar.id),
            after_state={"version": approved.version, "from_snapshot": True},
        )
        await db.commit()
        return Response(
            content=rendered,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="dsar-{dsar.id}-v{approved.version}.txt"'
                )
            },
        )

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
        received_at=payload.received_at,
        actor_user_id=context.user.id,
    )
    # A new request is already at identity verification, not sitting at
    # "received" waiting for somebody to open it. The list should say so
    # the moment it is logged.
    await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    await db.refresh(dsar)
    return dsar


@router.get("/dsars/{dsar_id}", response_model=DSAROut)
async def get_dsar(
    dsar_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DSAR:
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    # The stored phase is a cache for lists; opening a request recomputes
    # it, so a detail view is never stale even if a child row moved
    # without passing through this router.
    await dsar_workflow.refresh_phase(db, dsar=dsar)
    await db.commit()
    return dsar


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
    # Check the confirmed transfers against the records they were
    # assessed from before returning them. A vendor that changed country
    # last week should not wait for somebody to re-run detection before
    # the screen says so. This only ever sets `review_reason` — the
    # transfer's own destination and mechanism are left exactly as the
    # person who approved them left them.
    await transfer_drift.flag_drifted_transfers(
        db, organization_id=context.organization_id
    )
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


@router.get("/data-transfers/{transfer_id}", response_model=DataTransferDetailOut)
async def get_data_transfer(
    transfer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DataTransferDetailOut:
    """One transfer, with the records it was assessed against.

    The vendor's country and DPA status are shown as the vendor records
    them — not merged into the transfer. A reviewer deciding whether a
    mechanism still holds needs to see both claims side by side; a single
    reconciled number would hide the disagreement that makes the question
    worth asking.
    """
    transfer = await _get_org_data_transfer(db, transfer_id, context.organization_id)
    # Same check the list runs, so opening a transfer from a stale link
    # does not show a flag the list already cleared, or miss one it set.
    await transfer_drift.flag_drifted_transfers(
        db, organization_id=context.organization_id
    )
    await db.refresh(transfer)

    organization = await db.get(Organization, context.organization_id)
    activity = (
        await db.get(ProcessingActivity, transfer.processing_activity_id)
        if transfer.processing_activity_id
        else None
    )
    vendor = await db.get(Vendor, transfer.vendor_id) if transfer.vendor_id else None

    return DataTransferDetailOut(
        **{
            field: getattr(transfer, field)
            for field in DataTransferOut.model_fields
        },
        exporter_name=organization.name if organization else "This organization",
        processing_activity_name=activity.name if activity else None,
        vendor_name=vendor.name if vendor else None,
        vendor_country=(vendor.country or None) if vendor else None,
        vendor_dpa_status=(vendor.dpa_status or None) if vendor else None,
    )


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

    # A vendor's location is what makes a third-country transfer
    # detectable. Idempotent, so a vendor created before any activity
    # simply proposes nothing yet.
    await privacy_suggestions.analyse(db, organization_id=context.organization_id)
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


@router.post(
    "/vendors/{vendor_id}/privacy-review",
    response_model=VendorAssessmentDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def review_vendor_privacy(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.vendors.manage")),
) -> VendorAssessment:
    """Check the privacy position from what is actually on file: DPA
    status, and the questionnaire answers about transfers, retention and
    subprocessors. Reports what is missing; it does not judge the vendor.
    """
    vendor = await _get_org_vendor(db, vendor_id, context.organization_id)
    assessment = await run_privacy_review(
        db, organization_id=context.organization_id, vendor=vendor, actor_user_id=context.user.id
    )
    await db.commit()
    await db.refresh(assessment)
    return assessment


@router.post(
    "/vendors/{vendor_id}/security-review",
    response_model=VendorAssessmentDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def review_vendor_security(
    vendor_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.vendors.manage")),
) -> VendorAssessment:
    """Check the security position: evidence on file, and whether the
    questionnaire was actually completed."""
    vendor = await _get_org_vendor(db, vendor_id, context.organization_id)
    assessment = await run_security_review(
        db, organization_id=context.organization_id, vendor=vendor, actor_user_id=context.user.id
    )
    await db.commit()
    await db.refresh(assessment)
    return assessment


@router.post("/vendors/{vendor_id}/approval", response_model=VendorOut)
async def decide_vendor(
    vendor_id: uuid.UUID,
    payload: VendorApprovalRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.vendors.manage")),
) -> Vendor:
    """Record the approval decision.

    `conditionally_approved` is the state real reviews end in most often,
    and it requires its conditions in writing — see
    `app.compliance.vendor_review.decide_vendor_approval`.
    """
    vendor = await _get_org_vendor(db, vendor_id, context.organization_id)
    try:
        await decide_vendor_approval(
            db,
            organization_id=context.organization_id,
            vendor=vendor,
            decision=payload.decision,
            conditions=payload.conditions,
            actor_user_id=context.user.id,
        )
    except VendorApprovalError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(vendor)
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
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[QuestionnaireOut]:
    """The questionnaires being worked on, or the ones put away.

    Archived is a separate list rather than a filter chip over one list.
    Somebody clearing up wants their working set to get shorter, and a
    list that still contains everything with a badge on some of it has
    not done that.

    Each row carries whether it may be deleted, worked out here from what
    has actually happened to it. The client draws its menu from that; the
    endpoints check again anyway.
    """
    result = await db.execute(
        select(Questionnaire)
        .where(
            Questionnaire.organization_id == context.organization_id,
            Questionnaire.archived_at.is_not(None)
            if archived
            else Questionnaire.archived_at.is_(None),
        )
        .order_by(Questionnaire.created_at.desc())
    )
    rows = list(result.scalars().all())

    # How far each one has got. Built from one grouped query rather than
    # a count per row: this list is the questionnaires screen, and the
    # progress on a card is the first thing anybody looks at.
    #
    # `progress` was declared on this schema but never filled in here, so
    # every row on the list reported zero of everything while the detail
    # page showed the real numbers.
    statuses_by_questionnaire: dict[uuid.UUID, list[str]] = {}
    if rows:
        answer_rows = (
            await db.execute(
                select(
                    QuestionnaireQuestion.questionnaire_id,
                    QuestionnaireAnswer.status,
                )
                .outerjoin(
                    QuestionnaireAnswer,
                    QuestionnaireAnswer.question_id == QuestionnaireQuestion.id,
                )
                .where(
                    QuestionnaireQuestion.questionnaire_id.in_(
                        [questionnaire.id for questionnaire in rows]
                    )
                )
            )
        ).all()
        for questionnaire_id, answer_status in answer_rows:
            # A question with no answer row is unanswered, which is a
            # state the progress bar has to show rather than a row it
            # gets to leave out.
            statuses_by_questionnaire.setdefault(questionnaire_id, []).append(
                answer_status or "unanswered"
            )

    out: list[QuestionnaireOut] = []
    for questionnaire in rows:
        item = QuestionnaireOut.model_validate(questionnaire)
        item.progress = _questionnaire_progress(
            statuses_by_questionnaire.get(questionnaire.id, [])
        )
        eligibility = await questionnaire_eligibility(db, questionnaire=questionnaire)
        item.can_delete = eligibility.can_delete
        item.delete_blocked_reason = eligibility.message or None
        _fill_readiness(
            item,
            questionnaire,
            statuses_by_questionnaire.get(questionnaire.id, []),
        )
        out.append(item)
    return out


@router.post(
    "/questionnaires", response_model=QuestionnaireOut, status_code=status.HTTP_201_CREATED
)
async def create_questionnaire(
    payload: QuestionnaireCreate,
    background: BackgroundTasks,
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
    # Same org check as the opportunity above: an unknown or another
    # tenant's id must not reach the foreign key as an opaque 500.
    if payload.vendor_id is not None:
        await _get_org_vendor(db, payload.vendor_id, context.organization_id)

    fields = payload.model_dump(exclude={"questions_text", "draft_answers"})
    questionnaire = Questionnaire(organization_id=context.organization_id, **fields)
    db.add(questionnaire)
    await db.flush()

    # A customer-provided questionnaire is part of an engagement by
    # definition, so the engagement is made here rather than left for
    # somebody to create afterwards. An internal assessment is nobody's
    # engagement but our own and gets none; a customer questionnaire with
    # no customer named gets none either, because inventing one would put
    # a customer in the record who does not exist.
    await link_questionnaire_to_review(
        db,
        organization_id=context.organization_id,
        questionnaire=questionnaire,
        actor_user_id=context.user.id,
    )

    # The customer's questions, straight out of their email. Creating a
    # questionnaire and then typing a hundred questions into a form is
    # the workflow this replaces.
    extracted = 0
    if payload.questions_text:
        extracted = await _import_questions(
            db,
            organization_id=context.organization_id,
            questionnaire=questionnaire,
            questions=extract_questions(payload.questions_text),
        )

    # The status the questionnaire is actually in, rather than the column
    # default. A customer questionnaire created with no customer is
    # `needs_setup` from the moment it exists — it was already reporting
    # that in `readiness` while the stored status said `draft`, which is
    # two answers to one question and the thing this calculation exists
    # to prevent.
    await recalculate_questionnaire_status(
        db,
        organization_id=context.organization_id,
        questionnaire_id=questionnaire.id,
    )

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.questionnaire.created",
        object_type="questionnaire",
        object_id=str(questionnaire.id),
        after_state={
            "title": questionnaire.title,
            "source": questionnaire.source,
            "customer": questionnaire.customer_name,
            "questions_imported": extracted,
            "status": questionnaire.status,
        },
    )
    await db.commit()

    # Drafting happens after the response so the user is not staring at a
    # spinner while a hundred questions are answered; the page polls and
    # watches them fill in.
    if extracted and payload.draft_answers:
        background.add_task(
            _draft_questionnaire_answers,
            context.organization_id,
            questionnaire.id,
            context.user.id,
        )

    await db.refresh(questionnaire)
    return questionnaire


async def _import_questions(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    questionnaire: Questionnaire,
    questions: list[ExtractedQuestion],
) -> int:
    """Add extracted questions, skipping ones already asked.

    Re-importing a corrected spreadsheet is a normal thing to do, and it
    must not double every question.
    """
    existing = {
        text.strip().lower()
        for text in (
            await db.execute(
                select(QuestionnaireQuestion.text).where(
                    QuestionnaireQuestion.questionnaire_id == questionnaire.id
                )
            )
        )
        .scalars()
        .all()
    }
    next_index = int(
        (
            await db.execute(
                select(func.coalesce(func.max(QuestionnaireQuestion.order_index), -1)).where(
                    QuestionnaireQuestion.questionnaire_id == questionnaire.id
                )
            )
        ).scalar_one()
    ) + 1

    added = 0
    for question in questions:
        if question.text.strip().lower() in existing:
            continue
        row = QuestionnaireQuestion(
            organization_id=organization_id,
            questionnaire_id=questionnaire.id,
            text=question.text,
            category=question.category,
            order_index=next_index + added,
        )
        db.add(row)
        await db.flush()
        # Every question carries exactly one answer row from the moment
        # it exists, so the screen has somewhere to say "nobody has
        # looked at this yet" rather than rendering a hole.
        db.add(
            QuestionnaireAnswer(
                organization_id=organization_id,
                question_id=row.id,
                status="unanswered",
            )
        )
        existing.add(question.text.strip().lower())
        added += 1
    await db.flush()
    return added


async def _draft_questionnaire_answers(
    organization_id: uuid.UUID, questionnaire_id: uuid.UUID, actor_user_id: uuid.UUID | None
) -> None:
    """Answer everything unanswered, in its own session.

    Never raises into the caller: a provider outage must leave the
    imported questions in place to be answered later, not lose them.
    """
    from app.compliance.questionnaire_ai import draft_pending_answers
    from app.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            await draft_pending_answers(
                session,
                organization_id=organization_id,
                questionnaire_id=questionnaire_id,
                actor_user_id=actor_user_id,
            )
    except Exception as exc:  # noqa: BLE001 - drafting is best effort
        # Logged with enough to diagnose it. A whole feature failing
        # silently behind one warning line is how "answers are being
        # drafted" turns into answers that never arrive and nobody knowing
        # why. Database errors get their detail because they are ours;
        # anything that might have come from a model provider is logged by
        # class alone, since provider exceptions carry request payloads.
        if isinstance(exc, SQLAlchemyError):
            logger.exception("Questionnaire drafting failed for %s", questionnaire_id)
        else:
            logger.error(
                "Questionnaire drafting failed for %s (%s)",
                questionnaire_id,
                type(exc).__name__,
            )


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
    statuses: list[str] = []
    for question in questions:
        answer_result = await db.execute(
            select(QuestionnaireAnswer).where(QuestionnaireAnswer.question_id == question.id)
        )
        answer = answer_result.scalar_one_or_none()
        statuses.append(answer.status if answer else "unanswered")
        question_details.append(
            QuestionnaireQuestionDetailOut(
                **QuestionnaireQuestionOut.model_validate(question).model_dump(),
                answer=_answer_out(answer) if answer else None,
            )
        )

    review = (
        await db.get(SecurityReview, questionnaire.security_review_id)
        if questionnaire.security_review_id is not None
        else None
    )

    return QuestionnaireDetailOut(
        **_fill_readiness(
            QuestionnaireOut.model_validate(questionnaire), questionnaire, statuses
        ).model_dump(exclude={"progress"}),
        progress=_questionnaire_progress(statuses),
        questions=question_details,
        security_review_id=review.id if review else None,
        security_review_title=(
            (review.title or "Customer security review") if review else None
        ),
        security_review_href=(
            f"/compliance/security-reviews/{review.id}" if review else None
        ),
        security_review_status=review.status if review else None,
        security_review_status_label=(
            customer_review_label(review.status) if review else None
        ),
        security_review_archived_at=review.archived_at if review else None,
        **_customer_repair_state(questionnaire, review),
        supported_import_formats=sorted(set(SUPPORTED_CONTENT_TYPES.values())),
    )


def _answer_out(answer: QuestionnaireAnswer) -> QuestionnaireAnswerOut:
    """One answer, with the words for its state and whether it can be
    approved at all.

    The guard is computed here rather than in the browser: Approve was
    offered over an empty answer, and a disabled button that cannot say
    why is only marginally better than one that does the wrong thing.
    """
    has_text = bool((answer.answer_text or "").strip())
    blocked: str | None = None
    if not has_text:
        blocked = "There is no answer to approve yet."
    elif answer.status == "approved":
        blocked = "This answer is already approved."

    return QuestionnaireAnswerOut(
        **QuestionnaireAnswerOut.model_validate(answer).model_dump(
            exclude={"status_label", "can_approve", "approval_blocked_reason"}
        ),
        status_label=ANSWER_LABELS.get(answer.status, answer.status),
        can_approve=blocked is None,
        approval_blocked_reason=blocked,
    )


def _fill_readiness(
    item: QuestionnaireOut,
    questionnaire: Questionnaire,
    statuses: list[str],
) -> QuestionnaireOut:
    """Attach the readiness rule's answer to a serialised questionnaire.

    Called from the list and from the detail, so a row and the page it
    opens cannot disagree — and neither of them works it out for itself.
    The rule lives in `app.compliance.questionnaire_status`; this only
    puts its output on the wire.
    """
    blocking = questionnaire_blockers(
        source=questionnaire.source,
        customer_name=questionnaire.customer_name,
        security_review_id=questionnaire.security_review_id,
        answer_statuses=statuses,
    )
    item.status_label = QUESTIONNAIRE_STATUS_LABELS.get(
        questionnaire.status, questionnaire.status.replace("_", " ").capitalize()
    )
    item.readiness = QuestionnaireReadinessOut(
        ready=not blocking,
        needs_setup=bool(questionnaire_setup_blockers(blocking)),
        blockers=[
            ReadinessBlockerOut(code=b.code, message=b.message) for b in blocking
        ],
    )
    item.title_looks_like_a_question = title_reads_like_a_question(questionnaire.title)
    return item


def _questionnaire_progress(statuses: list[str]) -> QuestionnaireProgressOut:
    """What is left to do.

    `percent_complete` counts approved answers only. A drafted answer
    nobody has read is not progress towards sending the questionnaire
    back, and counting it as such would tell the customer they are
    nearly done when nobody has checked anything.
    """
    total = len(statuses)
    approved = sum(1 for s in statuses if s == "approved")
    needs_review = sum(1 for s in statuses if s == "needs_review")
    draft = sum(1 for s in statuses if s == "draft")
    # Everything else is work nobody has started: unanswered, and
    # rejected answers that need new evidence.
    unanswered = total - approved - needs_review - draft
    return QuestionnaireProgressOut(
        total=total,
        approved=approved,
        needs_review=needs_review,
        draft=draft,
        unanswered=unanswered,
        percent_complete=round(100 * approved / total) if total else 0,
        ready_to_share=total > 0 and approved == total,
    )


@router.get("/questionnaires/{questionnaire_id}", response_model=QuestionnaireDetailOut)
async def get_questionnaire(
    questionnaire_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> QuestionnaireDetailOut:
    questionnaire = await _get_org_questionnaire(db, questionnaire_id, context.organization_id)
    return await _build_questionnaire_detail(db, questionnaire)


async def _import_input_lines(
    db: AsyncSession,
    *,
    payload: QuestionnaireImportRequest,
    organization_id: uuid.UUID,
    formats: list[str],
) -> tuple[list[str], str | None]:
    """The raw lines to analyse, and where they came from.

    Raw lines rather than extracted questions: the analysis has to see
    what was rejected, and extraction throws that away. A questionnaire
    where eight rows vanished without comment is one nobody can trust
    they have answered.
    """
    if payload.file_id is not None:
        file_record = await db.get(File, payload.file_id)
        if file_record is None or file_record.organization_id != organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        if file_record.content_type not in SUPPORTED_CONTENT_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Veyntra cannot read this file type. Supported formats: "
                    + ", ".join(formats)
                ),
            )
        try:
            file_bytes = await asyncio.to_thread(download_object, file_record.storage_key)
            text = await asyncio.to_thread(
                extract_text, file_record.content_type, file_bytes
            )
        except UnsupportedFormatError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Veyntra cannot read this file type. Supported formats: "
                    + ", ".join(formats)
                ),
            ) from None
        except Exception as exc:  # noqa: BLE001 - the reader needs to know it failed
            logger.warning("Questionnaire import could not read %s", payload.file_id)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "That file could not be read. It may be password-protected, or a "
                    "scan with no text layer."
                ),
            ) from exc
        return text.splitlines(), file_record.original_filename

    if payload.questions_text:
        return payload.questions_text.splitlines(), None

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Provide a file to import or paste the questions.",
    )


async def _after_answers_changed(
    db: AsyncSession, *, organization_id: uuid.UUID, questionnaire_id: uuid.UUID
) -> None:
    """Bring a questionnaire's status back in line with its answers.

    Called wherever a question or an answer changes. One function so the
    rule lives in one place: the bug this replaces was a status column
    that only a button moved, while every screen derived its own opinion
    from the answers and reported something else.

    A change also reaches the customer security review this questionnaire
    belongs to, if any — a review whose questionnaire just became ready
    to share must not still say it is waiting on one.
    """
    change = await recalculate_questionnaire_status(
        db, organization_id=organization_id, questionnaire_id=questionnaire_id
    )
    if change is None:
        return

    # The engagement this questionnaire belongs to. Checked on both
    # links: the new one every customer questionnaire gets, and the old
    # single link the sales-coupled reviews still carry.
    questionnaire = await db.get(Questionnaire, questionnaire_id)
    review = None
    if questionnaire is not None and questionnaire.security_review_id is not None:
        review = await db.get(SecurityReview, questionnaire.security_review_id)
    if review is None:
        review = (
            await db.execute(
                select(SecurityReview).where(
                    SecurityReview.organization_id == organization_id,
                    SecurityReview.questionnaire_id == questionnaire_id,
                )
            )
        ).scalars().first()

    if review is not None:
        # A review whose last outstanding answer was just approved must
        # not still say it is waiting on one.
        await recalculate_customer_review(db, review=review)


@router.post(
    "/questionnaires/{questionnaire_id}/import/analyze",
    response_model=ImportAnalysisOut,
)
async def analyze_questionnaire_import(
    questionnaire_id: uuid.UUID,
    payload: QuestionnaireImportRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> ImportAnalysisOut:
    """Say what an import would do. Create nothing.

    The safety half of the import. Somebody pasting a hundred-question
    spreadsheet gets to see what was found, what already exists and what
    could not be read *before* any of it becomes rows they would have to
    unpick by hand.
    """
    questionnaire = await _get_org_questionnaire(db, questionnaire_id, context.organization_id)
    formats = sorted(set(SUPPORTED_CONTENT_TYPES.values()))

    raw_lines, source_filename = await _import_input_lines(
        db,
        payload=payload,
        organization_id=context.organization_id,
        formats=formats,
    )

    analysis = await analyse_import(
        db,
        organization_id=context.organization_id,
        questionnaire_id=questionnaire.id,
        raw_lines=raw_lines,
    )

    return ImportAnalysisOut(
        headline=analysis.headline,
        detected=analysis.detected,
        new=analysis.new,
        duplicates=analysis.duplicates,
        possible_duplicates=analysis.possible_duplicates,
        unparsed=analysis.unparsed,
        lines=[
            AnalyzedLineOut(
                text=line.text,
                outcome=line.outcome,
                category=line.category,
                matches=line.matches,
                similarity=line.similarity,
                reason=line.reason,
                importable=line.importable,
            )
            for line in analysis.lines
        ],
        supported_formats=formats,
        source_filename=source_filename,
    )


@router.post(
    "/questionnaires/{questionnaire_id}/import/confirm",
    response_model=ImportResultOut,
)
async def confirm_questionnaire_import(
    questionnaire_id: uuid.UUID,
    payload: QuestionnaireImportConfirm,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> ImportResultOut:
    """Create the questions somebody just approved in the preview.

    Takes the chosen texts rather than re-reading the input. Re-extracting
    could reach a different answer than the preview did, and then the
    import would not be the one that was approved.

    Idempotent by content: a question whose normalized text already
    exists is skipped, so re-running the same import — a retry, a double
    click, the same spreadsheet sent twice — creates nothing the second
    time.
    """
    questionnaire = await _get_org_questionnaire(db, questionnaire_id, context.organization_id)

    existing = {
        normalize_question(text)
        for text in (
            await db.execute(
                select(QuestionnaireQuestion.text).where(
                    QuestionnaireQuestion.questionnaire_id == questionnaire.id
                )
            )
        )
        .scalars()
        .all()
    }
    next_index = int(
        (
            await db.execute(
                select(func.coalesce(func.max(QuestionnaireQuestion.order_index), -1)).where(
                    QuestionnaireQuestion.questionnaire_id == questionnaire.id
                )
            )
        ).scalar_one()
    ) + 1

    created = 0
    skipped = 0
    for text in payload.questions:
        cleaned = clean_line(text)
        key = normalize_question(cleaned)
        if not key or key in existing:
            skipped += 1
            continue
        existing.add(key)
        row = QuestionnaireQuestion(
            organization_id=context.organization_id,
            questionnaire_id=questionnaire.id,
            text=cleaned,
            category=categorize(cleaned),
            order_index=next_index + created,
        )
        db.add(row)
        await db.flush()
        # Every question carries exactly one answer row from the moment it
        # exists, so the screen has somewhere to say "nobody has looked at
        # this yet" rather than rendering a hole — and so the progress
        # counts include it before any drafting has run.
        db.add(
            QuestionnaireAnswer(
                organization_id=context.organization_id,
                question_id=row.id,
                status="unanswered",
            )
        )
        created += 1

    status_before = questionnaire.status
    status_after = status_before
    if created:
        # New unanswered questions are outstanding work, so the status
        # follows from them like every other change to the answers. This
        # used to be a hand-rolled `completed → in_progress` special case
        # here, which is how two calculations of one idea started.
        await _after_answers_changed(
            db,
            organization_id=context.organization_id,
            questionnaire_id=questionnaire.id,
        )
        status_after = questionnaire.status

        if payload.source_filename:
            questionnaire.source = "customer_provided"

        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="compliance.questionnaire.questions_imported",
            object_type="questionnaire",
            object_id=str(questionnaire.id),
            after_state={
                "created": created,
                "duplicates_skipped": skipped,
                "title": questionnaire.title,
                **(
                    {"source_file": payload.source_filename}
                    if payload.source_filename
                    else {}
                ),
            },
        )

    await db.commit()

    drafting = bool(created and payload.draft_answers)
    if drafting:
        # After the response. Drafting an answer is a model call per
        # question, and holding the request open for fifty of them would
        # make the import look hung during the part the product is for.
        background.add_task(
            _draft_questionnaire_answers,
            context.organization_id,
            questionnaire.id,
            context.user.id,
        )

    return ImportResultOut(
        created=created,
        duplicates_skipped=skipped,
        unparsed=0,
        drafting=drafting,
        status_before=status_before,
        status_after=status_after,
    )


@router.post(
    "/questionnaires/{questionnaire_id}/import",
    response_model=QuestionnaireImportResult,
)
async def import_questionnaire_questions(
    questionnaire_id: uuid.UUID,
    payload: QuestionnaireImportRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> QuestionnaireImportResult:
    """Pull the customer's questions out of their file, or their email.

    The normal way a questionnaire enters Veyntra. Extraction is
    conservative: a line that is not a question is left out rather than
    imported as one, because a reviewer cannot tell which rows the
    product invented.
    """
    questionnaire = await _get_org_questionnaire(db, questionnaire_id, context.organization_id)
    formats = sorted(set(SUPPORTED_CONTENT_TYPES.values()))

    if payload.file_id is not None:
        file_record = await db.get(File, payload.file_id)
        if file_record is None or file_record.organization_id != context.organization_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        try:
            file_bytes = await asyncio.to_thread(download_object, file_record.storage_key)
            extracted = extract_questions_from_file(file_record.content_type, file_bytes)
        except UnsupportedFormatError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Veyntra cannot read this file type. Supported formats: "
                    + ", ".join(formats)
                ),
            ) from None
    elif payload.questions_text:
        extracted = extract_questions(payload.questions_text)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide a file to import or paste the questions.",
        )

    if not extracted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No questions were found. Veyntra looks for lines that ask "
                "something — a question mark, or an instruction like "
                '"Describe your incident response process".'
            ),
        )

    added = await _import_questions(
        db,
        organization_id=context.organization_id,
        questionnaire=questionnaire,
        questions=extracted,
    )
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.questionnaire.questions_imported",
        object_type="questionnaire",
        object_id=str(questionnaire.id),
        after_state={"extracted": len(extracted), "added": added},
    )
    await db.commit()

    if added and payload.draft_answers:
        background.add_task(
            _draft_questionnaire_answers,
            context.organization_id,
            questionnaire.id,
            context.user.id,
        )

    return QuestionnaireImportResult(
        questions_extracted=len(extracted),
        questions_added=added,
        duplicates_skipped=len(extracted) - added,
        drafted=None,
        supported_formats=formats,
    )


@router.post(
    "/questionnaires/{questionnaire_id}/draft-answers",
    response_model=QuestionnaireImportResult,
)
async def draft_questionnaire_answers(
    questionnaire_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> QuestionnaireImportResult:
    """Answer everything still unanswered.

    Synchronous, because the caller pressed a button and wants to see the
    result. Approved answers and anything a person wrote by hand are left
    alone — regenerating over somebody's work to save them a click is not
    a saving.
    """
    from app.compliance.questionnaire_ai import draft_pending_answers

    questionnaire = await _get_org_questionnaire(db, questionnaire_id, context.organization_id)
    counts = await draft_pending_answers(
        db,
        organization_id=context.organization_id,
        questionnaire_id=questionnaire.id,
        actor_user_id=context.user.id,
    )
    return QuestionnaireImportResult(
        questions_extracted=0,
        questions_added=0,
        duplicates_skipped=0,
        drafted=counts,
        supported_formats=sorted(set(SUPPORTED_CONTENT_TYPES.values())),
    )


@router.patch("/questionnaires/{questionnaire_id}/status", response_model=QuestionnaireOut)
async def update_questionnaire_status(
    questionnaire_id: uuid.UUID,
    payload: QuestionnaireStatusUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> Questionnaire:
    questionnaire = await _get_org_questionnaire(db, questionnaire_id, context.organization_id)
    before_status = questionnaire.status
    if payload.status == "completed":
        # The one thing the answers cannot tell us: it actually went out.
        # Which is exactly why it has to be checked here — "we sent this
        # to the customer" is a claim about a customer, and a client that
        # gets the rule wrong must not be able to record it.
        blocking = await questionnaire_readiness(db, questionnaire=questionnaire)
        if blocking:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Cannot mark questionnaire ready to share: "
                    + " ".join(blocker.message for blocker in blocking)
                ),
            )
        questionnaire.status = "completed"
    else:
        # Anything else hands the status back to the calculation. A
        # person choosing "draft" for a questionnaire whose answers are
        # all approved is how the stored status and every screen came to
        # disagree in the first place.
        questionnaire.status = "draft"
        await _after_answers_changed(
            db,
            organization_id=context.organization_id,
            questionnaire_id=questionnaire.id,
        )
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
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> QuestionnaireQuestion:
    """Add one question by hand — the fallback, not the normal path.

    It still gets an answer drafted. A question typed in and left sitting
    at "unanswered" until somebody finds a button to press is the manual
    workflow this product exists to replace, and where the question came
    from makes no difference to that.
    """
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
    # A new unanswered question is outstanding work, whatever the
    # questionnaire said a moment ago.
    await _after_answers_changed(
        db, organization_id=context.organization_id, questionnaire_id=questionnaire.id
    )
    await db.commit()
    await db.refresh(question)

    background.add_task(
        _draft_questionnaire_answers,
        context.organization_id,
        questionnaire.id,
        context.user.id,
    )
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
) -> QuestionnaireAnswerOut:
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
    # The questionnaire's status is a function of its answers, so it moves
    # here rather than waiting for somebody to notice. Approving the last
    # outstanding answer makes it ready to share; reopening an approved
    # one takes that away again.
    await _after_answers_changed(
        db, organization_id=context.organization_id, questionnaire_id=questionnaire_id
    )
    # Approving is the moment the organization stands behind this answer,
    # so it is recorded rather than inferred from the status alone.
    if payload.status == "approved":
        answer.approved_by = context.user.id
        answer.approved_at = datetime.now(UTC)
        answer.review_reason = None
    await db.commit()
    await db.refresh(answer)
    return _answer_out(answer)


# --- lifecycle: archive, restore, delete ------------------------------
#
# Two different acts, deliberately kept apart. Archiving takes a record
# off the active list and keeps everything; deleting destroys it, and is
# only ever available for records nothing has happened to. The server
# decides which is allowed — a client that gets it wrong must not be able
# to destroy an approved answer by calling DELETE directly.


async def _questionnaire_or_404(
    db: AsyncSession, questionnaire_id: uuid.UUID, organization_id: uuid.UUID
) -> Questionnaire:
    questionnaire = await db.get(Questionnaire, questionnaire_id)
    if questionnaire is None or questionnaire.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Questionnaire not found"
        )
    return questionnaire


async def _sync_parent_review(
    db: AsyncSession, questionnaire: Questionnaire
) -> None:
    """Let the engagement follow the questionnaire's lifecycle.

    The link itself is never touched here. Archiving a questionnaire does
    not remove it from its review — it changes whether the review still
    has live work in it, which is a different question and the only one
    `sync_lifecycle` answers.
    """
    if questionnaire.security_review_id is None:
        return
    review = await db.get(SecurityReview, questionnaire.security_review_id)
    if review is not None:
        await sync_review_lifecycle(db, review=review)


@router.patch(
    "/questionnaires/{questionnaire_id}/title", response_model=QuestionnaireOut
)
async def rename_questionnaire(
    questionnaire_id: uuid.UUID,
    payload: QuestionnaireRename,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> QuestionnaireOut:
    """Give a questionnaire a name that describes it.

    Historical records exist whose title is one of their own questions —
    somebody pasted into the wrong box. The product flags those and
    offers this; it does not rewrite them, because a title is somebody's
    words and a plausible replacement is still a guess.

    Renaming changes nothing else. The questions, answers, customer and
    review are untouched, and the status does not move: what a
    questionnaire is called has never been part of whether it is ready.
    """
    questionnaire = await _questionnaire_or_404(
        db, questionnaire_id, context.organization_id
    )
    title = payload.title.strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A questionnaire title is required.",
        )
    before = questionnaire.title
    if title != before:
        questionnaire.title = title
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="compliance.questionnaire.renamed",
            object_type="questionnaire",
            object_id=str(questionnaire.id),
            before_state={"title": before},
            after_state={"title": title},
        )
        await db.commit()

    statuses = await _answer_statuses_for(db, questionnaire_id=questionnaire.id)
    item = QuestionnaireOut.model_validate(questionnaire)
    item.progress = _questionnaire_progress(statuses)
    return _fill_readiness(item, questionnaire, statuses)


@router.post(
    "/questionnaires/{questionnaire_id}/customer",
    response_model=QuestionnaireCustomerResultOut,
)
async def set_questionnaire_customer(
    questionnaire_id: uuid.UUID,
    payload: QuestionnaireCustomerUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> QuestionnaireCustomerResultOut:
    """Name the customer, and put the questionnaire in their engagement.

    The repair for a customer questionnaire that has no customer on it —
    most of them created before there was a column to put one in. The
    backfill deliberately will not decide this; a person does, here, and
    the name they choose is what gets written down.

    Idempotent in the way that matters: naming the same customer twice
    finds the same engagement rather than opening a second one.
    """
    questionnaire = await _questionnaire_or_404(
        db, questionnaire_id, context.organization_id
    )
    customer = payload.customer_name.strip()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A customer name is required.",
        )
    if questionnaire.source != "customer_provided":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only customer-provided questionnaires belong to a customer "
                "security review."
            ),
        )

    before = questionnaire.customer_name
    questionnaire.customer_name = customer
    if before != customer:
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="compliance.questionnaire.customer_set",
            object_type="questionnaire",
            object_id=str(questionnaire.id),
            before_state={"customer": before},
            after_state={"customer": customer, "title": questionnaire.title},
        )

    # A review carried over from the sales flow has no customer on it —
    # the identity lived on the opportunity, and the opportunity is gone.
    # The questionnaire is already inside it, so there is nothing to link;
    # what is missing is the name, and this is somebody supplying it.
    if questionnaire.security_review_id is not None:
        linked = await db.get(SecurityReview, questionnaire.security_review_id)
        if linked is not None and not (linked.customer_name or "").strip():
            before_customer = linked.customer_name
            before_title = linked.title
            linked.customer_name = customer
            if not (linked.title or "").strip():
                linked.title = customer_review_title(customer)
            await record_event(
                db,
                organization_id=context.organization_id,
                actor_user_id=context.user.id,
                action="compliance.security_review.customer_set",
                object_type="security_review",
                object_id=str(linked.id),
                before_state={"customer": before_customer, "title": before_title},
                after_state={"customer": customer, "title": linked.title},
            )
            await sync_review_lifecycle(db, review=linked)
            await db.commit()
            return QuestionnaireCustomerResultOut(
                questionnaire_id=questionnaire.id,
                customer_name=customer,
                security_review_id=linked.id,
                security_review_title=linked.title or "Customer security review",
                review_created=False,
            )

    existing_ids = set(
        (
            await db.execute(
                select(SecurityReview.id).where(
                    SecurityReview.organization_id == context.organization_id
                )
            )
        )
        .scalars()
        .all()
    )
    review = await link_questionnaire_to_review(
        db,
        organization_id=context.organization_id,
        questionnaire=questionnaire,
        actor_user_id=context.user.id,
    )
    if review is not None:
        # An engagement whose only questionnaire is already archived opens
        # closed. The alternative is an Active tab advertising work that
        # finished before the review existed.
        await sync_review_lifecycle(db, review=review)
    # The questionnaire was `needs_setup` precisely because of what just
    # got fixed. Leaving the stored status behind would mean the record
    # still reads "Customer required" over a customer that is now there.
    await recalculate_questionnaire_status(
        db,
        organization_id=context.organization_id,
        questionnaire_id=questionnaire.id,
    )
    await db.commit()

    return QuestionnaireCustomerResultOut(
        questionnaire_id=questionnaire.id,
        customer_name=customer,
        security_review_id=review.id if review else None,
        security_review_title=(
            (review.title or "Customer security review") if review else None
        ),
        review_created=bool(review and review.id not in existing_ids),
    )


@router.post(
    "/questionnaires/{questionnaire_id}/archive", response_model=ArchiveResultOut
)
async def archive_questionnaire(
    questionnaire_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> ArchiveResultOut:
    """Take a questionnaire off the active list, keeping everything.

    Always available, whatever state the questionnaire is in — that is
    the point of it. Answers, approvals, citations, the security review
    it belongs to and every audit event stay exactly where they are; the
    only thing that changes is that active lists stop showing it.

    Idempotent: archiving an already-archived questionnaire changes
    nothing and records nothing, so a retried request does not produce a
    second lifecycle event in the trail.
    """
    questionnaire = await _questionnaire_or_404(
        db, questionnaire_id, context.organization_id
    )

    if questionnaire.archived_at is not None:
        return ArchiveResultOut(
            id=questionnaire.id,
            title=questionnaire.title,
            archived_at=questionnaire.archived_at,
            status=questionnaire.status,
            changed=False,
        )

    questionnaire.archived_at = datetime.now(UTC)
    questionnaire.archived_by = context.user.id
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.questionnaire.archived",
        object_type="questionnaire",
        object_id=str(questionnaire.id),
        before_state={"archived": False, "status": questionnaire.status},
        after_state={
            "archived": True,
            "status": questionnaire.status,
            "title": questionnaire.title,
        },
    )
    await _sync_parent_review(db, questionnaire)
    await db.commit()

    return ArchiveResultOut(
        id=questionnaire.id,
        title=questionnaire.title,
        archived_at=questionnaire.archived_at,
        status=questionnaire.status,
        changed=True,
    )


@router.post(
    "/questionnaires/{questionnaire_id}/restore", response_model=ArchiveResultOut
)
async def restore_questionnaire(
    questionnaire_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.manage")),
) -> ArchiveResultOut:
    """Put an archived questionnaire back on the active list.

    Nothing was removed when it was archived, so nothing has to be
    rebuilt: the questions, answers and approvals are the same rows they
    always were. `status` is untouched throughout, which is why the
    questionnaire comes back exactly as far along as it was.
    """
    questionnaire = await _questionnaire_or_404(
        db, questionnaire_id, context.organization_id
    )

    if questionnaire.archived_at is None:
        return ArchiveResultOut(
            id=questionnaire.id,
            title=questionnaire.title,
            archived_at=None,
            status=questionnaire.status,
            changed=False,
        )

    questionnaire.archived_at = None
    questionnaire.archived_by = None
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.questionnaire.restored",
        object_type="questionnaire",
        object_id=str(questionnaire.id),
        before_state={"archived": True, "status": questionnaire.status},
        after_state={
            "archived": False,
            "status": questionnaire.status,
            "title": questionnaire.title,
        },
    )
    await _sync_parent_review(db, questionnaire)
    await db.commit()

    return ArchiveResultOut(
        id=questionnaire.id,
        title=questionnaire.title,
        archived_at=None,
        status=questionnaire.status,
        changed=True,
    )


@router.delete("/questionnaires/{questionnaire_id}", response_model=DeleteResultOut)
async def delete_questionnaire(
    questionnaire_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.questionnaires.delete")),
) -> DeleteResultOut:
    """Permanently remove a draft questionnaire and its draft records.

    Refused with a 409 the moment anything has happened to it that
    somebody would miss — a decided answer, a security review, a
    completed run. The check is server-side and runs here regardless of
    what the client believed when it drew the menu.

    What goes: the questionnaire, its questions, and the answers on those
    questions. All in one transaction, deepest first, so a failure
    part-way leaves nothing orphaned.

    What stays: the audit trail. The deletion event carries the id, the
    title, who did it and when — enough to answer "what happened to that
    questionnaire" without keeping the content somebody asked to have
    destroyed.
    """
    questionnaire = await db.get(Questionnaire, questionnaire_id)
    if questionnaire is None or questionnaire.organization_id != context.organization_id:
        # Nothing there. A retry, a double-click, or an id that never
        # existed — all fine outcomes for a delete, and none of them
        # something to show somebody an error about.
        return DeleteResultOut(deleted=False, id=questionnaire_id, title=None)

    eligibility = await questionnaire_eligibility(db, questionnaire=questionnaire)
    if not eligibility.can_delete:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=eligibility.message
        )

    title = questionnaire.title
    question_ids = list(
        (
            await db.execute(
                select(QuestionnaireQuestion.id).where(
                    QuestionnaireQuestion.questionnaire_id == questionnaire.id
                )
            )
        )
        .scalars()
        .all()
    )

    if question_ids:
        # Answers before questions: `QuestionnaireAnswer.question_id` is a
        # non-null foreign key, so the other order fails at the database.
        await db.execute(
            delete(QuestionnaireAnswer).where(
                QuestionnaireAnswer.question_id.in_(question_ids)
            )
        )
        await db.execute(
            delete(QuestionnaireQuestion).where(
                QuestionnaireQuestion.id.in_(question_ids)
            )
        )

    # The tombstone, written before the row goes. Deliberately the id,
    # the title, the actor and the time — and not the questions or the
    # answers, which are the content somebody asked to have destroyed.
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.questionnaire.deleted",
        object_type="questionnaire",
        object_id=str(questionnaire.id),
        before_state={"title": title, "status": questionnaire.status},
        after_state={"deleted": True, "questions_removed": len(question_ids)},
    )
    await db.delete(questionnaire)
    await db.commit()

    return DeleteResultOut(deleted=True, id=questionnaire_id, title=title)


async def _audit_or_404(
    db: AsyncSession, audit_id: uuid.UUID, organization_id: uuid.UUID
) -> Audit:
    audit = await db.get(Audit, audit_id)
    if audit is None or audit.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found")
    return audit


@router.post("/audits/{audit_id}/archive", response_model=ArchiveResultOut)
async def archive_audit(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> ArchiveResultOut:
    """Take an audit off the active list, keeping its findings.

    The findings, the remediation tasks they raised and the trail stay
    exactly as they are. An audit is the record of what an auditor saw,
    and that does not stop being true because the engagement is over.
    """
    audit = await _audit_or_404(db, audit_id, context.organization_id)

    if audit.archived_at is not None:
        return ArchiveResultOut(
            id=audit.id,
            title=audit.title,
            archived_at=audit.archived_at,
            status=audit.status,
            changed=False,
        )

    audit.archived_at = datetime.now(UTC)
    audit.archived_by = context.user.id
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.audit.archived",
        object_type="audit",
        object_id=str(audit.id),
        before_state={"archived": False, "status": audit.status},
        after_state={"archived": True, "status": audit.status, "title": audit.title},
    )
    await db.commit()

    return ArchiveResultOut(
        id=audit.id,
        title=audit.title,
        archived_at=audit.archived_at,
        status=audit.status,
        changed=True,
    )


@router.post("/audits/{audit_id}/restore", response_model=ArchiveResultOut)
async def restore_audit(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> ArchiveResultOut:
    """Put an archived audit back on the active list."""
    audit = await _audit_or_404(db, audit_id, context.organization_id)

    if audit.archived_at is None:
        return ArchiveResultOut(
            id=audit.id,
            title=audit.title,
            archived_at=None,
            status=audit.status,
            changed=False,
        )

    audit.archived_at = None
    audit.archived_by = None
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.audit.restored",
        object_type="audit",
        object_id=str(audit.id),
        before_state={"archived": True, "status": audit.status},
        after_state={"archived": False, "status": audit.status, "title": audit.title},
    )
    await db.commit()

    return ArchiveResultOut(
        id=audit.id,
        title=audit.title,
        archived_at=None,
        status=audit.status,
        changed=True,
    )


@router.delete("/audits/{audit_id}", response_model=DeleteResultOut)
async def delete_audit(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.delete")),
) -> DeleteResultOut:
    """Permanently remove an audit that never got started.

    Allowed only while it is still a plan: no findings, still `planned`,
    never completed. Once an auditor has raised a finding, the audit is
    the record of what they saw and archiving is the answer instead.
    """
    audit = await db.get(Audit, audit_id)
    if audit is None or audit.organization_id != context.organization_id:
        return DeleteResultOut(deleted=False, id=audit_id, title=None)

    eligibility = await audit_eligibility(db, audit=audit)
    if not eligibility.can_delete:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=eligibility.message
        )

    title = audit.title
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.audit.deleted",
        object_type="audit",
        object_id=str(audit.id),
        before_state={"title": title, "status": audit.status},
        after_state={"deleted": True},
    )
    await db.delete(audit)
    await db.commit()

    return DeleteResultOut(deleted=True, id=audit_id, title=title)


async def _prepare_audit_or_explain(
    db: AsyncSession,
    *,
    audit: Audit,
    actor_user_id: uuid.UUID | None,
) -> audit_workspace.PreparationReport:
    """Prepare an audit, and turn any failure into something readable.

    Preparation touches the framework catalog, the organization's
    declared facts, its controls, its evidence and its gaps. Any of those
    can be in a state this code did not anticipate, and when one was, the
    whole thing surfaced as "That did not go through. Nothing was
    changed." — which tells the person nothing and tells us nothing
    either.

    So: a failure this module named comes back with its own code and
    sentence, and anything else is logged in full server-side and
    reported as a safe message that at least names the framework. No
    stack traces or SQL reach the screen.
    """
    try:
        return await audit_workspace.prepare(
            db, audit=audit, actor_user_id=actor_user_id
        )
    except audit_workspace.PreparationFailed as failure:
        logger.warning(
            "Audit %s preparation refused (%s): %s",
            audit.id,
            failure.code,
            failure.message,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": failure.code, "message": failure.message},
        ) from failure
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - the whole point is not to leak
        # Logged with the traceback, because the next person debugging
        # this needs the line number and the customer must never see it.
        logger.exception(
            "Audit %s preparation failed for framework %s",
            audit.id,
            audit.framework_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "preparation_failed",
                "message": (
                    "Veyntra could not prepare this audit from your current "
                    "compliance data. The failure has been logged. Nothing "
                    "about the audit was changed."
                ),
            },
        ) from exc


async def _audit_item_or_404(
    db: AsyncSession, item_id: uuid.UUID, audit: Audit
) -> AuditItem:
    item = await db.get(AuditItem, item_id)
    if item is None or item.audit_id != audit.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Audit item not found"
        )
    return item


async def _audit_finding_or_404(
    db: AsyncSession, finding_id: uuid.UUID, audit: Audit
) -> AuditFinding:
    finding = await db.get(AuditFinding, finding_id)
    if finding is None or finding.audit_id != audit.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found"
        )
    return finding


@router.post("/audits/reconcile-auditors", response_model=dict)
async def reconcile_audit_auditors(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> dict:
    """Link legacy auditors to the accounts they unambiguously are.

    A repair, not a migration: audits created before the auditor type was
    recorded carry only a name, and a name matching exactly one member of
    this organization is that member. A name matching two members, or
    none, is left alone and reported — attributing an audit to the wrong
    person is worse than leaving it unresolved, and nothing here ever
    concludes that somebody was external.
    """
    result = await audit_identity.reconcile_auditors(
        db, organization_id=context.organization_id
    )
    if result.linked:
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="compliance.audit.auditors_reconciled",
            object_type="organization",
            object_id=str(context.organization_id),
            after_state={
                "linked": result.linked,
                "ambiguous": result.ambiguous,
                "unmatched": result.unmatched,
            },
        )
        await db.commit()
    return {
        "linked": result.linked,
        "already_resolved": result.already_resolved,
        "ambiguous": result.ambiguous,
        "unmatched": result.unmatched,
    }


@router.patch("/audits/{audit_id}", response_model=AuditOut)
async def update_audit(
    audit_id: uuid.UUID,
    payload: AuditUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditOut:
    """Correct an audit's scope.

    Mainly for the audit that was opened before anybody picked a
    framework: a title with nothing behind it. Attaching one here
    prepares the workspace, so the engagement people have already named
    becomes the one they work in rather than being abandoned for a second
    audit of the same thing.

    Re-scoping a completed audit is refused. Its conclusions were reached
    against the scope it had, and changing that underneath them would
    make the record say something nobody signed.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    if audit.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A completed audit cannot be re-scoped. Its findings were "
                "reached against the scope it had."
            ),
        )

    fields = payload.model_dump(exclude_unset=True)
    framework_changed = (
        "framework_id" in fields and fields["framework_id"] != audit.framework_id
    )
    if framework_changed and fields["framework_id"] is not None:
        framework = await db.get(Framework, fields["framework_id"])
        if framework is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found"
            )

    before = {
        "framework_id": str(audit.framework_id) if audit.framework_id else None,
        "scope": audit.scope,
    }
    for field, value in fields.items():
        setattr(audit, field, value)
    await db.flush()

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.audit.updated",
        object_type="audit",
        object_id=str(audit.id),
        before_state=before,
        after_state={
            "framework_id": str(audit.framework_id) if audit.framework_id else None,
            "scope": audit.scope,
            "title": audit.title,
        },
    )

    if framework_changed and audit.framework_id is not None:
        # A new framework is a new scope. Rows already decided keep both
        # the decision and the snapshot behind it; the rest are rebuilt.
        await _prepare_audit_or_explain(
            db, audit=audit, actor_user_id=context.user.id
        )

    await db.commit()
    await db.refresh(audit)
    return await _audit_out(db, audit)


@router.post("/audits/{audit_id}/prepare", response_model=AuditPreparationOut)
async def prepare_audit(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditPreparationOut:
    """Build the audit's worklist from the compliance state as it stands.

    The auditor should review Veyntra's prepared work, not reconstruct it.
    This walks the framework's requirements through the same assessment
    the readiness screen uses and writes one row per applicable
    requirement, carrying what was found: the control, the evidence, the
    state, and what is missing.

    Idempotent, and safe to re-run. Rows the auditor has already decided
    on keep both their decision and the snapshot it was reached from —
    a refresh must never quietly erase somebody's work.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    if audit.framework_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This audit has no framework, so there is nothing to scope it "
                "against. Set a framework on the audit first."
            ),
        )
    report = await _prepare_audit_or_explain(
        db, audit=audit, actor_user_id=context.user.id
    )
    await db.commit()
    return AuditPreparationOut(**report.as_dict())


@router.get("/audits/{audit_id}/scope", response_model=AuditScopeOut)
async def get_audit_scope(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> AuditScopeOut:
    """Every requirement the framework has, and why it is or is not here.

    "3 requirements in scope" is not an answer on its own — a reader
    wants to know what happened to the other fifteen. Included, not
    applicable, and excluded by the auditor are three different answers
    with three different consequences, and a report is defended on them.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    lines = await audit_workspace.scope_lines(db, audit=audit)
    return AuditScopeOut(
        framework_name=audit.framework_name,
        included=sum(1 for line in lines if line.disposition == "included"),
        not_applicable=sum(1 for line in lines if line.disposition == "not_applicable"),
        excluded=sum(1 for line in lines if line.disposition == "excluded"),
        lines=[
            AuditScopeLineOut(
                requirement_id=line.requirement_id,
                reference_code=line.reference_code,
                title=line.title,
                disposition=line.disposition,
                reason=line.reason,
                excluded_at=line.excluded_at,
            )
            for line in lines
        ],
    )


@router.post(
    "/audits/{audit_id}/items/{item_id}/exclude", response_model=AuditItemOut
)
async def exclude_audit_item(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: AuditExclusionIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditItemOut:
    """Take a requirement out of this audit's scope, with a reason.

    Scope is the auditor's to set, and this changes this audit only —
    the organization's framework applicability is a different question
    and is left exactly as it was.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    item = await _audit_item_or_404(db, item_id, audit)
    try:
        await audit_workspace.set_exclusion(
            db,
            audit=audit,
            item=item,
            reason=payload.reason,
            excluded=True,
            actor_user_id=context.user.id,
        )
    except audit_workspace.ExclusionRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "exclusion_refused", "message": str(exc)},
        ) from exc
    await db.commit()
    return _item_out(audit_workspace.ItemView(item=item, section="satisfied"))


@router.post(
    "/audits/{audit_id}/items/{item_id}/include", response_model=AuditItemOut
)
async def include_audit_item(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditItemOut:
    """Put an excluded requirement back into this audit's scope."""
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    item = await _audit_item_or_404(db, item_id, audit)
    await audit_workspace.set_exclusion(
        db,
        audit=audit,
        item=item,
        reason=None,
        excluded=False,
        actor_user_id=context.user.id,
    )
    await db.commit()
    return _item_out(audit_workspace.ItemView(item=item, section="satisfied"))


@router.get("/audits/{audit_id}/items", response_model=list[AuditItemOut])
async def list_audit_items(
    audit_id: uuid.UUID,
    section: str | None = None,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[AuditItemOut]:
    """The scoped requirements, exceptions first.

    Ordered the way an auditor works: known gaps, then what needs a human
    decision, then thin evidence, then anything that changed since the
    audit was prepared, then the rows with no issue found.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    views = await audit_workspace.item_views(db, audit=audit)
    # An excluded requirement is not outstanding work. It stays visible
    # under the scope view, with the reason it was left out.
    views = [view for view in views if view.item.excluded_at is None]
    if section:
        views = [view for view in views if view.section == section]
    return [_item_out(view) for view in views]


@router.post(
    "/audits/{audit_id}/items/{item_id}/decision",
    response_model=AuditDecisionResultOut,
)
async def decide_audit_item(
    audit_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: AuditDecisionIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditDecisionResultOut:
    """Record what the auditor concluded about one scoped requirement.

    This is the primary path to a finding. The requirement, control and
    evidence come from the row rather than being retyped, so the finding
    says what it was based on.

    A decision that asserts a deficiency needs a reason, and the server
    is what enforces that — "Major finding" with no sentence beside it is
    not something the organization can act on.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    item = await _audit_item_or_404(db, item_id, audit)
    try:
        result = await audit_finding_service.record_decision(
            db,
            audit=audit,
            item=item,
            decision=payload.decision,
            note=payload.note,
            title=payload.title,
            actor_user_id=context.user.id,
        )
    except audit_finding_service.DecisionRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()

    views = await audit_workspace.item_views(db, audit=audit)
    view = next((v for v in views if v.item.id == item.id), None)
    return AuditDecisionResultOut(
        item=_item_out(view)
        if view
        else _item_out(audit_workspace.ItemView(item=item, section="satisfied")),
        finding=_finding_out(result.finding) if result.finding else None,
        finding_created=result.finding_created,
        remediation_reused=result.task_reused,
        related_task_id=result.task_id,
    )


@router.post(
    "/audits/{audit_id}/findings/{finding_id}/ready",
    response_model=AuditFindingOut,
)
async def mark_finding_ready(
    audit_id: uuid.UUID,
    finding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditFindingOut:
    """The team says the remediation is done.

    Deliberately not a closure. Whether the fix answers the finding is a
    judgement about evidence, and the person who did the work does not
    get to make it.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    finding = await _audit_finding_or_404(db, finding_id, audit)
    changed = await audit_finding_service.mark_ready_for_verification(
        db, finding=finding, actor_user_id=context.user.id
    )
    if changed:
        await db.commit()
    return _finding_out(finding)


@router.post(
    "/audits/{audit_id}/findings/{finding_id}/verify",
    response_model=AuditFindingOut,
)
async def verify_finding(
    audit_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: AuditVerificationIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditFindingOut:
    """The auditor accepts the fix, and records on what basis.

    The note is required and kept: this is the record that says the
    organization's problem was actually solved, and a closure with no
    reasoning reads the same as no closure at all.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    finding = await _audit_finding_or_404(db, finding_id, audit)
    try:
        changed = await audit_finding_service.verify_and_close(
            db,
            finding=finding,
            note=payload.note,
            actor_user_id=context.user.id,
        )
    except audit_finding_service.DecisionRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    if changed:
        await db.commit()
    return _finding_out(finding)


@router.post(
    "/audits/{audit_id}/findings/{finding_id}/reopen",
    response_model=AuditFindingOut,
)
async def reopen_finding(
    audit_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: AuditReopenIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditFindingOut:
    """More work needed. Back to the team, with the reason."""
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    finding = await _audit_finding_or_404(db, finding_id, audit)
    changed = await audit_finding_service.reopen(
        db, finding=finding, note=payload.note, actor_user_id=context.user.id
    )
    if changed:
        await db.commit()
    return _finding_out(finding)


def _finding_out(finding: AuditFinding) -> AuditFindingOut:
    out = AuditFindingOut.model_validate(finding)
    out.status_label = audit_finding_service.STATUS_LABELS.get(
        finding.status, finding.status.replace("_", " ").capitalize()
    )
    return out


def _item_out(view: audit_workspace.ItemView) -> AuditItemOut:
    item = view.item
    out = AuditItemOut.model_validate(item)
    out.section = view.section
    out.new_evidence = [AuditEvidenceOut(**entry) for entry in view.new_evidence]
    # Two different claims by two different parties, labelled as such.
    # Veyntra says what the evidence shows; the auditor says what they
    # concluded about it. Rendering them as two bare badges side by side
    # was asking the reader to work out which was which.
    out.prepared_status_label = ASSESSMENT_STATUS_LABELS.get(
        item.prepared_status, item.prepared_status.replace("_", " ").capitalize()
    )
    out.decision_label = (
        audit_workspace.DECISION_LABELS.get(item.decision) if item.decision else None
    )
    if view.current_status:
        out.current_status = view.current_status
        out.current_status_label = ASSESSMENT_STATUS_LABELS.get(
            view.current_status, view.current_status.replace("_", " ").capitalize()
        )
    finding = view.finding
    if finding is not None:
        out.finding_status = finding.status
        out.finding_status_label = audit_finding_service.STATUS_LABELS.get(
            finding.status, finding.status.replace("_", " ").capitalize()
        )
        out.finding_severity = finding.severity
        out.remediation_task_id = finding.related_task_id
    return out


async def _audit_out(db: AsyncSession, audit: Audit) -> AuditOut:
    """One audit row, with how far through its scope the auditor is.

    Progress is review progress — scoped requirements dispositioned — and
    not compliance readiness. A card that shows one where the other
    belongs is worse than one that shows neither.
    """
    out = AuditOut.model_validate(audit)
    out.status_label = audit_state.LABELS.get(audit.status, audit.status)
    summary = await audit_state.summarise(db, audit_id=audit.id)
    # How many the framework has that do not bind this organization —
    # carried from preparation so the scope line adds up without
    # re-evaluating the whole framework on every list render.
    summary.not_applicable = int(
        (audit.prepared_summary or {}).get("not_applicable", 0) or 0
    )
    out.progress = AuditProgressOut(**summary.as_dict())
    out.finding_count = summary.open_findings
    return out


@router.get("/audits", response_model=list[AuditOut])
async def list_audits(
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[AuditOut]:
    """Audit engagements, active or archived.

    `finding_count` travels with the row because it is the thing that
    decides whether this audit may be deleted, and a reader looking at
    the menu deserves to see the reason it says what it says.
    """
    result = await db.execute(
        select(Audit)
        .where(
            Audit.organization_id == context.organization_id,
            Audit.archived_at.is_not(None) if archived else Audit.archived_at.is_(None),
        )
        .order_by(Audit.created_at.desc())
    )
    rows = list(result.scalars().all())

    counts = dict(
        (
            await db.execute(
                select(AuditFinding.audit_id, func.count(AuditFinding.id))
                .where(AuditFinding.organization_id == context.organization_id)
                .group_by(AuditFinding.audit_id)
            )
        ).all()
    )

    out: list[AuditOut] = []
    for audit in rows:
        # Progress, findings and what is awaiting verification — the card
        # should say where the engagement stands, not just "planned".
        item = await _audit_out(db, audit)
        eligibility = await audit_eligibility(db, audit=audit)
        item.can_delete = eligibility.can_delete
        item.delete_blocked_reason = eligibility.message or None
        out.append(item)
    return out


@router.post("/audits", response_model=AuditOut, status_code=status.HTTP_201_CREATED)
async def create_audit(
    payload: AuditCreate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditOut:
    """Open an audit engagement, and prepare its worklist.

    A framework is what makes an audit scopeable: it decides which
    requirements Veyntra walks. Where one is given, the workspace is
    built immediately, so the audit opens on prepared work rather than on
    a blank finding form.
    """
    framework = None
    if payload.framework_id is not None:
        framework = await db.get(Framework, payload.framework_id)
        if framework is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
    fields = payload.model_dump()

    # Who conducted it, established rather than accepted. A picked
    # colleague is internal because they are a member of this
    # organization — checked here, so an audit can never be recorded as
    # internal against somebody who is not one. An audit with no account
    # is external only when somebody said so; otherwise it stays
    # unresolved, because "no account id" is not evidence that a person
    # was external. That inference is what printed "Zach Warren
    # (external)" on a colleague's internal audit.
    if fields.get("auditor_user_id") is not None:
        if not await audit_identity.is_member(
            db,
            organization_id=context.organization_id,
            user_id=fields["auditor_user_id"],
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "That auditor is not a member of this organization. Pick a "
                    "colleague, or record an external auditor by name."
                ),
            )
        fields["auditor_type"] = audit_identity.INTERNAL
        # An internal auditor's organization is the one running the
        # audit; a firm name here would be a second, contradictory claim.
        fields["auditor_organization"] = None
        person = await db.get(User, fields["auditor_user_id"])
        if person is not None:
            fields["auditor_name"] = person.full_name or person.email

    audit = Audit(organization_id=context.organization_id, **fields)
    # A new audit has not started and has certainly not finished. Set
    # through the same function every other transition uses, so there is
    # one place that decides what each status means for the timestamps.
    audit_state.apply_status(audit, "planned")
    db.add(audit)
    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.audit.created",
        object_type="audit",
        object_id=str(audit.id),
        after_state={
            "title": audit.title,
            "status": audit.status,
            "framework": framework.name if framework else None,
            "scope": audit.scope,
        },
    )
    if framework is not None:
        # Create and prepare are one action. An audit that exists but has
        # not been scoped is a half-made thing somebody has to remember to
        # finish, and a failure here must undo the creation rather than
        # leaving that behind.
        await _prepare_audit_or_explain(
            db, audit=audit, actor_user_id=context.user.id
        )
    await db.commit()
    await db.refresh(audit)
    return await _audit_out(db, audit)


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

    # The scoped requirements, grouped the way an auditor works through
    # them. Empty sections are left out rather than shown as zeros — a
    # heading over nothing is noise on a screen whose whole point is
    # putting the exceptions first.
    views = await audit_workspace.item_views(db, audit=audit)
    grouped: dict[str, list[AuditItemOut]] = {}
    for view in views:
        if view.item.excluded_at is not None:
            continue
        grouped.setdefault(view.section, []).append(_item_out(view))
    sections = [
        AuditSectionOut(
            key=key,
            label=audit_workspace.SECTION_LABELS[key],
            items=grouped[key],
        )
        for key in audit_workspace.SECTIONS
        if key in grouped
    ]

    blockers = await audit_state.completion_blockers(db, audit=audit)

    return AuditDetailOut(
        **(await _audit_out(db, audit)).model_dump(),
        findings=[
            _finding_out(f) for f in findings_result.scalars().all()
        ],
        sections=sections,
        completion_blockers=[
            AuditCompletionBlockerOut(code=b.code, message=b.message) for b in blockers
        ],
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

    if payload.status == "completed":
        # Completing an audit is a claim about the organization. An audit
        # that finishes over an unverified critical finding says something
        # untrue, so the server refuses rather than the screen hiding a
        # button — a client that gets this wrong must not be able to
        # record a clean audit over open work.
        blockers = await audit_state.completion_blockers(db, audit=audit)
        if blockers:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "This audit cannot be completed yet: "
                    + " ".join(blocker.message for blocker in blockers)
                ),
            )

    if payload.status == "in_progress":
        # An audit with nothing in scope has examined nothing, and
        # starting one produces a record that says otherwise. This is the
        # server's copy of the rule the button also enforces.
        blockers = await audit_state.start_blockers(db, audit=audit)
        if blockers:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": blockers[0].code,
                    "message": " ".join(blocker.message for blocker in blockers),
                },
            )

    # The status and its timestamps move together. They were separate
    # writes, which is how an audit came to sit at "Planned" with a
    # completion date printed beside it.
    audit_state.apply_status(audit, payload.status)

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.audit.status_changed",
        object_type="audit",
        object_id=str(audit.id),
        before_state={"status": before_status},
        after_state={
            "status": audit.status,
            "started_at": audit.started_at.isoformat() if audit.started_at else None,
            "completed_at": (
                audit.completed_at.isoformat() if audit.completed_at else None
            ),
        },
    )
    await db.commit()
    await db.refresh(audit)
    return await _audit_out(db, audit)


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
    # Every questionnaire in the engagement. A review created before the
    # sales module was withdrawn also carries a single `questionnaire_id`;
    # the migration copied that onto the new link, so this one query finds
    # both kinds.
    linked = list(
        (
            await db.execute(
                select(Questionnaire)
                .where(Questionnaire.security_review_id == review.id)
                .order_by(Questionnaire.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    opportunity = (
        await db.get(Opportunity, review.opportunity_id)
        if review.opportunity_id is not None
        else None
    )
    approval_status = None
    if review.approval_id is not None:
        approval = await db.get(Approval, review.approval_id)
        approval_status = approval.status if approval else None

    # Gaps are still counted against the questionnaire the legacy flow
    # built them for; a review with none simply reports none.
    gaps = (
        await list_security_review_gaps(db, questionnaire_id=review.questionnaire_id)
        if review.questionnaire_id is not None
        else []
    )

    questionnaires: list[ReviewQuestionnaireOut] = []
    for row in linked:
        statuses = await _answer_statuses_for(db, questionnaire_id=row.id)
        questionnaires.append(
            ReviewQuestionnaireOut(
                id=row.id,
                title=row.title,
                source=row.source,
                status=row.status,
                href=f"/compliance/questionnaires/{row.id}",
                archived_at=row.archived_at,
                progress=_questionnaire_progress(statuses),
            )
        )

    return SecurityReviewDetailOut(
        **(await _review_out(db, review)).model_dump(),
        questionnaires=questionnaires,
        opportunity_title=opportunity.title if opportunity else None,
        approval_status=approval_status,
        gap_count=len(gaps),
        questionnaire=(
            await _build_questionnaire_detail(db, linked[0]) if linked else None
        ),
    )


def _customer_repair_state(
    questionnaire: Questionnaire, review: SecurityReview | None
) -> dict[str, object]:
    """Why this customer questionnaire has no engagement, and what to offer.

    Only ever set for a customer-provided questionnaire that is in no
    review — an internal assessment is not missing anything, and one
    already linked has nothing to repair. The suggestion is shown, never
    applied: the person on this screen is the one who knows whether the
    words in the title are a customer's name.
    """
    if questionnaire.source != "customer_provided":
        return {"needs_customer": False}
    if (questionnaire.customer_name or "").strip():
        # Named but unlinked. That is a backfill away, not a question.
        return {"needs_customer": False}
    if review is not None and (review.customer_name or "").strip():
        # In an engagement that knows whose it is. Nothing to ask.
        return {"needs_customer": False}
    suggestion = suggest_customer_name(questionnaire.title)
    return {
        "needs_customer": True,
        "suggested_customer": suggestion.name if suggestion else None,
        "suggested_customer_reason": suggestion.reason if suggestion else None,
    }


async def _answer_statuses_for(
    db: AsyncSession, *, questionnaire_id: uuid.UUID
) -> list[str]:
    """One entry per question, so an unanswered one counts.

    The same left join the questionnaire's own status uses — an inner
    join would drop exactly the questions that keep work outstanding.
    """
    rows = (
        await db.execute(
            select(QuestionnaireAnswer.status)
            .select_from(QuestionnaireQuestion)
            .outerjoin(
                QuestionnaireAnswer,
                QuestionnaireAnswer.question_id == QuestionnaireQuestion.id,
            )
            .where(QuestionnaireQuestion.questionnaire_id == questionnaire_id)
        )
    ).all()
    return [row[0] or "unanswered" for row in rows]


async def _review_out(db: AsyncSession, review: SecurityReview) -> SecurityReviewOut:
    """One review row, with its work added up.

    Progress comes from `app.compliance.customer_review`, the same
    calculation the review page and the status derivation use — so the
    card, the page and the badge cannot disagree.
    """
    # Scope is decided inside `progress_for`, from the questionnaires:
    # the live ones, or all of them when none are live. Passing the
    # review's own archived flag in here made the same three approved
    # answers read differently depending on which tab the review was on.
    progress = await customer_review_progress(db, review_id=review.id)
    out = SecurityReviewOut.model_validate(review)
    out.status_label = customer_review_label(review.status)
    out.progress = ReviewProgressOut(
        questionnaires=progress.questionnaires,
        total=progress.total,
        approved=progress.approved,
        needs_review=progress.needs_review,
        draft=progress.draft,
        unanswered=progress.unanswered,
        percent_complete=progress.percent_complete,
        ready_to_share=progress.ready,
    )
    return out


@router.post(
    "/security-reviews/{review_id}/archive", response_model=ArchiveResultOut
)
async def archive_security_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(
        require_permission("compliance.security_reviews.manage")
    ),
) -> ArchiveResultOut:
    """Close a customer engagement, keeping everything in it.

    The questionnaires stay linked and stay exactly as they are. This
    says the conversation with the customer is over, not that the
    evidence of it should go anywhere.
    """
    review = await _get_org_security_review(db, review_id, context.organization_id)
    changed = await set_review_lifecycle(
        db, review=review, archived=True, actor_user_id=context.user.id
    )
    if changed:
        await db.commit()
    return ArchiveResultOut(
        id=review.id,
        title=review.title or "Customer security review",
        archived_at=review.archived_at,
        status=review.status,
        changed=changed,
    )


@router.post(
    "/security-reviews/{review_id}/restore", response_model=ArchiveResultOut
)
async def restore_security_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(
        require_permission("compliance.security_reviews.manage")
    ),
) -> ArchiveResultOut:
    """Reopen a customer engagement.

    Refused when the customer already has an open one: two live reviews
    for one customer is the state the whole engagement model exists to
    prevent, and the partial unique index would refuse it anyway — better
    to say so than to surface a constraint error.
    """
    review = await _get_org_security_review(db, review_id, context.organization_id)
    if review.archived_at is not None and review.customer_name:
        clash = await find_active_customer_review(
            db,
            organization_id=context.organization_id,
            customer_name=review.customer_name,
        )
        if clash is not None and clash.id != review.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{review.customer_name} already has an open security "
                    "review. Archive that one first, or move the "
                    "questionnaires into it."
                ),
            )
    changed = await set_review_lifecycle(
        db, review=review, archived=False, actor_user_id=context.user.id
    )
    if changed:
        await db.commit()
    return ArchiveResultOut(
        id=review.id,
        title=review.title or "Customer security review",
        archived_at=review.archived_at,
        status=review.status,
        changed=changed,
    )


def _preview_out(
    preview: review_export.ExportPreview, *, next_version: int
) -> ExportPreviewOut:
    return ExportPreviewOut(
        output_type=preview.output_type,
        output_label=preview.output_label,
        file_format=preview.file_format,
        title=preview.title,
        customer_name=preview.customer_name,
        review_title=preview.review_title,
        review_status=preview.review_status,
        review_status_label=preview.review_status_label,
        review_archived=preview.review_archived,
        review_date=preview.review_date,
        progress=ReviewProgressOut(
            questionnaires=preview.progress.questionnaires,
            total=preview.progress.total,
            approved=preview.progress.approved,
            needs_review=preview.progress.needs_review,
            draft=preview.progress.draft,
            unanswered=preview.progress.unanswered,
            percent_complete=preview.progress.percent_complete,
            ready_to_share=preview.progress.ready,
        ),
        answers=[
            ExportAnswerOut(
                question_id=line.question_id,
                question=line.question,
                category=line.category,
                answer=line.answer,
                approved_at=line.approved_at,
                sources=line.sources,
                qualified=line.qualified,
            )
            for line in preview.answers
        ],
        documents=[
            ExportDocumentOut(
                file_id=document.file_id,
                title=document.title,
                kind=document.kind,
                disclosure=document.disclosure,
                disclosure_label=review_export.DISCLOSURE_LABELS.get(
                    document.disclosure, document.disclosure
                ),
                eligible=document.eligible,
                reason=document.reason,
                version=document.version,
                status=document.status,
                superseded=document.superseded,
                supports=document.supports,
                included=document.included,
            )
            for document in preview.documents
        ],
        disclosures=preview.disclosures,
        blockers=[
            ExportBlockerOut(code=b.code, message=b.message) for b in preview.blockers
        ],
        sections=preview.sections,
        section_labels=dict(review_export.SECTION_LABELS),
        introduction=preview.introduction,
        disclaimer=preview.disclaimer,
        ready=preview.ready,
        digest=preview.digest,
        next_version=next_version,
        column_mapping=preview.column_mapping,
        source_filename=preview.source_filename,
    )


async def _export_out(
    db: AsyncSession, export: ReviewExport, *, review: SecurityReview
) -> ReviewExportOut:
    out = ReviewExportOut.model_validate(export)
    out.output_label = review_export.OUTPUT_LABELS.get(
        export.output_type, export.output_type
    )
    contents = export.contents or {}
    out.answer_count = len(contents.get("answers") or [])
    out.document_count = len(contents.get("documents") or [])
    out.stale = await review_export.is_stale(db, export=export, review=review)
    return out


@router.post(
    "/security-reviews/{review_id}/export/preview", response_model=ExportPreviewOut
)
async def preview_review_export(
    review_id: uuid.UUID,
    payload: ExportPreviewRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> ExportPreviewOut:
    """Exactly what the customer would receive. Nothing is generated.

    Deliberately a read: opening and refreshing a preview must not leave
    a trail of packages nobody sent, and the export history has to mean
    "what we sent" rather than "what somebody looked at".

    Reading is also why this needs no export permission — anybody who can
    see the review can see what would go in a package. Turning that into
    a deliverable is the separate act, and the separate permission.
    """
    review = await _get_org_security_review(db, review_id, context.organization_id)
    try:
        preview = await review_export.build_preview(
            db,
            review=review,
            output_type=payload.output_type,
            include_documents=payload.include_documents,
            sections=payload.sections,
            title=payload.title,
            introduction=payload.introduction,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _preview_out(
        preview,
        next_version=await review_export.next_version(
            db, review_id=review.id, output_type=payload.output_type
        ),
    )


@router.post(
    "/security-reviews/{review_id}/export",
    response_model=ReviewExportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_review_export(
    review_id: uuid.UUID,
    payload: ExportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(
        require_permission("compliance.review_exports.generate")
    ),
) -> ReviewExportOut:
    """Generate the previewed package, and record having done so.

    `confirm_digest` comes from the preview. Requiring it back is what
    makes this "generate what I was shown" rather than "generate whatever
    is true now" — between reading a preview and clicking generate,
    somebody else can approve an answer, and the person confirming would
    be sending a document they never saw.
    """
    review = await _get_org_security_review(db, review_id, context.organization_id)
    preview = await review_export.build_preview(
        db,
        review=review,
        output_type=payload.output_type,
        include_documents=payload.include_documents,
        sections=payload.sections,
        title=payload.title,
        introduction=payload.introduction,
    )
    try:
        export = await review_export_service.generate(
            db,
            review=review,
            preview=preview,
            confirm_digest=payload.confirm_digest,
            actor_user_id=context.user.id,
            may_override_disclosure=(
                "compliance.review_exports.override_disclosure"
                in context.permissions
            ),
        )
    except review_export_service.ExportRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(export)
    return await _export_out(db, export, review=review)


@router.get(
    "/security-reviews/{review_id}/exports", response_model=list[ReviewExportOut]
)
async def list_review_exports(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[ReviewExportOut]:
    """Every package generated for this review, newest first.

    Nothing is ever replaced. Regenerating adds a version; the earlier
    one stays downloadable, because the customer still has their copy and
    our record of what we sent them has to match it.
    """
    review = await _get_org_security_review(db, review_id, context.organization_id)
    exports = await review_export_service.history(db, review_id=review.id)
    return [await _export_out(db, export, review=review) for export in exports]


@router.get("/security-reviews/{review_id}/exports/{export_id}/download")
async def download_review_export(
    review_id: uuid.UUID,
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> dict[str, str]:
    """A signed, time-limited link to the generated package."""
    await _get_org_security_review(db, review_id, context.organization_id)
    export = await db.get(ReviewExport, export_id)
    if (
        export is None
        or export.organization_id != context.organization_id
        or export.security_review_id != review_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Export not found"
        )
    if export.file_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This export has no file attached.",
        )
    file_record = await db.get(File, export.file_id)
    if file_record is None:  # pragma: no cover - the foreign key guarantees it
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    return {
        "url": presign_download(file_record.storage_key),
        "filename": file_record.original_filename,
    }


@router.post(
    "/security-reviews/{review_id}/exports/{export_id}/shared",
    response_model=ReviewExportOut,
)
async def mark_export_shared(
    review_id: uuid.UUID,
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(
        require_permission("compliance.review_exports.generate")
    ),
) -> ReviewExportOut:
    """Record that this package actually went to the customer.

    Separate from generating it. A product that marks something shared
    because a file exists is telling its user a delivery happened that
    nobody performed.
    """
    review = await _get_org_security_review(db, review_id, context.organization_id)
    export = await db.get(ReviewExport, export_id)
    if (
        export is None
        or export.organization_id != context.organization_id
        or export.security_review_id != review_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Export not found"
        )
    if await review_export_service.mark_shared(
        db, export=export, actor_user_id=context.user.id
    ):
        await db.commit()
    return await _export_out(db, export, review=review)


@router.patch("/documents/{file_id}/disclosure", response_model=dict)
async def set_document_disclosure(
    file_id: uuid.UUID,
    payload: FileDisclosureUpdate,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> dict:
    """Decide whether a document may leave the organization.

    Recorded rather than merely set. "Who marked the architecture diagram
    customer-shareable, and when" is a question somebody will ask after
    it has gone out, and a field with no history cannot answer it.
    """
    file_record = await db.get(File, file_id)
    if file_record is None or file_record.organization_id != context.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )
    before = file_record.disclosure
    if before == payload.disclosure:
        return {"file_id": str(file_id), "disclosure": before, "changed": False}

    file_record.disclosure = payload.disclosure
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.document.disclosure_changed",
        object_type="file",
        object_id=str(file_record.id),
        before_state={"disclosure": before},
        after_state={
            "disclosure": payload.disclosure,
            "filename": file_record.original_filename,
        },
    )
    await db.commit()
    return {
        "file_id": str(file_id),
        "disclosure": payload.disclosure,
        "changed": True,
    }


@router.post("/security-reviews/backfill", response_model=ReviewBackfillOut)
async def backfill_security_reviews(
    dry_run: bool = True,
    confirm_suggested_customers: bool = False,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.security_reviews.manage")),
) -> ReviewBackfillOut:
    """Link customer questionnaires that predate the engagement model.

    `SecurityReview` used to require a sales opportunity, so customer
    questionnaires created after that module was withdrawn have no
    engagement to point at. This gives them one.

    A questionnaire naming no customer comes back in `needs_customer`
    rather than being guessed about, with the name its title appears to
    contain offered as a suggestion. `confirm_suggested_customers` is a
    caller saying they have read those suggestions and accept them; it is
    not implied by `dry_run=False`, because "link the ones whose customer
    we recorded" and "and also trust the titles" are different decisions.

    Idempotent, and `dry_run` defaults to true.
    """
    report = await backfill_customer_reviews(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        dry_run=dry_run,
        confirm_suggested_customers=confirm_suggested_customers,
    )
    if not dry_run:
        await db.commit()
    return ReviewBackfillOut(**report.as_dict(), dry_run=dry_run)


@router.get("/security-reviews", response_model=list[SecurityReviewOut])
async def list_security_reviews(
    archived: bool = False,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[SecurityReviewOut]:
    """The customer engagements being worked on, or the ones put away.

    Each row carries its own progress, added up across the questionnaires
    inside it, so the card does not have to compute a percentage the
    review page would compute differently.
    """
    result = await db.execute(
        select(SecurityReview)
        .where(
            SecurityReview.organization_id == context.organization_id,
            SecurityReview.archived_at.is_not(None)
            if archived
            else SecurityReview.archived_at.is_(None),
        )
        .order_by(SecurityReview.created_at.desc())
    )
    return [await _review_out(db, review) for review in result.scalars().all()]


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


@router.post("/documents/reindex", response_model=CopilotIndexBackfillOut)
async def reindex_documents_for_copilot(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.evidence.manage")),
) -> CopilotIndexBackfillOut:
    """Index analysed documents the Copilot cannot yet see.

    Indexing was added after documents were already being processed, so
    every organization has a library the Copilot is blind to. This runs
    automatically when the document list is opened; the endpoint exists so
    a failed indexing attempt can be retried without re-uploading.

    Idempotent: it selects only files that analysed successfully and are
    not already indexed, and re-indexing one replaces its chunks rather
    than duplicating them.
    """
    counts = await backfill_organization(db, organization_id=context.organization_id)
    return CopilotIndexBackfillOut(
        indexed=counts.get("indexed", 0),
        failed=counts.get("failed", 0),
        unsupported=counts.get("unsupported", 0),
    )


# --- the audit report --------------------------------------------------
#
# A completed audit's last step, and the one the product was missing.
# Preview, read, generate: the same two-step the customer-facing export
# uses, for the same reason. An audit report is a statement somebody puts
# their name to, and the first click must not produce a document nobody
# has read.


def _report_preview_out(
    preview: audit_report.AuditReportPreview,
) -> AuditReportPreviewOut:
    def finding(line) -> AuditReportFindingOut:
        return AuditReportFindingOut(
            id=line.id,
            reference_code=line.reference_code,
            requirement_title=line.requirement_title,
            title=line.title,
            description=line.description,
            severity=line.severity,
            conclusion_label=line.conclusion_label,
            current_status=line.current_status,
            current_status_label=line.current_status_label,
            control_title=line.control_title,
            evidence_state=line.evidence_state,
            evidence_state_label=line.evidence_state_label,
            assessment=line.assessment,
            not_evidenced=line.not_evidenced,
            auditor_note=line.auditor_note,
            rationale_gap=line.rationale_gap,
            evidence_count=line.evidence_count,
            verified_at=line.verified_at,
            verified_by=line.verified_by,
            verification_note=line.verification_note,
            remediation_task=line.remediation_task,
            remediation_owner=line.remediation_owner,
            remediation_due=line.remediation_due,
            superseded_at=line.superseded_at,
            superseded_reason=line.superseded_reason,
        )

    def identity(entry) -> AuditorIdentityOut:
        return AuditorIdentityOut(
            name=entry.name,
            auditor_type=entry.auditor_type,
            type_label=entry.type_label,
            organization=entry.organization,
            unresolved=entry.unresolved,
        )

    def metric(entry) -> AuditReportMetricOut:
        return AuditReportMetricOut(
            label=entry.label, value=entry.value, emphasis=entry.emphasis
        )

    return AuditReportPreviewOut(
        audit_id=preview.audit_id,
        title=preview.title,
        audit_title=preview.audit_title,
        organization_name=preview.organization_name,
        framework_name=preview.framework_name,
        framework_basis=preview.framework_basis,
        auditor_name=preview.auditor_name,
        auditor=identity(preview.auditor),
        organization_name_configured=preview.organization_name_configured,
        scope=preview.scope,
        status=preview.status,
        status_label=preview.status_label,
        started_at=preview.started_at,
        completed_at=preview.completed_at,
        prepared_at=preview.prepared_at,
        classification=preview.classification,
        executive_summary=list(preview.executive_summary),
        metrics=[metric(entry) for entry in preview.metrics],
        methodology=list(preview.methodology),
        conclusion_summary=[metric(entry) for entry in preview.conclusion_summary],
        progress=AuditReportProgressOut(
            scoped=preview.progress.scoped,
            reviewed=preview.progress.reviewed,
            percent_reviewed=preview.progress.percent_reviewed,
            excluded=preview.progress.excluded,
            findings=preview.progress.findings,
            superseded=preview.progress.superseded,
        ),
        conclusions=[
            AuditReportConclusionOut(
                reference_code=line.reference_code,
                requirement_title=line.requirement_title,
                control_title=line.control_title,
                evidence_state=line.evidence_state,
                evidence_state_label=line.evidence_state_label,
                decision=line.decision,
                decision_label=line.decision_label,
                decision_note=line.decision_note,
                decided_at=line.decided_at,
                decided_by=line.decided_by,
                evidence_count=line.evidence_count,
                finding_id=line.finding_id,
                current_remediation=line.current_remediation,
                current_remediation_label=line.current_remediation_label,
            )
            for line in preview.conclusions
        ],
        conclusion_counts=dict(preview.conclusion_counts),
        findings=[finding(line) for line in preview.findings],
        findings_by_severity=[
            AuditReportSeverityGroupOut(
                key=group.key,
                severity=group.severity,
                label=group.label,
                count=group.count,
                findings=[finding(line) for line in group.findings],
            )
            for group in preview.findings_by_severity
        ],
        superseded_findings=[finding(line) for line in preview.superseded_findings],
        remediation=[
            AuditReportRemediationOut(
                status=group.status, label=group.label, count=group.count
            )
            for group in preview.remediation
        ],
        remediation_rows=[finding(line) for line in preview.remediation_rows],
        verification=[finding(line) for line in preview.verification],
        evidence_index=[
            AuditReportEvidenceOut(
                title=line.title,
                filename=line.filename,
                document_href=line.document_href,
                version=line.version,
                version_label=line.version_label,
                version_source=line.version_source,
                evidence_states=list(line.evidence_states),
                requirement_codes=list(line.requirement_codes),
            )
            for line in preview.evidence_index
        ],
        limitations=list(preview.limitations),
        disclaimer=preview.disclaimer,
        sign_off=AuditReportSignOffOut(
            auditor=identity(preview.sign_off.auditor),
            completed_at=preview.sign_off.completed_at,
            generated_at=preview.sign_off.generated_at,
            generated_by=preview.sign_off.generated_by,
            report_version=preview.sign_off.report_version,
            approved_by=preview.sign_off.approved_by,
            approved_at=preview.sign_off.approved_at,
        ),
        generated_for=preview.generated_for,
        digest=preview.digest,
        next_version=preview.next_version,
        blockers=[
            AuditReportBlockerOut(code=b.code, message=b.message)
            for b in preview.blockers
        ],
        ready=preview.ready,
    )


async def _audit_report_out(
    db: AsyncSession, report: AuditReport, *, current: str | None
) -> AuditReportOut:
    contents = report.contents or {}
    progress = contents.get("progress") or {}
    name: str | None = None
    if report.generated_by:
        person = await db.get(User, report.generated_by)
        name = (person.full_name or person.email) if person else None
    return AuditReportOut(
        id=report.id,
        audit_id=report.audit_id,
        title=report.title,
        version=report.version,
        file_format=report.file_format,
        file_id=report.file_id,
        generated_by=report.generated_by,
        generated_by_name=name,
        generated_at=report.generated_at,
        # The report is unchanged either way. This only says the screen
        # should offer a new version.
        stale=bool(
            current and report.source_digest and report.source_digest != current
        ),
        findings_count=int(progress.get("findings") or 0),
        requirements_reviewed=int(progress.get("reviewed") or 0),
    )


@router.post(
    "/audits/{audit_id}/report/preview", response_model=AuditReportPreviewOut
)
async def preview_audit_report(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> AuditReportPreviewOut:
    """Exactly what the report will say. Nothing is generated.

    Deliberately a read, and deliberately needs no generate permission:
    anybody who can see the audit can see what a report of it would say.
    Turning that into an issued document is the separate act, with the
    separate permission — and opening a preview must leave the history a
    record of reports issued, not reports considered.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    preview = await audit_report.build_preview(db, audit=audit)
    return _report_preview_out(preview)


@router.post(
    "/audits/{audit_id}/report",
    response_model=AuditReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_audit_report(
    audit_id: uuid.UUID,
    payload: AuditReportGenerateRequest,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.audits.manage")),
) -> AuditReportOut:
    """Issue the previewed report, and record having issued it.

    `confirm_digest` comes from the preview. Requiring it back is what
    makes this "issue what I read" rather than "issue whatever is true
    now" — between reading a preview and clicking generate, a colleague
    can close a finding, and the person confirming would be putting their
    name to a document they never saw.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    preview = await audit_report.build_preview(db, audit=audit)
    try:
        report = await audit_report_service.generate(
            db,
            audit=audit,
            preview=preview,
            confirm_digest=payload.confirm_digest,
            actor_user_id=context.user.id,
        )
    except audit_report_service.ReportRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(report)
    return await _audit_report_out(db, report, current=preview.digest)


@router.get("/audits/{audit_id}/reports", response_model=list[AuditReportOut])
async def list_audit_reports(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[AuditReportOut]:
    """Every report issued for this audit, newest first.

    Nothing is ever replaced. If remediation moves, version 1 keeps
    saying what it said and the row is marked as no longer describing the
    audit as it stands.
    """
    audit = await _get_org_audit(db, audit_id, context.organization_id)
    reports = await audit_report_service.history(db, audit_id=audit.id)
    if not reports:
        return []
    current = await audit_report.current_digest(db, audit=audit)
    return [
        await _audit_report_out(db, report, current=current) for report in reports
    ]


@router.get("/audits/{audit_id}/reports/{report_id}/download")
async def download_audit_report(
    audit_id: uuid.UUID,
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> dict[str, str]:
    """A signed, time-limited link to the issued report."""
    await _get_org_audit(db, audit_id, context.organization_id)
    report = await db.get(AuditReport, report_id)
    if (
        report is None
        or report.organization_id != context.organization_id
        or report.audit_id != audit_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Report not found"
        )
    if report.file_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This report has no file attached.",
        )
    file_record = await db.get(File, report.file_id)
    if file_record is None:  # pragma: no cover - the foreign key guarantees it
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    return {
        "url": presign_download(file_record.storage_key),
        "filename": file_record.original_filename,
    }


# --- the privacy workspace ---------------------------------------------
#
# Four lists stacked on one page answer "show me everything". A privacy
# team opens the product asking "what needs me this week", and that
# question is derivable from the same records — so it is derived, and
# every item leads to the record it is about.


@router.get("/privacy/overview", response_model=PrivacyOverviewOut)
async def get_privacy_overview(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> PrivacyOverviewOut:
    """The privacy worklist: the counts, and what needs a person.

    A read, and deliberately gated on org context alone — anybody who can
    see the privacy records can see which of them are incomplete.
    """
    overview = await privacy_overview.build_overview(
        db, organization_id=context.organization_id
    )
    return PrivacyOverviewOut(
        metrics=[
            PrivacyMetricOut(
                key=metric.key,
                label=metric.label,
                value=metric.value,
                href=metric.href,
                tone=metric.tone,
            )
            for metric in overview.metrics
        ],
        attention=[
            PrivacyAttentionOut(
                key=item.key,
                severity=item.severity,
                title=item.title,
                detail=item.detail,
                href=item.href,
                record_type=item.record_type,
                record_id=item.record_id,
            )
            for item in overview.attention
        ],
        needs_attention=overview.needs_attention,
    )


@router.post("/dsars/{dsar_id}/extension", response_model=DSAROut)
async def extend_dsar(
    dsar_id: uuid.UUID,
    payload: DSARExtensionIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DSAR:
    """Record a decision to take longer, with the reason for it.

    An extension is something a controller decides and can be asked to
    justify — not a longer default. The reason is required for that
    reason: "extended" with nothing beside it is not a record anybody can
    defend later.
    """
    dsar = await _get_org_dsar(db, dsar_id, context.organization_id)
    months = privacy_deadlines.clamp_extension(payload.months)
    if months == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "An extension must be one or two further months. Zero is not an "
                "extension."
            ),
        )
    before = dsar.due_at
    dsar.extension_months = months
    dsar.extension_reason = payload.reason.strip()
    dsar.extension_granted_at = utcnow()
    dsar.due_at = privacy_deadlines.response_due(
        dsar.received_at, extension_months=months
    )
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.dsar.extended",
        object_type="dsar",
        object_id=str(dsar.id),
        before_state={"due_at": before.isoformat()},
        after_state={
            "due_at": dsar.due_at.isoformat(),
            "months": months,
            "reason": dsar.extension_reason,
        },
    )
    await db.commit()
    await db.refresh(dsar)
    return dsar


@router.post(
    "/processing-activities/{activity_id}/review", response_model=ProcessingActivityOut
)
async def review_processing_activity(
    activity_id: uuid.UUID,
    payload: ProcessingActivityReviewIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> ProcessingActivity:
    """Confirm the record still describes what actually happens.

    A RoPA entry is a claim the organization keeps making about itself.
    This is the act of somebody standing behind it again, and it is
    recorded with who and when — the review is the evidence, not the
    date field.
    """
    activity = await _get_org_processing_activity(
        db, activity_id, context.organization_id
    )
    now = utcnow()
    activity.last_reviewed_at = now
    activity.last_reviewed_by = context.user.id
    activity.next_review_at = privacy_deadlines.next_review_from(
        now, months=payload.next_review_months
    )
    if activity.status == "needs_review":
        activity.status = "active"
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.processing_activity.reviewed",
        object_type="processing_activity",
        object_id=str(activity.id),
        after_state={
            "name": activity.name,
            "next_review_at": activity.next_review_at.isoformat(),
        },
    )
    await db.commit()
    await db.refresh(activity)
    return activity


# --- privacy suggestions ------------------------------------------------
#
# Veyntra drafts from what the organization already declared; a person
# supplies the judgements a draft is not allowed to contain. The two
# halves are separate endpoints because they are separate acts.


def _suggestion_out(suggestion: PrivacySuggestion) -> PrivacySuggestionOut:
    return PrivacySuggestionOut(
        id=suggestion.id,
        kind=suggestion.kind,
        status=suggestion.status,
        title=suggestion.title,
        sources=[
            PrivacySuggestionSourceOut(
                type=source.get("type", ""),
                id=source.get("id"),
                label=source.get("label", ""),
            )
            for source in (suggestion.sources or [])
        ],
        payload=suggestion.payload or {},
        created_record_id=suggestion.created_record_id,
        created_at=suggestion.created_at,
    )


async def _get_org_suggestion_row(
    db: AsyncSession, suggestion_id: uuid.UUID, organization_id: uuid.UUID
) -> PrivacySuggestion:
    suggestion = await db.get(PrivacySuggestion, suggestion_id)
    if suggestion is None or suggestion.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found"
        )
    return suggestion


@router.post("/privacy/suggestions/analyse", response_model=PrivacyAnalysisOut)
async def analyse_privacy_records(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> PrivacyAnalysisOut:
    """Draft the privacy records this organization's own data implies.

    Reads AI systems, vendors and processing activities; writes only
    proposals. Running it twice reconciles rather than duplicating, and
    a proposal somebody already accepted or dismissed is left alone —
    re-analysis must not resurrect a decision a person made.
    """
    result = await privacy_suggestions.analyse(
        db, organization_id=context.organization_id
    )
    if result.created:
        await record_event(
            db,
            organization_id=context.organization_id,
            actor_user_id=context.user.id,
            action="compliance.privacy_suggestion.analysed",
            object_type="organization",
            object_id=str(context.organization_id),
            after_state={
                "created": result.created,
                "already_proposed": result.unchanged,
                "already_recorded": result.already_recorded,
            },
        )
    await db.commit()
    return PrivacyAnalysisOut(
        created=result.created,
        already_proposed=result.unchanged,
        already_recorded=result.already_recorded,
    )


@router.get("/privacy/suggestions", response_model=list[PrivacySuggestionOut])
async def list_privacy_suggestions(
    kind: str | None = None,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[PrivacySuggestionOut]:
    """Drafts waiting for a person. Never records."""
    rows = await privacy_suggestions.open_suggestions(
        db, organization_id=context.organization_id, kind=kind
    )
    return [_suggestion_out(row) for row in rows]


@router.post(
    "/privacy/suggestions/{suggestion_id}/accept",
    response_model=PrivacySuggestionOut,
)
async def accept_privacy_suggestion(
    suggestion_id: uuid.UUID,
    payload: PrivacySuggestionAcceptIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> PrivacySuggestionOut:
    """Turn a draft into a record, with the judgements you supply.

    Refuses without them. A RoPA entry with no lawful basis is not a
    RoPA entry, and one whose basis a machine chose is worse, because it
    looks answered.
    """
    suggestion = await _get_org_suggestion_row(
        db, suggestion_id, context.organization_id
    )
    try:
        if suggestion.kind == privacy_suggestions.PROCESSING_ACTIVITY:
            await privacy_accept.accept_processing_activity(
                db,
                suggestion=suggestion,
                legal_basis=payload.legal_basis or "",
                retention_period=payload.retention_period or "",
                special_category=payload.special_category,
                special_category_condition=payload.special_category_condition,
                actor_user_id=context.user.id,
            )
        else:
            await privacy_accept.accept_transfer(
                db,
                suggestion=suggestion,
                transfer_mechanism=payload.transfer_mechanism or "",
                safeguards_description=payload.safeguards_description,
                actor_user_id=context.user.id,
            )
    except privacy_accept.AcceptRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # A new processing activity is a new set of transfer questions, so
    # the transfer implied by its own processor appears without anybody
    # asking for it.
    await privacy_suggestions.analyse(db, organization_id=context.organization_id)
    await db.commit()
    await db.refresh(suggestion)
    return _suggestion_out(suggestion)


@router.post(
    "/privacy/suggestions/{suggestion_id}/dismiss",
    response_model=PrivacySuggestionOut,
)
async def dismiss_privacy_suggestion(
    suggestion_id: uuid.UUID,
    payload: PrivacySuggestionDismissIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> PrivacySuggestionOut:
    """Record that somebody looked and said no."""
    suggestion = await _get_org_suggestion_row(
        db, suggestion_id, context.organization_id
    )
    await privacy_accept.dismiss(
        db,
        suggestion=suggestion,
        reason=payload.reason,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(suggestion)
    return _suggestion_out(suggestion)


@router.get("/privacy/data-locations", response_model=list[PrivacyDataLocationOut])
async def list_privacy_data_locations(
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> list[PrivacyDataLocationOut]:
    """Where to look when answering a data request.

    A search **scope**, assembled from the organization's own inventory.
    Nothing here reads or discloses anybody's personal data; what was
    actually found, and what may lawfully be released, stays with the
    person answering the request.
    """
    locations = await privacy_suggestions.data_locations(
        db, organization_id=context.organization_id
    )
    return [
        PrivacyDataLocationOut(
            label=location.label,
            kind=location.kind,
            record_id=location.record_id,
            reason=location.reason,
        )
        for location in locations
    ]


@router.get(
    "/processing-activities/{activity_id}/related",
    response_model=ProcessingActivityRelatedOut,
)
async def get_processing_activity_related(
    activity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> ProcessingActivityRelatedOut:
    """What this activity connects to, navigable from here.

    The whole reason the links exist: nobody should maintain the same
    fact in a RoPA entry, a vendor record and a transfer record.
    """
    activity = await _get_org_processing_activity(
        db, activity_id, context.organization_id
    )

    ai_rows = (
        await db.execute(
            select(AISystem)
            .join(
                ProcessingActivityAISystem,
                ProcessingActivityAISystem.ai_system_id == AISystem.id,
            )
            .where(
                ProcessingActivityAISystem.processing_activity_id == activity.id
            )
        )
    ).scalars().all()
    vendor_rows = (
        await db.execute(
            select(Vendor)
            .join(
                ProcessingActivityVendor,
                ProcessingActivityVendor.vendor_id == Vendor.id,
            )
            .where(ProcessingActivityVendor.processing_activity_id == activity.id)
        )
    ).scalars().all()
    dpia_rows = (
        await db.execute(
            select(DPIA).where(DPIA.processing_activity_id == activity.id)
        )
    ).scalars().all()
    transfer_rows = (
        await db.execute(
            select(DataTransfer).where(
                DataTransfer.processing_activity_id == activity.id
            )
        )
    ).scalars().all()

    return ProcessingActivityRelatedOut(
        ai_systems=[
            RelatedRecordOut(
                id=row.id,
                label=row.name,
                kind="ai_system",
                href=f"/ai-systems/{row.id}",
            )
            for row in ai_rows
        ],
        vendors=[
            RelatedRecordOut(
                id=row.id,
                label=row.name,
                kind="vendor",
                href=f"/compliance/vendors/{row.id}",
                detail=(row.country or None),
            )
            for row in vendor_rows
        ],
        dpias=[
            RelatedRecordOut(
                id=row.id,
                label=row.title,
                kind="dpia",
                href=f"/compliance/dpias/{row.id}",
                detail=row.status,
            )
            for row in dpia_rows
        ],
        transfers=[
            RelatedRecordOut(
                id=row.id,
                label=f"{row.recipient_name} ({row.destination_country})",
                kind="transfer",
                href=f"/compliance/data-transfers/{row.id}",
                detail=row.transfer_mechanism,
            )
            for row in transfer_rows
        ],
    )


# --- what a processing activity is called -------------------------------
#
# The organization answers who is doing the processing; the activity
# answers what processing is being done. A RoPA entry titled with the
# organization's name answers the first question twice and the second
# not at all.


@router.post(
    "/processing-activities/{activity_id}/title",
    response_model=ProcessingActivityOut,
)
async def rename_processing_activity(
    activity_id: uuid.UUID,
    payload: RopaTitleRepairApply,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> ProcessingActivity:
    """Give the activity a title that describes the processing.

    Guarded by the same rule as creation: a title that names the
    organization or a person is refused, so a repair cannot land back
    where it started.
    """
    activity = await _get_org_processing_activity(
        db, activity_id, context.organization_id
    )
    problem = await ropa_titles.identity_conflict(
        db, organization_id=context.organization_id, title=payload.title
    )
    if problem is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=problem.message
        )

    before = activity.name
    activity.name = payload.title.strip()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.processing_activity.renamed",
        object_type="processing_activity",
        object_id=str(activity.id),
        before_state={"name": before},
        after_state={"name": activity.name},
    )
    await db.commit()
    await db.refresh(activity)
    return activity


# --- the DPIA lifecycle: screening, then the assessment ------------------
#
# Selecting a processing activity used to open a full assessment: four
# empty boxes, no risks, and "Inherent risk: Low" on a document where
# nobody had assessed anything. Screening comes first, a person decides,
# and only then is there a draft to fill in.


def _screening_out(
    dpia: DPIA,
    state,
    blockers,
    suggested,
    *,
    completed_by_name: str | None = None,
    consultation_recorded_by_name: str | None = None,
    risk_reviewed_by_name: str | None = None,
    can_conclude_no_material_risks: bool = False,
    missing: list | None = None,
    signals: list | None = None,
    stale: set[str] | None = None,
) -> DpiaWorkflowOut:
    findings = dpia.screening_findings or {}
    reviews = dpia.section_reviews or {}
    return DpiaWorkflowOut(
        id=dpia.id,
        title=dpia.title,
        status=dpia.status,
        processing_activity_id=dpia.processing_activity_id,
        ai_system_id=dpia.ai_system_id,
        screening_outcome=dpia.screening_outcome,
        screening_rationale_text=findings.get("rationale"),
        screening_criteria_met=list(findings.get("criteria_met") or []),
        screened_at=dpia.screened_at,
        screening_decision=dpia.screening_decision,
        screening_decided_at=dpia.screening_decided_at,
        screening_decision_rationale=dpia.screening_rationale,
        processing_description=dpia.processing_description,
        necessity_assessment=dpia.necessity_assessment,
        proportionality_assessment=dpia.proportionality_assessment,
        consultation_notes=dpia.consultation_notes,
        inherent_risk=state.inherent,
        residual_risk=state.residual,
        risk_count=state.risk_count,
        assessed_count=state.assessed_count,
        mitigated_count=state.mitigated_count,
        can_calculate_residual=state.can_calculate_residual,
        risk_blocked_reason=state.blocked_reason,
        suggested_risks=[
            DpiaSuggestedRiskOut(
                id=risk.id,
                title=risk.title,
                description=risk.description,
                reason=risk.reason,
                status=risk.status,
                suggested_safeguards=risk.suggested_safeguards,
                created_risk_id=risk.created_risk_id,
                decided_at=risk.decided_at,
            )
            for risk in suggested
        ],
        completion_blockers=[
            DpiaBlockerOut(code=b.code, message=b.message) for b in blockers
        ],
        section_reviews=[
            DpiaSectionReviewOut(
                section=key,
                approved_by=(
                    uuid.UUID(entry["approved_by"])
                    if entry.get("approved_by")
                    else None
                ),
                approved_at=entry.get("approved_at"),
            )
            for key, entry in reviews.items()
            if isinstance(entry, dict)
        ],
        consultation_state=dpia_workflow.consultation_state(dpia),
        consultation_performed=dpia.consultation_performed,
        consulted_party=dpia.consulted_party,
        consulted_role=dpia.consulted_role,
        consulted_at=dpia.consulted_at,
        consultation_recorded_by_name=consultation_recorded_by_name,
        consultation_recorded_at=dpia.consultation_recorded_at,
        risk_conclusion=dpia_workflow.risk_conclusion_of(dpia),
        risk_conclusion_rationale=dpia.risk_conclusion_rationale,
        risk_reviewed_by_name=risk_reviewed_by_name,
        risk_reviewed_at=dpia.risk_reviewed_at,
        can_conclude_no_material_risks=can_conclude_no_material_risks,
        missing_facts=[
            DpiaMissingFactOut(code=gap.code, message=gap.message, href=gap.href)
            for gap in (missing or [])
        ],
        special_category_signals=[
            DpiaSpecialSignalOut(kind=signal.kind, evidence=signal.evidence)
            for signal in (signals or [])
        ],
        special_category_confirmed=dpia.special_category_confirmed,
        special_category_rationale=dpia.special_category_rationale,
        stale_sections=sorted(stale or set()),
        section_guidance=dict(dpia_quality.SECTION_GUIDANCE),
        quality_review_reason=dpia.quality_review_reason,
        can_complete=not blockers and dpia.status != dpia_workflow.COMPLETED,
        completed_at=dpia.completed_at,
        completed_by_name=completed_by_name,
        snapshot=dpia.snapshot,
        review_reason=dpia.review_reason,
        review_flagged_at=dpia.review_flagged_at,
        allowed_transitions=list(dpia_workflow.TRANSITIONS.get(dpia.status, ())),
    )


async def _workflow_view(
    db: AsyncSession, *, organization_id: uuid.UUID, dpia: DPIA
) -> DpiaWorkflowOut:
    state = await dpia_workflow.risk_state(
        db, organization_id=organization_id, dpia=dpia
    )
    blockers = await dpia_workflow.completion_blockers(
        db, organization_id=organization_id, dpia=dpia
    )
    # Read, never recompute. Suggestions used to be derived on every
    # request, which made them impossible to approve or dismiss — the
    # thing a reviewer acted on did not exist between two page loads.
    suggested = await dpia_risks.for_dpia(
        db, organization_id=organization_id, dpia_id=dpia.id
    )
    async def name_of(user_id: uuid.UUID | None) -> str | None:
        if user_id is None:
            return None
        person = await db.get(User, user_id)
        if person is None:
            return None
        return (person.full_name or "").strip() or person.email

    # The reviewer can conclude "nothing material" only once there is
    # nothing left open: every suggestion decided, and no risk on the
    # register to contradict the conclusion.
    undecided = await dpia_workflow.pending_risk_suggestions(
        db, organization_id=organization_id, dpia=dpia
    )
    can_conclude = (
        undecided == 0
        and state.risk_count == 0
        and dpia.risk_conclusion != dpia_workflow.NO_MATERIAL_RISKS
        and dpia.status not in (dpia_workflow.COMPLETED, dpia_workflow.NOT_REQUIRED)
    )

    missing, signals, stale = await dpia_workflow.content_gaps(
        db, organization_id=organization_id, dpia=dpia
    )

    return _screening_out(
        dpia,
        state,
        blockers,
        suggested,
        completed_by_name=await name_of(dpia.completed_by),
        consultation_recorded_by_name=await name_of(dpia.consultation_recorded_by),
        risk_reviewed_by_name=await name_of(dpia.risk_reviewed_by),
        can_conclude_no_material_risks=can_conclude,
        missing=missing,
        signals=signals,
        stale=stale,
    )


async def _reconcile_dpia_risks(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    dpia: DPIA,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Refresh the proposed risks from the current facts, if there are any.

    Safe to call repeatedly — `dpia_risks.reconcile` matches on what a
    proposal is about, so re-running never duplicates and never revives
    something a person dismissed.
    """
    if not dpia.processing_activity_id:
        return
    activity = await db.get(ProcessingActivity, dpia.processing_activity_id)
    if activity is None:
        return
    await dpia_risks.reconcile(
        db,
        organization_id=organization_id,
        dpia=dpia,
        context=await dpia_workflow.context_for(db, activity=activity),
        actor_user_id=actor_user_id,
    )


@router.post("/dpias/{dpia_id}/screening/decision", response_model=DpiaWorkflowOut)
async def decide_dpia_screening(
    dpia_id: uuid.UUID,
    payload: DpiaScreeningDecisionIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DpiaWorkflowOut:
    """Record whether a DPIA is required.

    Veyntra counted the criteria; this is the controller concluding. The
    two are stored separately because they are different claims by
    different parties, and a screen showing only the count would imply
    the product made the call.
    """
    dpia = await _get_org_dpia(db, dpia_id, context.organization_id)
    processing = None
    if dpia.processing_activity_id:
        activity = await db.get(ProcessingActivity, dpia.processing_activity_id)
        if activity is not None:
            processing = await dpia_workflow.context_for(db, activity=activity)

    try:
        await dpia_workflow.decide_screening(
            db,
            organization_id=context.organization_id,
            dpia=dpia,
            decision=payload.decision,
            rationale=payload.rationale,
            actor_user_id=context.user.id,
            context=processing,
        )
    except dpia_workflow.DpiaRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # The assessment is open, so refresh the risks the record implies.
    if payload.decision == dpia_workflow.DECISION_REQUIRED:
        await _reconcile_dpia_risks(
            db,
            organization_id=context.organization_id,
            dpia=dpia,
            actor_user_id=context.user.id,
        )
    else:
        # No assessment is going to happen, so the proposals raised
        # while screening have nothing to belong to. Only undecided
        # ones go — a decided proposal is a record of a decision.
        await dpia_risks.withdraw_undecided(
            db,
            organization_id=context.organization_id,
            dpia_id=dpia.id,
        )

    await db.commit()
    await db.refresh(dpia)
    return await _workflow_view(
        db, organization_id=context.organization_id, dpia=dpia
    )


@router.post(
    "/dpias/{dpia_id}/sections/approve", response_model=DpiaWorkflowOut
)
async def approve_dpia_section(
    dpia_id: uuid.UUID,
    payload: DpiaSectionApproveIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DpiaWorkflowOut:
    """Sign off one Article 35(7) section.

    Recorded rather than inferred. Completion used to test whether the
    text still began with Veyntra's draft marker, so deleting one word
    counted as review — and a reviewer who agreed with the draft
    verbatim had no way to say so without editing it first.
    """
    dpia = await _get_org_dpia(db, dpia_id, context.organization_id)
    if dpia.status == dpia_workflow.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This DPIA is complete. Its assessment is frozen.",
        )
    digest = None
    if dpia.processing_activity_id:
        activity = await db.get(ProcessingActivity, dpia.processing_activity_id)
        if activity is not None:
            digest = dpia_workflow.context_digest(
                await dpia_workflow.context_for(db, activity=activity)
            )
    try:
        dpia_workflow.approve_section(
            dpia,
            section=payload.section,
            actor_user_id=context.user.id,
            context_digest_at_approval=digest,
        )
    except dpia_workflow.DpiaRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.dpia.section_approved",
        object_type="dpia",
        object_id=str(dpia.id),
        after_state={"section": payload.section},
    )
    await db.commit()
    await db.refresh(dpia)
    return await _workflow_view(
        db, organization_id=context.organization_id, dpia=dpia
    )


@router.post("/dpias/{dpia_id}/consultation", response_model=DpiaWorkflowOut)
async def record_dpia_consultation(
    dpia_id: uuid.UUID,
    payload: DpiaConsultationIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DpiaWorkflowOut:
    """Article 35(2): whether a DPO or data subjects were consulted.

    The single authoritative consultation record. Writing it is also what
    satisfies Article 35(7)'s consultation section — there is no second
    "approve the consultation" step, because there is only one decision
    here to make, and having two produced a page that said "No
    consultation performed" and "Nobody has approved the consultation
    record" about the same fact.
    """
    dpia = await _get_org_dpia(db, dpia_id, context.organization_id)
    if dpia.status == dpia_workflow.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This DPIA is complete. Its assessment is frozen.",
        )
    try:
        await dpia_workflow.record_consultation(
            db,
            organization_id=context.organization_id,
            dpia=dpia,
            performed=payload.performed,
            party=payload.party,
            role=payload.role,
            consulted_at=payload.consulted_at,
            notes=payload.notes,
            actor_user_id=context.user.id,
        )
    except dpia_workflow.DpiaRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await db.commit()
    await db.refresh(dpia)
    return await _workflow_view(
        db, organization_id=context.organization_id, dpia=dpia
    )


@router.post(
    "/dpias/{dpia_id}/risk-suggestions/{suggestion_id}/approve",
    response_model=DpiaWorkflowOut,
)
async def approve_dpia_risk_suggestion(
    dpia_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    payload: DpiaRiskApproveIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DpiaWorkflowOut:
    """Accept a proposed risk, with the rating a person chose.

    The likelihood and impact come from the request rather than the
    proposal: this is the moment the DPIA acquires a risk position, and
    a rating Veyntra supplied would flow straight into an inherent level
    nobody decided.
    """
    dpia = await _get_org_dpia(db, dpia_id, context.organization_id)
    suggestion = await db.get(DpiaRiskSuggestion, suggestion_id)
    if (
        suggestion is None
        or suggestion.dpia_id != dpia.id
        or suggestion.organization_id != context.organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found"
        )
    try:
        await dpia_risks.approve(
            db,
            organization_id=context.organization_id,
            suggestion=suggestion,
            likelihood=payload.likelihood,
            impact=payload.impact,
            title=payload.title,
            description=payload.description,
            affected_data_subjects=payload.affected_data_subjects,
            existing_safeguards=payload.existing_safeguards,
            owner_id=payload.owner_id,
            actor_user_id=context.user.id,
        )
    except dpia_risks.RiskSuggestionRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # A risk reached the register, so that is what the review concluded
    # — and it clears any earlier "no material risks", which the presence
    # of a risk contradicts.
    await dpia_workflow.note_risks_identified(
        db,
        organization_id=context.organization_id,
        dpia=dpia,
        actor_user_id=context.user.id,
    )
    # The register changed, so the level derived from it has.
    await recalculate_residual_risk(
        db, organization_id=context.organization_id, dpia=dpia
    )
    await dpia_approval.sync_high_residual_approval(
        db,
        organization_id=context.organization_id,
        dpia=dpia,
        actor_user_id=context.user.id,
    )
    await db.commit()
    await db.refresh(dpia)
    return await _workflow_view(
        db, organization_id=context.organization_id, dpia=dpia
    )


@router.post(
    "/dpias/{dpia_id}/risk-suggestions/{suggestion_id}/dismiss",
    response_model=DpiaWorkflowOut,
)
async def dismiss_dpia_risk_suggestion(
    dpia_id: uuid.UUID,
    suggestion_id: uuid.UUID,
    payload: DpiaRiskDismissIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DpiaWorkflowOut:
    """Record that this is not a risk here, and why."""
    dpia = await _get_org_dpia(db, dpia_id, context.organization_id)
    suggestion = await db.get(DpiaRiskSuggestion, suggestion_id)
    if (
        suggestion is None
        or suggestion.dpia_id != dpia.id
        or suggestion.organization_id != context.organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found"
        )
    try:
        await dpia_risks.dismiss(
            db,
            organization_id=context.organization_id,
            suggestion=suggestion,
            reason=payload.reason,
            actor_user_id=context.user.id,
        )
    except dpia_risks.RiskSuggestionRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await db.commit()
    await db.refresh(dpia)
    return await _workflow_view(
        db, organization_id=context.organization_id, dpia=dpia
    )


@router.post(
    "/risks/{risk_id}/remediation",
    response_model=TaskOut,
    status_code=status.HTTP_201_CREATED,
)
async def open_risk_remediation(
    risk_id: uuid.UUID,
    payload: RiskRemediationIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.risks.manage")),
) -> Task:
    """Open the work that reduces a risk, in the existing task system.

    Reuses `core.Task` rather than adding a second thing called
    remediation. The mitigation is also written onto the risk, because
    the residual rating has to be justified by something recorded — a
    lower number whose reason lives only in a task nobody reads back is
    the failure this link exists to prevent.
    """
    risk = await db.get(Risk, risk_id)
    if risk is None or risk.organization_id != context.organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found"
        )

    existing = (
        await db.execute(
            select(Task).where(
                Task.organization_id == context.organization_id,
                Task.entity_type == "risk",
                Task.entity_id == str(risk.id),
                Task.status != "done",
            )
        )
    ).scalars().first()
    if existing is not None:
        # §31: pressing the button twice is one piece of work, not two.
        return existing

    task = Task(
        organization_id=context.organization_id,
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        module="compliance",
        status="open",
        priority=payload.priority,
        assignee_id=payload.assignee_id,
        due_at=payload.due_at,
        created_by=context.user.id,
        entity_type="risk",
        entity_id=str(risk.id),
    )
    db.add(task)

    # The commitment, on the risk it justifies.
    addition = payload.title.strip()
    if payload.description:
        addition = f"{addition} — {payload.description.strip()}"
    risk.additional_mitigations = (
        f"{risk.additional_mitigations}\n{addition}"
        if risk.additional_mitigations
        else addition
    )[:2000]

    await db.flush()
    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action="compliance.risk.remediation_opened",
        object_type="risk",
        object_id=str(risk.id),
        after_state={"task_id": str(task.id), "title": task.title},
    )
    await db.commit()
    await db.refresh(task)
    return task


@router.post(
    "/dpias/{dpia_id}/risk-conclusion", response_model=DpiaWorkflowOut
)
async def conclude_dpia_risk_review(
    dpia_id: uuid.UUID,
    payload: DpiaRiskConclusionIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DpiaWorkflowOut:
    """Record that the risks were reviewed and none met the threshold.

    The alternative used to be inventing a risk. Completion demanded at
    least one on the register, so a reviewer who had read every candidate
    and judged none material could only finish by writing down something
    they did not believe — which is a worse record than the honest one.

    Refused while any suggestion is undecided or any risk is on the
    register: the conclusion is a claim about a review that finished.
    """
    dpia = await _get_org_dpia(db, dpia_id, context.organization_id)
    if dpia.status == dpia_workflow.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This DPIA is complete. Its assessment is frozen.",
        )
    try:
        await dpia_workflow.conclude_no_material_risks(
            db,
            organization_id=context.organization_id,
            dpia=dpia,
            rationale=payload.rationale,
            actor_user_id=context.user.id,
        )
    except dpia_workflow.DpiaRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await db.commit()
    await db.refresh(dpia)
    return await _workflow_view(
        db, organization_id=context.organization_id, dpia=dpia
    )


@router.post(
    "/dpias/{dpia_id}/special-category", response_model=DpiaWorkflowOut
)
async def decide_dpia_special_category(
    dpia_id: uuid.UUID,
    payload: DpiaSpecialCategoryIn,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DpiaWorkflowOut:
    """Answer the Article 9 question Veyntra raised.

    Veyntra reads health signals out of the processing record — a name
    like "Employee medical-leave administration" strongly suggests them —
    and stops there. Whether special-category data is in scope, and on
    what Article 9 condition, is a legal conclusion the product does not
    reach.

    Ruling it out needs a reason. Without one this endpoint would let a
    detected signal be dismissed with a click, which is how "no
    categories recorded" became "nothing sensitive here".
    """
    dpia = await _get_org_dpia(db, dpia_id, context.organization_id)
    if dpia.status == dpia_workflow.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This DPIA is complete. Its assessment is frozen.",
        )
    if not payload.confirmed and not (payload.rationale or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Ruling out special-category data needs a reason. Veyntra "
                "detected a signal in this processing, and an unexplained "
                "dismissal is indistinguishable from nobody having looked."
            ),
        )

    before = {
        "confirmed": dpia.special_category_confirmed,
        "rationale": dpia.special_category_rationale,
    }
    changing = dpia.special_category_confirmed is not None

    dpia.special_category_confirmed = payload.confirmed
    dpia.special_category_rationale = (payload.rationale or "").strip() or None
    dpia.special_category_decided_by = context.user.id
    dpia.special_category_decided_at = utcnow()

    await record_event(
        db,
        organization_id=context.organization_id,
        actor_user_id=context.user.id,
        action=(
            "compliance.dpia.special_category_changed"
            if changing
            else "compliance.dpia.special_category_decided"
        ),
        object_type="dpia",
        object_id=str(dpia.id),
        before_state=before if changing else None,
        after_state={
            "confirmed": payload.confirmed,
            "rationale": dpia.special_category_rationale,
        },
    )
    await db.commit()
    await db.refresh(dpia)
    return await _workflow_view(
        db, organization_id=context.organization_id, dpia=dpia
    )


@router.post("/dpias/{dpia_id}/complete", response_model=DpiaWorkflowOut)
async def complete_dpia(
    dpia_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(require_permission("compliance.privacy.manage")),
) -> DpiaWorkflowOut:
    """Finish the assessment and freeze what it concluded.

    Refuses while anything is outstanding, and says everything that is —
    together, so the work can be finished in one pass rather than
    discovering the next missing thing on each press.
    """
    dpia = await _get_org_dpia(db, dpia_id, context.organization_id)
    try:
        await dpia_completion.complete(
            db,
            organization_id=context.organization_id,
            dpia=dpia,
            actor_user_id=context.user.id,
        )
    except dpia_workflow.DpiaRefused as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await db.commit()
    await db.refresh(dpia)
    return await _workflow_view(
        db, organization_id=context.organization_id, dpia=dpia
    )


@router.get("/dpias/{dpia_id}/workflow", response_model=DpiaWorkflowOut)
async def get_dpia_workflow(
    dpia_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    context: OrgContext = Depends(get_org_context),
) -> DpiaWorkflowOut:
    """The DPIA's screening, risk position and what blocks completion."""
    dpia = await _get_org_dpia(db, dpia_id, context.organization_id)
    if dpia.status == dpia_workflow.COMPLETED:
        # §16: a DPIA completed before the quality gates existed keeps
        # its snapshot and gains a flag. Rewriting it to satisfy a rule
        # introduced afterwards would replace the record with a
        # better-looking one nobody signed.
        problems = dpia_completion.snapshot_quality_problems(dpia)
        reason = (
            "This DPIA was completed before Veyntra checked assessment "
            "quality, and its record would not pass those checks now: "
            + " ".join(problems)
        )[:2000] if problems else None
        if reason != dpia.quality_review_reason:
            dpia.quality_review_reason = reason
            if reason:
                await record_event(
                    db,
                    organization_id=context.organization_id,
                    actor_user_id=context.user.id,
                    action="compliance.dpia.quality_review_recommended",
                    object_type="dpia",
                    object_id=str(dpia.id),
                    after_state={"problems": problems},
                )
            await db.commit()
            await db.refresh(dpia)

        # §24: notice that the processing moved. This never edits the
        # frozen assessment — it raises a flag saying somebody should
        # look again, which is a different claim by a different party.
        changes = await dpia_completion.check_for_drift(
            db, organization_id=context.organization_id, dpia=dpia
        )
        if changes:
            await dpia_completion.flag_for_review(
                db,
                organization_id=context.organization_id,
                dpia=dpia,
                changes=changes,
            )
            await db.commit()
            await db.refresh(dpia)
    return await _workflow_view(
        db, organization_id=context.organization_id, dpia=dpia
    )
