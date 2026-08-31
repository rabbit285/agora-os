from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class FrameworkOut(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    is_custom: bool
    # What an audit against this framework covers, in the domains its own
    # requirements fall into. Offered to fill an empty scope box; never
    # applied over something a person wrote, and null for a framework
    # this product has no wording for — including an organization's own,
    # where inventing the subject matter would be worse than an empty box.
    suggested_audit_scope: str | None = None

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
    """A control, with the derived assessment attached.

    `assessment_status` is the primary badge everywhere. `status` is the
    stored workflow field and answers a different question — has anyone
    declared this control operational — which is why the two disagreed
    on screen when the list rendered `status` and the detail page
    rendered the derived one.
    """

    id: uuid.UUID
    title: str
    description: str | None
    category: str | None = None
    priority: str = "medium"
    # Secondary metadata: not_started | needs_review | implemented.
    status: str
    # --- Three dimensions, deliberately not one badge ----------------
    #
    # They used to be rendered together as "Needs review · 100%", which
    # asked the reader to hold an assessment state and a coverage
    # percentage in one glance and work out they were different kinds
    # of thing. And a human decision never became the headline, so a
    # control read "Needs review" after somebody had reviewed it.

    # What the user acts on: the human verdict where one exists, the
    # derived assessment otherwise. Decided once, in
    # app.compliance.control_assessment.effective_status.
    assessment_status: str = "no_evidence"
    assessment_label: str = "No evidence"
    # What Veyntra derived. Never overwritten by a human decision —
    # "a person disagreed with the automated assessment" is exactly
    # what an auditor wants to see.
    ai_assessment_status: str = "no_evidence"
    ai_assessment_label: str = "No evidence"
    # The human verdict, if one was recorded. Null otherwise.
    human_assessment_status: str | None = None
    human_assessment_label: str | None = None
    human_reviewed_at: datetime | None = None
    human_reviewed_by: uuid.UUID | None = None
    # Whether a person still has to decide. Drives the Review Center.
    review_required: bool = False
    # Share of *applicable* mapped requirements the evidence supports.
    # A measurement, never part of the status.
    coverage_percent: int = 0
    evidence_count: int = 0
    applicable_requirement_count: int = 0
    mapped_requirement_count: int = 0
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


class EvidenceMappingOut(BaseModel):
    """One statement in a document, and the control it supports."""

    evidence_id: uuid.UUID
    control_id: uuid.UUID
    control_title: str
    source_location: str | None = None
    evidence_type: str | None = None
    quoted_passage: str | None = None
    confidence: float | None = None
    mapped_by: str = "manual"


class GroupedEvidenceOut(BaseModel):
    """One source document with everything it evidences.

    A document mapped to six controls used to render as six identical
    rows, which reads as six documents. The mappings are unchanged in the
    database — this is presentation: one document, many statements, many
    controls."""

    file_id: uuid.UUID
    filename: str
    # What to call it, and where it opens. Composed server-side
    # (app.core.routes) so this list, the document library and a Copilot
    # citation all point at the one Document Detail page. None when the
    # document is not indexed and so has no page yet.
    title: str = ""
    document_href: str | None = None
    document_type: str | None = None
    document_domain: str | None = None
    processing_status: str
    evidence_count: int
    control_count: int
    mappings: list[EvidenceMappingOut]


class EvidenceProvenanceOut(BaseModel):
    """One piece of evidence with where it came from.

    `source_location` and `model_confidence` are null for evidence a
    person attached by hand — there is no citation behind it, and
    inventing one would misrepresent how it got here."""

    evidence_id: uuid.UUID
    file_id: uuid.UUID
    filename: str
    title: str
    # Where the document this came from opens. Same route as everywhere
    # else; None when it has no indexed document to open.
    document_href: str | None = None
    source_location: str | None = None
    evidence_type: str | None = None
    model_confidence: float | None = None
    quoted_passage: str | None = None
    # auto | human | manual
    mapped_by: str = "manual"

    model_config = {"from_attributes": True}


class RequirementCoverageLineOut(BaseModel):
    """One requirement this control serves, and where it stands.

    Shipped per requirement so the percentage beside it can be checked
    against the same list rather than taken on trust.
    """

    requirement_id: uuid.UUID
    reference_code: str
    title: str
    framework_key: str
    applicability: str
    applicability_reason: str
    coverage: str
    covered: bool = False
    missing_conditions: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ControlAssessmentViewOut(BaseModel):
    """What the evidence on file supports, and what it does not.

    Derived on read rather than stored, so it cannot go stale against
    the evidence it describes. `recorded_status` is the last human
    verdict and is shown beside this, never replaced by it."""

    control_id: uuid.UUID
    status: str
    confidence: int
    why: str
    missing: str | None
    evidence: list[EvidenceProvenanceOut]
    requirement_codes: list[str]
    requirements: list[RequirementCoverageLineOut] = Field(default_factory=list)
    # The effective label — what the detail header shows. The three
    # dimensions travel separately below it.
    label: str = ""
    ai_status: str = ""
    ai_label: str = ""
    human_status: str | None = None
    human_label: str | None = None
    effective_status: str = ""
    review_required: bool = False
    recorded_by: uuid.UUID | None = None
    applicable_count: int = 0
    satisfied_count: int = 0
    recorded_status: str | None = None
    recorded_at: str | None = None

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
    # What the evidence actually supports, so the screen can lead with
    # an assessment instead of an empty pass/fail form.
    assessment: ControlAssessmentViewOut | None = None


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
    """The manual fallback. Normal policies are detected from an upload;
    this is for one that exists outside Veyntra, or has no document
    yet."""

    title: str = Field(min_length=1, max_length=300)
    file_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    category: str | None = Field(default=None, max_length=120)
    version: str | None = Field(default=None, max_length=40)


class PolicyOut(BaseModel):
    """A policy as its list row and detail header need it.

    Governance fields are nullable and stay null until a person fills
    them in. Automatic detection sets the title, the document and the
    category — never an owner, an approval or a review date, because the
    product cannot know those and a guess would be a compliance record
    nobody wrote.
    """

    id: uuid.UUID
    title: str
    file_id: uuid.UUID | None
    status: str
    category: str | None = None
    owner_id: uuid.UUID | None
    version: str | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    effective_date: datetime | None = None
    next_review_at: datetime | None = None
    review_frequency_months: int | None = None
    detected_automatically: bool = False
    ai_system_id: uuid.UUID | None
    created_at: datetime
    # Derived on read, so neither can go stale against the calendar or
    # against a field somebody just filled in.
    review_state: str = "not_scheduled"
    # Days until the review, computed here rather than in the browser: a
    # `Date.now()` in a render is impure and gives a different answer on
    # every paint. Null when nothing is scheduled.
    days_until_review: int | None = None
    missing_governance: list[str] = Field(default_factory=list)
    # What the linked document is and what it produced, so a row can say
    # "10 controls" without the UI fetching every document separately.
    document_filename: str | None = None
    # Where that document opens — the same Document Detail route the
    # library, the evidence list and a Copilot citation use.
    document_href: str | None = None
    evidence_count: int = 0
    control_count: int = 0
    framework_names: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PolicyVersionOut(BaseModel):
    """One document that was, at some point, this policy.

    Superseded versions stay readable: "what did your retention policy
    say in March" is a question an auditor asks.
    """

    id: uuid.UUID
    file_id: uuid.UUID
    filename: str | None = None
    version: str | None
    status: str
    approved_at: datetime | None
    superseded_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyControlOut(BaseModel):
    """A control this policy's evidence supports.

    Read from the existing evidence relationships rather than a second
    mapping table — the document was already mapped to controls when it
    was analysed, and asking the customer to connect them again is the
    duplicate data entry this whole feature exists to remove.
    """

    id: uuid.UUID
    title: str
    assessment_status: str
    assessment_label: str


class PolicyDetailOut(PolicyOut):
    versions: list[PolicyVersionOut] = Field(default_factory=list)
    controls: list[PolicyControlOut] = Field(default_factory=list)
    document_index_status: str | None = None


class PolicyGovernanceUpdate(BaseModel):
    """The fields a person fills in. All optional — this is the form the
    "Complete setup" action opens, and it is normal to know the owner
    before the review cadence."""

    owner_id: uuid.UUID | None = None
    version: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, max_length=120)
    effective_date: datetime | None = None
    next_review_at: datetime | None = None
    review_frequency_months: int | None = Field(default=None, ge=1, le=120)


class PolicyApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class PolicyVersionUploadRequest(BaseModel):
    file_id: uuid.UUID
    version: str | None = Field(default=None, max_length=40)


class PolicyStatusUpdate(BaseModel):
    # `published`/`draft` are the old two-state vocabulary and still
    # accepted so an existing integration does not break; they map onto
    # `approved`/`needs_review`.
    status: str = Field(
        pattern="^(draft|published|needs_review|approved|review_due|superseded|retired)$"
    )


class PolicyBackfillOut(BaseModel):
    created: int
    linked: int
    skipped: int


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
    # Drives whether post-market obligations have begun — Art. 72 binds a
    # high-risk system once it is placed on the market, not while it is
    # still being built. Surfaced because a field that changes what
    # applies to you should not be invisible.
    deployment_status: str = "development"
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
    # --- governance ----------------------------------------------------
    #
    # A RoPA entry is a claim the organization keeps making about itself.
    # One nobody has confirmed in two years is a different thing from one
    # reviewed last month, and the record should say which it is.
    last_reviewed_at: datetime | None = None
    last_reviewed_by: uuid.UUID | None = None
    next_review_at: datetime | None = None
    # Article 9 processing needs its own condition on top of a lawful
    # basis. Held apart so the record can show whether that second
    # question was ever answered.
    special_category: bool = False
    special_category_condition: str | None = None
    # Derived, not stored: a review date in the past is overdue whether
    # or not a job has run.
    review_overdue: bool = False

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _derive_review_state(self) -> "ProcessingActivityOut":
        from datetime import UTC, datetime

        from app.compliance.privacy_deadlines import as_utc

        if self.next_review_at is not None:
            self.review_overdue = as_utc(self.next_review_at) <= datetime.now(UTC)
        return self


class ProcessingActivityReviewIn(BaseModel):
    """Confirming a record still describes what actually happens."""

    # Twelve months matches the cadence the rest of the product uses for
    # policy review. Nothing requires an annual RoPA review; the field
    # exists so an organization can hold itself to a schedule.
    next_review_months: int = Field(default=12, ge=1, le=60)


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
    # When the request arrived — not when somebody logged it. The clock
    # runs from receipt.
    received_at: datetime | None = None
    # One month from receipt, plus any recorded extension.
    due_at: datetime
    # The deadline before any extension, so the screen can say "extended
    # to" rather than showing a later date as though it were always the
    # deadline.
    base_due_at: datetime | None = None
    extension_months: int = 0
    extension_reason: str | None = None
    extension_granted_at: datetime | None = None
    # Derived on read. A stored "overdue" is wrong the moment the clock
    # passes it and nobody has run a job.
    days_remaining: int | None = None
    overdue: bool = False
    due_soon: bool = False
    deadline_label: str | None = None
    fulfilled_at: datetime | None
    notes: str | None
    assigned_to: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _derive_deadline(self) -> "DSAROut":
        """Where this request stands against its deadline.

        Computed here rather than stored, so a request does not become
        overdue only once some job has noticed. `received_at` is null
        on rows that predate the column being populated; those fall back
        to `created_at`, which is the best evidence of receipt we have
        for them.
        """
        from app.compliance import privacy_deadlines

        received = self.received_at or self.created_at
        if received is None:  # pragma: no cover - both are non-null in practice
            return self
        state = privacy_deadlines.describe(
            received_at=received,
            extension_months=self.extension_months or 0,
            completed_at=self.fulfilled_at,
        )
        self.base_due_at = state.base_due_at
        self.days_remaining = state.days_remaining
        self.overdue = state.overdue
        self.due_soon = state.due_soon
        self.deadline_label = state.label
        return self


class DSARExtensionIn(BaseModel):
    """A recorded decision to take longer, with the reason for it.

    Not a longer default. An extension is something a controller decides
    and can be asked to justify, so the reason is required.
    """

    months: int = Field(ge=1, le=2)
    reason: str = Field(min_length=1, max_length=1000)


# --- the privacy workspace ---------------------------------------------


class PrivacyMetricOut(BaseModel):
    key: str
    label: str
    value: int
    # Where this number's records live. A dashboard figure that leads
    # nowhere is a decoration.
    href: str
    tone: str = "neutral"


class PrivacyAttentionOut(BaseModel):
    """One thing a person can act on, and the route to it."""

    key: str
    # overdue | urgent | attention | info
    severity: str
    title: str
    detail: str
    href: str
    record_type: str
    record_id: uuid.UUID | None = None


class PrivacyOverviewOut(BaseModel):
    metrics: list[PrivacyMetricOut] = []
    attention: list[PrivacyAttentionOut] = []
    needs_attention: int = 0


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
    # Who is asking, and by when. A questionnaire without them is a form;
    # with them it is a piece of work somebody owns.
    customer_name: str | None = Field(default=None, max_length=200)
    due_at: datetime | None = None
    source: str = Field(
        default="internal_template", pattern="^(customer_provided|internal_template)$"
    )
    opportunity_id: uuid.UUID | None = None
    # The same machinery serves vendor due diligence; without this a
    # security questionnaire sent *to* a vendor has nowhere to attach.
    vendor_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    # The customer's questions, as pasted out of their email or
    # spreadsheet. Veyntra pulls the questions out rather than asking
    # somebody to retype them one per form field.
    questions_text: str | None = None
    # Start drafting answers immediately. This is the product: a
    # questionnaire should arrive mostly answered.
    draft_answers: bool = True


class QuestionnaireStatusUpdate(BaseModel):
    """The one workflow transition a person makes by hand.

    `completed` means the questionnaire went back to the customer, which
    is the only thing about its state that reading the answers cannot
    tell us. Every other status is derived from the answers by
    `app.compliance.questionnaire_status`, so sending one of them here
    hands control back to that calculation rather than overriding it —
    a hand-set `draft` on a fully approved questionnaire is exactly the
    disagreement this endpoint used to create.
    """

    status: str = Field(pattern="^(draft|in_review|ready_to_share|completed)$")


class QuestionnaireProgressOut(BaseModel):
    """What is left to do, in the four states work moves through.

    The counts sum to `total` by construction, so the progress bar and
    the numbers beside it cannot disagree.
    """

    total: int = 0
    approved: int = 0
    needs_review: int = 0
    draft: int = 0
    unanswered: int = 0
    # Share of questions approved — the only state that means "ready to
    # send". A drafted answer nobody has read is not progress towards
    # sharing, and counting it as such would flatter the figure.
    percent_complete: int = 0
    # Whether every question has an approved answer.
    ready_to_share: bool = False


class ReadinessBlockerOut(BaseModel):
    """One reason a questionnaire cannot be shared.

    `code` is what the UI keys an action off — `customer_required` is the
    one that puts a "Set customer" button on the row. `message` is the
    sentence a person reads, and it is the same sentence the API returns
    when it refuses the transition, because two wordings for one rule is
    how a screen and a server start disagreeing.
    """

    code: str
    message: str


