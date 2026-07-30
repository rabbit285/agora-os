"""Compliance domain (spec sections 12, 50 — Phase 3).

Follows the spec's core chain: Framework -> Requirement -> Control ->
Evidence / Assessment -> Risk. Frameworks and Requirements are global
catalog data (organization_id is nullable/absent, same pattern as system
Roles in app.core.rbac) since regulatory text doesn't vary per tenant;
everything an organization actually does — Control, ControlAssessment,
Evidence, Risk, Policy — is tenant-scoped.

Deliberately not modeled yet (see docs/KNOWN_LIMITATIONS.md): framework
versioning, evidence versioning, audits (auditor portal), regulatory
updates (external intelligence feed), data transfers, vendor risk,
questionnaires, Trust Center. Each is a substantial feature in its own
right; this slice ships the backbone they would all attach to.

`AISystem` / `AIAssessment` add the spec §12 "AI System Inventory" / "AI
Risk Assessment" screens (EU AI Act governance). `AISystem.approval_id`
is the cross-module hook (spec §69 "New AI Tool Adoption": "... -> AI
risk assessment -> Approval -> Add to AI inventory -> ..."): registering
a `high` or `unacceptable`-risk system creates a real `core.Approval`,
and it cannot be moved to `approved` status until that Approval is
granted — see app.compliance.service.register_ai_system /
decide_ai_system_status and docs/DECISIONS.md ADR-0027.

`ProcessingActivity` / `DPIA` / `DSAR` add spec §12's Privacy sub-features
(Module 1 — AI Compliance explicitly lists "privacy operations, RoPA,
DPIAs, DSARs" alongside frameworks/controls, not as a separate module).
`DPIA.ai_system_id` extends the same "New AI Tool Adoption" hook a second
time: registering a high/unacceptable-risk AI system now also creates a
linked draft DPIA — the chain's "Privacy assessment" step (spec §69) —
see app.compliance.service.register_ai_system and docs/DECISIONS.md
ADR-0029. A `high`-risk-level DPIA created directly (not via that hook)
gets its own real `core.Approval`, gating `approved` the same way
`AISystem` does (GDPR Article 35: a DPIA concluding high residual risk
requires supervisory-authority consultation / formal sign-off before the
processing can proceed).

`AIIncident` adds spec §50's "AI GOVERNANCE" `ai_incidents` table — a
post-deployment incident log for an `AISystem` (EU AI Act Article 73's
"serious incident" reporting obligation for high-risk systems). A
`critical`-severity incident auto-creates a linked Compliance `Risk` and
a response `core.Task` (+ owner `core.Notification`), reusing the exact
chain `app.secops.service.create_incident` already established for
`SecurityIncident` (ADR-0018, ADR-0023) — this build's third use of that
specific hook shape, not a new mechanism. See
app.compliance.service.create_ai_incident and docs/DECISIONS.md ADR-0030.

`Vendor` / `VendorAssessment` add spec §12/§67's "Vendors" screen (vendor
risk management). `Evidence.vendor_id` generalizes Evidence beyond
Control (a SOC 2 report or DPA is evidence about a vendor, not a
Control). A `VendorAssessment` concluding `critical`/`high` risk
auto-creates a linked Compliance `Risk` — the same "assessment creates a
tracked consequence" hook shape `record_assessment` established for
Control (spec §80), reused for a fourth entity type. See
app.compliance.service.record_vendor_assessment and docs/DECISIONS.md
ADR-0031.

`Questionnaire` / `QuestionnaireQuestion` / `QuestionnaireAnswer` add
spec §12/§67's "Questionnaires" screen. `Questionnaire.opportunity_id`
is the forward-looking link the Enterprise Sales Security Review (spec
§69) will use. Each answer either reuses a previously-`approved` answer
from the org's own answer library (`source_type="reused_from_library"`)
or is drafted by the existing AI Copilot (`app.ai.copilot.ask_copilot`,
retrieval-grounded over the Knowledge base) as `source_type=
"ai_suggested"` — never auto-approved, consistent with this build's
human-in-the-loop discipline everywhere an AI-authored artifact could
reach a customer. See app.compliance.service.suggest_questionnaire_answer
and docs/DECISIONS.md ADR-0032.

`Audit` / `AuditFinding` add spec §12/§67's "Audits" screen (the auditor
portal's audit-run tracking, distinct from a one-off `ControlAssessment`
— an Audit groups many findings under one auditor engagement, optionally
against a `Framework`). A `high`/`critical`-severity finding auto-creates
a remediation `core.Task`, reusing `record_assessment`'s "assessment
creates a tracked consequence" hook shape for a fifth entity type — the
same Task-creating half of that shape `ControlAssessment` itself uses,
not the Risk-creating half `VendorAssessment`/`AIIncident` use, since an
audit finding is a remediation checklist item, not an ongoing risk to
track. See app.compliance.service.record_audit_finding and
docs/DECISIONS.md ADR-0033.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class Framework(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Catalog data: GDPR, EU AI Act, ISO 27001, etc. Seeded once,
    shared across every organization — never tenant-scoped."""

    __tablename__ = "frameworks"

    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class Requirement(UUIDPrimaryKeyMixin, Base):
    """Catalog data: one clause/article of a Framework. Global, like
    Framework — an organization's own response to it is a Control mapped
    via ControlMapping, not a copy of this row."""

    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint("framework_id", "reference_code", name="uq_requirement_framework_code"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("frameworks.id"), nullable=False, index=True
    )
    reference_code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class Control(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An organization's own implemented measure. May satisfy zero or more
    catalog Requirements (see ControlMapping)."""

    __tablename__ = "controls"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # not_started | in_progress | implemented | needs_review
    status: Mapped[str] = mapped_column(String(30), default="not_started")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ControlMapping(Base):
    __tablename__ = "control_mappings"

    control_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), primary_key=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("requirements.id"), primary_key=True
    )


class ControlAssessment(UUIDPrimaryKeyMixin, Base):
    """Point-in-time judgement of whether a Control is operating
    effectively. A `fail` assessment creates a remediation Task — see
    app.compliance.service.record_assessment and docs/DECISIONS.md."""

    __tablename__ = "control_assessments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    control_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=False, index=True
    )
    # pass | fail | partial | not_assessed
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    assessed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A stored artifact (reuses the Phase 1 File primitive — spec section
    80: shared platform primitives, not a duplicate storage path) that
    supports a Control or a Vendor, or stands alone in the evidence
    library."""

    __tablename__ = "evidence"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=True, index=True
    )
    # A SOC 2 report, DPA, or security questionnaire response is evidence
    # about a Vendor, not a Control — kept as a second optional target
    # rather than a new evidence table (spec §80).
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vendors.id"), nullable=True, index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Risk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "risks"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="general")
    likelihood: Mapped[str] = mapped_column(String(10), nullable=False)  # low|medium|high
    impact: Mapped[str] = mapped_column(String(10), nullable=False)  # low|medium|high
    # open | mitigated | accepted
    status: Mapped[str] = mapped_column(String(20), default="open")
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Policy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "policies"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class AISystem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One entry in the AI System Inventory (spec §12/§55, EU AI Act
    governance). `risk_classification` follows the EU AI Act's own risk
    tiers rather than inventing a parallel scale."""

    __tablename__ = "ai_systems"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    purpose: Mapped[str] = mapped_column(String(2000), nullable=False)
    # minimal | limited | high | unacceptable (EU AI Act risk tiers)
    risk_classification: Mapped[str] = mapped_column(String(20), default="minimal")
    # in_review | approved | rejected | retired
    status: Mapped[str] = mapped_column(String(20), default="in_review")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Cross-module hook (spec §69 "New AI Tool Adoption") — set when
    # risk_classification is high/unacceptable. See
    # app.compliance.service.register_ai_system / decide_ai_system_status.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approvals.id"), nullable=True
    )


class AIAssessment(UUIDPrimaryKeyMixin, Base):
    """Point-in-time risk/impact assessment of an AISystem — mirrors
    ControlAssessment's shape deliberately (same judgement vocabulary)."""

    __tablename__ = "ai_assessments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    # pass | fail | partial | not_assessed
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    assessed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProcessingActivity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One entry in the Record of Processing Activities (RoPA, GDPR
    Article 30) — an organization's own catalog of what personal data it
    processes and why. Tenant-scoped, unlike Framework/Requirement's
    global catalog data: this is the organization's own record, not
    shared regulatory text."""

    __tablename__ = "processing_activities"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    purpose: Mapped[str] = mapped_column(String(2000), nullable=False)
    # consent | contract | legal_obligation | vital_interests | public_task | legitimate_interests
    # (GDPR Article 6's six lawful bases)
    legal_basis: Mapped[str] = mapped_column(String(30), nullable=False)
    data_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    data_subjects: Mapped[str] = mapped_column(String(300), nullable=False)
    retention_period: Mapped[str] = mapped_column(String(300), nullable=False)
    # active | archived
    status: Mapped[str] = mapped_column(String(20), default="active")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class DPIA(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Data Protection Impact Assessment (GDPR Article 35). May be
    conducted for an organization's own `ProcessingActivity`, created
    automatically for a high/unacceptable-risk `AISystem` (the "New AI
    Tool Adoption" chain's Privacy assessment step — see
    app.compliance.service.register_ai_system), or both."""

    __tablename__ = "dpias"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    processing_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processing_activities.id"), nullable=True, index=True
    )
    # Cross-module hook (spec §69 "New AI Tool Adoption" -> "Privacy assessment").
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # low | medium | high — DPIA's own concluded risk level, not necessarily
    # the same scale as AISystem.risk_classification
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    # draft | in_review | approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="draft")
    findings: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Set only when a `high`-risk-level DPIA is created directly (not via
    # the AISystem hook, which already has its own Approval) — see
    # app.compliance.service.create_dpia / decide_dpia_status.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approvals.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class DSAR(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Data Subject Access Request (GDPR Articles 15-20: access,
    rectification, erasure, portability). `due_at` defaults to 30 days
    from creation — GDPR Article 12(3)'s one-month response deadline."""

    __tablename__ = "dsars"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    requester_name: Mapped[str] = mapped_column(String(300), nullable=False)
    requester_email: Mapped[str] = mapped_column(String(320), nullable=False)
    # access | deletion | rectification | portability
    request_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # received | in_progress | fulfilled | rejected
    status: Mapped[str] = mapped_column(String(20), default="received")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class AIIncident(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A post-deployment incident involving an AI system (spec §50's AI
    Governance `ai_incidents` — EU AI Act Article 73's "serious incident"
    reporting obligation for high-risk systems). Always tied to a specific
    `AISystem`, unlike `DPIA` which may stand alone."""

    __tablename__ = "ai_incidents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_systems.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # low | medium | high | critical
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    # open | investigating | resolved | closed
    status: Mapped[str] = mapped_column(String(20), default="open")
    # Cross-module hook (spec §69-style chain, reusing SecurityIncident's
    # exact shape — ADR-0018/ADR-0023/ADR-0030): a `critical` incident
    # auto-creates a linked Compliance Risk.
    related_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risks.id"), nullable=True
    )
    # Same hook: a `critical` incident also creates a response core.Task.
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Vendor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An organization's own third-party vendor record (spec §12/§67
    "Vendors" screen) — tenant-scoped, like Control, unlike Framework's
    global catalog data."""

    __tablename__ = "vendors"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    category: Mapped[str] = mapped_column(String(100), default="general")
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # low | medium | high | critical — current concluded risk tier, mirrors
    # the vocabulary Risk/SecurityAsset already use, kept updated by
    # record_vendor_assessment rather than a separate rollup job.
    risk_tier: Mapped[str] = mapped_column(String(10), default="low")
    # active | under_review | offboarded
    status: Mapped[str] = mapped_column(String(20), default="active")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class VendorAssessment(UUIDPrimaryKeyMixin, Base):
    """Point-in-time risk judgement of a Vendor — mirrors
    ControlAssessment's shape deliberately (same "assessment creates a
    tracked consequence" hook, spec §80). A `critical`/`high` conclusion
    auto-creates a linked Compliance Risk — see
    app.compliance.service.record_vendor_assessment."""

    __tablename__ = "vendor_assessments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    # low | medium | high | critical
    risk_conclusion: Mapped[str] = mapped_column(String(10), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Cross-module hook: set when risk_conclusion is high/critical.
    related_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risks.id"), nullable=True
    )
    assessed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Questionnaire(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A customer or internal security/compliance questionnaire (spec
    §12/§67 "Questionnaires"). `opportunity_id` is the forward-looking
    link the Enterprise Sales Security Review (spec §69) creates/imports
    a Questionnaire against."""

    __tablename__ = "questionnaires"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # customer_provided | internal_template
    source: Mapped[str] = mapped_column(String(30), default="internal_template")
    # draft | in_progress | completed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_opportunities.id"), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class QuestionnaireQuestion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "questionnaire_questions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("questionnaires.id"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String(2000), nullable=False)
    # compliance | security
    category: Mapped[str] = mapped_column(String(20), default="compliance")
    order_index: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuestionnaireAnswer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The current answer to a QuestionnaireQuestion. One-to-one with the
    question — re-answering replaces this row's fields rather than
    accumulating a history, since only the current answer matters for
    what goes into a trust package (spec §69)."""

    __tablename__ = "questionnaire_answers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("questionnaire_questions.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    answer_text: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # draft | approved | missing
    status: Mapped[str] = mapped_column(String(20), default="missing")
    # ai_suggested | manual | reused_from_library
    source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    citations: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=True
    )
    answered_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Audit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One auditor engagement (spec §12/§67 "Audits" screen) — a
    named audit run that groups many `AuditFinding` rows, optionally
    against a catalog `Framework` (e.g. an annual ISO 27001 audit)."""

    __tablename__ = "audits"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    framework_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("frameworks.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    auditor_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # planned | in_progress | completed
    status: Mapped[str] = mapped_column(String(20), default="planned")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class AuditFinding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single finding raised during an Audit, optionally against a
    specific Control. A `high`/`critical` finding auto-creates a
    remediation `core.Task` — see
    app.compliance.service.record_audit_finding."""

    __tablename__ = "audit_findings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audits.id"), nullable=False, index=True
    )
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # low | medium | high | critical
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    # open | remediated
    status: Mapped[str] = mapped_column(String(20), default="open")
    # Cross-module hook: set when severity is high/critical.
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
