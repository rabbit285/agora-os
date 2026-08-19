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
    # The organization's own taxonomy, not ours — see Control.category.
    category: str | None = Field(default=None, max_length=100)
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")
    owner_id: uuid.UUID | None = None
    requirement_ids: list[uuid.UUID] = Field(default_factory=list)


class ControlOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    category: str | None = None
    priority: str = "medium"
    status: str
    owner_id: uuid.UUID | None
    created_at: datetime
    # True when evidence changed after the last assessment — the UI uses
    # this to prompt a re-run rather than presenting a stale conclusion
    # as current.
    needs_reassessment: bool = False

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
    # Which assessment this is. Without it a reader cannot tell an EU AI
    # Act screening from a privacy review from an ad-hoc note, and any UI
    # trying to show "the latest screening" has nothing to filter on.
    assessment_type: str = "general"
    status: str
    notes: str | None
    findings: dict[str, Any] | None = None
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
    processing_description: str | None = None
    necessity_assessment: str | None = None
    proportionality_assessment: str | None = None
    consultation_notes: str | None = None
    # Null until the risks raised against this DPIA have been reassessed.
    residual_risk_level: str | None = None
    screening_outcome: str | None = None
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
    # The gate on disclosure. Surfaced so the UI can disable export rather
    # than offering a button that will be refused.
    verification_status: str = "pending"
    verification_method: str | None = None
    verified_at: datetime | None = None
    discovery_findings: dict[str, Any] | None = None
    discovery_run_at: datetime | None = None
    export_generated_at: datetime | None = None
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
    # The decision, separate from the operational `status`. A vendor can
    # be operationally active while its review is still conditional.
    approval_state: str = "not_submitted"
    approval_conditions: str | None = None
    approval_decided_at: datetime | None = None
    owner_id: uuid.UUID | None
    compliance_owner_id: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class VendorAssessmentCreate(BaseModel):
    risk_conclusion: str = Field(pattern="^(low|medium|high|critical)$")
    notes: str | None = None