class QuestionnaireReadinessOut(BaseModel):
    """Whether this questionnaire can go back to the customer, and why not.

    Computed by `app.compliance.questionnaire_status`, which is also what
    writes the stored status and what the transition endpoint checks. The
    UI renders this; it does not recompute it.
    """

    ready: bool = False
    blockers: list[ReadinessBlockerOut] = []
    # True when something no amount of answering will fix — no customer,
    # or no review to belong to. The row shows "Needs setup" and offers
    # the repair rather than a progress bar.
    needs_setup: bool = False


class QuestionnaireOut(BaseModel):
    id: uuid.UUID
    title: str
    # Who is asking, and by when.
    customer_name: str | None = None
    due_at: datetime | None = None
    source: str
    status: str
    opportunity_id: uuid.UUID | None
    vendor_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None
    created_at: datetime
    progress: QuestionnaireProgressOut = QuestionnaireProgressOut()
    # --- lifecycle ----------------------------------------------------
    #
    # Whether this may be permanently deleted, decided by the server from
    # what has actually happened to it — never by the client from a
    # status field. The UI uses it to choose between offering Delete and
    # offering Archive; the endpoint checks again regardless, because a
    # client that gets this wrong must not be able to destroy anything.
    can_delete: bool = False
    # Why not, in words meant for the person who clicked Delete.
    delete_blocked_reason: str | None = None
    archived_at: datetime | None = None
    archived_by: uuid.UUID | None = None
    # --- readiness ------------------------------------------------------
    #
    # The words for the stored status, and what is standing in its way.
    # Both server-side, so every surface says the same thing.
    status_label: str = ""
    readiness: QuestionnaireReadinessOut = QuestionnaireReadinessOut()
    # True when the title reads like one of the questions rather than the
    # name of the questionnaire. Flagged, never acted on — renaming
    # somebody's record on a guess is not a fix.
    title_looks_like_a_question: bool = False

    model_config = {"from_attributes": True}


class QuestionnaireRename(BaseModel):
    """Giving a questionnaire a name that describes it.

    The repair for a record titled "Do you encrypt customer data at rest?"
    — a question somebody pasted into the title box. Offered, never
    applied automatically: the product can see the title reads oddly, but
    only a person knows what it should say instead.
    """

    title: str = Field(min_length=1, max_length=300)


class QuestionnaireCustomerUpdate(BaseModel):
    """Naming the customer a questionnaire came from.

    This is the human decision the backfill refuses to make on its own.
    It writes the name down and puts the questionnaire into that
    customer's engagement in one step, because the two are the same
    intention and splitting them leaves a named questionnaire sitting
    outside any review.
    """

    customer_name: str = Field(min_length=1, max_length=200)


class QuestionnaireCustomerResultOut(BaseModel):
    """The engagement a repaired questionnaire ended up in."""

    questionnaire_id: uuid.UUID
    customer_name: str
    security_review_id: uuid.UUID | None = None
    security_review_title: str | None = None
    review_created: bool = False


class ArchiveResultOut(BaseModel):
    """What an archive or restore call did.

    `changed` is false when the record was already in the state asked
    for. Retries land there, and a retry must not look like a second
    archiving — no second audit event, no second notification.
    """

    id: uuid.UUID
    title: str
    archived_at: datetime | None = None
    # The status the record was in before, kept so restoring puts it back
    # exactly as it was rather than guessing.
    status: str
    changed: bool = True


class DeleteResultOut(BaseModel):
    """What a delete call did.

    `deleted` is false when there was nothing there — a retry, a double
    click, or an id that never existed. All three are fine outcomes for
    a delete and none of them is an error worth showing somebody.
    """

    deleted: bool
    id: uuid.UUID
    title: str | None = None


class AnalyzedLineOut(BaseModel):
    """One line of an import, and what Veyntra made of it."""

    text: str
    # new | duplicate | possible_duplicate | unparsed
    outcome: str
    category: str = "compliance"
    # The question already on the questionnaire this one resembles.
    matches: str | None = None
    similarity: float = 0.0
    # Why a line was not read as a question, in words somebody can act on.
    reason: str | None = None
    # Whether importing this would create anything. A possible duplicate
    # counts: it is the reader's decision, which is the entire reason it
    # is flagged rather than merged.
    importable: bool = False


class ImportAnalysisOut(BaseModel):
    """What an import would do, before anything is created.

    Nothing here has been written. The counts and the lines are a
    description of the input, offered so a person can decide — which is
    the difference between an import that is safe to run on a
    hundred-question spreadsheet and one that is not.
    """

    headline: str
    detected: int = 0
    new: int = 0
    duplicates: int = 0
    possible_duplicates: int = 0
    unparsed: int = 0
    lines: list[AnalyzedLineOut] = []
    supported_formats: list[str] = []
    # Where the questions came from, carried through so the confirmation
    # step can record it without the client having to send it back.
    source_filename: str | None = None


class QuestionnaireImportConfirm(BaseModel):
    """Create exactly these questions.

    The texts come from a preview the person just read. Sending the
    chosen lines rather than re-parsing the input is what makes the
    confirmation mean what it said: re-extraction could reach a different
    answer, and then the import would not be the one that was approved.
    """

    questions: list[str] = Field(default_factory=list, max_length=500)
    draft_answers: bool = True
    # Kept for the record on the questionnaire, when the import came from
    # a file rather than a paste.
    source_filename: str | None = Field(default=None, max_length=300)


class ImportResultOut(BaseModel):
    """What the import actually did.

    Every number a person needs to know whether to go and look at
    something. `drafting` says whether answers are still being written,
    because that work continues after this response.
    """

    created: int = 0
    duplicates_skipped: int = 0
    unparsed: int = 0
    # True while answer drafting runs in the background.
    drafting: bool = False
    # The questionnaire's stored status before and after. Importing
    # unresolved questions into something marked complete has to move it
    # back, and saying so is better than letting somebody notice later.
    status_before: str | None = None
    status_after: str | None = None


class QuestionnaireImportRequest(BaseModel):
    """Import questions into an existing questionnaire.

    Either from a file already uploaded to Veyntra, or from text pasted
    straight out of the customer's email.
    """

    file_id: uuid.UUID | None = None
    questions_text: str | None = None
    draft_answers: bool = True


class QuestionnaireImportResult(BaseModel):
    questions_extracted: int
    questions_added: int
    duplicates_skipped: int
    # Null when drafting was not requested; otherwise what came back.
    drafted: dict[str, int] | None = None
    supported_formats: list[str] = []


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
    status: str = Field(pattern="^(unanswered|draft|needs_review|approved|rejected)$")
    evidence_id: uuid.UUID | None = None
    control_id: uuid.UUID | None = None


