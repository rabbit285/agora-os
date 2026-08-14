from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FrameworkOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    is_custom: bool

    model_config = {"from_attributes": True}


class RequirementOut(BaseModel):
    id: uuid.UUID
    reference_code: str
    title: str
    description: str | None

    model_config = {"from_attributes": True}


class RequirementCreate(BaseModel):
    reference_code: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)


class FrameworkCreate(BaseModel):
    """spec §12's own named "Custom Frameworks" item — an organization's
    own private framework, distinct from the shared global catalog."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    requirements: list[RequirementCreate] = Field(default_factory=list)


class FrameworkDashboardControlOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str


class FrameworkDashboardRequirementOut(BaseModel):
    id: uuid.UUID
    reference_code: str
    title: str
    controls: list[FrameworkDashboardControlOut]


class FrameworkDashboardOut(BaseModel):
    framework: FrameworkOut
    requirements: list[FrameworkDashboardRequirementOut]
    coverage_percent: float


class ControlCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    owner_id: uuid.UUID | None = None
    requirement_ids: list[uuid.UUID] = Field(default_factory=list)


class ControlOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    status: str
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ControlAssessmentCreate(BaseModel):
    status: str = Field(pattern="^(pass|fail|partial|not_assessed)$")
    notes: str | None = None


class ControlAssessmentOut(BaseModel):
    id: uuid.UUID
    status: str
    notes: str | None
    assessed_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EvidenceCreate(BaseModel):
    file_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    control_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    incident_id: uuid.UUID | None = None
    valid_until: datetime | None = None


class EvidenceOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    control_id: uuid.UUID | None
    vendor_id: uuid.UUID | None
    incident_id: uuid.UUID | None
    title: str
    valid_until: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ControlDetailOut(ControlOut):
    requirements: list[RequirementOut]
    assessments: list[ControlAssessmentOut]
    # Without this the Requirement -> Control -> Evidence -> Document
    # chain could be built but never followed: evidence was linkable to a
    # control and listable org-wide, but not reachable *from* the control
    # it belonged to, which is the direction anyone auditing a requirement
    # actually walks.
    evidence: list[EvidenceOut] = []


class RiskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    category: str = "general"
    likelihood: str = Field(pattern="^(low|medium|high)$")
    impact: str = Field(pattern="^(low|medium|high)$")
    control_id: uuid.UUID | None = None
    # What the risk is about. A register that cannot say this forces every
    # reader to re-derive it from the title.
    ai_system_id: uuid.UUID | None = None
    dpia_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None


class RiskUpdate(BaseModel):
    status: str = Field(pattern="^(open|mitigated|accepted)$")


class RiskOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    category: str
    likelihood: str
    impact: str
    status: str
    control_id: uuid.UUID | None
    ai_system_id: uuid.UUID | None = None
    dpia_id: uuid.UUID | None = None
    # Null until the mitigation has actually been assessed — deliberately
    # not defaulted to the inherent rating, so "not yet reassessed" stays
    # distinguishable from "reassessed and unchanged".
    residual_likelihood: str | None = None
    residual_impact: str | None = None
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    file_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None


class PolicyOut(BaseModel):
    id: uuid.UUID
    title: str
    file_id: uuid.UUID | None
    status: str
    owner_id: uuid.UUID | None
    ai_system_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyStatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|published)$")


class AISystemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    vendor: str | None = None
    purpose: str = Field(min_length=1, max_length=2000)
    risk_classification: str = Field(
        default="minimal", pattern="^(minimal|limited|high|unacceptable)$"
    )
    owner_id: uuid.UUID | None = None


class AISystemStatusUpdate(BaseModel):
    status: str = Field(pattern="^(in_review|approved|rejected|retired)$")


class AISystemOut(BaseModel):
    id: uuid.UUID
    name: str
    vendor: str | None
    vendor_id: uuid.UUID | None
    purpose: str
    description: str | None = None
    model_name: str | None = None
    internal_users: list[str] = []
    affected_users: list[str] = []
    processed_data: list[dict[str, str]] = []
    business_owner_id: uuid.UUID | None = None
    technical_owner_id: uuid.UUID | None = None
    governance_owner_id: uuid.UUID | None = None
    last_reviewed_at: datetime | None = None
    risk_classification: str
    status: str
    owner_id: uuid.UUID | None
    approval_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIAssessmentCreate(BaseModel):
    status: str = Field(pattern="^(pass|fail|partial|not_assessed)$")
    notes: str | None = None


class AIAssessmentOut(BaseModel):
    id: uuid.UUID
    ai_system_id: uuid.UUID
    status: str
    notes: str | None
    assessed_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AISystemDetailOut(AISystemOut):
    assessments: list[AIAssessmentOut]


class ProcessingActivityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    purpose: str = Field(min_length=1, max_length=2000)
    legal_basis: str = Field(
        pattern="^(consent|contract|legal_obligation|vital_interests|public_task|"
        "legitimate_interests)$"
    )
    data_categories: list[str] = Field(default_factory=list)
    data_subjects: str = Field(min_length=1, max_length=300)
    retention_period: str = Field(min_length=1, max_length=300)
    owner_id: uuid.UUID | None = None


class ProcessingActivityOut(BaseModel):
    id: uuid.UUID
    name: str
    purpose: str
    legal_basis: str
    data_categories: list[str]
    data_subjects: str
    retention_period: str
    status: str
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DPIACreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    processing_activity_id: uuid.UUID | None = None
    risk_level: str = Field(default="low", pattern="^(low|medium|high)$")
    owner_id: uuid.UUID | None = None


class DPIAStatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|in_review|approved|rejected)$")
    findings: str | None = None


class DPIAOut(BaseModel):
    id: uuid.UUID
    processing_activity_id: uuid.UUID | None
    ai_system_id: uuid.UUID | None
    title: str
    risk_level: str
    status: str
    findings: str | None
    approval_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DSARCreate(BaseModel):
    requester_name: str = Field(min_length=1, max_length=300)
    requester_email: str = Field(min_length=3, max_length=320)
    request_type: str = Field(pattern="^(access|deletion|rectification|portability)$")
    assigned_to: uuid.UUID | None = None


class DSARStatusUpdate(BaseModel):
    status: str = Field(pattern="^(received|in_progress|fulfilled|rejected)$")
    notes: str | None = None


class DSAROut(BaseModel):
    id: uuid.UUID
    requester_name: str
    requester_email: str
    request_type: str
    status: str
    due_at: datetime
    fulfilled_at: datetime | None
    notes: str | None
    assigned_to: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIIncidentCreate(BaseModel):
    ai_system_id: uuid.UUID
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    owner_id: uuid.UUID | None = None


class AIIncidentStatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|investigating|resolved|closed)$")


class AIIncidentOut(BaseModel):
    id: uuid.UUID
    ai_system_id: uuid.UUID
    title: str
    description: str | None
    severity: str
    status: str
    related_risk_id: uuid.UUID | None
    related_task_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VendorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    category: str = "general"
    website: str | None = None
    contact_email: str | None = None
    owner_id: uuid.UUID | None = None


class VendorStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|under_review|offboarded)$")


class VendorDpaStatusUpdate(BaseModel):
    dpa_status: str = Field(pattern="^(pending|signed|not_required)$")


class VendorOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    category: str
    website: str | None
    contact_email: str | None
    risk_tier: str
    status: str
    dpa_status: str
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VendorAssessmentCreate(BaseModel):
    risk_conclusion: str = Field(pattern="^(low|medium|high|critical)$")
    notes: str | None = None


class VendorAssessmentOut(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    risk_conclusion: str
    notes: str | None
    related_risk_id: uuid.UUID | None
    assessed_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VendorDetailOut(VendorOut):
    assessments: list[VendorAssessmentOut]
    evidence: list[EvidenceOut]


class QuestionnaireCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    source: str = Field(
        default="internal_template", pattern="^(customer_provided|internal_template)$"
    )
    opportunity_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None


class QuestionnaireStatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|in_progress|completed)$")


class QuestionnaireOut(BaseModel):
    id: uuid.UUID
    title: str
    source: str
    status: str
    opportunity_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionnaireQuestionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    category: str = Field(default="compliance", pattern="^(compliance|security)$")
    order_index: int = 0


class QuestionnaireQuestionOut(BaseModel):
    id: uuid.UUID
    questionnaire_id: uuid.UUID
    text: str
    category: str
    order_index: int
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionnaireAnswerUpdate(BaseModel):
    answer_text: str | None = None
    status: str = Field(pattern="^(draft|approved|missing)$")
    evidence_id: uuid.UUID | None = None
    control_id: uuid.UUID | None = None


class QuestionnaireAnswerOut(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    answer_text: str | None
    status: str
    source_type: str | None
    citations: list[dict[str, object]] | None
    evidence_id: uuid.UUID | None
    control_id: uuid.UUID | None
    answered_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionnaireQuestionDetailOut(QuestionnaireQuestionOut):
    answer: QuestionnaireAnswerOut | None


class QuestionnaireDetailOut(QuestionnaireOut):
    questions: list[QuestionnaireQuestionDetailOut]


class AuditCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    framework_id: uuid.UUID | None = None
    auditor_name: str | None = None
    scheduled_at: datetime | None = None
    owner_id: uuid.UUID | None = None


class AuditStatusUpdate(BaseModel):
    status: str = Field(pattern="^(planned|in_progress|completed)$")


class AuditOut(BaseModel):
    id: uuid.UUID
    title: str
    framework_id: uuid.UUID | None
    auditor_name: str | None
    status: str
    scheduled_at: datetime | None
    completed_at: datetime | None
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditFindingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    control_id: uuid.UUID | None = None


class AuditFindingStatusUpdate(BaseModel):
    status: str = Field(pattern="^(open|remediated)$")


class AuditFindingOut(BaseModel):
    id: uuid.UUID
    audit_id: uuid.UUID
    control_id: uuid.UUID | None
    title: str
    description: str | None
    severity: str
    status: str
    related_task_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditDetailOut(AuditOut):
    findings: list[AuditFindingOut]


class SecurityReviewCreate(BaseModel):
    opportunity_id: uuid.UUID
    # If set, imports this existing Questionnaire (setting its
    # opportunity_id) instead of creating a new one.
    questionnaire_id: uuid.UUID | None = None


class SecurityReviewStatusUpdate(BaseModel):
    # "cleared" is deliberately excluded — that gated transition only
    # happens via POST /security-reviews/{id}/clear.
    status: str = Field(pattern="^(in_progress|blocked)$")


class SecurityReviewOut(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    questionnaire_id: uuid.UUID
    approval_id: uuid.UUID | None
    trust_package_file_id: uuid.UUID | None
    status: str
    is_deal_blocker: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SecurityReviewDetailOut(SecurityReviewOut):
    opportunity_title: str
    approval_status: str | None
    gap_count: int
    questionnaire: QuestionnaireDetailOut


class SecurityReviewSyncResult(BaseModel):
    review: SecurityReviewDetailOut
    tasks_created: int


class DataTransferCreate(BaseModel):
    processing_activity_id: uuid.UUID | None = None
    recipient_name: str = Field(min_length=1, max_length=300)
    destination_country: str = Field(min_length=2, max_length=2)
    transfer_mechanism: str = Field(pattern="^(adequacy_decision|sccs|bcrs|derogation)$")
    safeguards_description: str | None = None
    owner_id: uuid.UUID | None = None


class DataTransferStatusUpdate(BaseModel):
    status: str = Field(pattern="^(active|under_review|terminated)$")


class DataTransferOut(BaseModel):
    id: uuid.UUID
    processing_activity_id: uuid.UUID | None
    recipient_name: str
    destination_country: str
    transfer_mechanism: str
    safeguards_description: str | None
    status: str
    related_risk_id: uuid.UUID | None
    owner_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FrameworkActivationOut(BaseModel):
    framework_id: uuid.UUID
    status: str
    activated_at: datetime | None = None

    model_config = {"from_attributes": True}


class SetFrameworkActivationRequest(BaseModel):
    active: bool


class ComplianceGapOut(BaseModel):
    id: uuid.UUID
    framework_id: uuid.UUID
    requirement_id: uuid.UUID
    control_id: uuid.UUID | None
    kind: str
    status: str
    severity: str
    summary: str
    recommendation: str | None
    task_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RequirementEvaluationOut(BaseModel):
    """One requirement's assessed position plus the counts behind it, so a
    reader can see what the status was computed from rather than being
    asked to trust it."""

    requirement_id: uuid.UUID
    reference_code: str
    title: str
    status: str
    control_ids: list[uuid.UUID]
    evidence_count: int
    latest_assessment_status: str | None
    summary: str
    gap_id: uuid.UUID | None = None


class FrameworkAssessmentResultOut(BaseModel):
    framework_id: uuid.UUID
    assessed_at: datetime
    requirements: list[RequirementEvaluationOut]
    satisfied_count: int
    gap_count: int
    evidence_coverage_percent: float


class CreateGapTaskRequest(BaseModel):
    title: str | None = None
    assignee_id: uuid.UUID | None = None
    priority: str = Field(default="high", pattern="^(low|medium|high|urgent)$")
    due_in_days: int = Field(default=7, ge=1, le=365)


class AISystemProfileUpdate(BaseModel):
    """The inventory detail an EU AI Act record is expected to carry.

    Separate from AISystemCreate so an existing system can be enriched
    without re-stating everything, which is how these records are actually
    built up — the person who registers a tool rarely knows every field on
    day one.
    """

    description: str | None = Field(default=None, max_length=2000)
    model_name: str | None = Field(default=None, max_length=200)
    internal_users: list[str] | None = None
    affected_users: list[str] | None = None
    processed_data: list[dict[str, str]] | None = None
    business_owner_id: uuid.UUID | None = None
    technical_owner_id: uuid.UUID | None = None
    governance_owner_id: uuid.UUID | None = None


class EuAiActScreeningRequest(BaseModel):
    """Indicator answers, keyed by the catalog at
    GET /ai-systems/indicator-catalog. Anything omitted is reported as
    unanswered rather than assumed false."""

    indicators: dict[str, bool]


class PrivacyAssessmentRequest(BaseModel):
    answers: dict[str, str]


class AIAssessmentDetailOut(BaseModel):
    id: uuid.UUID
    ai_system_id: uuid.UUID
    assessment_type: str
    status: str
    notes: str | None
    findings: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskResidualUpdate(BaseModel):
    """Risk remaining after mitigating controls. Both are required
    together — half a residual rating is not a rating."""

    residual_likelihood: str = Field(pattern="^(low|medium|high)$")
    residual_impact: str = Field(pattern="^(low|medium|high)$")