class VendorAssessmentOut(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    # Which review this was. Without it the vendor detail cannot tell a
    # privacy review from a security review, and any UI showing "the
    # latest privacy position" has nothing to filter on.
    assessment_type: str = "general"
    risk_conclusion: str
    notes: str | None
    findings: dict[str, Any] | None = None
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
    # The same machinery serves vendor due diligence; without this a
    # security questionnaire sent *to* a vendor has nowhere to attach.
    vendor_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None


class QuestionnaireStatusUpdate(BaseModel):
    status: str = Field(pattern="^(draft|in_progress|completed)$")


class QuestionnaireOut(BaseModel):
    id: uuid.UUID
    title: str
    source: str
    status: str
    opportunity_id: uuid.UUID | None
    vendor_id: uuid.UUID | None = None
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


class ReadinessBreakdownOut(BaseModel):
    """The readiness score with its arithmetic attached, so the number is
    never presented without the reason for it."""

    percent: float
    satisfied: int
    partial: int
    needs_review: int
    evidence_missing: int
    not_assessed: int
    total: int
    explanation: str

    model_config = {"from_attributes": True}


class FrameworkAssessmentResultOut(BaseModel):
    framework_id: uuid.UUID
    assessed_at: datetime
    requirements: list[RequirementEvaluationOut]
    satisfied_count: int
    gap_count: int
    evidence_coverage_percent: float
    readiness: ReadinessBreakdownOut


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


class DpiaScreeningRequest(BaseModel):
    """Article 35(3) cases and the EDPB's nine criteria, keyed by the
    catalog at GET /dpias/screening-criteria."""

    answers: dict[str, bool]
    processing_activity_id: uuid.UUID


class DpiaScreeningResultOut(BaseModel):
    outcome: str
    rationale: str
    criteria_met: list[str]
    mandatory_triggers: list[str]
    unanswered: list[str]


class DPIASectionsUpdate(BaseModel):
    """Article 35(7)'s required content, each section separately
    assessable so a reviewer can see what is missing."""

    processing_description: str | None = Field(default=None, max_length=4000)
    necessity_assessment: str | None = Field(default=None, max_length=4000)
    proportionality_assessment: str | None = Field(default=None, max_length=4000)
    consultation_notes: str | None = Field(default=None, max_length=4000)


class DsarVerificationRequest(BaseModel):
    """Identity verification outcome. `verified=false` is recorded too —
    a refused request is a fact the audit trail needs."""

    verified: bool
    method: str = Field(min_length=1, max_length=200)


class DsarDiscoveryOut(BaseModel):
    email: str
    sources: list[dict[str, Any]]
    total_matches: int
    coverage_note: str


class VendorApprovalRequest(BaseModel):
    """A conditional approval must state its conditions — the service
    rejects one without them, since a vendor marked "conditionally
    approved" with no recorded condition is the exact record that makes
    the state worthless later."""

    decision: str = Field(pattern="^(pending|approved|conditionally_approved|rejected)$")
    conditions: str | None = Field(default=None, max_length=2000)


class VendorReviewFindingOut(BaseModel):
    check: str
    outcome: str
    detail: str


class VendorAssessmentDetailOut(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    assessment_type: str
    risk_conclusion: str
    notes: str | None
    findings: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ControlRequirementMapping(BaseModel):
    """Map an existing control to requirements after it was created.

    Mapping was previously only possible at creation time, which forced a
    duplicate control whenever the same measure answered a second
    requirement — and one control satisfying several requirements is the
    normal case, not the exception.
    """

    requirement_ids: list[uuid.UUID] = Field(min_length=1)


class EvidenceSuggestionOut(BaseModel):
    """A proposal, not evidence. `quote_verified` is the field that
    matters: it says the quoted passage was found in the document, which
    is what separates a citation from an assertion."""

    id: uuid.UUID
    file_id: uuid.UUID
    control_id: uuid.UUID
    status: str
    confidence: float | None
    rationale: str | None
    quoted_passage: str | None
    quote_verified: bool
    source_location: str | None = None
    evidence_type: str | None = None
    requirement_id: uuid.UUID | None = None
    routing_reason: str | None = None
    evidence_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalyzeDocumentRequest(BaseModel):
    file_id: uuid.UUID


class AnalyzeDocumentResult(BaseModel):
    suggestions: list[EvidenceSuggestionOut]
    controls_considered: int
    # How many proposals were dropped because their quote could not be
    # found in the document. Surfaced rather than hidden — it is the
    # honest measure of how much the model made up on this run.
    unverifiable_count: int


class ComplianceDocumentOut(BaseModel):
    """A document in the compliance library, with where it is in the
    processing pipeline.

    `extracted_characters` travels with the status so the UI can prove
    `ready` meant something was actually read, rather than asking the
    user to trust a green badge over an empty result.
    """

    id: uuid.UUID
    original_filename: str
    content_type: str
    size_bytes: int
    classification: str
    processing_status: str
    processing_error: str | None
    processed_at: datetime | None
    extracted_characters: int | None
    document_type: str | None
    document_domain: str | None
    created_at: datetime

    proposed_count: int = 0
    approved_count: int = 0
    unverifiable_count: int = 0

    model_config = {"from_attributes": True}


class CompanyFactsUpdate(BaseModel):
    """The declarations that decide which frameworks are in scope."""

    operates_in_eu: bool = False
    sells_to_eu_customers: bool = False
    processes_personal_data: bool = False
    processes_special_category_data: bool = False
    uses_third_party_ai: bool = False
    builds_ai_features: bool = False
    is_data_processor: bool = False
    sells_to_enterprise: bool = False
    sector: str | None = Field(default=None, max_length=60)


class FrameworkRecommendationOut(BaseModel):
    """A framework we do or do not think applies, and why.

    `reasons` restates the facts the organization declared, so a
    recommendation can be argued with: disagree with the reason, change
    the fact, get a different answer."""

    framework_key: str
    framework_id: uuid.UUID | None = None
    framework_name: str | None = None
    applicability: str
    reasons: list[str]
    uncertainties: list[str]
    requires_legal_review: bool
    already_active: bool = False


class FrameworkRecommendationsOut(BaseModel):
    recommendations: list[FrameworkRecommendationOut]
    # False until the organization has declared anything. The UI must ask
    # the questions rather than present an empty result as "nothing
    # applies to you", which is the one wrong answer here.
    facts_declared: bool


class AdoptRecommendedRequest(BaseModel):
    """Which recommendations to act on. Explicit rather than "adopt
    everything", so adopting a framework stays a decision the customer
    made."""

    framework_keys: list[str] = Field(min_length=1)

class FrameworkReadinessOut(BaseModel):
    """One active framework's current standing."""

    framework_id: uuid.UUID
    framework_key: str
    framework_name: str
    readiness: ReadinessBreakdownOut
    open_gap_count: int


class ComplianceOverviewOut(BaseModel):
    """Everything needed to answer "where do we stand" without leaving the
    Compliance screen.

    Computed from the assessments already on record rather than by
    re-running them: this is read on every page load, and an endpoint that
    silently reassessed on read would make the number depend on who looked
    at it last."""

    frameworks: list[FrameworkReadinessOut]
    total_open_gaps: int
    proposals_awaiting_review: int
    documents_processing: int
    controls_needing_reassessment: int

class ConnectorOut(BaseModel):
    """A monitoring source and its real state.

    `status` is never optimistic. A customer who believes their GitHub
    settings are being watched, and is wrong, is worse off than one who
    knows they are not.
    """

    key: str
    name: str
    category: str
    status: str
    observes: str

    model_config = {"from_attributes": True}


class ConnectorCatalogOut(BaseModel):
    connectors: list[ConnectorOut]
    available_count: int
    coming_soon_count: int


class EvidenceEventOut(BaseModel):
    id: uuid.UUID
    source: str
    event_type: str
    summary: str
    control_id: uuid.UUID | None
    observed_at: datetime
    # Whether this observation actually called an assessment into
    # question, as judged at the time it arrived.
    triggered_reassessment: bool

    model_config = {"from_attributes": True}

class ActivityLineOut(BaseModel):
    count: int
    label: str

    model_config = {"from_attributes": True}


class NextActionOut(BaseModel):
    title: str
    detail: str
    href: str
    priority: str

    model_config = {"from_attributes": True}


class FrameworkStatusOut(BaseModel):
    framework_id: uuid.UUID
    key: str
    name: str
    readiness_percent: float
    # The arithmetic behind the figure. Never shown without it.
    explanation: str
    open_gap_count: int

    model_config = {"from_attributes": True}


class SystemAtRiskOut(BaseModel):
    ai_system_id: uuid.UUID
    name: str
    risk_classification: str
    readiness_percent: float
    open_action_count: int

    model_config = {"from_attributes": True}


class ComplianceDashboardOut(BaseModel):
    """The executive view. Every figure is either clickable through to
    the thing it counts, or carries the arithmetic that produced it.
    """

    readiness_percent: float
    readiness_explanation: str
    critical_gap_count: int
    open_risk_count: int
    ai_system_count: int
    high_risk_ai_system_count: int
    overdue_action_count: int
    frameworks: list[FrameworkStatusOut]
    critical_issues: list[NextActionOut]
    systems_at_risk: list[SystemAtRiskOut]
    recent_activity: list[ActivityLineOut]
    recommended_next_actions: list[NextActionOut]

    model_config = {"from_attributes": True}

class ReviewItemOut(BaseModel):
    id: str
    title: str
    detail: str
    priority: str
    # Where the decision is actually made. A queue that lists work
    # without taking you to it just relocates the searching.
    href: str

    model_config = {"from_attributes": True}


class ReviewCategoryOut(BaseModel):
    key: str
    label: str
    description: str
    count: int
    items: list[ReviewItemOut]


class ReviewCenterOut(BaseModel):
    categories: list[ReviewCategoryOut]
    total_needing_review: int
    # What the AI accepted without asking, over the same window, so the
    # customer can see the ratio they are actually buying.
    auto_accepted_recently: int
    proposals_recently: int

class RequiredActionOut(BaseModel):
    title: str
    detail: str
    priority: str
    # Which obligation drives this. An action nobody can trace back to
    # a requirement is busywork.
    basis: str

    # Needed on the nested model too: without it Pydantic will not read
    # the RequiredAction dataclass the governance engine returns.
    model_config = {"from_attributes": True}


class AISystemGovernanceOut(BaseModel):
    """One AI system, as the governance screen needs it."""

    ai_system_id: uuid.UUID
    name: str
    risk_classification: str
    deployment_status: str
    vendor: str | None
    model_name: str | None
    documentation_completeness: int
    missing_documentation: list[str]
    applicable_regulations: list[str]
    open_risk_count: int
    open_incident_count: int
    has_current_screening: bool
    required_actions: list[RequiredActionOut]
    readiness_percent: float
    explanation: str

    model_config = {"from_attributes": True}


class AIGovernanceOverviewOut(BaseModel):
    systems: list[AISystemGovernanceOut]
    total_systems: int
    high_risk_systems: int
    systems_without_screening: int
    total_open_actions: int


class AISystemGovernanceUpdate(BaseModel):
    """The governance facts, editable without restating the whole record."""

    is_external: bool | None = None
    personal_data_processed: bool | None = None
    sensitive_data_processed: bool | None = None
    automated_decision_making: bool | None = None
    geography: str | None = Field(default=None, max_length=200)
    human_oversight: str | None = Field(default=None, max_length=2000)
    deployment_status: str | None = Field(
        default=None, pattern="^(development|pilot|production|retired)$"
    )
    third_party_vendors: list[str] | None = None

class ProcessDocumentRequest(BaseModel):
    file_id: uuid.UUID


class ApproveSuggestionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)