class QuestionnaireAnswerOut(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    answer_text: str | None
    status: str
    # The word the screen shows for that status.
    status_label: str = ""
    source_type: str | None
    # Already resolved to a reference and a link — never a chunk id.
    citations: list[dict[str, object]] | None
    # What the model said about its own output. Shown, never used alone
    # to decide whether a person must look at it.
    confidence: float | None = None
    # Why this needs a human, in words they can act on.
    review_reason: str | None = None
    # Whether Approve is available at all. An empty answer cannot be
    # approved, and the reason travels with the flag so the button can
    # say why it is disabled rather than just being dead.
    can_approve: bool = False
    approval_blocked_reason: str | None = None
    approved_by: uuid.UUID | None = None
    approved_at: datetime | None = None
    evidence_id: uuid.UUID | None
    control_id: uuid.UUID | None
    answered_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionnaireQuestionDetailOut(QuestionnaireQuestionOut):
    answer: QuestionnaireAnswerOut | None


class QuestionnaireDetailOut(QuestionnaireOut):
    questions: list[QuestionnaireQuestionDetailOut]
    # The customer engagement this belongs to, when it is one a customer
    # sent. Null for internal assessments — those are nobody's engagement
    # but our own, and that distinction is the point of the field.
    security_review_id: uuid.UUID | None = None
    security_review_title: str | None = None
    security_review_href: str | None = None
    # The engagement's own state, so the questionnaire page can show the
    # two dimensions apart: how far the review got, and whether it is
    # still open. "Ready to share" and "Archived" together is a normal
    # thing for a finished engagement to be.
    security_review_status: str | None = None
    security_review_status_label: str | None = None
    security_review_archived_at: datetime | None = None
    # Set only when this is a customer questionnaire with no customer on
    # it and therefore no engagement. The screen uses it to offer the
    # repair rather than silently showing nothing.
    needs_customer: bool = False
    suggested_customer: str | None = None
    suggested_customer_reason: str | None = None
    # The formats a questionnaire file can be imported from, so the UI
    # names what actually works rather than guessing.
    supported_import_formats: list[str] = []


class AuditCreate(BaseModel):
    """Opening an audit engagement.

    `framework_id` and `scope` are what make it an audit rather than a
    title. The framework decides which requirements Veyntra prepares;
    the scope says what the engagement actually covers, which no amount
    of data can infer — two ISO 42001 audits can look at different
    systems, and "which of our things did you examine" is the first
    question anybody reading the report will ask.
    """

    title: str = Field(min_length=1, max_length=300)
    framework_id: uuid.UUID | None = None
    # Who conducted it, recorded rather than inferred.
    #
    # An internal audit names a colleague's account; the name is stored
    # alongside so the record still reads correctly after they leave. An
    # external audit names a person and, where known, their firm.
    #
    # `auditor_type` is explicit because the alternative — treating a
    # missing account id as proof of externality — labelled every audit
    # created before there was a picker as external, including all the
    # internal ones.
    auditor_user_id: uuid.UUID | None = None
    auditor_name: str | None = None
    auditor_type: Literal["internal", "external"] | None = None
    auditor_organization: str | None = Field(default=None, max_length=300)
    # A scope statement is what a reader checks the report against, so a
    # placeholder is worse than an empty box — "This is" reads as a
    # description until somebody tries to use it. Short enough to be
    # meaningless is refused; the form offers framework wording to fill
    # it, and anything a person actually writes is kept.
    scope: str | None = Field(default=None, max_length=2000)
    scheduled_at: datetime | None = None
    owner_id: uuid.UUID | None = None

    @field_validator("scope")
    @classmethod
    def _scope_says_something(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) < 20:
            raise ValueError(
                "Describe what this audit covers — a scope statement is what "
                "a reader checks the report against."
            )
        return cleaned


class AuditUpdate(BaseModel):
    """Correcting an audit's scope after it was opened.

    Audits exist that were created before a framework could be chosen —
    an "ISO 42001 Internal Audit" with no framework attached, which is a
    title and nothing to scope against. Setting one here is what lets
    Veyntra prepare it, rather than making somebody abandon the record
    and open a second audit for the same engagement.

    Every field is optional and only what is sent is changed.
    """

    title: str | None = Field(default=None, min_length=1, max_length=300)
    framework_id: uuid.UUID | None = None
    auditor_user_id: uuid.UUID | None = None
    auditor_name: str | None = Field(default=None, max_length=300)
    scope: str | None = Field(default=None, max_length=2000)
    scheduled_at: datetime | None = None
    owner_id: uuid.UUID | None = None


class AuditStatusUpdate(BaseModel):
    status: str = Field(pattern="^(planned|in_progress|completed)$")


class AuditProgressOut(BaseModel):
    """How far through the scope the auditor is.

    Review progress, not compliance readiness. "12 of 18 reviewed" and
    "67% of requirements evidenced" are different numbers about different
    things, and a card showing one where the other belongs is worse than
    showing neither.
    """

    scoped: int = 0
    reviewed: int = 0
    unreviewed: int = 0
    percent_reviewed: int = 0
    no_finding: int = 0
    observations: int = 0
    minor: int = 0
    major: int = 0
    critical: int = 0
    needs_evidence: int = 0
    open_findings: int = 0
    ready_for_verification: int = 0
    evidence_reviewed: int = 0
    remediation_completed: int = 0
    # --- scope, so "3 requirements" is never left unexplained ----------
    not_applicable: int = 0
    excluded: int = 0
    # --- remediation, which is not the finding -------------------------
    remediation_open: int = 0
    remediation_in_progress: int = 0
    remediation_ready: int = 0
    remediation_closed: int = 0
    accepted_risk: int = 0


class AuditScopeLineOut(BaseModel):
    """One requirement and why it is, or is not, in this audit.

    Nothing is hidden. A compliance manager defending a report needs to
    say why fifteen requirements are absent as readily as why three are
    present, and "not applicable" and "the auditor left it out" are
    different answers with different consequences.
    """

    requirement_id: uuid.UUID | None = None
    reference_code: str
    title: str
    # included | not_applicable | excluded
    disposition: str
    reason: str | None = None
    excluded_at: datetime | None = None


class AuditScopeOut(BaseModel):
    framework_name: str | None = None
    included: int = 0
    not_applicable: int = 0
    excluded: int = 0
    lines: list[AuditScopeLineOut] = []


class AuditExclusionIn(BaseModel):
    """Taking a requirement out of this audit's scope.

    The reason is required. "Excluded" with nothing beside it is the one
    thing a reader of the report can do nothing with, and scope decisions
    are the first thing an external reviewer questions.
    """

    reason: str = Field(min_length=1, max_length=1000)


class AuditOut(BaseModel):
    id: uuid.UUID
    title: str
    framework_id: uuid.UUID | None
    # The framework as it was named when the audit ran. A completed audit
    # should still say what it was against after the catalog is renamed.
    framework_name: str | None = None
    auditor_user_id: uuid.UUID | None = None
    auditor_name: str | None
    # internal | external | null when nobody has established which.
    # Never inferred from whether an account is linked.
    auditor_type: str | None = None
    auditor_organization: str | None = None
    scope: str | None = None
    status: str
    status_label: str = ""
    scheduled_at: datetime | None
    # The timestamps are the state, not decoration beside it. A planned
    # audit has neither; an audit in progress has a start and no
    # completion. They move with `status` and never contradict it.
    started_at: datetime | None = None
    completed_at: datetime | None
    prepared_at: datetime | None = None
    owner_id: uuid.UUID | None
    created_at: datetime
    finding_count: int = 0
    progress: AuditProgressOut = AuditProgressOut()
    # See QuestionnaireOut — same rule, decided the same way, and checked
    # again by the endpoint whatever the client believes.
    can_delete: bool = False
    delete_blocked_reason: str | None = None
    archived_at: datetime | None = None
    archived_by: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class AuditFindingCreate(BaseModel):
    """The fallback path: a finding that maps to no scoped requirement.

    Kept because not everything an auditor notices is a clause in the
    standard. The primary path is a decision on an audit row, which
    carries the requirement, control and evidence with it — see
    `AuditDecisionIn`.
    """

    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    control_id: uuid.UUID | None = None


class AuditFindingStatusUpdate(BaseModel):
    status: str = Field(
        pattern="^(open|remediation_in_progress|ready_for_verification|accepted_risk)$"
    )


class AuditEvidenceOut(BaseModel):
    """One piece of evidence, as the audit row shows it.

    No chunk identifiers. `source_location` is the human-readable place
    in the document and `document_href` opens it — an auditor asked to
    trust "chunk 41f9a" has been shown the plumbing instead of the
    evidence.
    """

    evidence_id: str | None = None
    file_id: str | None = None
    title: str
    document_href: str | None = None
    source_location: str | None = None
    evidence_type: str | None = None
    model_confidence: float | None = None


class AuditFindingOut(BaseModel):
    id: uuid.UUID
    audit_id: uuid.UUID
    audit_item_id: uuid.UUID | None = None
    control_id: uuid.UUID | None
    # Copied at the moment the finding was raised, so it keeps reading
    # correctly after the catalog is renamed or the control retired.
    requirement_id: uuid.UUID | None = None
    requirement_code: str | None = None
    control_title: str | None = None
    title: str
    description: str | None
    severity: str
    status: str
    status_label: str = ""
    # What the auditor was looking at when they raised it.
    evidence_snapshot: list[AuditEvidenceOut] = []
    related_task_id: uuid.UUID | None
    verified_by: uuid.UUID | None = None
    verified_at: datetime | None = None
    verification_note: str | None = None
    created_at: datetime
    # Set when the auditor replaced this conclusion with a later one on
    # the same requirement. The finding keeps its severity, its status
    # and its verification; it stops counting as a live finding. Without
    # this, a completed audit read "18 conclusions, 19 findings" and
    # nothing on screen accounted for the extra one.
    superseded_at: datetime | None = None
    superseded_by_id: uuid.UUID | None = None
    superseded_reason: str | None = None

    model_config = {"from_attributes": True}


class AuditItemOut(BaseModel):
    """One scoped requirement, with everything needed to decide on it.

    Requirement, control, assessment, evidence and what is missing travel
    together so the auditor does not open four screens to understand one
    row. Everything prefixed `prepared_` is the snapshot taken when the
    audit was prepared — what was true when they looked.
    """

    id: uuid.UUID
    requirement_id: uuid.UUID
    reference_code: str
    requirement_title: str
    framework_key: str | None = None
    control_id: uuid.UUID | None = None
    control_title: str | None = None
    prepared_status: str
    prepared_status_label: str = ""
    prepared_confidence: int = 0
    prepared_why: str | None = None
    prepared_missing: str | None = None
    evidence_snapshot: list[AuditEvidenceOut] = []
    # Attached since the audit was prepared. Shown as new rather than
    # folded into the snapshot: "this arrived after you looked" is the
    # thing an auditor needs to know about it.
    new_evidence: list[AuditEvidenceOut] = []
    applicability: str | None = None
    applicability_reason: str | None = None
    decision: str | None = None
    # The auditor's own words for their conclusion — "Observation", not
    # "low". The severity is how the finding is tracked; the conclusion
    # is what the auditor decided, and a report that shows one where the
    # other belongs has lost the distinction the workflow rests on.
    decision_label: str | None = None
    decision_note: str | None = None
    decided_at: datetime | None = None
    finding_id: uuid.UUID | None = None
    # --- what the finding is doing now ---------------------------------
    finding_status: str | None = None
    finding_status_label: str | None = None
    finding_severity: str | None = None
    remediation_task_id: uuid.UUID | None = None
    # --- excluded from this audit --------------------------------------
    excluded_at: datetime | None = None
    exclusion_reason: str | None = None
    # --- §14: then, and now --------------------------------------------
    #
    # The snapshot is what the auditor assessed; this is where the
    # requirement stands today. Shown side by side so a completed audit
    # can display improvement without rewriting its own conclusions.
    current_status: str | None = None
    current_status_label: str | None = None
    # Which pile this row is in — derived, never stored, so a worklist
    # cannot go stale about what is left.
    section: str = "satisfied"

    model_config = {"from_attributes": True}


class AuditSectionOut(BaseModel):
    key: str
    label: str
    items: list[AuditItemOut] = []


class AuditDecisionIn(BaseModel):
    """What the auditor concluded about one scoped requirement."""

    decision: str = Field(
        pattern="^(no_finding|observation|minor|major|critical|needs_evidence)$"
    )
    # Required for anything that asserts a deficiency — the server
    # decides which, and refuses rather than trusting the client.
    note: str | None = Field(default=None, max_length=2000)
    # Overrides the title Veyntra would build from what is missing.
    title: str | None = Field(default=None, max_length=300)


class AuditDecisionResultOut(BaseModel):
    item: AuditItemOut
    finding: AuditFindingOut | None = None
    finding_created: bool = False
    # True when the finding was attached to remediation that already
    # existed for this requirement rather than opening a second task.
    remediation_reused: bool = False
    related_task_id: uuid.UUID | None = None


class AuditVerificationIn(BaseModel):
    """Closing a finding, and saying on what basis.

    The note is required. A closure with no reasoning is the same
    document as no closure at all to anybody reading the audit later.
    """

    note: str = Field(min_length=1, max_length=2000)


class AuditReopenIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class AuditCompletionBlockerOut(BaseModel):
    code: str
    message: str


class AuditDetailOut(AuditOut):
    findings: list[AuditFindingOut]
    sections: list[AuditSectionOut] = []
    # What stands between this audit and being called finished. Empty
    # means it can be completed; the endpoint checks again regardless.
    completion_blockers: list[AuditCompletionBlockerOut] = []


class AuditPreparationOut(BaseModel):
    """What preparing the audit scoped, and what it found there."""

    applicable: int = 0
    satisfied: int = 0
    needs_review: int = 0
    gaps: int = 0
    evidence: int = 0
    open_remediation: int = 0
    created: int = 0
    updated: int = 0
    not_applicable: int = 0


class SecurityReviewCreate(BaseModel):
    opportunity_id: uuid.UUID
    # If set, imports this existing Questionnaire (setting its
    # opportunity_id) instead of creating a new one.
    questionnaire_id: uuid.UUID | None = None


class SecurityReviewStatusUpdate(BaseModel):
    # "cleared" is deliberately excluded — that gated transition only
    # happens via POST /security-reviews/{id}/clear.
    status: str = Field(pattern="^(in_progress|blocked)$")


class ReviewProgressOut(BaseModel):
    """A review's work, added up across every questionnaire in it."""

    questionnaires: int = 0
    total: int = 0
    approved: int = 0
    needs_review: int = 0
    draft: int = 0
    unanswered: int = 0
    percent_complete: int = 0
    # True only when every question in every questionnaire is approved.
    ready_to_share: bool = False


class ExportBlockerOut(BaseModel):
    """One reason a customer-facing package should not be generated."""

    code: str
    message: str


class ExportAnswerOut(BaseModel):
    """One question and the answer approved for it.

    No confidence score and no model reasoning. Those are internal
    numbers about our process, not facts about the customer's security,
    and a customer reading "0.82" learns something misleading.
    """

    question_id: uuid.UUID
    question: str
    category: str | None = None
    answer: str
    approved_at: datetime | None = None
    sources: list[str] = []
    # The answer carries a limitation, which goes out with it rather than
    # being summarised away.
    qualified: bool = False


class ExportDocumentOut(BaseModel):
    """A document that could go in the package, and whether it may.

    `eligible` is the product's answer, `included` is the person's. An
    ineligible document is never on by default, whatever the client asks
    for.
    """

    file_id: uuid.UUID
    title: str
    kind: str
    disclosure: str
    disclosure_label: str = ""
    eligible: bool
    reason: str | None = None
    version: str | None = None
    status: str | None = None
    superseded: bool = False
    supports: list[str] = []
    included: bool = False


class ExportPreviewRequest(BaseModel):
    """Configure what the preview would contain. Writes nothing."""

    output_type: str = Field(pattern="^(summary|questionnaire|evidence_pack)$")
    # Null means "propose the eligible documents"; a list means the
    # person has chosen. Ineligible ids in the list are refused rather
    # than honoured.
    include_documents: list[uuid.UUID] | None = None
    sections: list[str] | None = None
    title: str | None = Field(default=None, max_length=300)
    introduction: str | None = Field(default=None, max_length=4000)


class ExportPreviewOut(BaseModel):
    """Exactly what the customer would receive, before any file exists."""

    output_type: str
    output_label: str
    file_format: str
    title: str
    customer_name: str | None = None
    review_title: str
    review_status: str
    review_status_label: str
    # §26: history rather than a live position, and the reader is told.
    review_archived: bool = False
    review_date: datetime
    progress: ReviewProgressOut = ReviewProgressOut()
    answers: list[ExportAnswerOut] = []
    documents: list[ExportDocumentOut] = []
    disclosures: list[str] = []
    blockers: list[ExportBlockerOut] = []
    sections: list[str] = []
    section_labels: dict[str, str] = {}
    introduction: str | None = None
    disclaimer: str
    ready: bool = False
    # The fingerprint of these contents. Sent back on generate, which is
    # how the server knows the person is confirming what they were shown
    # rather than whatever the review says by the time they click.
    digest: str = ""
    # The version this would be generated as, so the screen can say
    # "version 2" before it exists.
    next_version: int = 1
    # For the questionnaire: the customer's own column headings, and what
    # we would put where.
    column_mapping: dict[str, str] = {}
    source_filename: str | None = None


class ExportGenerateRequest(ExportPreviewRequest):
    """Turn the previewed contents into a file.

    `confirm_digest` is the fingerprint the preview returned. Sending it
    back is how the server knows the person is confirming what they were
    shown rather than whatever the review happens to say now — between
    opening a preview and clicking generate, somebody else can approve an
    answer.
    """

    confirm_digest: str = Field(min_length=1, max_length=64)


class ReviewExportOut(BaseModel):
    """One generated package, and what went into it."""

    id: uuid.UUID
    security_review_id: uuid.UUID
    output_type: str
    output_label: str = ""
    file_format: str
    title: str
    version: int
    file_id: uuid.UUID | None = None
    generated_by: uuid.UUID | None = None
    generated_at: datetime
    shared_at: datetime | None = None
    # True when the review has moved since this was generated. The
    # package itself is unchanged — this only says the screen should
    # offer a new version.
    stale: bool = False
    # A short description of the frozen contents, for the history row.
    answer_count: int = 0
    document_count: int = 0

    model_config = {"from_attributes": True}


# --- audit reports ---------------------------------------------------
#
# A completed audit's last step. Preview first, always: the generate
# endpoint takes back the digest the preview returned, so what gets
# issued is what somebody read.


class AuditReportBlockerOut(BaseModel):
    code: str
    message: str


class AuditReportConclusionOut(BaseModel):
    """One requirement, what the auditor concluded, and where it stands.

    Two clocks, named rather than merged: `decision_label` is the
    auditor's conclusion and cannot move; `current_remediation_label` is
    live.
    """

    reference_code: str
    requirement_title: str
    control_title: str | None = None
    evidence_state: str | None = None
    evidence_state_label: str | None = None
    decision: str | None = None
    decision_label: str
    decision_note: str | None = None
    decided_at: datetime | None = None
    decided_by: str | None = None
    evidence_count: int = 0
    finding_id: uuid.UUID | None = None
    current_remediation: str | None = None
    current_remediation_label: str | None = None


class AuditReportFindingOut(BaseModel):
    """One finding, as an audit report states it.

    The requirement is the subject; `title` is what the finding was
    named and is never the heading. That distinction is the fix for
    findings headed "1 document(s) are mapped to this requirement, but
    Veyntra has no itemised expectation set for it yet" — the plumbing
    presented as the audit result.
    """

    id: uuid.UUID
    reference_code: str | None = None
    requirement_title: str | None = None
    title: str
    description: str | None = None
    severity: str
    # "Minor finding", not "medium". The report speaks the auditor's
    # language rather than the database's.
    conclusion_label: str
    current_status: str
    current_status_label: str
    control_title: str | None = None
    evidence_state: str | None = None
    evidence_state_label: str | None = None
    # A report-grade sentence for what Veyntra could establish, derived
    # from the evidence state rather than quoting the diagnostic.
    assessment: str | None = None
    not_evidenced: str | None = None
    # The auditor's reason, where they recorded one. Never invented.
    auditor_note: str | None = None
    # The conclusion and the evidence state disagree and nobody wrote
    # down why. Said out loud, so the report does not read as though it
    # contradicts itself.
    rationale_gap: bool = False
    evidence_count: int = 0
    verified_at: datetime | None = None
    verified_by: str | None = None
    verification_note: str | None = None
    remediation_task: str | None = None
    remediation_owner: str | None = None
    remediation_due: datetime | None = None
    superseded_at: datetime | None = None
    superseded_reason: str | None = None


class AuditReportSeverityGroupOut(BaseModel):
    key: str
    severity: str
    label: str
    count: int
    findings: list[AuditReportFindingOut] = []


class AuditReportMetricOut(BaseModel):
    """One number on the results summary, with its zeros kept."""

    label: str
    value: str
    emphasis: bool = False


class AuditorIdentityOut(BaseModel):
    """The auditor, as structured fields rather than a formatted string.

    "Zach Warren (external)" glued two claims into one name, and the
    second was inferred from whether an account happened to be linked.
    """

    name: str | None = None
    # internal | external | null when nobody has established which
    auditor_type: str | None = None
    type_label: str | None = None
    # The firm, for an external auditor only.
    organization: str | None = None
    unresolved: bool = False


class AuditReportSignOffOut(BaseModel):
    """Who conducted the audit, who issued it, and when.

    Not a signature. The product records no formal approval on an audit,
    and drawing a signature block nobody signed would be a forgery in a
    document people rely on.
    """

    auditor: AuditorIdentityOut
    completed_at: datetime | None = None
    generated_at: datetime
    generated_by: str | None = None
    report_version: int
    approved_by: str | None = None
    approved_at: datetime | None = None


class AuditReportRemediationOut(BaseModel):
    status: str
    label: str
    count: int


class AuditReportEvidenceOut(BaseModel):
    title: str
    filename: str | None = None
    document_href: str | None = None
    # The version as reviewed at audit preparation, taken from the
    # audit's own snapshot. A document revised since must not change
    # what the report says was reviewed.
    version: str | None = None
    version_label: str = "Version not recorded"
    version_source: str = "unrecorded"
    evidence_states: list[str] = []
    requirement_codes: list[str] = []


class AuditReportProgressOut(BaseModel):
    scoped: int
    reviewed: int
    percent_reviewed: int
    excluded: int
    findings: int
    superseded: int


class AuditReportPreviewOut(BaseModel):
    """Exactly what the report will say. Nothing has been generated."""

    audit_id: uuid.UUID
    title: str
    audit_title: str
    organization_name: str | None = None
    framework_name: str | None = None
    framework_basis: str | None = None
    auditor_name: str | None = None
    auditor: AuditorIdentityOut
    scope: str | None = None
    status: str
    status_label: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    prepared_at: datetime | None = None
    classification: str = "Confidential"
    # False when the organization record has no usable name — the report
    # says so rather than substituting anything derived from a person.
    organization_name_configured: bool = True
    progress: AuditReportProgressOut
    # The result in sentences, before any table.
    executive_summary: list[str] = []
    metrics: list[AuditReportMetricOut] = []
    methodology: list[str] = []
    conclusions: list[AuditReportConclusionOut] = []
    conclusion_counts: dict[str, int] = {}
    conclusion_summary: list[AuditReportMetricOut] = []
    findings: list[AuditReportFindingOut] = []
    findings_by_severity: list[AuditReportSeverityGroupOut] = []
    superseded_findings: list[AuditReportFindingOut] = []
    remediation: list[AuditReportRemediationOut] = []
    remediation_rows: list[AuditReportFindingOut] = []
    verification: list[AuditReportFindingOut] = []
    evidence_index: list[AuditReportEvidenceOut] = []
    limitations: list[str] = []
    disclaimer: str
    sign_off: AuditReportSignOffOut
    generated_for: datetime
    # Handed back to the generate endpoint. What makes generation
    # "issue what I just read" rather than "issue whatever is true now".
    digest: str
    next_version: int
    blockers: list[AuditReportBlockerOut] = []
    ready: bool = True


class AuditReportGenerateRequest(BaseModel):
    confirm_digest: str


class AuditReportOut(BaseModel):
    """One issued report. Written once, never edited."""

    id: uuid.UUID
    audit_id: uuid.UUID
    title: str
    version: int
    file_format: str
    file_id: uuid.UUID | None = None
    generated_by: uuid.UUID | None = None
    generated_by_name: str | None = None
    generated_at: datetime
    # True when the audit or its remediation has moved since this was
    # generated. The report itself is unchanged — this only says the
    # screen should offer a new version.
    stale: bool = False
    # A short description of the frozen contents, for the history row.
    findings_count: int = 0
    requirements_reviewed: int = 0

    model_config = {"from_attributes": True}


class FileDisclosureUpdate(BaseModel):
    """Deciding whether a document may leave the organization."""

    disclosure: str = Field(pattern="^(internal|customer_shareable|restricted)$")


class SecurityReviewOut(BaseModel):
    """One customer's security review: the engagement questionnaires
    belong to.

    `opportunity_id` and `questionnaire_id` are the sales-coupled model
    this replaced — nullable, carried by rows that predate the change,
    and set by nothing new. The engagement is identified by
    `customer_name`, which is a name rather than a foreign key into a CRM
    this product does not have.
    """

    id: uuid.UUID
    title: str | None = None
    customer_name: str | None = None
    status: str
    # The words for that status, decided server-side so every surface
    # says the same thing.
    status_label: str = ""
    progress: ReviewProgressOut = ReviewProgressOut()
    archived_at: datetime | None = None
    archived_by: uuid.UUID | None = None
    # Legacy, from when a review belonged to a sales opportunity.
    opportunity_id: uuid.UUID | None = None
    questionnaire_id: uuid.UUID | None = None
    approval_id: uuid.UUID | None = None
    trust_package_file_id: uuid.UUID | None = None
    is_deal_blocker: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewQuestionnaireOut(BaseModel):
    """One questionnaire inside a review, as its card shows it.

    `status` is how far it got; `archived_at` is whether it is still on
    the working list. A finished engagement is a list of archived
    questionnaires that are each still "ready to share", and collapsing
    those two into one badge is what made an archived record read as
    outstanding work.
    """

    id: uuid.UUID
    title: str
    source: str
    status: str
    href: str
    archived_at: datetime | None = None
    progress: QuestionnaireProgressOut = QuestionnaireProgressOut()


class SecurityReviewDetailOut(SecurityReviewOut):
    # Every questionnaire in the engagement, in the order they arrived.
    questionnaires: list[ReviewQuestionnaireOut] = []
    opportunity_title: str | None = None
    approval_status: str | None
    gap_count: int
    # The first questionnaire in the engagement, kept so the existing
    # detail screen keeps working. `questionnaires` above is the real
    # relationship — a review holds as many as the customer sends.
    questionnaire: QuestionnaireDetailOut | None = None


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


class RemediationPlanOut(BaseModel):
    """The structured fix behind a gap.

    Shipped whole rather than as a paragraph so the UI can render the
    checklist as a checklist and the required evidence as an upload
    target, instead of asking the reader to parse prose.
    """

    problem: str
    why: str
    action: str
    owner: str
    priority: str
    due_in_days: int
    required_evidence: list[str] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    evidence_reviewed: list[str] = Field(default_factory=list)
    missing_conditions: list[str] = Field(default_factory=list)
    missing_evidence: str = ""
    requirement_code: str = ""
    requirement_title: str = ""
    framework_name: str = ""
    control_title: str | None = None
    affected_ai_systems: list[str] = Field(default_factory=list)


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
    remediation_plan: RemediationPlanOut | None = None
    missing_conditions: list[str] = Field(default_factory=list)
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
    # The conditions the evidence on file does not meet, named. Empty
    # unless the status is `deficient` — we never list a condition we
    # could not actually check.
    missing_conditions: list[str] = Field(default_factory=list)
    # Why no conclusion was reached, when the status is `needs_review`.
    uncertainty: str | None = None


class ReadinessBreakdownOut(BaseModel):
    """The readiness score with its arithmetic attached, so the number is
    never presented without the reason for it."""

    percent: float
    satisfied: int
    needs_review: int
    deficient: int
    assessment_failed: int
    evidence_missing: int
    not_assessed: int
    # Applicable requirements only — the denominator the percentage was
    # actually computed against.
    total: int
    not_applicable: int
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
    """Overrides, not defaults.

    Every field is optional because the remediation plan already carries
    a suggested priority and a realistic due date derived from the work
    itself. Sending a hardcoded \"high / 7 days\" on every gap was how a
    training programme and a one-line policy edit ended up with the same
    deadline.
    """

    title: str | None = None
    assignee_id: uuid.UUID | None = None
    priority: str | None = Field(default=None, pattern="^(low|normal|high|urgent)$")
    due_in_days: int | None = Field(default=None, ge=1, le=365)


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
    # Whether the Copilot can retrieve from this document. Separate
    # from `processing_status`, which only says Document Intelligence
    # finished — a document can be analysed and mapped perfectly while
    # its embedding call failed.
    # The governance record this document is, when it is a policy. Lets
    # the document row link straight to it rather than making the reader
    # go and find it.
    policy_id: uuid.UUID | None = None
    policy_title: str | None = None
    policy_status: str | None = None
    index_status: str = "pending"
    index_error: str | None = None
    indexed_at: datetime | None = None
    extracted_characters: int | None
    # How many versions of this document exist, this one included. The
    # library lists logical documents, not uploads, so a document
    # revised twice is one row that says so — not three rows a reader
    # has to work out the relationship between.
    version_count: int = 1
    version_label: str | None = None
    # Why this document has the mappings it has — or none.
    #
    # `no_controls` is a normal state, not a failure: a new organization
    # has nothing to map evidence to until it adopts a framework, and the
    # document is fully analysed regardless. Saying so is the difference
    # between "we are still setting up" and "your policy did not work".
    #
    # mapped | no_matches | no_controls | not_analyzed
    mapping_state: str = "not_analyzed"
    # Set while an upload is waiting for somebody to say whether it is a
    # new version of this document. Shown on the row because that
    # decision is the reason the library looks wrong until it is made.
    has_pending_version: bool = False
    document_type: str | None
    document_domain: str | None
    created_at: datetime

    proposed_count: int = 0
    approved_count: int = 0
    unverifiable_count: int = 0

    # What to call this in a list, cleaned of the sort prefix and
    # extension somebody's folder left on it. The filename is still shown
    # underneath — it is how the customer finds the file on their own
    # disk — but it is not the document's name.
    title: str = ""
    # The canonical Document Detail route for this file, composed
    # server-side (app.core.routes). None when the document has not been
    # indexed yet: there is no page to open, and the row renders without
    # a link rather than with one that 404s.
    document_id: uuid.UUID | None = None
    href: str | None = None

    model_config = {"from_attributes": True}


class DocumentVersionOut(BaseModel):
    """One version of a document, in the chain it belongs to."""

    file_id: uuid.UUID
    document_id: uuid.UUID | None = None
    href: str | None = None
    filename: str
    version_label: str | None = None
    # current | superseded
    status: str
    uploaded_at: datetime
    uploaded_by: uuid.UUID | None = None
    evidence_count: int = 0


class VersionCandidateOut(BaseModel):
    """What Veyntra thinks this upload is a newer version of.

    A proposal. Nothing is linked until a person says so — the whole
    point of reporting the confidence and the reasons is that the
    decision is theirs.
    """

    file_id: uuid.UUID
    title: str
    # high | medium | low
    confidence: str
    reasons: list[str] = []
    # Both sides of the comparison, so the reader decides from what the
    # two documents say about themselves rather than from a similarity
    # score they have no way to check. Every field is absent when the
    # document does not state it — nothing here is inferred.
    current_version: str | None = None
    current_effective_date: str | None = None
    current_approved_at: datetime | None = None
    current_filename: str | None = None
    detected_version: str | None = None
    detected_effective_date: str | None = None
    uploaded_filename: str | None = None


class NeedsCustomerOut(BaseModel):
    """A questionnaire the backfill would not name a customer for.

    `suggested_customer` is what the title appears to say, with `reason`
    explaining how that was arrived at. It is offered, never applied —
    the screen shows it with the customer's name in an editable field so
    the person confirming can see what they are agreeing to.
    """

    questionnaire_id: uuid.UUID
    title: str
    archived: bool = False
    suggested_customer: str | None = None
    reason: str | None = None


class ReviewBackfillOut(BaseModel):
    """What a customer-review backfill linked, and what it would not decide.

    Two counts, because there are two kinds of evidence and only one of
    them can be wrong. `linked` is questionnaires whose customer was
    recorded on the record itself. `linked_from_title` is the subset a
    caller linked by accepting a name read off the title, which happens
    only when they ask for it explicitly.

    `needs_customer` is the rest: customer-provided questionnaires with
    no customer on them. They are reported rather than guessed about, so
    the screen can ask somebody instead of a product deciding.
    """

    examined: int = 0
    linked: int = 0
    linked_from_title: int = 0
    reviews_created: int = 0
    # Reviews the pass closed because every questionnaire in them was
    # already archived — the engagement follows its work.
    reviews_archived: int = 0
    unnamed: int = 0
    suggested: int = 0
    already_linked: int = 0
    needs_customer: list[NeedsCustomerOut] = []
    dry_run: bool = True


class ClassificationBackfillOut(BaseModel):
    """What a classification backfill pass looked at, and what it fixed.

    For documents processed before classification was separated from
    control mapping: readable and indexed, but with no `document_type`,
    and therefore no Managed Policy. Nobody re-uploads anything.
    """

    examined: int = 0
    classified: int = 0
    policies_created: int = 0
    failed: int = 0
    # True when nothing was written, which is the default.
    dry_run: bool = True


class VersionBackfillOut(BaseModel):
    """What a version backfill pass looked at, and what it proposes.

    Counts only. The pass never links anything — it proposes, and each
    proposal waits on a person — so this reports what there is to decide
    rather than claiming work was done.
    """

    examined: int = 0
    proposed: int = 0
    already_linked: int = 0
    already_proposed: int = 0
    unreadable: int = 0
    # True when nothing was written, which is the default.
    dry_run: bool = True


class SectionChangeOut(BaseModel):
    """One section of a document, and what happened to it between versions."""

    # added | removed | rewritten | reworded | unchanged
    change: str
    section: str | None = None
    summary: str
    previous_text: str | None = None
    current_text: str | None = None


class VersionDiffOut(BaseModel):
    """What changed between two versions, as a person would describe it.

    Section-level, not line-level: a policy re-flowed by a word processor
    changes every line and says nothing new, while a reviewer needs to
    know that §7 now requires monthly review where it used to say
    "should be monitored".
    """

    previous_file_id: uuid.UUID
    current_file_id: uuid.UUID
    previous_label: str | None = None
    current_label: str | None = None
    headline: str
    added: int = 0
    removed: int = 0
    modified: int = 0
    unchanged: int = 0
    changes: list[SectionChangeOut] = []


class AcceptVersionRequest(BaseModel):
    """Accept an upload as the next version of an existing document."""

    supersedes_file_id: uuid.UUID
    version_label: str | None = Field(default=None, max_length=40)


class VersionAcceptedOut(BaseModel):
    """What accepting the version did to the compliance state."""

    file_id: uuid.UUID
    supersedes_file_id: uuid.UUID
    version_label: str | None = None
    unchanged: int = 0
    modified: int = 0
    added: int = 0
    removed: int = 0
    approvals_preserved: int = 0
    approvals_reopened: int = 0


class DocumentEvidenceOut(BaseModel):
    """One thing Veyntra found in this document, and what it supports.

    The chain a reader needs to follow is document → passage → control →
    requirement, so all four travel together. `status` is the suggestion's
    own state, never flattened into "approved": a proposal awaiting a
    person and a mapping somebody stood behind are different claims.
    """

    id: uuid.UUID
    # Where in the document, as the document labels it ("§1 Purpose").
    source_location: str | None
    quoted_passage: str | None
    evidence_type: str | None
    status: str
    confidence: float | None
    control_id: uuid.UUID | None
    control_title: str | None
    requirement_id: uuid.UUID | None
    requirement_reference: str | None
    requirement_title: str | None
    framework_name: str | None


class DocumentDetailOut(BaseModel):
    """Everything the Document Detail page shows, in one response.

    Addressed by the knowledge Document id — the same identifier a
    Copilot citation carries — so a document opened from the library and
    the same document opened from a citation are one page.
    """

    document_id: uuid.UUID
    file_id: uuid.UUID
    href: str
    title: str
    filename: str
    document_type: str | None
    document_domain: str | None
    classification: str
    # Document Intelligence: whether the compliance analysis ran.
    processing_status: str
    processing_error: str | None
    # Whether the text is readable here — a different pipeline with a
    # different failure mode. A document can be ingested and readable
    # while the compliance analysis was never asked for, which is the
    # state every attachment that arrived from elsewhere is in. Gating
    # the reader on `processing_status` showed an empty page for a
    # document the Copilot was happily citing.
    content_status: str
    content_error: str | None = None
    index_status: str
    index_error: str | None
    extracted_characters: int | None
    size_bytes: int
    created_at: datetime
    processed_at: datetime | None

    # The governance record, when this document is a policy. The detail
    # page links to it rather than editing governance here — that screen
    # already exists and does it properly.
    policy_id: uuid.UUID | None = None
    policy_title: str | None = None
    policy_status: str | None = None

    # What the analysis found. Counts of distinct things, not of rows:
    # four suggestions pointing at one control is one control.
    evidence_count: int = 0
    control_count: int = 0
    requirement_count: int = 0
    proposed_count: int = 0
    approved_count: int = 0
    unverifiable_count: int = 0

    evidence: list[DocumentEvidenceOut] = []
    # mapped | no_matches | no_controls | not_analyzed — see
    # ComplianceDocumentOut.mapping_state.
    mapping_state: str = "not_analyzed"
    # Every version of this document, oldest first. One entry for a
    # document that has only ever been uploaded once.
    versions: list[DocumentVersionOut] = []
    version_label: str | None = None
    # Set while an upload is proposed as a newer version of something and
    # nobody has decided yet.
    version_candidate: VersionCandidateOut | None = None


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
    # Set when the person uploaded this *as* a new version of a document
    # they named. That is a decision, not a guess, so detection is
    # skipped and the version is linked as soon as the analysis finishes
    # — asking them to confirm what they just told us is asking twice.
    supersedes_file_id: uuid.UUID | None = None


class ApproveSuggestionRequest(BaseModel):
    title: str | None = Field(default=None, max_length=300)


class CopilotIndexBackfillOut(BaseModel):
    """What a backfill run did. Counts, so the UI can say so rather than
    claiming success it did not verify."""

    indexed: int
    failed: int
    unsupported: int
