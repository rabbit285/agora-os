"""Compliance domain (spec sections 12, 50 — Phase 3).

Follows the spec's core chain: Framework -> Requirement -> Control ->
Evidence / Assessment -> Risk. Frameworks and Requirements are global
catalog data (organization_id is nullable/absent, same pattern as system
Roles in app.core.rbac) since regulatory text doesn't vary per tenant;
everything an organization actually does — Control, ControlAssessment,
Evidence, Risk, Policy — is tenant-scoped.

Deliberately not modeled yet (see docs/KNOWN_LIMITATIONS.md): framework
versioning, evidence versioning, regulatory updates (external
intelligence feed). Each is a substantial feature in its own right; this
slice ships the backbone they would all attach to. (Trust Center lives
in `app.trust_center`, not here — see that module's docstring for why.)

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

`SecurityReview` adds spec §69's "Enterprise Sales Security Review"
cross-module scenario — the payoff for `Questionnaire.opportunity_id`
having been forward-looking since ADR-0032. Starting a review creates or
imports a `Questionnaire` against the `sales.Opportunity`, moves the
opportunity into a `security_review` stage, and sets
`is_deal_blocker=True`; a materiality threshold on `Opportunity.value`
decides whether clearing the review requires a real `core.Approval`
first (the same primitive every other high-stakes gate in this build
uses). Syncing a review reuses `suggest_questionnaire_answer` for every
still-`missing` question (retrieving the org's approved answer library or
drafting via AI Copilot), attaches the most relevant `Evidence` for any
answer whose `control_id` has none yet, and creates a remediation
`core.Task` per remaining gap — a sixth reuse of this build's "creates a
tracked consequence" hook shape (spec §80), here producing many Tasks
per review rather than one. Clearing a review is refused while gaps or a
pending Approval remain, and generates a real trust package `core.File`
(a compiled document of approved Q&A + evidence titles) rather than a
placeholder. See app.compliance.service.start_security_review /
sync_security_review / clear_security_review and docs/DECISIONS.md
ADR-0035.

`DataTransfer` completes Privacy's four sub-features (RoPA, DPIAs,
DSARs, and now international transfers — GDPR Chapter V, Articles
44-49), extending Privacy exactly like `ProcessingActivity`/`DPIA`/`DSAR`
did rather than becoming a new module (ADR-0029's precedent) — reusing
`compliance.privacy.manage` rather than minting a new permission. A
transfer relying on an Article 49 derogation — meant to be exceptional,
not a routine transfer mechanism — auto-creates a linked Compliance
`Risk`, the seventh reuse of this build's "creates a tracked consequence"
hook shape (spec §80). See app.compliance.service.create_data_transfer
and docs/DECISIONS.md ADR-0036.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, DateTime, Uuid

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class Framework(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Catalog data: GDPR, EU AI Act, ISO 27001, etc. Seeded once, shared
    across every organization. `organization_id` is null for these global
    catalog frameworks; an organization can also define its own private
    "Custom Framework" (spec §12's own named "Custom Frameworks" item),
    which sets `organization_id` and is only ever visible to that org."""

    __tablename__ = "frameworks"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True
    )
    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    @property
    def is_custom(self) -> bool:
        return self.organization_id is not None


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
    # standard | high
    #
    # "high" marks requirements where a wrongly-accepted evidence mapping
    # is expensive to discover later: breach notification, DPIA,
    # prohibited AI practices, human oversight. Evidence proposed against
    # these always goes to a human, whatever the model's confidence.
    # Sensitivity is a property of the requirement, not of the document,
    # so it lives in the catalog rather than being inferred per upload.
    sensitivity: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")


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
    #
    # Workflow state only. Whether a control is *evidenced* is derived in
    # app.compliance.assessment from what is actually attached, and is
    # deliberately not a field here — a self-declared "evidenced" flag
    # that nothing checks is the thing an auditor discounts first.
    status: Mapped[str] = mapped_column(String(30), default="not_started")
    # Free text: organizations group controls by their own taxonomy
    # ("Privacy / Data Governance", "Access Management"), and forcing them
    # onto ours would mean maintaining a list that fits nobody.
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # low | medium | high
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    # Raised when evidence is attached or approved against this control,
    # cleared when the framework is next assessed. The point is that new
    # evidence must not silently change a stated position: the previous
    # assessment stays on the record, visibly stale, until someone runs
    # the assessment again. It is a prompt to re-run, never an automatic
    # re-grading.
    needs_reassessment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Set when this control came from app.compliance.control_library.
    # Lets adopting a second framework extend an existing control with
    # new requirement mappings instead of creating a near-identical one
    # in a different vocabulary. Null for controls the organization
    # wrote themselves, which are never touched by scaffolding.
    template_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
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
    library.

    One document supporting one control is one piece of evidence. Both
    creation paths — a person approving a suggestion, and an
    auto-approval during analysis — used to insert blindly, so
    reprocessing a policy five times left five identical rows and the
    control's evidence count counted our retries. The unique index below
    makes that unrepresentable; `app.core.idempotency.get_or_create` is
    how callers reach it without racing.
    """

    __tablename__ = "evidence"
    __table_args__ = (
        Index(
            "uq_evidence_org_file_control",
            "organization_id",
            "file_id",
            "control_id",
            unique=True,
            postgresql_where=text("control_id IS NOT NULL"),
            sqlite_where=text("control_id IS NOT NULL"),
        ),
    )

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
    # A third optional target: a security incident's workspace (spec §19
    # "Evidence") reuses this same library rather than a fourth table.
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("security_incidents.id"), nullable=True, index=True
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
    # Which AI system or DPIA this risk was raised against. A risk
    # register that cannot say what a risk is *about* forces every reader
    # to re-derive it from the title.
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True, index=True
    )
    dpia_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dpias.id"), nullable=True, index=True
    )
    # Risk after mitigating controls are applied. Null until someone has
    # actually assessed the mitigation — deliberately not defaulted to the
    # inherent value, so "not yet reassessed" stays distinguishable from
    # "reassessed and unchanged".
    residual_likelihood: Mapped[str | None] = mapped_column(String(10), nullable=True)
    residual_impact: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Who the risk lands on. A privacy risk without the people it affects
    # is a statement about a system, and Article 35(7)(c) asks about the
    # risk "to the rights and freedoms of data subjects" — which ones is
    # part of the answer.
    affected_data_subjects: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # What already reduces this risk, and what is being added. Kept apart:
    # the first is the state of the world, the second is a commitment, and
    # a residual rating justified by a safeguard nobody has built yet is
    # the failure mode this separation exists to prevent.
    existing_safeguards: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    additional_mitigations: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class Policy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The governance wrapper around a policy document.

    A `File` is the document somebody uploaded. `Evidence` is what the
    document proves. A Policy is the third thing: who owns it, which
    version is current, whether anybody approved it, and when it is next
    due for review. None of that lives in the document, which is why it
    needs a record of its own — and why that record references the
    document rather than copying it.

    Created automatically when Document Intelligence classifies an upload
    as a policy (see app.compliance.policy_governance). Detection is not
    approval: a detected policy starts at `needs_review` with its
    governance fields empty, because the product cannot know who owns a
    document or whether the organization has signed it off, and inventing
    either would be a fabricated compliance record.
    """

    __tablename__ = "policies"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # The document this policy currently is. Superseded versions keep
    # their own rows in `policy_versions` so an auditor can still read
    # what was in force at a past date.
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    # needs_review | draft | approved | review_due | superseded | retired
    #
    # `published` from the original two-state field maps onto `approved`.
    status: Mapped[str] = mapped_column(String(30), default="needs_review")
    # What kind of policy this is, in the document's own words — taken
    # from the classifier rather than a fixed enum of ours, which would
    # fit nobody.
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # --- Governance ---------------------------------------------------
    #
    # All nullable, all left empty by automatic detection. A missing
    # value means "nobody has told us", which the UI asks about; a
    # guessed value would be a compliance record nobody wrote.
    version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Months between reviews. Drives `next_review_at` when a review is
    # completed, so the schedule survives without being retyped.
    review_frequency_months: Mapped[int | None] = mapped_column(nullable=True)
    # True when this record was created by classification rather than by
    # a person. Kept so the UI can say where it came from, and so a
    # backfill can tell its own rows from hand-made ones.
    detected_automatically: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # spec §69 "New AI Tool Adoption" chain's final step, "Add approved-use
    # policy" — set when `decide_ai_system_status` approves an AISystem.
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ai_systems.id"), nullable=True
    )


class PolicyVersion(UUIDPrimaryKeyMixin, Base):
    """A document that was, at some point, this policy.

    Append-only. A superseded version is never deleted: "what did your
    retention policy say in March" is a question an auditor asks, and a
    product that overwrote the file cannot answer it.
    """

    __tablename__ = "policy_versions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("policies.id"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=False
    )
    # As recorded when this version was current. Free text: a customer's
    # versioning scheme is theirs.
    version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # current | superseded
    status: Mapped[str] = mapped_column(String(20), default="current")
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
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
    # spec §69 "New AI Tool Adoption" step 1, "Vendor created" — a real
    # Vendor row (looked up by name or created), not just this free-text
    # display field. `vendor` above is kept as-is for display/back-compat.
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vendors.id"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(2000), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # The specific model behind the system. Recorded separately from
    # `vendor` because "Anthropic" and "claude-opus-4" are different facts
    # and an inventory that conflates them cannot answer which model is
    # actually in production. A demo/unconfigured deployment must say so
    # here rather than naming a live model it is not calling.
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Who uses it internally, and who is affected by it without using it —
    # the second group is the one the EU AI Act cares most about, and the
    # one an inventory keyed only on "owner" loses entirely.
    internal_users: Mapped[list[str]] = mapped_column(JSON, default=list)
    affected_users: Mapped[list[str]] = mapped_column(JSON, default=list)
    # [{"name": "Customer email", "classification": "confidential"}, ...]
    processed_data: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    # --- Governance facts -------------------------------------------
    #
    # Each of these answers a question the EU AI Act or GDPR asks
    # directly, and each is a fact the organization declares rather than
    # something inferred from the model's behaviour. Nullable because an
    # inventory entry starts incomplete, and how incomplete is itself
    # the thing `documentation_completeness` reports.

    # Whether the system faces outside the organization. A tool only
    # staff touch carries different obligations from one customers meet.
    is_external: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    personal_data_processed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    sensitive_data_processed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Where the system operates or its output lands. Drives whether the
    # EU AI Act reaches it at all.
    geography: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # How a person can interpret, intervene in, or interrupt the system
    # (Article 14). Free text: what counts as effective oversight differs
    # per system, and a checkbox here would let an empty gesture pass.
    human_oversight: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Whether the system makes decisions with legal or similarly
    # significant effects on people (GDPR Article 22).
    automated_decision_making: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # development | pilot | production | retired
    deployment_status: Mapped[str] = mapped_column(String(20), default="development")
    # Third parties in this system's supply chain, by name.
    third_party_vendors: Mapped[list[str]] = mapped_column(JSON, default=list)

    # minimal | limited | high | unacceptable (EU AI Act risk tiers)
    risk_classification: Mapped[str] = mapped_column(String(20), default="minimal")
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # in_review | approved | rejected | retired
    status: Mapped[str] = mapped_column(String(20), default="in_review")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    business_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    technical_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    governance_owner_id: Mapped[uuid.UUID | None] = mapped_column(
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
    # eu_ai_act | privacy | general. Without this, the regulatory
    # applicability assessment and the privacy assessment are the same
    # undifferentiated row, and neither can be shown as done independently
    # — they answer different questions to different regulators.
    assessment_type: Mapped[str] = mapped_column(String(20), nullable=False, default="general")
    # pass | fail | partial | not_assessed
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # The reasoning, kept structured rather than prose: which indicators
    # were answered, what was concluded from them, what remains uncertain,
    # and whether a human still has to look. A classification without its
    # basis is an assertion, and this is a domain where an unsupported
    # assertion is worse than no answer.
    findings: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
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
    # --- what a source document said, kept as what it is ---------------
    #
    # A document naming "OpenAI" is a claim in a file, not proof it means
    # the vendor row of that name, so these are never promoted to a
    # foreign key. They exist because acceptance used to discard them:
    # the document knew there was a US transfer and the activity it
    # became knew nothing, so transfer detection had nothing to work
    # from and correctly proposed nothing.
    processor_named: Mapped[str | None] = mapped_column(String(300), nullable=True)
    destination_country_named: Mapped[str | None] = mapped_column(
        String(2), nullable=True
    )
    # draft | active | needs_review | retired | archived
    #
    # A RoPA entry is a claim the organization keeps making about itself,
    # so it has a lifecycle rather than just existing. `needs_review`
    # is the state a record enters when something it depends on moved or its
    # review date passed — it is still the record of what is processed,
    # and it is no longer one anybody has confirmed lately.
    status: Mapped[str] = mapped_column(String(20), default="active")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # --- governance ----------------------------------------------------
    #
    # When a person last confirmed this record still describes reality,
    # and when they said they would look again. Null review dates mean
    # nobody has set a cadence, which the overview reports as such rather
    # than inventing one.
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Whether this activity processes Article 9 data, and on what
    # condition. Held apart from `data_categories` because the legal
    # question is different: special-category processing needs its own
    # condition on top of a lawful basis, and a record that mixes them
    # cannot show whether the second one was ever answered.
    special_category: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    special_category_condition: Mapped[str | None] = mapped_column(
        String(60), nullable=True
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
    # low | medium | high, or null for "nobody has assessed this yet".
    #
    # Nullable deliberately. This defaulted to "low", so a DPIA with no
    # risks raised against it reported `Inherent risk: Low` — an
    # assessment nobody performed, stated as fact, on the document whose
    # whole purpose is to record that somebody assessed the risk. A
    # cautious default would be "high"; the honest one is nothing.
    #
    # Not the same scale as AISystem.risk_classification.
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Article 35(7)'s required content. Held as named sections rather than
    # one `findings` blob because each is separately assessable and a DPO
    # reviewing one needs to see what is missing, not read prose looking
    # for whether necessity was addressed at all.
    processing_description: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    necessity_assessment: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    proportionality_assessment: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    consultation_notes: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # Derived from the risks raised against this DPIA once they have been
    # reassessed — see app.compliance.dpia_screening.recalculate_residual_risk.
    residual_risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # What the screening concluded, and on what basis. Kept so the
    # decision to carry out (or skip) the DPIA is itself auditable.
    # What the screening counted, and when.
    screening_outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    screening_findings: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    screened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # --- and what a person decided about it ----------------------------
    #
    # Kept apart from the outcome above, because they are different
    # claims by different parties: Veyntra counted criteria against a
    # published rule, and a controller decided whether a DPIA is
    # required. A screen showing only the first implies the product made
    # the call.
    #
    # required | not_required | null while nobody has decided.
    screening_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    screening_decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    screening_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Required when somebody decides a DPIA is *not* needed. "We looked
    # and decided no" is a defensible record; an unexplained no is not.
    screening_rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Which sections a person has actually signed off, as
    # {section_key: {"approved_by": str, "approved_at": iso}}.
    #
    # Review state has to be recorded, not inferred. Completion used to
    # test whether the text still began with Veyntra's draft marker,
    # which means deleting one word from the front of a draft counted as
    # having reviewed it — and a reviewer who agrees with the draft
    # verbatim had no way to say so without editing it first.
    section_reviews: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # --- Article 35(2)/(9) consultation --------------------------------
    #
    # Null means nobody has resolved it, which is not the same as "no
    # consultation happened" — that is itself a recorded answer. Veyntra
    # never fills these in: whether a DPO advised is a fact about
    # something that occurred, and drafting it would be inventing advice.
    # This is the single authoritative consultation state:
    #
    #   None  -> nobody has decided
    #   True  -> a consultation happened, and who/when/what is recorded
    #   False -> a decision that none was needed, with the reason
    #
    # It used to compete with a section sign-off on `consultation_notes`,
    # so the page could say "No consultation performed" and "Nobody has
    # approved the consultation record" about the same fact. Recording
    # the decision *is* the review — see dpia_workflow.NARRATIVE_SECTIONS.
    consultation_performed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    consulted_party: Mapped[str | None] = mapped_column(String(300), nullable=True)
    consulted_role: Mapped[str | None] = mapped_column(String(150), nullable=True)
    consulted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Who resolved it and when — as opposed to who was consulted and
    # when that happened, which is what the three fields above hold.
    consultation_recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    consultation_recorded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- what the risk review concluded --------------------------------
    #
    #   None                -> nobody has reviewed the risks
    #   "risks_identified"  -> at least one risk was accepted onto the register
    #   "no_material_risks" -> reviewed, and none met the threshold
    #
    # The distinction the completion rule turns on. "No risks have been
    # raised" used to block completion outright, which forced a reviewer
    # who had genuinely concluded there were none to invent one. An
    # unreviewed DPIA and a reviewed one that found nothing look the same
    # in a risk count and are not the same claim, so they are stored
    # apart.
    risk_conclusion: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Required for "no_material_risks". A conclusion that nothing is
    # risky is exactly the one an auditor asks to see reasoning for.
    risk_conclusion_rationale: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )
    risk_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    risk_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Article 9 signals, and the answer to them ---------------------
    #
    #   None  -> Veyntra flagged possible special-category data and
    #            nobody has answered
    #   True  -> confirmed present
    #   False -> confirmed not applicable, with the reason
    #
    # Veyntra detects; a person decides. A processing record named
    # "Employee medical-leave administration" strongly suggests health
    # data, and the failure this prevents is the product reading "no
    # categories recorded" and concluding there is nothing sensitive.
    # Whether Article 9 applies, and on what condition, is never recorded
    # here by the product.
    special_category_confirmed: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    # Required when answering "not applicable" to a detected signal.
    special_category_rationale: Mapped[str | None] = mapped_column(
        String(2000), nullable=True
    )
    special_category_decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    special_category_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when a completed DPIA is found to have been signed off on
    # content that would not pass the quality gates today. Never rewrites
    # the snapshot — see dpia_quality_audit.
    quality_review_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # screening | not_required | draft | in_review | approved | completed
    # | rejected
    status: Mapped[str] = mapped_column(String(20), default="draft")
    findings: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # --- completion, and what was true when it happened ----------------
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # The assessment as it stood at completion: context, screening,
    # sections, risks, safeguards, residual rating, approvals, evidence
    # references. Frozen rather than re-derived, because re-deriving it
    # next quarter answers "what is true now", and a completed DPIA is a
    # statement about what was assessed then. When the ROPA or the vendor
    # moves afterwards, this does not quietly improve.
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # A fingerprint of the processing this was assessed against, so
    # "something underneath has changed" can be detected without diffing
    # two snapshots on every page load.
    source_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Why a completed DPIA is being flagged for another look. Set by
    # change detection; never mutates the snapshot above.
    review_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    review_flagged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    #
    # Kept as the coarse outward status. Where the request actually *is*
    # lives in "phase" below: "in progress" covers everything between
    # logging a request and sending it, which is precisely the span
    # somebody needs to know their way around.
    status: Mapped[str] = mapped_column(String(20), default="received")
    # received | identity_verification | scope_review | discovery |
    # response_review | ready_to_respond | completed | blocked
    #
    # Derived from the record rather than set by hand -- see
    # app.compliance.dsar_workflow.derive_phase. Stored so lists can sort
    # and filter on it without loading every request's children, and
    # refreshed on every write that could move it.
    phase: Mapped[str] = mapped_column(String(30), default="received", nullable=False)
    # Why the request cannot proceed, when it cannot. Null whenever the
    # phase is anything but blocked.
    blocked_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    scope_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scope_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # pending | verified | failed. The gate on disclosure: fulfilling an
    # unverified access request hands one person's data to another, which
    # is itself a breach — the request is the attack. Article 12(6) exists
    # precisely so a controller can demand proof before answering.
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")
    verification_method: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # What was actually done to establish identity, in the verifier's own
    # words. The method is a category; this is the evidence, and it is
    # what a regulator asking "how did you know it was her?" needs.
    verification_notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # What the search across authorised sources found, and where. Recorded
    # so the response can be reviewed before it is sent, and so "we looked"
    # is demonstrable after the fact.
    discovery_findings: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    discovery_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    export_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    export_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the request actually arrived. Distinct from `created_at`,
    # which is when somebody got around to logging it — the deadline runs
    # from receipt, and a request logged three days late does not get
    # three extra days.
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    # One month from receipt, recomputed when receipt or the extension
    # changes. Stored so a list can sort and filter on it without
    # deriving it per row.
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # A recorded decision to take longer, not a longer default. Zero
    # means no extension; the maximum the product records is two further
    # months.
    extension_months: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    extension_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    extension_granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class DsarScopeSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One place a request might reach, and the human decision about it.

    Veyntra proposes; a person confirms. The proposal is persisted rather
    than recomputed per request because the decision attaches to it: once
    somebody has excluded "Employee medical-leave administration" for a
    customer's request, re-running the suggestion must not quietly put it
    back in scope.

    Relevance ranks; it never filters. A source the product thinks is
    unrelated is still shown, still listed, and still available to
    include -- silently dropping a low-confidence source is how a
    response ends up incomplete, and the product cannot know enough to
    take that risk on somebody's behalf.
    """

    __tablename__ = "dsar_scope_sources"
    __table_args__ = (
        # One row per logical source per request. Re-running suggestion
        # reconciles against this rather than appending, which is what
        # keeps "Refresh" from tripling the list.
        UniqueConstraint("dsar_id", "source_key", name="uq_dsar_scope_source_key"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    dsar_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dsars.id"), nullable=False, index=True
    )
    # Derived from what the source *is* -- this activity, this vendor --
    # never from the wording of the suggestion.
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    # processing_activity | ai_system | vendor | named_processor | manual
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    # Why this is on the list, in the reviewer's terms. Shown beside the
    # checkbox so the decision is informed rather than trusting.
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    # high | possible | low -- a ranking, not a filter, and computed
    # from the requester and the register alone. Never from whether
    # Veyntra happens to be able to search the source cheaply: that is a
    # fact about our plumbing, not about where this person's data is.
    relevance: Mapped[str] = mapped_column(String(10), default="possible", nullable=False)
    # What the ranking was based on, so a reviewer can disagree with the
    # reasoning rather than just the answer.
    relevance_reason: Mapped[str | None] = mapped_column(String(600), nullable=True)
    # The systems this source's data actually sits in, named so the
    # reviewer knows what confirming it will search.
    linked_systems: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # The actual data sources behind a processing activity, each with its
    # own connection state:
    # [{"name": str, "kind": str, "capability": str, "detail": str}, ...]
    #
    # A RoPA entry is compliance context, not a database. Knowing that
    # "AI Customer Support" is in scope says where to look next; it does
    # not say the person's records live in the activity itself.
    potential_sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # searchable | manual_follow_up | processor_follow_up | not_connected
    # | unsupported
    #
    # What Veyntra can actually do with this source, kept strictly apart
    # from whether it is relevant. "Searchable" means a real adapter
    # exists and the organization has connected it -- never that a table
    # happens to sit in our own database.
    search_capability: Mapped[str] = mapped_column(
        String(30), default="manual_follow_up", nullable=False
    )
    # The human decision. Null until somebody decides -- distinct from
    # False, which is a deliberate exclusion.
    included: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Set when a person added a source Veyntra did not propose.
    added_by_user: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Why a reviewer left a relevant source out. Required when excluding
    # something Veyntra ranked high, so a narrowed scope carries its own
    # justification rather than being an unexplained gap in the response.
    exclusion_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    record_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class DsarDiscoveredItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """What one source yielded, and what a person decided to do with it.

    Rows are counts and references, never the personal data itself. A
    discovery result that copied the records would make the DSAR record a
    second uncontrolled copy of the data it was asked about.

    The review decision lives here rather than being applied to the
    findings blob, so re-running discovery updates what was *found*
    without touching what a person *decided* -- the failure mode being
    that somebody redacts an internal security note, hits refresh, and
    silently un-redacts it.
    """

    __tablename__ = "dsar_discovered_items"
    __table_args__ = (
        UniqueConstraint("dsar_id", "source_key", name="uq_dsar_discovered_source_key"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    dsar_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dsars.id"), nullable=False, index=True
    )
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source_name: Mapped[str] = mapped_column(String(300), nullable=False)
    # not_searched | searched_none | searched_found | search_failed |
    # manual_follow_up
    #
    # These are five different things and the old single "matches" number
    # collapsed them into two. "Searched and found nothing" and "never
    # searched" look identical in a count and mean opposite things to
    # somebody signing a response.
    search_state: Mapped[str] = mapped_column(String(30), nullable=False)
    matches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    record_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Why a search failed or could not run. Carries the operator detail
    # a case worker needs without implying the source was clean.
    state_detail: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # include | exclude | redact | needs_review -- the human decision
    # about disclosure. Defaults to needs_review for anything Veyntra
    # flagged; nothing reaches a response package undecided.
    review_decision: Mapped[str] = mapped_column(
        String(20), default="needs_review", nullable=False
    )
    review_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # What Veyntra noticed that a person should look at -- third-party
    # data, privileged content, security-sensitive material. A flag, and
    # explicitly not an exemption decision: Article 15(4) is a legal
    # judgement and the product does not make it.
    sensitivity_flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # The manual follow-up raised for a source Veyntra cannot search.
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )


class DsarResponsePackage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The response as it was approved, frozen.

    Same shape as AuditReport and for the same reason: what a person
    previewed and approved is what gets sent. Regenerating at send time
    would let the answer change between approval and delivery, which
    makes the approval meaningless -- and for a DSAR the thing that
    changed would be somebody's personal data.

    The source digest is the fingerprint of the inputs at preview. If the
    underlying request moves after approval the mismatch is visible
    rather than silently absorbed.
    """

    __tablename__ = "dsar_response_packages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    dsar_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dsars.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # draft | approved | sent -- a package is drafted, approved once, and
    # then recorded as sent. Approval does not send.
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    contents: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
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
    # Where the processor is, ISO 3166-1 alpha-2 — the same convention
    # LegalEntity uses. Without it the product cannot tell whether
    # sending data here is a third-country transfer, which is the one
    # question a transfer record exists to answer. Null means nobody has
    # recorded it, reported as unknown rather than assumed domestic.
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # The detail a country code cannot carry: "EU region (Frankfurt)".
    data_location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # low | medium | high | critical — current concluded risk tier, mirrors
    # the vocabulary Risk/SecurityAsset already use, kept updated by
    # record_vendor_assessment rather than a separate rollup job.
    risk_tier: Mapped[str] = mapped_column(String(10), default="low")
    # active | under_review | offboarded
    status: Mapped[str] = mapped_column(String(20), default="active")
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # spec §69 "New AI Tool Adoption" step "DPA review" — pending | signed |
    # not_required. Real, reviewable state an admin updates directly;
    # never auto-flipped to "signed" (that would fabricate a legal fact).
    dpa_status: Mapped[str] = mapped_column(String(20), default="pending")
    # not_submitted | pending | approved | conditionally_approved | rejected
    #
    # "Conditionally approved" is the state real vendor reviews actually
    # end in, and its absence is why review processes quietly become
    # rubber stamps: without it, a reviewer holding one outstanding
    # question must either block a vendor the business needs or approve
    # outright and lose the caveat. Conditions are required text on that
    # decision, so the caveat outlives the person who made it.
    approval_state: Mapped[str] = mapped_column(String(30), default="not_submitted")
    approval_conditions: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    approval_decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # `owner_id` above is the business owner; compliance carries its own
    # accountable name, which is rarely the same person.
    compliance_owner_id: Mapped[uuid.UUID | None] = mapped_column(
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
    # privacy | security | general. A privacy review and a security review
    # reach different conclusions about the same vendor, and one must not
    # overwrite or stand in for the other.
    assessment_type: Mapped[str] = mapped_column(String(20), nullable=False, default="general")
    # low | medium | high | critical
    risk_conclusion: Mapped[str] = mapped_column(String(10), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Which checks ran and what each concluded, so a reviewer can see the
    # gaps that drove the rating rather than taking the rating on trust.
    findings: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
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
    # Who is asking, and by when. A questionnaire without them is a form;
    # with them it is a piece of work somebody owns.
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # customer_provided | internal_template
    source: Mapped[str] = mapped_column(String(30), default="internal_template")
    # draft | in_progress | completed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_opportunities.id"), nullable=True, index=True
    )
    # The same questionnaire machinery serves vendor due diligence. It was
    # reachable only from a sales opportunity, so a security questionnaire
    # sent *to* a vendor had nowhere to attach.
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vendors.id"), nullable=True, index=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # --- archived, not deleted ----------------------------------------
    #
    # A timestamp rather than a status value, deliberately. Archiving is
    # orthogonal to where the work got to: a completed questionnaire that
    # is archived is still completed, and restoring it has to put it back
    # exactly as it was. Folding "archived" into `status` would overwrite
    # the answer to "how far did this get" with the answer to "is it on
    # the active list", and the first one is not recoverable afterwards.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    archived_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # The customer engagement this belongs to, for a questionnaire a
    # customer sent. Null for internal assessments, which are nobody's
    # engagement but our own — that distinction is the whole reason this
    # is nullable rather than required.
    security_review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("security_reviews.id"), nullable=True, index=True
    )
    # --- where the questions came from --------------------------------
    #
    # The customer's own spreadsheet, when they sent one. Kept so the
    # completed questionnaire can go back in the shape it arrived in
    # rather than in ours: a security team that sent a 42-row XLSX with
    # their own columns wants those 42 rows back, not a different
    # document that happens to contain the same answers.
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    # What the importer made of that file's columns:
    # {"question": "Customer Question", "category": "Requirement",
    #  "answer": "Response", "sheet": "Sheet1", "header_row": 1}
    # Shown back for confirmation before anything is written — a mapping
    # nobody checked is a mapping that silently puts answers in the wrong
    # column.
    source_columns: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


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
    # unanswered | draft | needs_review | approved | rejected
    #
    # `missing` is gone. It described the row being empty rather than
    # what the reader has to do about it, and the screen printed it
    # verbatim — "missing" tells a compliance manager nothing about
    # whether Veyntra failed, or nobody has looked yet, or an answer
    # exists and needs a decision.
    status: Mapped[str] = mapped_column(String(20), default="unanswered")
    # What the model said about its own output. Displayed, never used on
    # its own to decide whether a person must look — see
    # app.compliance.questionnaire_ai.route_answer, where the checks that
    # matter (is anything actually backing this) come first.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Why this needs a human, in words the reviewer can act on. Null when
    # nothing is outstanding.
    review_reason: Mapped[str | None] = mapped_column(String(600), nullable=True)
    # Who approved it and when — the record that makes an approved answer
    # something the organization stands behind rather than something a
    # model wrote.
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The words somebody actually approved.
    #
    # "Has this changed since it was approved" cannot be answered from
    # timestamps: `updated_at` moves on the same flush that records the
    # approval, and on every later touch for any reason. Comparing the
    # text against what was signed off is the only way to answer it
    # truthfully — and it is the question a customer-facing export has to
    # ask before quoting an answer as approved.
    #
    # Null on rows approved before this existed. Null means "we cannot
    # tell", and the export treats that as unchanged rather than
    # inventing a discrepancy nobody can act on.
    approved_text: Mapped[str | None] = mapped_column(String(4000), nullable=True)
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
    # Who performed the audit. Two fields because there are two cases and
    # collapsing them loses the one that matters: a colleague running an
    # internal audit is a real account with a real identity in the trail,
    # and an external firm is a name we were given. Storing the firm in a
    # user column would assert an account that does not exist; storing
    # the colleague only as text throws away the actor.
    auditor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    auditor_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # internal | external | null
    #
    # Recorded, never inferred. "No user id, therefore external" is the
    # rule this column replaces, and it was wrong in the ordinary case: a
    # colleague whose name was typed as text before there was a picker is
    # an internal auditor whose account simply was not linked. Calling
    # them external in a formal report misstates who conducted the audit.
    #
    # Null means nobody has established which this is — a legacy row
    # whose name matched no member, or matched more than one. Unresolved
    # is reported as unresolved; it is not quietly resolved either way.
    auditor_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # The firm an external auditor belongs to. Only ever set alongside
    # `auditor_type == "external"`; an internal auditor's organization is
    # the one running the audit.
    auditor_organization: Mapped[str | None] = mapped_column(
        String(300), nullable=True
    )
    # What this audit covers, in the auditor's words. Not derivable from
    # the framework: two ISO 42001 audits can scope different systems,
    # and "which of our things did you look at" is the first question
    # anybody reading the report later will ask.
    scope: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # planned | in_progress | completed
    #
    # The timestamps below are the state, not decoration beside it. A
    # `planned` audit carrying a `completed_at` is what this product was
    # doing: the completion stamp was set on the way to completed and
    # never cleared on the way back, so the screen showed "Planned" over
    # "Completed 8/26/2026". They move together now — see
    # `app.compliance.audit_state`.
    status: Mapped[str] = mapped_column(String(20), default="planned")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When Veyntra built the workspace, and what it found. The counts are
    # a snapshot: the point of an audit is what was true when the auditor
    # looked, and compliance state moves underneath it constantly.
    prepared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # {"applicable": int, "satisfied": int, "needs_review": int,
    #  "gaps": int, "evidence": int, "open_remediation": int}
    prepared_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # The framework as it was named when the audit ran. Frameworks are
    # catalog rows that get renamed and re-versioned; a completed audit
    # should still say what it audited against.
    framework_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # --- archived, not deleted ----------------------------------------
    #
    # A timestamp rather than a status value, deliberately. Archiving is
    # orthogonal to where the work got to: a completed questionnaire that
    # is archived is still completed, and restoring it has to put it back
    # exactly as it was. Folding "archived" into `status` would overwrite
    # the answer to "how far did this get" with the answer to "is it on
    # the active list", and the first one is not recoverable afterwards.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    archived_by: Mapped[uuid.UUID | None] = mapped_column(
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
    # The row in the audit workspace this came from. Null for a finding
    # raised by hand — the fallback for something that maps to no
    # requirement — which is why this is nullable rather than the audit
    # being the only link.
    audit_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_items.id"), nullable=True, index=True
    )
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("requirements.id"), nullable=True, index=True
    )
    # Copied, not joined. A finding has to keep reading correctly after
    # the catalog is renamed or the control is retired.
    requirement_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    control_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # low | medium | high | critical
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    # open | remediation_in_progress | ready_for_verification | closed
    # | accepted_risk
    #
    # Remediation finishing is not the finding closing. The team can do
    # the work and attach the evidence; whether that answers the finding
    # is the auditor's call, and collapsing the two would let a task
    # board close an audit finding.
    status: Mapped[str] = mapped_column(String(30), default="open")
    # What the auditor was looking at when they raised it. A list of
    # {evidence_id, title, document_href, evidence_type} — frozen,
    # because "the evidence I reviewed" is a claim about a moment.
    evidence_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # --- verification, which is a human act ---------------------------
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Cross-module hook: the remediation task doing the work. Reused from
    # an existing task where the same gap already has one, rather than
    # opening a second for the same underlying problem.
    related_task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    # --- superseded, not deleted --------------------------------------
    #
    # An auditor who verified and closed an observation, and then changed
    # their conclusion on that same requirement to a Minor finding, ends
    # up with two findings for one row. That is correct: reopening a
    # closed verification somebody signed would rewrite a signature. But
    # leaving the first one in the list unlabelled is what made a
    # completed audit report "18 conclusions, 19 findings" with nothing
    # on screen explaining the extra one.
    #
    # So the earlier finding is marked as replaced, keeping its severity,
    # its status and its verification intact. It stays in the record and
    # out of the counts.
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_findings.id"), nullable=True
    )
    superseded_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)


class AuditReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One generated audit report, and exactly what it said.

    Written once, never edited. An audit report is a statement about what
    an auditor concluded on a given day; if remediation moves afterwards,
    the report does not get quietly better. Version 1 keeps saying what
    it said, the screen notes that the audit has changed since, and
    somebody generates version 2 if they want the current picture.

    `contents` is the snapshot — the conclusions as decided, the finding
    states and remediation states at generation, the evidence and
    document versions cited. Stored rather than re-derived, because
    re-deriving it next month answers a different question than "what did
    this report say".

    A preview writes none of this. The two-step exists so somebody reads
    the report before it exists as a file, and a preview that left a
    record behind would make the history a list of things considered
    rather than things issued.
    """

    __tablename__ = "audit_reports"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audits.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # Increments per audit, so "version 2 of the report" is a thing
    # somebody can ask for and point at.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False, default="pdf")
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    contents: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # A fingerprint of the audit state this was generated from. Compared
    # against the audit now, to say "changed since generated" without
    # diffing two snapshots on every page load.
    source_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("audit_id", "version", name="uq_audit_report_version"),
    )


class ReviewExport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One customer-facing package, and exactly what went into it.

    A generated deliverable is a claim made to somebody outside the
    organization, so this is written once and never edited. When the
    review moves on afterwards — an answer is reopened, a policy gets a
    new version — the export stays as it was and the screen says the
    review has changed since. Rewriting it would mean the customer's copy
    and our record of what we sent them no longer match, which is the one
    thing an assurance record must never do.

    `contents` is the snapshot: the answers as approved at that moment,
    the document versions included, the sections chosen, the disclosures
    kept. It is stored rather than re-derived because re-deriving it
    tomorrow answers a different question than "what did we send".

    A preview writes none of these. The two-step exists so somebody sees
    the contents before they exist as a file, and a preview that left a
    record behind would make the history a log of things considered
    rather than things sent.
    """

    __tablename__ = "review_exports"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    security_review_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("security_reviews.id"), nullable=False, index=True
    )
    # summary | questionnaire | evidence_pack
    output_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # pdf | xlsx | zip
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # Increments per (review, output_type), so "version 2 of the summary"
    # is a thing somebody can ask for and point at.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # The generated file. Delivered through the same signed, time-limited
    # download the rest of the product uses; never inlined.
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    # The frozen contents. See the class docstring — this is the record
    # of what was sent, not a cache of what is currently true.
    contents: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # A fingerprint of the review state this was generated from. Compared
    # against the review now, to say "changed since generated" without
    # having to diff two snapshots on every page load.
    source_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    # Set only when somebody records that it actually went to the
    # customer. Generating a PDF is not sending it, and a product that
    # conflates the two tells its user a package was delivered because a
    # file exists.
    shared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shared_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class AuditItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One scoped requirement in an audit, and what the auditor did with it.

    This is the thing that turns an audit from a blank finding form into
    a prepared workspace. When an audit is prepared, Veyntra writes one
    of these per applicable requirement, carrying what it found at that
    moment: the control serving the requirement, the evidence on file,
    the assessment state, and the sentences explaining both.

    Everything prefixed `prepared_` is a **snapshot**, deliberately
    denormalised. Compliance state moves constantly — documents get new
    versions, controls get reassessed, evidence gets attached — and an
    audit is a record of what was true when somebody looked. Joining
    live to controls and evidence would mean a completed audit silently
    rewriting its own conclusions every time the underlying data moved,
    which is the opposite of what an audit is for.

    The auditor's decision lives beside the snapshot rather than
    replacing it, so the record shows both what Veyntra found and what a
    person concluded about it.
    """

    __tablename__ = "audit_items"
    __table_args__ = (
        # One row per requirement per audit. Preparing twice reconciles
        # rather than duplicating, and this is what makes that safe under
        # a retry rather than merely likely.
        UniqueConstraint("audit_id", "requirement_id", name="uq_audit_item_requirement"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audits.id"), nullable=False, index=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("requirements.id"), nullable=False, index=True
    )
    # --- snapshot: the requirement, as it read at preparation ---------
    reference_code: Mapped[str] = mapped_column(String(50), nullable=False)
    requirement_title: Mapped[str] = mapped_column(String(300), nullable=False)
    framework_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # --- snapshot: the organization's answer to it --------------------
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=True, index=True
    )
    control_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # evidenced | partially_evidenced | needs_review | evidence_insufficient
    # | no_evidence | not_applicable — the vocabulary of
    # app.compliance.control_assessment, not a second scale.
    prepared_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="no_evidence"
    )
    prepared_confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prepared_why: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    prepared_missing: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # [{evidence_id, title, document_href, source_location, evidence_type,
    #   model_confidence}] — enough for the auditor to read the evidence
    # without leaving the audit, and to open the document when they want.
    evidence_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    applicability: Mapped[str | None] = mapped_column(String(30), nullable=True)
    applicability_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # --- the auditor's decision ---------------------------------------
    #
    # null while unreviewed. no_finding | observation | minor | major
    # | critical | needs_evidence. Kept apart from `prepared_status`
    # because "what the evidence shows" and "what the auditor concluded"
    # are different claims by different parties.
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    decision_note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audit_findings.id"), nullable=True
    )
    # --- excluded from this audit, by a person --------------------------
    #
    # Scope is the auditor's to set. A requirement that binds the
    # organization can still be outside the scope of one engagement — a
    # limited internal audit is a legitimate thing to run — and saying so
    # here changes this audit only. The organization's framework
    # applicability is a different question with a different answer, and
    # editing it to shape an audit's scope would quietly rewrite what the
    # company is held to.
    #
    # A reason is required by the service that sets these. "Excluded"
    # with no explanation is the one thing a reader of the report cannot
    # do anything with.
    excluded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    excluded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    exclusion_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class SecurityReview(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One customer's security review: the engagement a questionnaire
    belongs to.

    Originally "Enterprise Sales Security Review", one per Sales
    Opportunity. That module was withdrawn, and because
    `opportunity_id` was a non-null foreign key into it, this table
    became impossible to write to — which is why the Assessments page
    could show a finished customer questionnaire beside "No customer
    security reviews". There was no way to create one.

    So it is compliance-native now. The customer is `customer_name`,
    which is a name rather than a foreign key into a CRM this product
    does not have. `opportunity_id` stays nullable for the rows that
    predate the change; nothing new sets it.

    One review holds many questionnaires — a customer sends a security
    questionnaire, then a privacy one, then an AI governance one, and
    they are one engagement. The link lives on
    `Questionnaire.security_review_id`; `questionnaire_id` below is the
    old single link, kept so existing reviews still resolve.
    """

    __tablename__ = "security_reviews"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # What to call the engagement, and who it is with. The customer is a
    # name because this product has no account model and is not getting
    # one back — see the module docstring.
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    # Legacy. Rows created before the Sales module was withdrawn point at
    # an opportunity; nothing creates one now.
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales_opportunities.id"), nullable=True, unique=True
    )
    # Legacy single link. New reviews hold their questionnaires through
    # `Questionnaire.security_review_id` instead.
    questionnaire_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("questionnaires.id"), nullable=True
    )
    # --- archived, not deleted -----------------------------------------
    #
    # The same separation as everywhere else: where the record lives is
    # not how far its work got. Archiving a review never touches the
    # questionnaires hanging off it.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    archived_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Cross-module hook: set when Opportunity.value is at/above the
    # materiality threshold — clearing then requires this Approval granted.
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("approvals.id"), nullable=True
    )
    # Set once cleared: a compiled trust package (approved Q&A + evidence
    # titles) reusing the Phase 1 File primitive, not a new document path.
    trust_package_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=True
    )
    # in_progress | blocked | cleared
    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    is_deal_blocker: Mapped[bool] = mapped_column(default=True)


class DataTransfer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An international transfer of personal data outside the EEA (GDPR
    Chapter V, Articles 44-49) — optionally tied to the `ProcessingActivity`
    that generates the data being transferred. A `derogation`-based
    transfer auto-creates a linked Compliance `Risk` — see
    app.compliance.service.create_data_transfer."""

    __tablename__ = "data_transfers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    processing_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("processing_activities.id"), nullable=True, index=True
    )
    recipient_name: Mapped[str] = mapped_column(String(300), nullable=False)
    # ISO 3166-1 alpha-2, same convention as LegalEntity.country
    destination_country: Mapped[str] = mapped_column(String(2), nullable=False)
    # The logical identity of a detected transfer, so re-running
    # detection reconciles rather than duplicating. Derived from what the
    # transfer is *about* — this activity, this recipient — never from
    # the wording of the draft. Null on a manually logged transfer,
    # which has no detection to reconcile with.
    source_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Which edge detection followed to find this, so a reviewer can check
    # the inference instead of trusting it.
    detected_from: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Set when something underneath a confirmed transfer moves — a vendor
    # changing country, a new DPA version. Never rewrites the confirmed
    # record; it asks for another look.
    review_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # adequacy_decision | sccs | bcrs | derogation (GDPR Articles 45-49)
    transfer_mechanism: Mapped[str] = mapped_column(String(30), nullable=False)
    safeguards_description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # The vendor this transfer goes to, where one is on file. Linked
    # rather than retyped: the destination country and the DPA already
    # live on the vendor record, and two copies of one fact drift.
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vendors.id"), nullable=True, index=True
    )
    # active | under_review | terminated
    status: Mapped[str] = mapped_column(String(20), default="active")
    # When somebody last confirmed the mechanism still holds. Adequacy
    # decisions get struck down and SCCs get superseded, so "we recorded
    # SCCs once" is not the same claim as "this transfer is covered".
    last_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Cross-module hook: set when transfer_mechanism is "derogation".
    related_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risks.id"), nullable=True
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class FrameworkActivation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Which catalog Frameworks an organization has actually adopted.

    Frameworks and Requirements are global catalog rows, so "GDPR is
    active for us" is not a property of the framework — it is a property
    of the relationship between an organization and that framework, which
    is what this row is. Without it every tenant sees all seven
    frameworks as equally in-scope and no one can say which ones they are
    actually being held to.

    Deactivation is a status change rather than a delete: the controls,
    evidence, assessments and gaps built against a framework must survive
    someone switching it off, or turning it back on would silently lose
    the organization's own work.
    """

    __tablename__ = "framework_activations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "framework_id", name="uq_framework_activation_org_framework"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    framework_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("frameworks.id"), nullable=False, index=True
    )
    # active | inactive
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=utcnow
    )
    activated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class ComplianceGap(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named, explainable deficiency against one Requirement.

    This is the missing link in the spec's chain. Before it, a failed
    assessment produced a Task whose only record of *why* was a free-text
    title, and a requirement with no evidence produced nothing at all —
    so nothing could be traced from "GDPR Article 30 is not satisfied"
    back to what was missing, or forward to the work that fixed it.

    Deliberately factual rather than legal. `summary` states what
    evidence was and was not found; it must not assert that the
    organization is in breach. Absence of evidence in this system is
    evidence of absence *in this system*, not proof of a violation, and
    the copy here is written to keep that distinction visible to whoever
    reads it.
    """

    __tablename__ = "compliance_gaps"
    __table_args__ = (
        # One open gap per requirement per org: re-running an assessment
        # updates the existing finding rather than stacking duplicates of
        # the same deficiency.
        UniqueConstraint(
            "organization_id", "requirement_id", name="uq_compliance_gap_org_requirement"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    framework_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("frameworks.id"), nullable=False, index=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("requirements.id"), nullable=False, index=True
    )
    # Null when the deficiency is that no control is mapped at all.
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=True, index=True
    )
    # no_control | evidence_missing | evidence_partial | assessment_failed
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # open | remediating | resolved
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    # low | medium | high
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    summary: Mapped[str] = mapped_column(String(2000), nullable=False)
    # Populated by generate_remediation — kept separate from `summary` so
    # the finding and the proposed fix stay distinguishable.
    recommendation: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # The structured plan behind that sentence: problem, why, owner,
    # required evidence, checklist. Stored as a whole rather than as
    # columns because it is written once and read once, and every reader
    # wants all of it — see app.compliance.remediation.RemediationPlan.
    remediation_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # The specific conditions the evidence on file does not meet, as the
    # coverage analysis named them at the moment the gap was raised.
    # Stored rather than re-derived so a finding cannot quietly change its
    # own wording underneath somebody who is working on it.
    missing_conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    # The remediation Task, once one has been raised from this gap.
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tasks.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvidenceEvent(UUIDPrimaryKeyMixin, Base):
    """An observation from a connector that may bear on a control.

    The receiving end of continuous monitoring. An event is evidence that
    the compliance position may have moved — never a new position: it
    flags the control for reassessment and lets the deterministic
    assessment decide, so one rule stays in one place rather than letting
    connectors grade controls by a second standard.

    Append-only by design. A connector reporting that something changed
    must never be able to destroy the record of what was true before.
    """

    __tablename__ = "evidence_events"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # Which connector observed it — a key from
    # app.compliance.connectors.CONNECTORS.
    source: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=True, index=True
    )
    # The identifier this observation has in the source system, so a
    # repeated observation can be recognised rather than duplicated.
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Whether this event actually called an assessment into question.
    # Recorded rather than derived, so the trail shows what the event did
    # at the time even if the rules later change.
    triggered_reassessment: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EvidenceSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A proposed link between an uploaded document and a control.

    The whole point of this table is that it is *not* Evidence. A model
    reading a policy and concluding "this demonstrates your breach
    procedure" is a suggestion, and a compliance record built from
    unreviewed suggestions is worth nothing to an auditor — the value of
    the evidence chain comes from a person having stood behind each link.
    So suggestions accumulate here, the assessment ignores them entirely,
    and approving one is what creates the real Evidence row.

    `quoted_passage` and `quote_verified` are the anti-fabrication
    mechanism. The model must quote the passage it relied on, and that
    quote is checked against the extracted document text before the
    suggestion is ever offered for approval. A quote that cannot be found
    in the source is recorded as `unverifiable` and never shown as
    something to approve — which turns "the AI might be making it up"
    from a worry into a measurement.
    """

    __tablename__ = "evidence_suggestions"
    __table_args__ = (
        # One document proposed against one control *for one requirement*
        # is one mapping, however many times the document is analysed.
        #
        # The requirement is part of the identity because it is part of
        # the claim: a policy can evidence one control for Article 32 and
        # for Article 33, and those are different obligations. Leaving it
        # out collapsed them and halved the control's coverage.
        #
        # The passage the model quoted is deliberately *not* part of it —
        # keying on the quote made the identity only as stable as the
        # model, and a re-extraction that phrased the same citation
        # differently read as a second proposal.
        #
        # Two indexes because a null requirement means something: the
        # model named a control without resolving which requirement the
        # passage speaks to, and that is one mapping per document and
        # control.
        Index(
            "uq_suggestion_requirement",
            "organization_id",
            "file_id",
            "control_id",
            "requirement_id",
            unique=True,
            # Both dialects: the tests run on SQLite, which ignores a
            # `postgresql_where` and would silently create a *plain*
            # unique index — rejecting the second requirement for one
            # control, which is exactly what this partial index exists
            # to allow.
            postgresql_where=text("requirement_id IS NOT NULL"),
            sqlite_where=text("requirement_id IS NOT NULL"),
        ),
        Index(
            "uq_suggestion_control_only",
            "organization_id",
            "file_id",
            "control_id",
            unique=True,
            postgresql_where=text("requirement_id IS NULL"),
            sqlite_where=text("requirement_id IS NULL"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id"), nullable=False, index=True
    )
    control_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("controls.id"), nullable=False, index=True
    )
    # proposed | approved | rejected | unverifiable
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    # The model's own stated confidence. Displayed, never used to decide
    # anything — a number a model assigns to its own output is not a
    # measurement, and auto-approving above a threshold would reintroduce
    # exactly the unreviewed evidence this table exists to prevent.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    quoted_passage: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # The logical identity of this proposal: a fingerprint over the
    # section it came from and the passage it quotes, normalized for
    # whitespace and case. See app.core.idempotency.text_fingerprint.
    passage_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Where in the document the passage came from, as the document
    # labels it ("Section 4", "Clause 7.2"). Traceability is the
    # difference between evidence an auditor can follow and a claim
    # they have to take on trust — without it, verifying a mapping
    # means re-reading the whole document.
    source_location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # policy_statement | procedure | record | attestation | other.
    # A policy saying what the organization will do is weaker evidence
    # than a record showing it happened, and the assessment should be
    # able to tell them apart.
    evidence_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # The specific requirement this passage supports. Nullable because
    # a proposal may map to a control without the model resolving which
    # of that control's requirements it speaks to.
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("requirements.id"), nullable=True, index=True
    )
    # Why this suggestion did or did not reach a human. Recorded rather
    # than recomputed, so an auto-approval can always be explained after
    # the fact even if the rules later change.
    routing_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quote_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Set when approved — the Evidence row this became.
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("evidence.id"), nullable=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProcessingActivityAISystem(Base):
    """One processing activity, one AI system it runs through.

    A join table rather than a column because both sides are plural in
    practice: a support activity can run through two assistants, and one
    assistant can serve support and sales. Navigable both ways, which is
    the point — a person looking at an AI system should see which
    processing depends on it without searching for it.
    """

    __tablename__ = "processing_activity_ai_systems"

    processing_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("processing_activities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ProcessingActivityVendor(Base):
    """One processing activity, one processor acting on it."""

    __tablename__ = "processing_activity_vendors"

    processing_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("processing_activities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        primary_key=True,
    )


class PrivacySuggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A privacy record Veyntra thinks exists, that nobody has confirmed.

    Deliberately not a ProcessingActivity and not a DataTransfer. The
    organization's RoPA is a statement it makes to a regulator; a table
    assembled from inference is not that, however good the inference.
    So proposals accumulate here, the privacy screens and the overview
    ignore them as records, and accepting one is what creates the real
    row — with a person's judgement on the parts only a person can
    supply.

    Everything here is drawn from **facts the organization already
    declared**: an AI system's stated purpose, the users it says it
    affects, the data it says it processes, the vendor it names. Nothing
    is inferred about lawfulness. `payload` never carries a lawful basis
    or an Article 9 condition — those are the questions the review
    exists to ask, and pre-filling them would answer the one thing the
    reviewer was brought in for.

    `source_key` is the logical identity of the proposal, so analysing
    the same records again reconciles rather than duplicating. It is
    derived from what the suggestion is *about* — this AI system, this
    vendor pair — and never from the wording of the draft, which would
    make identity only as stable as the phrasing.
    """

    __tablename__ = "privacy_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "kind",
            "source_key",
            name="uq_privacy_suggestion_identity",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # processing_activity | transfer
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # The stable identity of what is being proposed.
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    # proposed | accepted | dismissed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # Which records this was read out of, so a reviewer can check the
    # draft against its sources rather than taking it on trust.
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # The drafted facts. Never a lawful basis; see the class docstring.
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # What the record became once somebody accepted it.
    created_record_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class DpiaRiskSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A risk Veyntra thinks this processing carries, that nobody has
    confirmed.

    Deliberately not a `Risk`. A DPIA's risk register is the controller's
    statement of what it believes threatens data subjects; a list
    assembled from what a record happens to mention is not that. So
    proposals accumulate here, the residual-risk arithmetic ignores them
    entirely, and approving one is what creates the real `Risk` row —
    with the likelihood and impact only a person can supply.

    `source_key` is the logical identity of the proposal, so re-running
    the analysis reconciles rather than duplicating. It is derived from
    what the suggestion is *about* — an AI system being involved, a
    processor being named, no retention being recorded — and never from
    the wording, which would make identity only as stable as the phrasing
    and turn every copy edit into a new unreviewed risk.
    """

    __tablename__ = "dpia_risk_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "dpia_id", "source_key", name="uq_dpia_risk_suggestion_identity"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    dpia_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dpias.id"), nullable=False, index=True
    )
    source_key: Mapped[str] = mapped_column(String(200), nullable=False)
    # suggested | approved | dismissed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="suggested")
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    # The fact on record that produced this, so a reviewer can check the
    # proposal against its source instead of taking it on trust.
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Safeguards the record already shows, offered as a starting point.
    # Never a likelihood or an impact: those are the judgement the review
    # exists to make, and pre-filling them would answer the one question
    # the reviewer was brought in for.
    suggested_safeguards: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # The Risk this became once somebody approved it.
    created_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("risks.id"), nullable=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
