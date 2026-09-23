// Mirrors apps/api/app/identity/schemas.py and app/core/schemas.py.
// Phase 2+ should generate this from the OpenAPI schema instead of hand
// maintaining it (see docs/PLATFORM_ARCHITECTURE.md packages/sdk note).

export type User = {
  id: string;
  email: string;
  full_name: string | null;
  email_verified_at: string | null;
  mfa_enabled: boolean;
};

export type Organization = {
  id: string;
  name: string;
  slug: string;
  notification_webhook_url: string | null;
};

export type ChecklistItem = {
  text: string;
  done: boolean;
};

export type Task = {
  id: string;
  title: string;
  description: string | null;
  module: string;
  status: "open" | "in_progress" | "done" | "cancelled";
  priority: "low" | "normal" | "high" | "urgent";
  assignee_id: string | null;
  due_at: string | null;
  created_by: string | null;
  entity_type: string | null;
  entity_id: string | null;
  checklist: ChecklistItem[];
  created_at: string;
};

export type TaskComment = {
  id: string;
  author_id: string;
  body: string;
  created_at: string;
};

/** A stored file as `/api/v1/files/{id}` returns it. Kept minimal — the
 * only reason to look one up outside the document library is to name it. */
export type FileRecord = {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  classification: string;
  created_at: string;
  download_url: string | null;
};

export type TaskEvidence = {
  id: string;
  file_id: string;
  created_by: string;
  created_at: string;
};

export type TaskActivity = {
  action: string;
  /** The event as a sentence, phrased server-side. Render this — never
   * `action`, which is an internal name. */
  label: string;
  actor_user_id: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  created_at: string;
};

export type Approval = {
  id: string;
  action_type: string;
  risk_class: "read_only" | "low" | "moderate" | "high" | "critical";
  status: "pending" | "approved" | "rejected" | "expired";
  requested_by: string;
  decided_by: string | null;
  decided_at: string | null;
  module: string | null;
  ai_generated: boolean;
  due_at: string | null;
  created_at: string;
};

export type Membership = {
  id: string;
  user_id: string;
  status: string;
  roles: string[];
};

export type LegalEntity = {
  id: string;
  name: string;
  country: string | null;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
};

export type Team = {
  id: string;
  name: string;
  legal_entity_id: string | null;
  is_active: boolean;
  created_at: string;
};

export type Invitation = {
  id: string;
  email: string;
  role_key: string;
  accepted_at: string | null;
  expires_at: string;
};

export type InvitationPreview = {
  organization_name: string;
  email: string;
  role_key: string;
  inviter_name: string | null;
  expires_at: string;
  status: "pending" | "expired" | "revoked" | "accepted";
  account_exists: boolean;
};

// Mirrors app.core.rbac.SYSTEM_ROLE_KEYS.
export const SYSTEM_ROLES: { key: string; name: string }[] = [
  { key: "org_admin", name: "Organization Admin" },
  { key: "executive", name: "Executive" },
  { key: "operations_manager", name: "Operations Manager" },
  { key: "compliance_manager", name: "Compliance Manager" },
  { key: "dpo", name: "DPO" },
  { key: "security_manager", name: "Security Manager" },
  { key: "ai_governance_manager", name: "AI Governance Manager" },
  { key: "sales_manager", name: "Sales Manager" },
  { key: "sales_representative", name: "Sales Representative" },
  { key: "support_manager", name: "Support Manager" },
  { key: "support_agent", name: "Support Agent" },
  { key: "automation_manager", name: "Automation Manager" },
  { key: "legal", name: "Legal" },
  { key: "auditor", name: "Auditor" },
  { key: "employee", name: "Employee" },
  { key: "read_only", name: "Read Only" },
];

export type OnboardingProfile = {
  industry: string | null;
  employee_count_range: string | null;
  selected_goals: string[];
  selected_framework_keys: string[];
  primary_cloud_provider: string | null;
  sales_focus: string | null;
  support_channels: string[];
  current_step: number;
  completed_at: string | null;
};

export const ONBOARDING_GOALS: { key: string; label: string }[] = [
  { key: "improve_compliance", label: "Improve compliance" },
  { key: "improve_security", label: "Improve security" },
  { key: "prepare_for_audit", label: "Prepare for an audit" },
  { key: "govern_ai_systems", label: "Govern our AI systems" },
  { key: "handle_privacy_requests", label: "Handle privacy requests" },
];

export type ReadinessDimension = {
  label: string;
  percent: number;
};

export type ReadinessOpportunity = {
  title: string;
  detail: string;
};

export type Readiness = {
  /** Controls marked implemented. */
  compliance: ReadinessDimension;
  /** Controls with at least one piece of evidence attached — reported
   * separately from `compliance` because a control ticked as implemented
   * but never evidenced is the first thing an auditor finds. */
  evidence_coverage: ReadinessDimension;
  framework_adoption: ReadinessDimension;
  security: ReadinessDimension;
  opportunities: ReadinessOpportunity[];
};

export type Plan = {
  key: string;
  name: string;
  entitlements: Record<string, number | boolean | null>;
};

/** Billing state, kept separate from entitlements so the UI can explain
 * *why* something is unavailable instead of just showing it greyed out. */
export type Subscription = {
  /** What the row says: trialing | active | past_due | trial_expired | canceled. */
  status: string;
  /** What the entitlement service actually resolved. Not always `status` —
   * an expired trial still reads "trialing" in the row until a write
   * touches it, but resolves to "locked" here. Branch on this. */
  access_state: "trialing" | "active" | "past_due" | "locked";
  plan_key: string;
  trial_ends_at: string | null;
  trial_days_remaining: number | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  /** False when the deployment has no Stripe keys — upgrade buttons must
   * say so rather than leading to a dead end. */
  payments_configured: boolean;
  has_payment_method: boolean;
  tax_id: string | null;
};

export type OrganizationPlan = {
  plan_key: string;
  entitlements: Record<string, number | boolean | null>;
  current_users: number;
  /** Null only for organizations created before billing existed. */
  subscription: Subscription | null;
};

export const ENTITLEMENT_LABELS: Record<string, string> = {
  max_users: "Users",
  max_ai_usage_monthly: "AI usage / month",
  max_documents: "Documents",
  max_storage_gb: "Storage (GB)",
  max_frameworks: "Compliance frameworks",
  max_ai_systems: "AI systems",
  max_security_connectors: "Security connectors",
  max_sales_leads: "Sales leads",
  max_outreach_volume_monthly: "Outreach volume / month",
  max_support_conversations_monthly: "Support conversations / month",
  max_automation_runs_monthly: "Automation runs / month",
  max_integrations: "Integrations",
  sso_enabled: "SSO",
  scim_enabled: "SCIM",
  api_enabled: "API access",
  custom_frameworks_enabled: "Custom frameworks",
  trust_center_enabled: "Trust Center",
  advanced_reporting_enabled: "Advanced reporting",
  data_residency_enabled: "Data residency",
};

export type Role = {
  key: string;
  name: string;
  permissions: string[];
};

export type AIProviderStatus = {
  provider_key: string;
  name: string;
  has_adapter: boolean;
  configured: boolean;
  active: boolean;
};

export type Notification = {
  id: string;
  title: string;
  body: string | null;
  link: string | null;
  channels_requested: string[];
  channels_delivered: string[];
  read_at: string | null;
  created_at: string;
};

export type NotificationPreference = {
  channel: string;
  enabled: boolean;
};

export const NOTIFICATION_CHANNELS = [
  "email",
  "slack",
  "teams",
  "webhook",
] as const;

export type ReportType = {
  key: string;
  label: string;
};

export type Report = {
  id: string;
  report_type: string;
  format: string;
  status: string;
  error_message: string | null;
  created_at: string;
};

// spec §65's export list is PDF/DOCX/XLSX/CSV/Secure link; "Secure link"
// is the download-delivery mechanism every format already uses (a
// signed URL from GET /reports/{id}/download), not a 5th format to pick
// here — see apps/api/app/reporting/models.py.
export const REPORT_FORMATS = ["pdf", "docx", "xlsx", "csv"] as const;

export type Recommendation = {
  id: string;
  category: string;
  title: string;
  business_impact: string;
  reason: string;
  sources: string[];
  confidence: string;
  estimated_value: string | null;
  suggested_action: string;
  risk: string;
  required_approval: boolean;
  status: string;
  created_at: string;
};

export type BriefingItem = {
  text: string;
  link: string | null;
};

export type BriefingSection = {
  key: string;
  label: string;
  headline: string;
  items: BriefingItem[];
};

export type Briefing = {
  id: string;
  briefing_date: string;
  sections: BriefingSection[];
  ai_suggestion: string | null;
  created_at: string;
};

export type OrganizationSettings = {
  id: string;
  name: string;
  slug: string;
  notification_webhook_url: string | null;
  deletion_requested_at: string | null;
};

export const BUSINESS_RULE_TRIGGER_TYPES = [
  "new_employee",
  "control_failed",
  "new_vendor",
  "document_uploaded",
  "new_crm_lead",
  "crm_stage_change",
  "security_alert",
  "new_support_ticket",
  "ai_system_registered",
] as const;

export const BUSINESS_RULE_OPERATORS = [
  "==",
  "!=",
  ">",
  ">=",
  "<",
  "<=",
] as const;
export const BUSINESS_RULE_ACTION_TYPES = [
  "notify",
  "require_approval",
] as const;

export type BusinessRule = {
  id: string;
  name: string;
  trigger_type: string;
  condition_field: string;
  condition_operator: string;
  condition_value: string;
  action_type: string;
  action_role_key: string;
  action_risk_class: string | null;
  is_active: boolean;
  created_at: string;
};

export const MEMORY_ENTRY_TYPES = [
  "approved_fact",
  "approved_answer",
  "policy",
  "business_rule",
  "preference",
  "past_decision",
  "workflow_outcome",
] as const;

export type MemoryEntry = {
  id: string;
  entry_type: string;
  content: string;
  provenance_type: string;
  provenance_id: string | null;
  created_by: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
};

export type DocumentStatus =
  "pending" | "processing" | "ready" | "failed" | "unsupported_format";

export type KnowledgeDocument = {
  id: string;
  knowledge_base_id: string;
  file_id: string;
  title: string;
  status: DocumentStatus;
  error: string | null;
  classification: string;
  created_at: string;
};

export type DocumentChunk = {
  id: string;
  chunk_index: number;
  content: string;
  token_count: number;
  section_label: string | null;
  page_number: number | null;
};

/** One source, already resolved to somewhere a person can look.
 *
 * There is no `chunk_id`, `chunk_index` or `score` here, and that is
 * deliberate — the API does not send them. They still exist server-side
 * against the AI request record, where an auditor can trace exactly what
 * the model read; "chunk 5" is simply not something anyone can find in
 * their own copy of a PDF.
 *
 * `document_id` is the sole identifier that survives, purely so clicking
 * a citation can open the document. It is a link target, never text.
 *
 * `href` comes from the server too. This component used to build it, and
 * went on pointing at `/knowledge/<id>` long after that module was
 * withdrawn — the middleware rewrote every such link to a 404. Routes are
 * decided in one place now (app.ai.citations.DOCUMENT_ROUTE); nothing
 * here composes a URL. */
export type Citation = {
  /** "AI Governance Policy — §7 Monitoring", composed server-side. */
  reference: string;
  document_title: string;
  section: string | null;
  page: number | null;
  passage: string;
  source_type: string | null;
  document_id: string;
  /** Render this as-is. Do not build a URL from `document_id`. */
  href: string;
};

/** A value read from Veyntra's compliance records, not from a document.
 *
 * Separate from `Citation` on purpose. "Current status: Needs review" is
 * a determination this product made; no uploaded document says it, and
 * showing it under a document citation would send the reader to argue
 * with a PDF about it. */
export type ComplianceFact = {
  label: string;
  value: string;
  detail: string | null;
};

export type CopilotAnswer = {
  text: string;
  provider: string;
  model: string;
  grounded: boolean;
  facts: ComplianceFact[];
  citations: Citation[];
};

/** A colleague, as a form offers them. Name and email only — enough to
 * pick a person and no more. */
export type OrganizationPerson = {
  id: string;
  full_name: string | null;
  email: string;
};

export type Framework = {
  /** What an audit against this framework covers, in the domains its own
   * requirements fall into. Offered to fill an empty scope box; never
   * applied over something a person wrote. Null for a framework the
   * product has no wording for, including an organization's own. */
  suggested_audit_scope?: string | null;
  id: string;
  key: string;
  name: string;
  description: string | null;
  is_custom: boolean;
};

/** Where a policy sits in its governance lifecycle.
 *
 * `draft`/`published` were the whole vocabulary before, which could not
 * express "somebody owns this, nobody has approved it, and a review is
 * overdue". Detection creates records at `needs_review`. */
export type PolicyStatus =
  | "needs_review"
  | "draft"
  | "approved"
  | "review_due"
  | "superseded"
  | "retired";

/** Whether a review is coming, late, or unscheduled. Derived on read so
 * it cannot go stale against the calendar. */
export type PolicyReviewState =
  "scheduled" | "due_soon" | "overdue" | "not_scheduled" | "not_applicable";

export type Policy = {
  id: string;
  title: string;
  file_id: string | null;
  status: PolicyStatus;
  category: string | null;
  owner_id: string | null;
  version: string | null;
  approved_by: string | null;
  approved_at: string | null;
  effective_date: string | null;
  next_review_at: string | null;
  review_frequency_months: number | null;
  /** True when classification created this record rather than a person. */
  detected_automatically: boolean;
  ai_system_id: string | null;
  created_at: string;
  review_state: PolicyReviewState;
  /** Days until review; negative when overdue. Computed server-side
   * because a `Date.now()` in a render is impure. */
  days_until_review: number | null;
  /** What a person still has to tell us. Empty means complete. */
  missing_governance: string[];
  document_filename: string | null;
  /** Where that document opens — the same Document Detail route the
   * library, the evidence list and a Copilot citation use. */
  document_href: string | null;
  evidence_count: number;
  control_count: number;
  framework_names: string[];
};

export type PolicyVersion = {
  id: string;
  file_id: string;
  filename: string | null;
  version: string | null;
  status: "current" | "superseded";
  approved_at: string | null;
  superseded_at: string | null;
  created_at: string;
};

export type PolicyControl = {
  id: string;
  title: string;
  assessment_status: ControlAssessmentStatus;
  assessment_label: string;
};

export type PolicyDetail = Policy & {
  versions: PolicyVersion[];
  controls: PolicyControl[];
  document_index_status: string | null;
};

export type FrameworkDashboardControl = {
  id: string;
  title: string;
  status: string;
};

export type FrameworkDashboardRequirement = {
  id: string;
  reference_code: string;
  title: string;
  controls: FrameworkDashboardControl[];
};

export type FrameworkDashboard = {
  framework: Framework;
  requirements: FrameworkDashboardRequirement[];
  coverage_percent: number;
};

export type Requirement = {
  id: string;
  reference_code: string;
  title: string;
  description: string | null;
};

export type ControlStatus =
  "not_started" | "in_progress" | "implemented" | "needs_review";

export type Control = {
  id: string;
  title: string;
  description: string | null;
  /** The organization's own taxonomy, not a fixed enum — an enum of ours
   * would fit nobody and need extending forever. */
  category: string | null;
  priority: "low" | "medium" | "high";
  /** Workflow state only — has anyone declared this control
   * operational. Secondary metadata: never the primary badge, and not
   * the same question as whether the evidence supports it. */
  status: ControlStatus;
  /** The derived assessment, from the one shared service. This is what
   * every screen shows. See apps/api/app/compliance/control_assessment.py. */
  /** What the user acts on: the human verdict where one exists, the
   * derived assessment otherwise. Decided once, server-side. */
  assessment_status: ControlAssessmentStatus;
  assessment_label: string;
  /** What Veyntra derived. Never overwritten by a human decision. */
  ai_assessment_status: ControlAssessmentStatus;
  ai_assessment_label: string;
  /** The human verdict, if one was recorded. */
  human_assessment_status: ControlAssessmentStatus | null;
  human_assessment_label: string | null;
  human_reviewed_at: string | null;
  human_reviewed_by: string | null;
  /** Whether a person still has to decide. Drives the Review Center. */
  review_required: boolean;
  /** How much supporting evidence exists — a measurement, never part of
   * the status. Rendered separately for that reason. */
  coverage_percent: number;
  evidence_count: number;
  applicable_requirement_count: number;
  mapped_requirement_count: number;
  owner_id: string | null;
  created_at: string;
};

/** Each state is a range of `coverage_percent`, not an independent
 * judgement — the server derives one from the other, so
 * `partially_evidenced` at 0% cannot occur:
 *
 *   evidenced             100%
 *   partially_evidenced   >0% and <100%
 *   evidence_insufficient evidence exists, 0% demonstrated, cause known
 *   needs_review          evidence exists, 0% demonstrated, cause unclear
 *   no_evidence           no evidence items
 *   not_applicable        no applicable requirements */
export type ControlAssessmentStatus =
  | "evidenced"
  | "partially_evidenced"
  | "evidence_insufficient"
  | "needs_review"
  | "no_evidence"
  | "not_applicable"
  // Human verdicts. Same vocabulary because they answer the same
  // question — what state is this control in — and a reader should not
  // have to learn which scale a word came from.
  | "passed"
  | "failed"
  | "partially_implemented";

/** Whether a requirement binds this organization, and how sure we are.
 * Only `not_applicable` is excluded from coverage and readiness. */
export type RequirementApplicabilityStatus =
  "applicable" | "likely_applicable" | "needs_review" | "not_applicable";

export type RequirementCoverageLine = {
  requirement_id: string;
  reference_code: string;
  title: string;
  framework_key: string;
  applicability: RequirementApplicabilityStatus;
  applicability_reason: string;
  coverage:
    "satisfied" | "deficient" | "uncertain" | "no_evidence" | "not_applicable";
  missing_conditions: string[];
};

export type ControlAssessment = {
  id: string;
  status: "pass" | "fail" | "partial" | "not_assessed";
  notes: string | null;
  assessed_by: string | null;
  created_at: string;
};

export type EvidenceMapping = {
  evidence_id: string;
  control_id: string;
  control_title: string;
  source_location: string | null;
  evidence_type: string | null;
  quoted_passage: string | null;
  confidence: number | null;
  mapped_by: "auto" | "human" | "manual";
};

/** One source document with everything it evidences. The mappings are
 * unchanged in the database — this is presentation: one document, many
 * statements, many controls. */
export type GroupedEvidence = {
  file_id: string;
  filename: string;
  /** The document name, and where it opens. Composed server-side so this
   * list, the document library and a Copilot citation all point at the
   * one Document Detail page. Null when it has no indexed document. */
  title: string;
  document_href: string | null;
  document_type: string | null;
  document_domain: string | null;
  processing_status: string;
  evidence_count: number;
  control_count: number;
  mappings: EvidenceMapping[];
};

export type EvidenceProvenance = {
  evidence_id: string;
  file_id: string;
  filename: string;
  title: string;
  /** Where the document this came from opens. Null when it has no
   * indexed document, so the filename renders without a link rather than
   * with one that 404s. */
  document_href: string | null;
  /** Null for evidence attached by hand — there is no citation behind
   * it, and inventing one would misrepresent how it got here. */
  source_location: string | null;
  evidence_type: string | null;
  model_confidence: number | null;
  quoted_passage: string | null;
  mapped_by: "auto" | "human" | "manual";
};

/** What the evidence on file supports. Derived on read, so it cannot go
 * stale against the evidence it describes. */
export type ControlAssessmentView = {
  control_id: string;
  status: ControlAssessmentStatus;
  confidence: number;
  why: string;
  missing: string | null;
  evidence: EvidenceProvenance[];
  requirement_codes: string[];
  /** Per requirement, so the percentage can be checked against the same
   * list rather than taken on trust. */
  requirements: RequirementCoverageLine[];
  label: string;
  ai_status: ControlAssessmentStatus;
  ai_label: string;
  human_status: ControlAssessmentStatus | null;
  human_label: string | null;
  effective_status: ControlAssessmentStatus;
  review_required: boolean;
  recorded_by: string | null;
  applicable_count: number;
  satisfied_count: number;
  /** The last human verdict. Shown beside the derived one, never
   * replaced by it. */
  recorded_status: string | null;
  recorded_at: string | null;
};

export type ControlDetail = Control & {
  requirements: Requirement[];
  /** Human-recorded verdicts, oldest to newest. */
  assessments: ControlAssessment[];
  evidence: Evidence[];
  /** What the evidence on file supports. Null only if the server could
   * not derive one. */
  assessment: ControlAssessmentView | null;
};

export type Evidence = {
  id: string;
  file_id: string;
  control_id: string | null;
  vendor_id: string | null;
  title: string;
  valid_until: string | null;
  created_at: string;
};

export type Risk = {
  id: string;
  title: string;
  description: string | null;
  category: string;
  likelihood: "low" | "medium" | "high";
  impact: "low" | "medium" | "high";
  status: "open" | "mitigated" | "accepted";
  control_id: string | null;
  /** What the risk is about, so the register does not force every reader
   * to re-derive it from the title. */
  ai_system_id: string | null;
  dpia_id: string | null;
  /** Risk remaining after mitigating controls. Null until someone has
   * actually reassessed — deliberately not defaulted to the inherent
   * rating, so "not yet reassessed" stays visible. */
  residual_likelihood: "low" | "medium" | "high" | null;
  residual_impact: "low" | "medium" | "high" | null;
  owner_id: string | null;
  created_at: string;
};

export type AIRiskClassification =
  "minimal" | "limited" | "high" | "unacceptable";
export type AISystemStatus = "in_review" | "approved" | "rejected" | "retired";

export type AISystem = {
  id: string;
  name: string;
  vendor: string | null;
  vendor_id: string | null;
  purpose: string;
  description: string | null;
  /** The specific model, recorded separately from the vendor: "Anthropic"
   * and "claude-opus-4" are different facts, and an inventory that
   * conflates them cannot answer which model is actually in production. */
  model_name: string | null;
  internal_users: string[];
  /** People affected by the system without using it — the group the EU AI
   * Act cares most about, and the one an owner-only record loses. */
  affected_users: string[];
  processed_data: { name: string; classification: string }[];
  business_owner_id: string | null;
  technical_owner_id: string | null;
  governance_owner_id: string | null;
  last_reviewed_at: string | null;
  risk_classification: AIRiskClassification;
  /** Whether post-market obligations have begun. A high-risk system in
   * development is subject to the design-time articles and not yet to
   * Art. 72. */
  deployment_status: "development" | "pilot" | "production" | "retired";
  status: AISystemStatus;
  owner_id: string | null;
  approval_id: string | null;
  created_at: string;
};

export type AIAssessment = {
  id: string;
  ai_system_id: string;
  status: "pass" | "fail" | "partial" | "not_assessed";
  notes: string | null;
  assessed_by: string | null;
  created_at: string;
};

export type AISystemDetail = AISystem & {
  assessments: AIAssessment[];
};

export type LegalBasis =
  | "consent"
  | "contract"
  | "legal_obligation"
  | "vital_interests"
  | "public_task"
  | "legitimate_interests";

export type ProcessingActivity = {
  id: string;
  name: string;
  purpose: string;
  legal_basis: LegalBasis;
  data_categories: string[];
  data_subjects: string;
  retention_period: string;
  status: "active" | "archived";
  owner_id: string | null;
  created_at: string;
};

export type DPIARiskLevel = "low" | "medium" | "high";
/** The DPIA lifecycle, in order:
 *
 *   screening → draft → in_review → approved → completed
 *
 * `not_required` sits off it entirely — somebody screened this and
 * concluded no assessment is needed, which is a finished record rather
 * than a stage of one. It used to be stored as `approved`, which read on
 * every list as though the DPIA had been carried out and signed off. */
export type DPIAStatus =
  | "screening"
  | "not_required"
  | "draft"
  | "in_review"
  | "approved"
  | "completed"
  | "rejected";

export type DPIA = {
  id: string;
  processing_activity_id: string | null;
  ai_system_id: string | null;
  title: string;
  /** Null until somebody has assessed it. A DPIA with no risks raised
   * against it has no inherent level — the column used to default to
   * "low", which asserted an assessment nobody had performed. */
  risk_level: DPIARiskLevel | null;
  status: DPIAStatus;
  findings: string | null;
  /** Article 35(7)'s required content, one field per section so a
   * reviewer can see which parts were never addressed. */
  processing_description: string | null;
  necessity_assessment: string | null;
  proportionality_assessment: string | null;
  consultation_notes: string | null;
  /** Derived from the risks raised against this DPIA. Null until they
   * have been reassessed — a DPIA must not reach "low" by inaction. */
  residual_risk_level: DPIARiskLevel | null;
  screening_outcome: string | null;
  /** Article 35(2). Null means nobody has resolved it, which is not the
   * same as a recorded "no consultation was carried out". */
  consultation_performed: boolean | null;
  completed_at: string | null;
  /** Set when the processing under a completed DPIA has moved on. A
   * recommendation to reassess, never an edit to what was concluded. */
  review_reason: string | null;
  approval_id: string | null;
  owner_id: string | null;
  created_at: string;
};

export type DSARRequestType =
  "access" | "deletion" | "rectification" | "portability";
export type DSARStatus = "received" | "in_progress" | "fulfilled" | "rejected";

export type DSAR = {
  id: string;
  requester_name: string;
  requester_email: string;
  request_type: DSARRequestType;
  status: DSARStatus;
  /** The gate on disclosure. Export is refused server-side until this
   * reads "verified" — answering an unverified request hands one
   * person's data to whoever asked. */
  verification_status: "pending" | "verified" | "failed";
  verification_method: string | null;
  /** What was actually done to establish identity. The method is a
   * category; this is the evidence behind it. */
  verification_notes: string | null;
  verified_at: string | null;
  /** Where the request actually is. "In progress" covers everything
   * between logging a request and sending it, which is exactly the span
   * somebody needs to navigate. */
  phase: DsarPhase;
  blocked_reason: string | null;
  scope_confirmed_at: string | null;
  discovery_findings: DsarDiscovery | null;
  discovery_run_at: string | null;
  export_generated_at: string | null;
  /** When the request arrived — not when somebody logged it. The
   * response clock runs from receipt. */
  received_at: string | null;
  /** One month from receipt, plus any recorded extension. */
  due_at: string;
  /** The deadline before any extension, so the screen can say
   * "extended to" rather than showing a later date as the deadline. */
  base_due_at: string | null;
  extension_months: number;
  extension_reason: string | null;
  extension_granted_at: string | null;
  /** Derived server-side on read. A stored "overdue" is wrong the
   * moment the clock passes it and nobody has run a job. */
  days_remaining: number | null;
  overdue: boolean;
  due_soon: boolean;
  deadline_label: string | null;
  fulfilled_at: string | null;
  notes: string | null;
  assigned_to: string | null;
  created_at: string;
};

/** Where the data subject appears, as counts and record references — not
 * the records themselves, so the discovery result does not become a
 * second uncontrolled copy of the personal data it located. */
export type DsarDiscovery = {
  email: string;
  sources: { source: string; matches: number; record_ids: string[] }[];
  total_matches: number;
  /** Says what was *not* searched, so a clean result is not read as
   * "there is nothing to disclose". */
  coverage_note: string;
};

export type DsarPhase =
  | "received"
  | "identity_verification"
  | "scope_review"
  | "discovery"
  | "response_review"
  | "ready_to_respond"
  | "completed"
  | "blocked";

/** What Veyntra can actually do about a source.
 *
 * Deliberately separate from relevance. "Searchable" means a real
 * adapter on a real connection — never that a table happens to sit in
 * our own database. */
export type DsarSearchCapability =
  | "searchable"
  | "manual_follow_up"
  | "processor_follow_up"
  | "not_connected"
  | "unsupported";

/** One of the systems behind a processing activity.
 *
 * A RoPA entry is compliance context, not a database: it says the
 * person's data may be in the systems used for that processing, and
 * these are those systems. */
export type DsarPotentialSource = {
  name: string;
  kind: "ai_system" | "vendor" | "named_processor";
  capability: DsarSearchCapability;
  detail: string;
};

/** One candidate source, its ranking, and the decision about it.
 *
 * `relevance` ranks; it never filters. A source ranked "low" is still
 * listed and still includable — a filter that is wrong costs a response
 * its completeness, where a ranking that is wrong costs a click.
 *
 * Relevance is computed from the requester and the register alone. It is
 * never a function of `search_capability`: how cheaply Veyntra can query
 * something says nothing about whether this person's data is there. */
export type DsarScopeSource = {
  id: string;
  source_key: string;
  kind: "processing_activity" | "ai_system" | "vendor" | "named_processor" | "internal" | "manual";
  name: string;
  reason: string;
  relevance: "high" | "possible" | "low";
  relevance_reason: string | null;
  linked_systems: string[];
  potential_sources: DsarPotentialSource[];
  search_capability: DsarSearchCapability;
  /** null means nobody has decided yet, which is not the same as
   * excluded. */
  included: boolean | null;
  added_by_user: boolean;
  record_id: string | null;
};

/** Five states, because they mean five different things. Only
 * `searched_none` is evidence of absence; the rest are kinds of
 * "unknown". */
export type DsarSearchState =
  | "not_searched"
  | "searched_none"
  | "searched_found"
  | "search_failed"
  | "manual_follow_up"
  | "processor_follow_up"
  | "not_connected";

export type DsarReviewDecision = "include" | "exclude" | "redact" | "needs_review";

export type DsarDiscoveredItem = {
  id: string;
  source_key: string;
  source_name: string;
  search_state: DsarSearchState;
  matches: number;
  record_ids: string[];
  state_detail: string | null;
  review_decision: DsarReviewDecision;
  review_reason: string | null;
  reviewed_at: string | null;
  /** What Veyntra noticed for a person to look at. Flags, never
   * exemption decisions. */
  sensitivity_flags: string[];
  task_id: string | null;
};

export type DsarDiscoveryPlan = {
  total: number;
  connected: number;
  manual: number;
  excluded: number;
  manual_sources: string[];
  connected_sources: string[];
};

export type DsarBlocker = { code: string; message: string; anchor: string };

export type DsarWorkflowState = {
  phase: DsarPhase;
  phase_label: string;
  next_action: { label: string; detail: string; anchor: string } | null;
  blockers: DsarBlocker[];
  scope_total: number;
  scope_included: number;
  scope_undecided: number;
  discovered_total: number;
  needs_review: number;
  manual_follow_ups: number;
  open_follow_ups: number;
  package_status: string | null;
};

export type DsarSourceLine = {
  name: string;
  state: DsarSearchState;
  state_label: string;
  matches: number;
  decision: DsarReviewDecision;
  decision_reason: string | null;
  flags: string[];
};

export type DsarResponsePreview = {
  dsar_id: string;
  requester_name: string;
  requester_email: string;
  request_type: string;
  received_at: string;
  due_at: string;
  identity_method: string | null;
  identity_notes: string | null;
  identity_verified_at: string | null;
  identity_verified_by: string | null;
  letter: string;
  included: DsarSourceLine[];
  excluded: DsarSourceLine[];
  redacted: DsarSourceLine[];
  not_searched: DsarSourceLine[];
  follow_ups: string[];
  blockers: string[];
  coverage: DsarCoverage | null;
  /** Fingerprint of the response's content. Sent back on approval so a
   * request that moved in between is refused rather than absorbed. */
  digest: string;
};

/** What the search actually covered.
 *
 * "Searched and empty" and "not searched at all" are counted separately:
 * a package that adds them together claims a completeness it does not
 * have. */
export type DsarCoverage = {
  scope_confirmed: number;
  automatically_searched: number;
  manual_completed: number;
  outstanding: number;
  searched_no_matches: number;
  records_found: number;
  complete: boolean;
};

export type DsarResponsePackage = {
  id: string;
  version: number;
  status: "draft" | "approved" | "sent";
  source_digest: string;
  approved_at: string | null;
  sent_at: string | null;
};

/** One place a request may reach, and why it is on the list.
 *
 * Read out of the privacy graph — not out of a search. Nothing here is
 * personal data; these are systems, not findings. */
export type DsarLocation = {
  kind: "processing_activity" | "ai_system" | "vendor" | "named_processor";
  name: string;
  reason: string;
  record_id: string | null;
};

export type DsarScope = {
  locations: DsarLocation[];
  /** "Nothing is recorded to search" — which is not the same claim as
   * "this person has no data", and only the first is supportable. */
  nothing_recorded: boolean;
};

export type AIIncidentStatus = "open" | "investigating" | "resolved" | "closed";

export type AIIncident = {
  id: string;
  ai_system_id: string;
  title: string;
  description: string | null;
  severity: Severity;
  status: AIIncidentStatus;
  related_risk_id: string | null;
  related_task_id: string | null;
  owner_id: string | null;
  created_at: string;
};

export type VendorStatus = "active" | "under_review" | "offboarded";

export type Vendor = {
  id: string;
  name: string;
  description: string | null;
  category: string;
  website: string | null;
  contact_email: string | null;
  risk_tier: Severity;
  status: VendorStatus;
  dpa_status: "pending" | "signed" | "not_required";
  /** The review decision, separate from the operational `status`: a
   * vendor can be operationally active while its review is conditional.
   * "Conditionally approved" is the state real reviews usually end in —
   * without it a reviewer must either block a vendor the business needs
   * or approve outright and lose the caveat. */
  approval_state:
    | "not_submitted"
    | "pending"
    | "approved"
    | "conditionally_approved"
    | "rejected";
  approval_conditions: string | null;
  approval_decided_at: string | null;
  owner_id: string | null;
  compliance_owner_id: string | null;
  created_at: string;
};

export type VendorReviewCheck = {
  check: string;
  outcome: "satisfied" | "missing" | "unanswered";
  detail: string;
};

export type VendorAssessment = {
  id: string;
  vendor_id: string;
  /** Privacy and security reviews reach different conclusions about the
   * same vendor; neither stands in for the other. */
  assessment_type: "privacy" | "security" | "general";
  risk_conclusion: Severity;
  notes: string | null;
  /** Which checks ran and what each concluded, so a reader can see the
   * gaps that drove the rating rather than taking it on trust. */
  findings: {
    checks?: VendorReviewCheck[];
    outstanding?: number;
    coverage_note?: string;
  } | null;
  related_risk_id: string | null;
  assessed_by: string | null;
  created_at: string;
};

export type VendorDetail = Vendor & {
  assessments: VendorAssessment[];
  evidence: Evidence[];
};

export type QuestionnaireSource = "customer_provided" | "internal_template";
/** How far the work got — never where the record lives.
 *
 * Derived by the server from the answers themselves, so every screen
 * reports the same thing. `completed` is the exception: it means the
 * questionnaire went back to the customer, which reading the answers
 * cannot tell us, so a person sets it.
 *
 * Orthogonal to `archived_at`. "Archived · Ready to share" is a valid
 * and common combination. */
export type QuestionnaireStatus =
  | "needs_setup"
  | "draft"
  | "in_review"
  | "ready_to_share"
  | "completed";

/** One reason a questionnaire cannot go back to the customer.
 *
 * `code` is what a row keys its action off — `customer_required` puts a
 * "Set customer" button on it. `message` is the sentence to show, and it
 * is the same sentence the API returns when it refuses the transition. */
export type ReadinessBlocker = {
  code:
    | "customer_required"
    | "review_required"
    | "no_questions"
    | "unanswered_questions"
    | "needs_review";
  message: string;
};

/** Whether a questionnaire can be shared, decided by the server.
 *
 * The rule lives in `app/compliance/questionnaire_status.py` and is the
 * same one that writes the stored status and refuses the transition. The
 * UI renders this; it never recomputes it from `progress`, which is how
 * a detail page came to say "Ready to share" over a record stored as
 * something else. */
export type QuestionnaireReadiness = {
  ready: boolean;
  blockers: ReadinessBlocker[];
  /** Something no amount of answering will fix — no customer, or no
   * review to belong to. */
  needs_setup: boolean;
};

/** What is left to do, in the four states work moves through.
 *
 * `percent_complete` counts approved answers only. A drafted answer
 * nobody has read is not progress towards sending the questionnaire
 * back, and counting it as such would say "nearly done" when nobody has
 * checked anything. */
export type QuestionnaireProgress = {
  total: number;
  approved: number;
  needs_review: number;
  draft: number;
  unanswered: number;
  percent_complete: number;
  ready_to_share: boolean;
};

/** One line of an import, and what Veyntra made of it.
 *
 * `possible_duplicate` is importable on purpose: it is the reader's
 * decision, which is the whole reason it is flagged rather than merged.
 * Silently collapsing two similarly-worded questions would drop one a
 * customer actually asked. */
export type AnalyzedLine = {
  text: string;
  outcome: "new" | "duplicate" | "possible_duplicate" | "unparsed";
  category: string;
  /** The question already on the questionnaire this one resembles. */
  matches: string | null;
  similarity: number;
  /** Why a line was not read as a question, in words worth acting on. */
  reason: string | null;
  importable: boolean;
};

/** What an import would do, before anything is created. */
export type ImportAnalysis = {
  headline: string;
  detected: number;
  new: number;
  duplicates: number;
  possible_duplicates: number;
  unparsed: number;
  lines: AnalyzedLine[];
  supported_formats: string[];
  source_filename: string | null;
};

/** What the import actually did. */
export type ImportResult = {
  created: number;
  duplicates_skipped: number;
  unparsed: number;
  /** True while answers are still being drafted in the background. */
  drafting: boolean;
  status_before: string | null;
  status_after: string | null;
};

export type Questionnaire = {
  /** Whether this may be permanently deleted, decided by the server from
   * what has actually happened to it — never by the client from a status
   * field. The menu is drawn from it; the endpoint checks again anyway,
   * so a stale list cannot talk anybody into destroying an approval. */
  can_delete: boolean;
  /** Why not, in words meant for the person who clicked Delete. */
  delete_blocked_reason: string | null;
  archived_at: string | null;
  archived_by: string | null;
  id: string;
  title: string;
  /** Who is asking, and by when. */
  customer_name: string | null;
  due_at: string | null;
  source: QuestionnaireSource;
  status: QuestionnaireStatus;
  /** The words for that status, chosen server-side. */
  status_label: string;
  readiness: QuestionnaireReadiness;
  /** The title reads like one of the questions rather than the name of
   * the questionnaire. Flagged so it can be offered for rename — never
   * acted on, because a plausible replacement is still a guess. */
  title_looks_like_a_question: boolean;
  opportunity_id: string | null;
  owner_id: string | null;
  created_at: string;
  progress: QuestionnaireProgress;
};

export type QuestionCategory =
  "compliance" | "security" | "privacy" | "ai_governance";

export type QuestionnaireQuestion = {
  id: string;
  questionnaire_id: string;
  text: string;
  category: QuestionCategory;
  order_index: number;
  created_at: string;
};

/** `missing` is gone: it described the row being empty rather than what
 * the reader has to do about it, and the screen printed it verbatim. */
export type AnswerStatus =
  "unanswered" | "draft" | "needs_review" | "approved" | "rejected";
export type AnswerSourceType =
  "ai_suggested" | "manual" | "reused_from_library" | null;

/** One source behind a drafted answer, already resolved to something a
 * person can look up — never a chunk id. Same shape the Copilot uses. */
export type AnswerCitation = {
  reference: string;
  document_title: string;
  section: string | null;
  page: number | null;
  passage: string;
  source_type: string | null;
  document_id: string;
  href: string | null;
};

export type QuestionnaireAnswer = {
  id: string;
  question_id: string;
  answer_text: string | null;
  status: AnswerStatus;
  /** The word the screen shows for that status, phrased server-side. */
  status_label: string;
  source_type: AnswerSourceType;
  citations: AnswerCitation[] | null;
  /** What the model said about its own output. Shown, never used alone
   * to decide whether a person must look at it. */
  confidence: number | null;
  /** Why this needs a human, in words they can act on. */
  review_reason: string | null;
  /** Whether Approve is available at all, and why not when it is not —
   * so a disabled button can explain itself. */
  can_approve: boolean;
  approval_blocked_reason: string | null;
  approved_by: string | null;
  approved_at: string | null;
  evidence_id: string | null;
  control_id: string | null;
  answered_by: string | null;
  created_at: string;
};

export type QuestionnaireQuestionDetail = QuestionnaireQuestion & {
  answer: QuestionnaireAnswer | null;
};

export type QuestionnaireDetail = Questionnaire & {
  questions: QuestionnaireQuestionDetail[];
  /** The formats a questionnaire file can be imported from, named by the
   * server so the UI offers what actually works. */
  supported_import_formats: string[];
  /** The customer engagement this belongs to, when a customer sent it.
   * Null for internal assessments — those are nobody's engagement but
   * our own, and that distinction is the point of the field. */
  security_review_id: string | null;
  security_review_title: string | null;
  security_review_href: string | null;
  /** The engagement's own state. Two dimensions, kept apart: how far the
   * review got, and whether it is still open. "Ready to share" and
   * "Archived" together is what a finished engagement looks like. */
  security_review_status: string | null;
  security_review_status_label: string | null;
  security_review_archived_at: string | null;
  /** Set only for a customer questionnaire with no customer recorded on
   * it, and therefore no engagement. Most of these predate the column.
   * The suggestion is what the title appears to say — offered to a
   * person, never applied on its own. */
  needs_customer: boolean;
  suggested_customer: string | null;
  suggested_customer_reason: string | null;
};

/** What naming a customer did. */
export type CustomerLinkResult = {
  questionnaire_id: string;
  customer_name: string;
  security_review_id: string | null;
  security_review_title: string | null;
  review_created: boolean;
};

/** A questionnaire the reconciliation would not name a customer for. */
export type NeedsCustomer = {
  questionnaire_id: string;
  title: string;
  archived: boolean;
  suggested_customer: string | null;
  reason: string | null;
};

/** What a customer-review reconciliation linked, and what it left alone. */
export type ReviewBackfillReport = {
  examined: number;
  linked: number;
  linked_from_title: number;
  reviews_created: number;
  reviews_archived: number;
  unnamed: number;
  suggested: number;
  already_linked: number;
  needs_customer: NeedsCustomer[];
  dry_run: boolean;
};

export type AuditStatus = "planned" | "in_progress" | "completed";

export type Audit = {
  finding_count: number;
  /** Whether this may be permanently deleted, decided by the server from
   * what has actually happened to it — never by the client from a status
   * field. The menu is drawn from it; the endpoint checks again anyway,
   * so a stale list cannot talk anybody into destroying an approval. */
  can_delete: boolean;
  /** Why not, in words meant for the person who clicked Delete. */
  delete_blocked_reason: string | null;
  archived_at: string | null;
  archived_by: string | null;
  id: string;
  title: string;
  framework_id: string | null;
  /** The framework as it was named when the audit ran, so a completed
   * audit still says what it was against after a catalog rename. */
  framework_name: string | null;
  /** Set when a colleague ran the audit, so the trail carries a real
   * identity. Null for an external firm, where the name is genuinely all
   * we have — the two cases are distinguishable rather than flattened. */
  auditor_user_id: string | null;
  auditor_name: string | null;
  /** internal | external | null when nobody has established which.
   * Never inferred from whether an account is linked. */
  auditor_type: "internal" | "external" | null;
  auditor_organization: string | null;
  /** What the engagement covers, in the auditor's words. No amount of
   * data infers this — two ISO 42001 audits can scope different systems. */
  scope: string | null;
  status: AuditStatus;
  status_label: string;
  scheduled_at: string | null;
  /** The timestamps are the state, not decoration beside it. A planned
   * audit has neither; one in progress has a start and no completion.
   * They move with `status` and never contradict it — which they did,
   * which is why an audit could read "Planned · Completed 8/26/2026". */
  started_at: string | null;
  completed_at: string | null;
  prepared_at: string | null;
  owner_id: string | null;
  created_at: string;
  progress: AuditProgress;
};

/** How far through the scope the auditor is.
 *
 * Review progress, not compliance readiness. "12 of 18 reviewed" and
 * "67% evidenced" are different numbers about different things. */
export type AuditProgress = {
  scoped: number;
  reviewed: number;
  unreviewed: number;
  percent_reviewed: number;
  no_finding: number;
  observations: number;
  minor: number;
  major: number;
  critical: number;
  needs_evidence: number;
  open_findings: number;
  ready_for_verification: number;
  evidence_reviewed: number;
  remediation_completed: number;
  /** Scope, so "3 requirements" is never left unexplained. */
  not_applicable: number;
  excluded: number;
  /** Remediation is the work attached to a finding, not the finding.
   * Collapsing them is why a completed audit read "3 open findings" when
   * all three were observations with fixes under way. */
  remediation_open: number;
  remediation_in_progress: number;
  remediation_ready: number;
  remediation_closed: number;
  accepted_risk: number;
};

/** One requirement, and why it is or is not in this audit. */
export type AuditScopeLine = {
  requirement_id: string | null;
  reference_code: string;
  title: string;
  disposition: "included" | "not_applicable" | "excluded";
  reason: string | null;
  excluded_at: string | null;
};

export type AuditScope = {
  framework_name: string | null;
  included: number;
  not_applicable: number;
  excluded: number;
  lines: AuditScopeLine[];
};

/** Fixing is not closing. The team can reach `ready_for_verification`;
 * only an auditor reaches `closed`, and only with a note. */
export type FindingStatus =
  | "open"
  | "remediation_in_progress"
  | "ready_for_verification"
  | "closed"
  | "accepted_risk";

/** What the auditor concluded about one scoped requirement. */
export type AuditDecision =
  | "no_finding"
  | "observation"
  | "minor"
  | "major"
  | "critical"
  | "needs_evidence";

/** One piece of evidence as the audit shows it. No chunk identifiers —
 * `source_location` is the readable place and `document_href` opens it. */
export type AuditEvidence = {
  evidence_id: string | null;
  file_id: string | null;
  title: string;
  document_href: string | null;
  source_location: string | null;
  evidence_type: string | null;
  model_confidence: number | null;
};

/** One scoped requirement, with everything needed to decide on it.
 *
 * Everything prefixed `prepared_` is the snapshot taken when the audit
 * was prepared — what was true when the auditor looked. */
export type AuditItem = {
  id: string;
  requirement_id: string;
  reference_code: string;
  requirement_title: string;
  framework_key: string | null;
  control_id: string | null;
  control_title: string | null;
  prepared_status: string;
  prepared_status_label: string;
  prepared_confidence: number;
  prepared_why: string | null;
  prepared_missing: string | null;
  evidence_snapshot: AuditEvidence[];
  /** Attached since the audit was prepared — shown as new rather than
   * folded into the snapshot. */
  new_evidence: AuditEvidence[];
  applicability: string | null;
  applicability_reason: string | null;
  /** What the auditor concluded. Kept apart from `prepared_status`,
   * which is what Veyntra makes of the evidence — two claims by two
   * parties, and a screen that shows them as adjacent unlabelled badges
   * asks the reader to work out which is which. */
  decision: AuditDecision | null;
  decision_label: string | null;
  decision_note: string | null;
  decided_at: string | null;
  finding_id: string | null;
  finding_status: FindingStatus | null;
  finding_status_label: string | null;
  finding_severity: Severity | null;
  remediation_task_id: string | null;
  /** Excluded from this audit only. The organization's framework
   * applicability is a different question and is left as it was. */
  excluded_at: string | null;
  exclusion_reason: string | null;
  /** Where the requirement stands today, against the snapshot the
   * auditor assessed. Null when nothing has moved. */
  current_status: string | null;
  current_status_label: string | null;
  section: string;
};

export type AuditSection = {
  key: string;
  label: string;
  items: AuditItem[];
};

export type AuditDecisionResult = {
  item: AuditItem;
  finding: AuditFinding | null;
  finding_created: boolean;
  /** True when the finding was attached to remediation that already
   * existed for this requirement rather than opening a second task. */
  remediation_reused: boolean;
  related_task_id: string | null;
};

export type AuditPreparation = {
  applicable: number;
  satisfied: number;
  needs_review: number;
  gaps: number;
  evidence: number;
  open_remediation: number;
  created: number;
  updated: number;
  not_applicable: number;
};

export type AuditFinding = {
  id: string;
  audit_id: string;
  audit_item_id: string | null;
  control_id: string | null;
  /** Copied when the finding was raised, so it keeps reading correctly
   * after the catalog is renamed or the control retired. */
  requirement_id: string | null;
  requirement_code: string | null;
  control_title: string | null;
  title: string;
  description: string | null;
  severity: Severity;
  status: FindingStatus;
  status_label: string;
  /** What the auditor was looking at when they raised it. */
  evidence_snapshot: AuditEvidence[];
  related_task_id: string | null;
  verified_by: string | null;
  verified_at: string | null;
  verification_note: string | null;
  created_at: string;
  /** Set when the auditor replaced this conclusion with a later one on
   * the same requirement. The finding keeps its severity, its status and
   * its verification; it stops counting as a live finding. Without this,
   * a completed audit read "18 conclusions, 19 findings" and nothing on
   * screen accounted for the extra one. */
  superseded_at: string | null;
  superseded_by_id: string | null;
  superseded_reason: string | null;
};

export type AuditReportConclusion = {
  reference_code: string;
  requirement_title: string;
  control_title: string | null;
  evidence_state: string | null;
  evidence_state_label: string | null;
  decision: string | null;
  /** The auditor's conclusion. Frozen — it came from a person. */
  decision_label: string;
  decision_note: string | null;
  decided_at: string | null;
  decided_by: string | null;
  evidence_count: number;
  finding_id: string | null;
  current_remediation: string | null;
  /** Where the work stands now. Moves after the audit closes; the
   * conclusion above does not. */
  current_remediation_label: string | null;
};

export type AuditReportFinding = {
  id: string;
  reference_code: string | null;
  /** The requirement this is about, and the heading of the block.
   * `title` is what the finding was named — sometimes a diagnostic
   * sentence, and never the heading. */
  requirement_title: string | null;
  title: string;
  description: string | null;
  severity: Severity;
  /** "Minor finding", not "medium". */
  conclusion_label: string;
  current_status: string;
  current_status_label: string;
  control_title: string | null;
  evidence_state: string | null;
  evidence_state_label: string | null;
  /** A report-grade sentence for what Veyntra could establish, derived
   * from the evidence state rather than quoting the diagnostic. */
  assessment: string | null;
  not_evidenced: string | null;
  /** The auditor's reason, where they recorded one. Never invented. */
  auditor_note: string | null;
  /** The conclusion and the evidence state disagree and nobody wrote
   * down why. Said out loud rather than left to look contradictory. */
  rationale_gap: boolean;
  evidence_count: number;
  verified_at: string | null;
  verified_by: string | null;
  verification_note: string | null;
  remediation_task: string | null;
  remediation_owner: string | null;
  remediation_due: string | null;
  superseded_at: string | null;
  superseded_reason: string | null;
};

export type AuditorIdentity = {
  name: string | null;
  /** internal | external | null when nobody has established which.
   * Never inferred from whether an account is linked. */
  auditor_type: "internal" | "external" | null;
  type_label: string | null;
  /** The firm, for an external auditor only. */
  organization: string | null;
  unresolved: boolean;
};

export type AuditReportMetric = {
  label: string;
  value: string;
  emphasis: boolean;
};

export type AuditReportSignOff = {
  auditor: AuditorIdentity;
  completed_at: string | null;
  generated_at: string;
  generated_by: string | null;
  report_version: number;
  approved_by: string | null;
  approved_at: string | null;
};

export type AuditReportPreview = {
  audit_id: string;
  title: string;
  audit_title: string;
  organization_name: string | null;
  framework_name: string | null;
  framework_basis: string | null;
  auditor_name: string | null;
  /** internal | external | null when nobody has established which.
   * Never inferred from whether an account is linked. */
  auditor_type: "internal" | "external" | null;
  auditor_organization: string | null;
  auditor: AuditorIdentity;
  scope: string | null;
  status: string;
  status_label: string;
  started_at: string | null;
  completed_at: string | null;
  prepared_at: string | null;
  classification: string;
  /** False when the organization record has no usable name. The report
   * says so rather than substituting anything derived from a person. */
  organization_name_configured: boolean;
  /** The result in sentences, before any table. */
  executive_summary: string[];
  metrics: AuditReportMetric[];
  methodology: string[];
  conclusion_summary: AuditReportMetric[];
  progress: {
    scoped: number;
    reviewed: number;
    percent_reviewed: number;
    excluded: number;
    findings: number;
    superseded: number;
  };
  conclusions: AuditReportConclusion[];
  conclusion_counts: Record<string, number>;
  findings: AuditReportFinding[];
  findings_by_severity: {
    key: string;
    severity: Severity;
    label: string;
    count: number;
    findings: AuditReportFinding[];
  }[];
  superseded_findings: AuditReportFinding[];
  remediation: { status: string; label: string; count: number }[];
  remediation_rows: AuditReportFinding[];
  verification: AuditReportFinding[];
  evidence_index: {
    title: string;
    filename: string | null;
    document_href: string | null;
    /** As reviewed at audit preparation. A document revised since must
     * not change what the report says was reviewed. */
    version: string | null;
    version_label: string;
    version_source: string;
    evidence_states: string[];
    requirement_codes: string[];
  }[];
  limitations: string[];
  disclaimer: string;
  sign_off: AuditReportSignOff;
  generated_for: string;
  /** Handed back on generate. What makes it "issue what I read" rather
   * than "issue whatever is true now". */
  digest: string;
  next_version: number;
  blockers: { code: string; message: string }[];
  ready: boolean;
};

export type AuditReportRecord = {
  id: string;
  audit_id: string;
  title: string;
  version: number;
  file_format: string;
  file_id: string | null;
  generated_by: string | null;
  generated_by_name: string | null;
  generated_at: string;
  /** The audit has moved since this was generated. The report itself is
   * unchanged; this only means a new version can be offered. */
  stale: boolean;
  findings_count: number;
  requirements_reviewed: number;
};

export type AuditCompletionBlocker = {
  code: string;
  message: string;
};

export type AuditDetail = Audit & {
  findings: AuditFinding[];
  /** The scope, grouped the way an auditor works through it: gaps first,
   * clean rows last. Empty sections are left out. */
  sections: AuditSection[];
  /** What stands between this audit and being called finished. Empty
   * means it can be completed; the endpoint checks again regardless. */
  completion_blockers: AuditCompletionBlocker[];
};

export type TrustCenterCategory =
  | "security_overview"
  | "privacy_overview"
  | "subprocessors"
  | "data_locations"
  | "encryption_practices"
  | "availability"
  | "vulnerability_reporting"
  | "compliance_roadmap"
  | "dpa_availability"
  | "incident_communication"
  | "responsible_ai"
  | "ai_provider_disclosures"
  | "retention_deletion"
  | "business_continuity";

export type TrustCenterItemStatus =
  | "planned"
  | "in_progress"
  | "implemented"
  | "independently_assessed"
  | "certified";

export type TrustCenterItem = {
  id: string;
  category: TrustCenterCategory;
  title: string;
  content: string | null;
  status: TrustCenterItemStatus;
  is_public: boolean;
  policy_id: string | null;
  owner_id: string | null;
  created_at: string;
};

export type EvidenceRequestStatus = "open" | "fulfilled";

export type EvidenceRequest = {
  id: string;
  requester_name: string;
  requester_email: string;
  company_name: string | null;
  message: string | null;
  status: EvidenceRequestStatus;
  related_task_id: string | null;
  created_at: string;
};

export type TrustCenterPublicPolicy = {
  id: string;
  title: string;
};

export type TrustCenterPublicItem = {
  category: TrustCenterCategory;
  title: string;
  content: string | null;
  status: TrustCenterItemStatus;
  policy: TrustCenterPublicPolicy | null;
};

export type TrustCenterPublic = {
  organization_name: string;
  items: TrustCenterPublicItem[];
};

export type SecurityReviewStatus = "in_progress" | "blocked" | "cleared";

/** One customer's security review: the engagement questionnaires
 * belong to.
 *
 * `opportunity_id` and `questionnaire_id` are the sales-coupled model
 * this replaced — carried by rows predating the change, set by nothing
 * new. The engagement is identified by `customer_name`, a name rather
 * than a key into a CRM this product does not have. */
export type SecurityReview = {
  id: string;
  title: string | null;
  customer_name: string | null;
  status: string;
  status_label: string;
  progress: ReviewProgress;
  archived_at: string | null;
  archived_by: string | null;
  opportunity_id: string | null;
  questionnaire_id: string | null;
  approval_id: string | null;
  trust_package_file_id: string | null;
  is_deal_blocker: boolean;
  created_at: string;
};

/** A review's work, added up across every questionnaire in it. */
export type ReviewProgress = {
  questionnaires: number;
  total: number;
  approved: number;
  needs_review: number;
  draft: number;
  unanswered: number;
  percent_complete: number;
  ready_to_share: boolean;
};

/** One questionnaire inside an engagement.
 *
 * Two dimensions, kept apart: `status` is how far it got, and
 * `archived_at` is whether it is still on the working list. A finished
 * engagement is a list of archived questionnaires that are each still
 * "ready to share". */
export type ReviewQuestionnaire = {
  id: string;
  title: string;
  source: string;
  status: QuestionnaireStatus;
  href: string;
  archived_at: string | null;
  progress: QuestionnaireProgress;
};

export type ExportOutputType = "summary" | "questionnaire" | "evidence_pack";

export type ExportBlocker = { code: string; message: string };

/** One question and the answer approved for it.
 *
 * No confidence and no model reasoning: those are internal numbers about
 * our process, not facts about the customer's security. */
export type ExportAnswer = {
  question_id: string;
  question: string;
  category: string | null;
  answer: string;
  approved_at: string | null;
  sources: string[];
  /** The answer carries a limitation, which goes out with it rather than
   * being summarised away. */
  qualified: boolean;
};

/** A document that could go in the package, and whether it may.
 *
 * `eligible` is the product's answer; `included` is the person's. An
 * ineligible document is never on by default. */
export type ExportDocument = {
  file_id: string;
  title: string;
  kind: string;
  disclosure: string;
  disclosure_label: string;
  eligible: boolean;
  reason: string | null;
  version: string | null;
  status: string | null;
  superseded: boolean;
  supports: string[];
  included: boolean;
};

/** Exactly what the customer would receive, before any file exists. */
export type ExportPreview = {
  output_type: ExportOutputType;
  output_label: string;
  file_format: string;
  title: string;
  customer_name: string | null;
  review_title: string;
  review_status: string;
  review_status_label: string;
  /** History rather than a live position, and the reader is told. */
  review_archived: boolean;
  review_date: string;
  progress: ReviewProgress;
  answers: ExportAnswer[];
  documents: ExportDocument[];
  disclosures: string[];
  blockers: ExportBlocker[];
  sections: string[];
  section_labels: Record<string, string>;
  introduction: string | null;
  disclaimer: string;
  ready: boolean;
  /** Sent back on generate, so the server knows the person is confirming
   * what they were shown rather than whatever is true by the time they
   * click. */
  digest: string;
  next_version: number;
  column_mapping: Record<string, string>;
  source_filename: string | null;
};

/** One generated package. Never edited — regenerating adds a version. */
export type ReviewExportRecord = {
  id: string;
  security_review_id: string;
  output_type: ExportOutputType;
  output_label: string;
  file_format: string;
  title: string;
  version: number;
  file_id: string | null;
  generated_by: string | null;
  generated_at: string;
  shared_at: string | null;
  /** The review has moved since this was generated. The package itself
   * is unchanged; this only means a new version can be offered. */
  stale: boolean;
  answer_count: number;
  document_count: number;
};

export type SecurityReviewDetail = SecurityReview & {
  /** Every questionnaire in the engagement, oldest first. */
  questionnaires: ReviewQuestionnaire[];
  /** The sales-coupled fields this replaced. Null on anything created
   * since; carried by rows that predate the change so they still open. */
  opportunity_title: string | null;
  approval_status: string | null;
  gap_count: number;
  questionnaire: QuestionnaireDetail | null;
};

export type SecurityReviewSyncResult = {
  review: SecurityReviewDetail;
  tasks_created: number;
};

export type TransferMechanism =
  "adequacy_decision" | "sccs" | "bcrs" | "derogation";
export type DataTransferStatus = "active" | "under_review" | "terminated";

export type DataTransfer = {
  id: string;
  processing_activity_id: string | null;
  recipient_name: string;
  destination_country: string;
  transfer_mechanism: TransferMechanism;
  safeguards_description: string | null;
  status: DataTransferStatus;
  related_risk_id: string | null;
  owner_id: string | null;
  /** Which edge detection followed to find this, so a reviewer can check
   * the inference. Null on a manually logged transfer. */
  detected_from: string | null;
  /** Set when a fact underneath a confirmed transfer moved. The record
   * itself is untouched — this asks for another look. */
  review_reason: string | null;
  vendor_id: string | null;
  last_reviewed_at: string | null;
  created_at: string;
};

/** One transfer with the records it was assessed against.
 *
 * The vendor's own country and DPA status ride alongside the transfer's
 * rather than being merged into it: a reviewer deciding whether a
 * mechanism still holds needs both claims, and one reconciled value
 * would hide the disagreement that makes the question worth asking. */
export type DataTransferDetail = DataTransfer & {
  exporter_name: string;
  processing_activity_name: string | null;
  vendor_name: string | null;
  vendor_country: string | null;
  vendor_dpa_status: "pending" | "signed" | "not_required" | null;
};

export type Severity = "low" | "medium" | "high" | "critical";

export type SecurityAsset = {
  id: string;
  name: string;
  asset_type: string;
  environment: string;
  provider: string | null;
  criticality: Severity;
  data_classification: string;
  internet_exposed: boolean;
  status: "healthy" | "at_risk" | "compromised";
  owner_id: string | null;
  last_observed_at: string | null;
  created_at: string;
};

export type SecurityFinding = {
  id: string;
  title: string;
  description: string | null;
  category: "vulnerability" | "cloud_misconfiguration" | "identity" | "other";
  severity: Severity;
  cve: string | null;
  status:
    "open" | "investigating" | "resolved" | "false_positive" | "risk_accepted";
  asset_id: string | null;
  owner_id: string | null;
  due_at: string | null;
  created_at: string;
};

export type SecurityAlert = {
  id: string;
  title: string;
  description: string | null;
  severity: Severity;
  status: "new" | "investigating" | "contained" | "resolved" | "false_positive";
  finding_id: string | null;
  created_at: string;
};

export type SecurityIncidentStatus =
  | "detected"
  | "triage"
  | "investigation"
  | "containment"
  | "eradication"
  | "recovery"
  | "postmortem"
  | "closed";

export type SecurityIncident = {
  id: string;
  title: string;
  description: string | null;
  severity: Severity;
  status: SecurityIncidentStatus;
  related_risk_id: string | null;
  related_task_id: string | null;
  owner_id: string | null;
  closed_at: string | null;
  ai_summary: string | null;
  personal_data_impact: boolean;
  root_cause: string | null;
  lessons_learned: string | null;
  created_at: string;
};

export type SecurityIncidentTimelineEntry = {
  id: string;
  entry_type: "update" | "communication";
  body: string;
  author_id: string | null;
  created_at: string;
};

export type SecurityIncidentDetail = SecurityIncident & {
  timeline: SecurityIncidentTimelineEntry[];
  affected_assets: SecurityAsset[];
};

export type SecurityOverview = {
  security_score: number;
  critical_alerts: number;
  high_risks: number;
  assets_monitored: number;
  vulnerabilities_open: number;
  identity_issues_open: number;
  cloud_misconfigurations_open: number;
  open_incidents: number;
  evidence_coverage_percent: number;
};

export type CloudScanResult = {
  configured: boolean;
  checks_run: string[];
  findings_created: number;
};

export type SalesAccount = {
  id: string;
  name: string;
  industry: string | null;
  website: string | null;
  employee_count: number | null;
  icp_score: number | null;
  status: "prospect" | "customer" | "churned";
  owner_id: string | null;
  created_at: string;
};

export type SalesContact = {
  id: string;
  full_name: string;
  email: string;
  job_title: string | null;
  account_id: string | null;
  do_not_contact: boolean;
  linkedin_url: string | null;
  created_at: string;
};

export type SalesLead = {
  id: string;
  source: string | null;
  status: "new" | "qualified" | "contacted" | "disqualified" | "converted";
  score: number | null;
  account_id: string | null;
  contact_id: string | null;
  ai_account_brief: string | null;
  created_at: string;
};

export type OpportunityStage =
  | "prospecting"
  | "qualification"
  | "proposal"
  | "security_review"
  | "negotiation"
  | "closed_won"
  | "closed_lost";

export type SalesOpportunity = {
  id: string;
  account_id: string;
  title: string;
  stage: OpportunityStage;
  value: number | null;
  probability: number | null;
  expected_close_at: string | null;
  owner_id: string | null;
  onboarding_customer_id: string | null;
  created_at: string;
};

export type SalesAccountDetail = SalesAccount & {
  contacts: SalesContact[];
  opportunities: SalesOpportunity[];
};

export type OutreachMessage = {
  id: string;
  contact_id: string;
  channel: "email" | "linkedin";
  subject: string | null;
  body: string;
  status: "draft" | "sent" | "blocked";
  blocked_reason: string | null;
  created_at: string;
  sent_at: string | null;
};

export type SalesLeadDetail = SalesLead & {
  account: SalesAccount | null;
  contact: SalesContact | null;
};

export type SalesContactDetail = SalesContact & {
  account: SalesAccount | null;
  outreach: OutreachMessage[];
};

export type SalesOpportunityDetail = SalesOpportunity & {
  account: SalesAccount;
};

export type ICPProfile = {
  id: string;
  target_industries: string[];
  min_employee_count: number | null;
  max_employee_count: number | null;
  created_at: string;
};

export type LeadFinderResult = {
  created_leads: SalesLead[];
  candidates_considered: number;
};

export type EnrichmentResult = {
  configured: boolean;
  updated_fields: string[];
};

export type SequenceStep = {
  id: string;
  order_index: number;
  wait_days: number;
  channel: "email" | "linkedin";
  subject_template: string | null;
  body_template: string;
};

export type Sequence = {
  id: string;
  name: string;
  status: "active" | "paused";
  created_at: string;
};

export type SequenceEnrollment = {
  id: string;
  sequence_id: string;
  contact_id: string;
  campaign_id: string | null;
  status: "active" | "completed" | "exited";
  current_step_index: number;
  next_step_due_at: string;
  enrolled_at: string;
};

export type SequenceDetail = Sequence & {
  steps: SequenceStep[];
  enrollments: SequenceEnrollment[];
};

export type ProcessDueStepsResult = {
  processed: number;
};

export type Campaign = {
  id: string;
  name: string;
  sequence_id: string;
  status: "draft" | "active" | "completed";
  created_at: string;
};

export type CampaignStats = {
  enrolled: number;
  messages_sent: number;
  messages_blocked: number;
  completed: number;
};

export type CampaignDetail = Campaign & {
  stats: CampaignStats;
};

export type Meeting = {
  id: string;
  title: string;
  account_id: string | null;
  opportunity_id: string | null;
  contact_id: string | null;
  scheduled_at: string;
  notes: string | null;
  prep_notes: string | null;
  status: "scheduled" | "completed" | "no_show" | "cancelled";
  owner_id: string | null;
  created_at: string;
};

export type SalesIntelligence = {
  pipeline_value_by_stage: Record<string, number>;
  win_rate_percent: number;
  average_deal_size: number;
  top_accounts_by_icp_score: SalesAccount[];
  sequence_completion_rate_percent: number;
};

// ---- Sales Lead Finder (provider-neutral company/people discovery) ----
// Mirrors apps/api/app/sales/lead_finder_schemas.py field-for-field.

export type CompanyFilters = {
  name?: string | null;
  domain?: string | null;
  locations?: string[];
  min_employee_count?: number | null;
  max_employee_count?: number | null;
  industries?: string[];
  keywords?: string[];
  min_revenue?: number | null;
  max_revenue?: number | null;
  funding_stages?: string[];
  technologies?: string[];
};

export type PersonFilters = {
  name?: string | null;
  current_company_domain?: string | null;
  titles?: string[];
  title_keywords?: string[];
  seniorities?: string[];
  departments?: string[];
  locations?: string[];
  require_verified_email?: boolean;
};

export type NormalizedCompanyOut = {
  provider: string;
  provider_record_id: string;
  name: string;
  domain: string | null;
  website: string | null;
  industry: string | null;
  locations: string[];
  employee_count: number | null;
  employee_range: string | null;
  revenue_range: string | null;
  funding_stage: string | null;
  total_funding_usd: number | null;
  technologies: string[];
  linkedin_url: string | null;
  source_url: string | null;
  retrieved_at: string;
  dedupe_status: "new" | "existing";
  existing_account_id: string | null;
};

export type NormalizedPersonOut = {
  provider: string;
  provider_record_id: string;
  full_name: string;
  title: string | null;
  seniority: string | null;
  department: string | null;
  current_company_name: string | null;
  current_company_domain: string | null;
  location: string | null;
  email: string | null;
  email_status: "verified" | "unverified" | "catch_all" | "unavailable";
  phone: string | null;
  phone_status: "verified" | "unverified" | "unavailable";
  linkedin_url: string | null;
  source_url: string | null;
  retrieved_at: string;
  dedupe_status: "new" | "existing";
  existing_contact_id: string | null;
};

export type CompanySearchOut = {
  provider: string;
  companies: NormalizedCompanyOut[];
  total_available: number | null;
  page: number;
  page_size: number;
  credits_used: number | null;
};

export type PersonSearchOut = {
  provider: string;
  people: NormalizedPersonOut[];
  total_available: number | null;
  page: number;
  page_size: number;
  credits_used: number | null;
};

export type ProviderCapabilitiesOut = {
  company_search: boolean;
  people_search: boolean;
  company_enrichment: boolean;
  person_enrichment: boolean;
  decision_makers: boolean;
  credit_estimation: boolean;
};

export type SalesProviderStatus =
  | "not_configured"
  | "ready_to_connect"
  | "connected"
  | "syncing"
  | "healthy"
  | "degraded"
  | "rate_limited"
  | "failed"
  | "disabled"
  | "revoked"
  | "demo";

export type ProviderStatusOut = {
  provider_key: string;
  status: SalesProviderStatus;
  capabilities: ProviderCapabilitiesOut;
  /** True only when this organization has connected its own workspace. */
  configured: boolean;
  connection_id: string | null;
  connected_user_email: string | null;
  connected_workspace_name: string | null;
  granted_scopes: string[];
  can_manage_connection: boolean;
};

export type SavedSearchOut = {
  id: string;
  name: string;
  search_type: "company" | "person";
  filters: CompanyFilters | PersonFilters;
  provider: string;
  columns: string[];
  sort: { field: string; direction: "asc" | "desc" } | null;
  density: "comfortable" | "compact";
  is_shared: boolean;
  owner_user_id: string;
  last_executed_at: string | null;
  last_result_count: number | null;
  created_at: string;
  updated_at: string;
};

export type SalesListOut = {
  id: string;
  name: string;
  list_type: "company" | "person";
  description: string | null;
  tags: string[];
  is_shared: boolean;
  owner_user_id: string;
  created_at: string;
  updated_at: string;
};

export type SalesListItemOut = {
  id: string;
  list_id: string;
  account_id: string | null;
  contact_id: string | null;
  added_by_user_id: string;
  created_at: string;
};

export type EnrichmentJobOut = {
  id: string;
  provider: string;
  operation: string;
  status: "pending" | "running" | "succeeded" | "failed" | "partial";
  estimated_credits: number;
  actual_credits: number | null;
  succeeded_count: number;
  failed_count: number;
  error_records: { record_id: string; error: string }[];
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type CreditEstimatePreviewOut = {
  provider: string;
  operation: string;
  estimated_credits: number;
  record_count: number;
  /** The customer's own Apollo workspace that will be charged. */
  connected_workspace_name: string | null;
  connected_user_email: string | null;
};

export type CreditUsageSummaryOut = {
  id: string;
  provider: string;
  operation: string;
  estimated_credits: number;
  actual_credits: number | null;
  requested_by_user_id: string | null;
  succeeded: boolean;
  created_at: string;
};

export type ParseQueryOut = {
  company_filters: CompanyFilters;
  person_filters: PersonFilters;
  unsupported_criteria: string[];
  provider: string;
};

export type EligibilityCheckOut = {
  status: "eligible" | "requires_review" | "blocked" | "unknown";
  reasons: string[];
};

export type SuppressionEntryOut = {
  id: string;
  email: string | null;
  domain: string | null;
  contact_id: string | null;
  reason: string;
  created_by_user_id: string;
  created_at: string;
};

export type ImportPreviewOut = {
  headers: string[];
  sample_rows: Record<string, string>[];
  suggested_mapping: Record<string, string | null>;
  total_rows: number;
};

export type ProvenanceOut = {
  provider: string;
  record_type: string;
  provider_record_id: string;
  source_url: string | null;
  retrieved_at: string;
  last_verified_at: string | null;
  verification_status: string;
  enrichment_status: string;
  imported_by_user_id: string | null;
  imported_by_workflow_id: string | null;
  created_at: string;
};

export type SaveCompanyOut = {
  account_id: string;
  created: boolean;
};

export type SavePersonOut = {
  contact_id: string;
  created: boolean;
};

export type ImportJobOut = {
  id: string;
  record_type: "company" | "person";
  status: "pending" | "running" | "succeeded" | "failed" | "partial";
  total_rows: number;
  imported_rows: number;
  skipped_rows: number;
  error_rows: { row_number: number; error: string }[];
  completed_at: string | null;
  created_at: string;
};

export type SupportCustomer = {
  id: string;
  name: string;
  email: string;
  plan: string | null;
  sales_account_id: string | null;
  status: "active" | "churned";
  owner_id: string | null;
  welcome_email_sent_at: string | null;
  created_at: string;
};

export type TicketCategory =
  "billing" | "technical" | "account" | "security" | "general";
export type TicketPriority = "low" | "medium" | "high" | "urgent";
export type TicketStatus = "open" | "pending" | "resolved" | "closed";

export type SupportTicket = {
  id: string;
  customer_id: string;
  subject: string;
  description: string | null;
  channel: "email" | "chat" | "api";
  category: TicketCategory;
  priority: TicketPriority;
  status: TicketStatus;
  owner_id: string | null;
  related_alert_id: string | null;
  upsell_lead_id: string | null;
  resolved_at: string | null;
  created_at: string;
};

export type TicketMessage = {
  id: string;
  ticket_id: string;
  sender_type: "customer" | "agent" | "ai";
  author_id: string | null;
  body: string;
  status: "draft" | "sent";
  created_at: string;
};

export type SupportTicketDetail = SupportTicket & {
  messages: TicketMessage[];
};

export type KnowledgeArticle = {
  id: string;
  title: string;
  body: string;
  category: string | null;
  published: boolean;
  created_at: string;
};

export type CSATResponse = {
  id: string;
  ticket_id: string;
  score: number;
  comment: string | null;
  created_at: string;
};

export type AIAgentConfig = {
  id: string;
  enabled: boolean;
  auto_send_grounded_replies: boolean;
  created_at: string;
};

export type QAScore = {
  id: string;
  ticket_id: string;
  score: number;
  reviewer_id: string | null;
  notes: string | null;
  created_at: string;
};

export type SupportAnalytics = {
  total_tickets: number;
  open_tickets: number;
  tickets_by_status: Record<string, number>;
  average_resolution_hours: number;
  average_csat: number;
  csat_response_count: number;
  average_qa_score: number;
  qa_score_count: number;
};

export type WorkflowStepType =
  | "create_task"
  | "send_notification"
  | "human_approval"
  | "export_data"
  | "create_record"
  | "update_record"
  | "send_email"
  | "send_chat_message"
  | "assign_user"
  | "generate_document"
  | "analyze_document"
  | "extract_data"
  | "classify_data"
  | "call_api"
  | "webhook"
  | "search_knowledge"
  | "generate_ai_response"
  | "run_compliance_assessment"
  | "run_security_check"
  | "create_lead"
  | "update_crm"
  | "create_support_ticket"
  | "create_report"
  | "delay"
  | "condition"
  | "loop";

export const WORKFLOW_STEP_TYPES: WorkflowStepType[] = [
  "create_task",
  "send_notification",
  "human_approval",
  "export_data",
  "create_record",
  "update_record",
  "send_email",
  "send_chat_message",
  "assign_user",
  "generate_document",
  "analyze_document",
  "extract_data",
  "classify_data",
  "call_api",
  "webhook",
  "search_knowledge",
  "generate_ai_response",
  "run_compliance_assessment",
  "run_security_check",
  "create_lead",
  "update_crm",
  "create_support_ticket",
  "create_report",
  "delay",
  "condition",
  "loop",
];

export type WorkflowTriggerType =
  | "manual"
  | "schedule"
  | "webhook"
  | "api"
  | "new_email"
  | "new_crm_lead"
  | "crm_stage_change"
  | "new_support_ticket"
  | "new_vendor"
  | "new_employee"
  | "document_uploaded"
  | "control_failed"
  | "security_alert"
  | "form_submission"
  | "database_event"
  | "new_regulatory_update";

export const WORKFLOW_TRIGGER_TYPES: WorkflowTriggerType[] = [
  "manual",
  "schedule",
  "webhook",
  "api",
  "new_email",
  "new_crm_lead",
  "crm_stage_change",
  "new_support_ticket",
  "new_vendor",
  "new_employee",
  "document_uploaded",
  "control_failed",
  "security_alert",
  "form_submission",
  "database_event",
  "new_regulatory_update",
];

// Trigger types with no real internal event source in this build yet —
// see app.automation.triggers's module docstring.
export const UNWIRED_TRIGGER_TYPES: WorkflowTriggerType[] = [
  "new_email",
  "form_submission",
  "database_event",
  "new_regulatory_update",
];

export type WorkflowStep = {
  step_type: WorkflowStepType;
  config: Record<string, unknown>;
};

export type WorkflowStatus =
  "draft" | "testing" | "active" | "paused" | "archived";

export type Workflow = {
  id: string;
  name: string;
  description: string | null;
  trigger_type: string;
  schedule_cron: string | null;
  status: WorkflowStatus;
  steps: WorkflowStep[];
  version: number;
  owner_id: string | null;
  created_at: string;
};

export type WorkflowRunStatus =
  "running" | "succeeded" | "failed" | "awaiting_approval";

export type WorkflowRun = {
  id: string;
  workflow_id: string;
  status: WorkflowRunStatus;
  trigger_payload: Record<string, unknown> | null;
  triggered_by: string | null;
  started_at: string;
  completed_at: string | null;
};

export type WorkflowStepRun = {
  id: string;
  run_id: string;
  step_index: number;
  step_type: WorkflowStepType;
  status: "succeeded" | "failed" | "awaiting_approval";
  output: Record<string, unknown> | null;
  approval_id: string | null;
  created_at: string;
};

export type WorkflowRunDetail = WorkflowRun & {
  step_runs: WorkflowStepRun[];
};

export type WorkflowVersion = {
  id: string;
  workflow_id: string;
  version_number: number;
  steps: WorkflowStep[];
  trigger_type: string;
  published_by: string | null;
  published_at: string;
};

export type WorkflowTemplate = {
  id: string;
  name: string;
  description: string | null;
  category: string;
  trigger_type: string;
  steps: WorkflowStep[];
};

export type WorkflowAnalytics = {
  total_workflows: number;
  active_workflows: number;
  total_runs: number;
  runs_by_status: Record<string, number>;
  success_rate_percent: number;
  awaiting_approval_count: number;
};

export type IntegrationConnection = {
  id: string;
  connector_key: string;
  name: string;
  // webhook: active|disabled — oauth2: not_connected|connected|error|disconnected
  status: string;
  webhook_secret: string | null;
  linked_workflow_id: string | null;
  scopes: string[] | null;
  external_account_id: string | null;
  health_status: "ok" | "error" | null;
  last_health_check_at: string | null;
  last_synced_at: string | null;
  last_error: string | null;
  created_at: string;
};

export type WebhookEvent = {
  id: string;
  connection_id: string;
  verified: boolean;
  payload: Record<string, unknown> | null;
  triggered_run_id: string | null;
  received_at: string;
};

export type ProviderCatalogEntry = {
  connector_key: string;
  name: string;
  auth_type: "hmac" | "oauth2";
  configured: boolean;
  scopes: string[];
};

export type OAuthStartResponse = {
  connection_id: string;
  authorization_url: string;
};

export type SyncRun = {
  id: string;
  connection_id: string;
  status: "running" | "succeeded" | "failed";
  items_synced: number | null;
  error: string | null;
  cursor_used: string | null;
  started_at: string;
  completed_at: string | null;
};

// Organization Knowledge Graph (spec section 10) — mirrors
// app.knowledge.graph.GraphNode/GraphEdge/GraphResult.
export type GraphNode = {
  entity_type: string;
  id: string;
  label: string;
};

export type GraphEdge = {
  relation: string;
  node: GraphNode;
};

export type GraphResult = {
  node: GraphNode;
  edges: GraphEdge[];
};

// Global Search (spec section 47) — mirrors
// app.search.schemas.SearchResultOut/SearchResponse.
export type SearchResult = {
  entity_type: string;
  id: string;
  label: string;
  module: string;
  /** Where to open it. Computed server-side so this cannot drift. */
  href: string;
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
};

export type FrameworkActivation = {
  framework_id: string;
  status: "active" | "inactive";
  activated_at: string | null;
};

/** The structured fix behind a gap.
 *
 * Assembled from playbooks written against the regulation, not
 * generated — see apps/api/app/compliance/remediation.py. Arrives whole
 * so the UI can render the checklist as a checklist and the required
 * evidence as an upload target, rather than asking the reader to parse
 * a paragraph. */
export type RemediationPlan = {
  problem: string;
  why: string;
  action: string;
  /** A team, not a person — we do not know the customer's org chart. */
  owner: string;
  priority: "low" | "normal" | "high" | "urgent";
  due_in_days: number;
  required_evidence: string[];
  checklist: string[];
  evidence_reviewed: string[];
  missing_conditions: string[];
  missing_evidence: string;
  requirement_code: string;
  requirement_title: string;
  framework_name: string;
  control_title: string | null;
  affected_ai_systems: string[];
};

export type ComplianceGap = {
  id: string;
  framework_id: string;
  requirement_id: string;
  control_id: string | null;
  kind:
    | "no_control"
    | "evidence_missing"
    | "evidence_partial"
    | "assessment_failed";
  status: "open" | "remediating" | "resolved";
  severity: "low" | "medium" | "high";
  summary: string;
  recommendation: string | null;
  remediation_plan: RemediationPlan | null;
  missing_conditions: string[];
  task_id: string | null;
  created_at: string;
};

/** One requirement's assessed position. `evidence_count` and
 * `latest_assessment_status` travel with the status deliberately — the
 * reader can see what the conclusion was computed from rather than being
 * asked to trust it. */
/** Where one requirement sits in the lifecycle.
 *
 * The order is: no control -> evidence missing -> (evidence read) ->
 * either a named deficiency, or needs_review while the conclusion is
 * open, or satisfied. Only the first four are findings; `needs_review`
 * deliberately carries no gap, because "nobody has confirmed this yet"
 * is not the same as "something is wrong". */
export type RequirementStatus =
  | "not_applicable"
  | "not_assessed"
  | "evidence_missing"
  | "assessment_failed"
  | "deficient"
  | "needs_review"
  | "satisfied";

export type RequirementEvaluation = {
  requirement_id: string;
  reference_code: string;
  title: string;
  status: RequirementStatus;
  control_ids: string[];
  evidence_count: number;
  latest_assessment_status: string | null;
  summary: string;
  gap_id: string | null;
  /** The conditions the evidence does not meet, named. Populated only
   * when the status is `deficient`. */
  missing_conditions: string[];
  /** Why no conclusion was reached, when the status is `needs_review`. */
  uncertainty: string | null;
};

export type FrameworkAssessmentResult = {
  framework_id: string;
  assessed_at: string;
  requirements: RequirementEvaluation[];
  satisfied_count: number;
  gap_count: number;
  /** Requirements actually backed by evidence — the number that must not
   * move when an unrelated document is uploaded. */
  evidence_coverage_percent: number;
  readiness: ReadinessBreakdown;
};

/** One field that moved, already in words. `before` is null where the
 * event recorded only a new value — most writes do, and inventing a
 * previous value to fill the arrow would be a claim the record does not
 * make. */
export type AuditChange = {
  label: string;
  before: string | null;
  after: string;
};

/** What an event happened to, by name rather than by id. `available` is
 * false when the record has since been deleted — the card says so
 * instead of printing a UUID nobody can use. */
export type AuditEntity = {
  kind: string;
  label: string;
  href: string | null;
  available: boolean;
};

/** Who or what performed an event.
 *
 * Classified server-side per action, never inferred from whether a user
 * id happens to be recorded: "a model proposed this" and "our rules
 * derived this" are exactly the distinction an auditor is reading the
 * trail to find. */
export type AuditActorKind =
  "person" | "ai" | "system" | "integration" | "unknown";

export type AuditEvent = {
  id: string;
  // --- what a person reads ------------------------------------------
  title: string;
  category: string;
  category_label: string;
  entity: AuditEntity | null;
  actor_name: string;
  actor_kind: AuditActorKind;
  changes: AuditChange[];
  reason: string | null;
  created_at: string;
  // --- the technical record, for the details drawer ------------------
  //
  // Still here deliberately. The timeline hides these; it does not lose
  // them, because the raw event is what makes the trail worth keeping.
  action: string;
  object_type: string;
  object_id: string | null;
  actor_user_id: string | null;
  actor_email: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  correlation_id: string | null;
  /** The terser per-record phrasing used by a task or policy feed, where
   * the record is already named on the page. */
  label: string | null;
};

export type IndicatorCatalog = {
  prohibited: Record<string, string>;
  high_risk: Record<string, string>;
  transparency: Record<string, string>;
  privacy_questions: Record<string, string>;
};

/** An EU AI Act screening or privacy assessment. `findings` carries the
 * reasoning — which indicators were relied on, what is still unanswered,
 * and whether a human must confirm. A classification without its basis is
 * an assertion, so the UI always renders the basis alongside it. */
export type AIAssessmentDetail = {
  id: string;
  ai_system_id: string;
  assessment_type: "eu_ai_act" | "privacy" | "general";
  status: string;
  notes: string | null;
  findings: {
    classification?: string;
    rationale?: string;
    facts_relied_on?: string[];
    uncertainties?: string[];
    requires_human_review?: boolean;
    indicators_answered?: Record<string, boolean>;
    indicators_unanswered?: string[];
    questions?: Record<string, string>;
    answers?: Record<string, string>;
    unanswered?: string[];
    dpia_indicated?: boolean;
  } | null;
  created_at: string;
};

/** An AI proposal that a document evidences a control. Deliberately not
 * Evidence: the assessment ignores these entirely, and approving one is
 * what creates the real evidence row. */
/** A document in the compliance library, with where it is in the
 * processing pipeline. `extracted_characters` travels with the status so
 * the UI can show that `ready` meant text was genuinely read, rather
 * than asking the user to trust a green badge over an empty result. */
export type ComplianceDocument = {
  /** source | generated_output. What kind of thing this is, stored on
   * the record rather than guessed from a filename — a customer can
   * upload something called "Audit Report v2". A generated output is a
   * result of Veyntra's compliance work and never an input to it. */
  artifact_type: "source" | "generated_output";
  artifact_label: string;
  origin_type: string | null;
  origin_id: string | null;
  /** "ISO 42001 Internal Audit", frozen at generation so it keeps
   * reading correctly after the audit is renamed. */
  origin_label: string | null;
  origin_href: string | null;
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  classification: string;
  processing_status:
    // Resting state: uploaded elsewhere in Veyntra and never submitted
    // for compliance analysis. Not a pipeline stage.
    | "not_analyzed"
    | "uploaded"
    | "parsing"
    | "analyzing"
    | "ready"
    | "failed"
    | "unsupported";
  processing_error: string | null;
  processed_at: string | null;
  /** Whether the Copilot can retrieve from this document. Separate
   * from `processing_status`, which only says Document Intelligence
   * finished — a document can be analysed and mapped perfectly while its
   * embedding call failed, and calling that "Analyzed" sent people to
   * ask the Copilot about a document it could not see. */
  /** The governance record this document is, when it is a policy.
   * Created automatically from the classification — see
   * apps/api/app/compliance/policy_governance.py. */
  policy_id: string | null;
  policy_title: string | null;
  policy_status: PolicyStatus | null;
  index_status: "pending" | "indexed" | "failed" | "unsupported";
  index_error: string | null;
  indexed_at: string | null;
  extracted_characters: number | null;
  document_type: string | null;
  document_domain: string | null;
  created_at: string;
  proposed_count: number;
  approved_count: number;
  unverifiable_count: number;
  /** The document's name, cleaned of the sort prefix and extension. The
   * filename is still shown underneath — it is how the customer finds
   * the file on their own disk — but it is not the document's name. */
  title: string;
  /** The canonical Document Detail route, composed server-side. Null
   * until the document is indexed: there is no page to open yet, and the
   * row renders without a link rather than with one that 404s. */
  document_id: string | null;
  href: string | null;
  /** How many versions of this document exist, this one included. The
   * library lists logical documents, not uploads: a policy revised
   * twice is one row that says "3 versions", not three rows a reader
   * has to work out the relationship between. */
  version_count: number;
  version_label: string | null;
  /** Why this document has the mappings it has — or none.
   *
   * `no_controls` is a normal state, not a failure: a new organization
   * has nothing to map evidence to until it adopts a framework, and the
   * document is fully read, classified, governed and searchable
   * regardless. Distinguishing it from `no_matches` is the difference
   * between "we are still setting up" and "your policy evidences
   * nothing". */
  mapping_state: "mapped" | "no_matches" | "no_controls" | "not_analyzed";
  /** An undecided version question involves this row — either it might
   * be a new version of something, or something might be a new version
   * of it. Until a person decides, the library really does hold two
   * rows for one document, and saying so beats looking broken. */
  has_pending_version: boolean;
};

/** One version of a document, in the chain it belongs to. */
export type DocumentVersion = {
  file_id: string;
  document_id: string | null;
  href: string | null;
  filename: string;
  version_label: string | null;
  status: "current" | "superseded";
  uploaded_at: string;
  uploaded_by: string | null;
  evidence_count: number;
};

/** What Veyntra thinks an upload is a newer version of.
 *
 * A proposal, never a decision. `reasons` is the whole point: a person
 * confirming a version link is agreeing with an argument, and an
 * argument they cannot read is one they cannot disagree with. */
export type VersionCandidate = {
  file_id: string;
  title: string;
  confidence: "high" | "medium" | "low";
  reasons: string[];
  /** Both sides of the comparison. The reader decides from what the two
   * documents say about themselves — a similarity score is not something
   * anybody can check, and version numbers and dates are. Every field is
   * null when the document does not state it; none of it is inferred. */
  current_version: string | null;
  current_effective_date: string | null;
  current_approved_at: string | null;
  current_filename: string | null;
  detected_version: string | null;
  detected_effective_date: string | null;
  uploaded_filename: string | null;
};

/** One section of a document, and what happened to it between versions. */
export type SectionChange = {
  change: "added" | "removed" | "rewritten" | "reworded" | "unchanged";
  section: string | null;
  summary: string;
  previous_text: string | null;
  current_text: string | null;
};

/** What changed between two versions, as a person would describe it.
 *
 * Section-level, never line-level: a policy re-flowed by a word
 * processor changes every line and says nothing new, while a reviewer
 * needs to know that §7 now requires monthly review where it used to say
 * "should be monitored". */
export type VersionDiff = {
  previous_file_id: string;
  current_file_id: string;
  previous_label: string | null;
  current_label: string | null;
  headline: string;
  added: number;
  removed: number;
  modified: number;
  unchanged: number;
  changes: SectionChange[];
};

/** One thing Veyntra found in a document, and what it supports.
 *
 * The chain a reader follows is document → passage → control →
 * requirement, so all four travel together. `status` is the suggestion's
 * own state and is never flattened into "approved": a proposal awaiting
 * a person and a mapping somebody stood behind are different claims. */
export type DocumentEvidence = {
  id: string;
  source_location: string | null;
  quoted_passage: string | null;
  evidence_type: string | null;
  status: string;
  confidence: number | null;
  control_id: string | null;
  control_title: string | null;
  requirement_id: string | null;
  requirement_reference: string | null;
  requirement_title: string | null;
  framework_name: string | null;
};

/** Everything the Document Detail page shows, besides the text itself.
 *
 * Addressed by the knowledge document id — the same identifier a Copilot
 * citation carries — so the library and a citation open one page. */
export type DocumentDetail = {
  document_id: string;
  file_id: string;
  href: string;
  title: string;
  filename: string;
  document_type: string | null;
  document_domain: string | null;
  classification: string;
  /** Document Intelligence: whether the compliance analysis ran. */
  processing_status: string;
  processing_error: string | null;
  /** Whether the text is readable here — a different pipeline. A
   * document can be ingested and readable while the compliance analysis
   * was never asked for, which is the state every attachment that
   * arrived from elsewhere is in. */
  content_status: string;
  content_error: string | null;
  index_status: string;
  index_error: string | null;
  extracted_characters: number | null;
  size_bytes: number;
  created_at: string;
  processed_at: string | null;
  policy_id: string | null;
  policy_title: string | null;
  policy_status: PolicyStatus | null;
  evidence_count: number;
  control_count: number;
  requirement_count: number;
  proposed_count: number;
  approved_count: number;
  unverifiable_count: number;
  evidence: DocumentEvidence[];
  /** See ComplianceDocument.mapping_state. */
  mapping_state: "mapped" | "no_matches" | "no_controls" | "not_analyzed";
  /** Every version of this document, oldest first. One entry for a
   * document uploaded only once. */
  versions: DocumentVersion[];
  version_label: string | null;
  version_candidate: VersionCandidate | null;
};

/** A readiness percentage with the arithmetic behind it. The explanation
 * is built from the same counts as the number, so the sentence can never
 * drift from the figure it explains. */
export type ReadinessBreakdown = {
  percent: number;
  satisfied: number;
  needs_review: number;
  deficient: number;
  assessment_failed: number;
  evidence_missing: number;
  not_assessed: number;
  /** Applicable requirements only — the denominator the percentage was
   * actually computed against, never the raw count. */
  total: number;
  not_applicable: number;
  explanation: string;
};

/** A framework we do or do not think applies, and why.
 *
 * `reasons` restates facts the organization declared, so the customer
 * can disagree with a recommendation by changing a fact rather than
 * arguing with a model. */
export type Connector = {
  key: string;
  name: string;
  category: string;
  /** Never optimistic. A customer who believes a source is watching
   * their systems, and is wrong, is worse off than one who knows. */
  status: "available" | "coming_soon";
  observes: string;
};

export type ConnectorCatalog = {
  connectors: Connector[];
  available_count: number;
  coming_soon_count: number;
};

export type EvidenceEvent = {
  id: string;
  source: string;
  event_type: string;
  summary: string;
  control_id: string | null;
  observed_at: string;
  triggered_reassessment: boolean;
};

export type ActivityLine = { count: number; label: string };

export type NextAction = {
  title: string;
  detail: string;
  href: string;
  priority: "high" | "medium" | "low";
};

export type FrameworkStatus = {
  framework_id: string;
  key: string;
  name: string;
  readiness_percent: number;
  /** The arithmetic behind the figure. Never shown without it. */
  explanation: string;
  open_gap_count: number;
};

export type SystemAtRisk = {
  ai_system_id: string;
  name: string;
  risk_classification: string;
  readiness_percent: number;
  open_action_count: number;
};

export type ComplianceDashboard = {
  readiness_percent: number;
  readiness_explanation: string;
  critical_gap_count: number;
  open_risk_count: number;
  ai_system_count: number;
  high_risk_ai_system_count: number;
  overdue_action_count: number;
  frameworks: FrameworkStatus[];
  critical_issues: NextAction[];
  systems_at_risk: SystemAtRisk[];
  /** Counted from the audit trail, never narrated. */
  recent_activity: ActivityLine[];
  recommended_next_actions: NextAction[];
};

export type ReviewItem = {
  id: string;
  title: string;
  detail: string;
  priority: "high" | "medium" | "low";
  /** Where the decision is actually made. */
  href: string;
};

export type ReviewCategory = {
  key: string;
  label: string;
  description: string;
  count: number;
  items: ReviewItem[];
};

export type ReviewCenter = {
  categories: ReviewCategory[];
  total_needing_review: number;
  /** Accepted without asking, over the same window. */
  auto_accepted_recently: number;
  proposals_recently: number;
};

export type RequiredAction = {
  title: string;
  detail: string;
  priority: "high" | "medium" | "low";
  /** The obligation behind this action. */
  basis: string;
};

/** One AI system as the governance screen needs it — computed
 * deterministically, never a model opinion. */
export type AISystemGovernance = {
  ai_system_id: string;
  name: string;
  risk_classification: string;
  deployment_status: string;
  vendor: string | null;
  model_name: string | null;
  documentation_completeness: number;
  missing_documentation: string[];
  applicable_regulations: string[];
  open_risk_count: number;
  open_incident_count: number;
  has_current_screening: boolean;
  required_actions: RequiredAction[];
  readiness_percent: number;
  explanation: string;
};

export type AIGovernanceOverview = {
  systems: AISystemGovernance[];
  total_systems: number;
  high_risk_systems: number;
  systems_without_screening: number;
  total_open_actions: number;
};

export type FrameworkRecommendation = {
  framework_key: string;
  framework_id: string | null;
  framework_name: string | null;
  applicability: "required" | "likely" | "recommended" | "not_indicated";
  reasons: string[];
  uncertainties: string[];
  requires_legal_review: boolean;
  already_active: boolean;
};

export type FrameworkRecommendations = {
  recommendations: FrameworkRecommendation[];
  /** False until anything has been declared. An empty result must
   * read as "we have not asked yet", never "nothing applies to you". */
  facts_declared: boolean;
};

export type FrameworkReadiness = {
  framework_id: string;
  framework_key: string;
  framework_name: string;
  readiness: ReadinessBreakdown;
  open_gap_count: number;
};

/** Where the organization stands, for the Compliance screen itself — so
 * "assessment runs" and "readiness appears" are visible where the
 * document was uploaded, not only on a framework detail page. */
export type ComplianceOverview = {
  frameworks: FrameworkReadiness[];
  total_open_gaps: number;
  proposals_awaiting_review: number;
  documents_processing: number;
  controls_needing_reassessment: number;
};

export type EvidenceSuggestion = {
  id: string;
  file_id: string;
  control_id: string;
  status:
    "proposed" | "auto_approved" | "approved" | "rejected" | "unverifiable";
  /** Where in the document the passage came from, as the document
   * labels it. The difference between a citation a reviewer can
   * follow and one they must take on trust. */
  source_location: string | null;
  evidence_type: string | null;
  requirement_id: string | null;
  /** Why this did or did not reach a human. */
  routing_reason: string | null;
  /** The model's own confidence. Displayed, never used to decide
   * anything — a number a model assigns to its own output is not a
   * measurement. */
  confidence: number | null;
  rationale: string | null;
  quoted_passage: string | null;
  /** Whether the quoted passage was actually found in the document. The
   * difference between a citation and an assertion. */
  quote_verified: boolean;
  evidence_id: string | null;
  created_at: string;
};

// --- the privacy workspace ---------------------------------------------
//
// The overview derives "what needs a person" from the same records the
// four lists show. Every metric and every attention item carries the
// route to what it is about — a dashboard figure that leads nowhere is a
// decoration.

export type PrivacyMetric = {
  key: string;
  label: string;
  value: number;
  href: string;
  /** "attention" where the number is itself a problem rather than a size. */
  tone: "neutral" | "attention";
};

export type PrivacyAttention = {
  key: string;
  severity: "overdue" | "urgent" | "attention" | "info";
  title: string;
  detail: string;
  href: string;
  record_type: string;
  record_id: string | null;
};

export type PrivacyOverview = {
  metrics: PrivacyMetric[];
  attention: PrivacyAttention[];
  needs_attention: number;
};

// --- privacy automation -------------------------------------------------
//
// Veyntra drafts from what the organization already declared; a person
// supplies the judgements a draft is not allowed to contain. The types
// keep that split visible: a suggestion payload carries
// "needs_confirmation" where a legal judgement belongs, never a value.

export type PrivacySuggestionSource = {
  type: string;
  id: string | null;
  label: string;
};

export type PrivacySuggestion = {
  id: string;
  kind: "processing_activity" | "transfer";
  status: "proposed" | "accepted" | "dismissed";
  title: string;
  /** The records this was read out of, so a reviewer can check it. */
  sources: PrivacySuggestionSource[];
  payload: Record<string, unknown>;
  created_record_id: string | null;
  created_at: string;
};

export type PrivacyAnalysis = {
  created: number;
  already_proposed: number;
  /** Drafts skipped because a real record already covers them. */
  already_recorded: number;
};

export type PrivacyDataLocation = {
  label: string;
  kind: string;
  record_id: string;
  reason: string;
};

export type RelatedRecord = {
  id: string;
  label: string;
  kind: string;
  href: string;
  detail: string | null;
};

export type ProcessingActivityRelated = {
  ai_systems: RelatedRecord[];
  vendors: RelatedRecord[];
  dpias: RelatedRecord[];
  transfers: RelatedRecord[];
};

// --- starting a DPIA from context ---------------------------------------

export type DpiaSuggestedAnswer = {
  criterion: string;
  value: boolean;
  /** What the suggestion was read from, so a person can disagree with
   * it rather than take it on trust. */
  reason: string;
};

export type DpiaLinkedRecord = {
  id: string;
  label: string;
  kind: string;
  detail: string | null;
};

export type DpiaContext = {
  title: string;
  purpose: string | null;
  data_subjects: string | null;
  data_categories: string[];
  special_category: boolean;
  processing_activity_id: string | null;
  ai_system_id: string | null;
  owner_id: string | null;
  ai_systems: DpiaLinkedRecord[];
  vendors: DpiaLinkedRecord[];
  transfers: DpiaLinkedRecord[];
  evidence_count: number;
  suggested_answers: DpiaSuggestedAnswer[];
  /** Criteria nothing on record speaks to — asked rather than assumed,
   * because silence on a criterion is not a "no". */
  unknown: string[];
};

export type DpiaScreeningResult = {
  /** required | recommended | not_indicated. A recommendation from the
   * criteria reported, never a determination. */
  outcome: string;
  rationale: string;
  criteria_met: string[];
  mandatory_triggers: string[];
  unanswered: string[];
};

// --- the DPIA lifecycle -------------------------------------------------

/** A risk Veyntra proposes, and the decision it is waiting on.
 *
 * Never carries a likelihood or an impact. Those are the judgement the
 * review exists to make, and a proposal arriving pre-rated would answer
 * the one question the reviewer was brought in for. */
export type DpiaSuggestedRisk = {
  id: string | null;
  title: string;
  description: string;
  /** The fact on record this was read from, so a reviewer can weigh it. */
  reason: string;
  status: "suggested" | "approved" | "dismissed";
  /** Safeguards already on record, as a starting point — never a claim
   * that they are sufficient. */
  suggested_safeguards: string | null;
  created_risk_id: string | null;
  decided_at: string | null;
};

export type DpiaBlocker = { code: string; message: string };

export type ConsultationState =
  | "not_decided"
  | "consultation_performed"
  | "no_consultation";

export type RiskConclusion =
  | "not_reviewed"
  | "risks_identified"
  | "no_material_risks";

export type DpiaMissingFact = {
  code: string;
  message: string;
  /** Where to go and fix it, so a blocker is actionable rather than a
   * statement that something is wrong somewhere. */
  href: string;
};

export type DpiaSpecialSignal = {
  kind: string;
  /** The recorded text this was read out of, so a reviewer checks the
   * detection rather than taking it on trust. */
  evidence: string;
};

export type DpiaSectionReview = {
  section: string;
  approved_by: string | null;
  approved_at: string | null;
};

export type DpiaSnapshotRisk = {
  id: string;
  title: string;
  description: string | null;
  affected_data_subjects: string | null;
  likelihood: string;
  impact: string;
  existing_safeguards: string | null;
  additional_mitigations: string | null;
  residual_likelihood: string | null;
  residual_impact: string | null;
  status: string;
};

/** The assessment as it stood at completion. Written once. */
export type DpiaSnapshot = {
  processing: {
    title: string;
    purpose: string | null;
    data_subjects: string | null;
    data_categories: string[];
    special_category: boolean;
    retention: string | null;
    ai_systems: string[];
    vendors: { name: string; country: string | null }[];
    transfers: string[];
  };
  screening: {
    outcome: string | null;
    decision: string | null;
    decided_by: string | null;
    decided_at: string | null;
    rationale: string | null;
  };
  consultation: {
    state: ConsultationState;
    performed: boolean | null;
    party: string | null;
    role: string | null;
    at: string | null;
    /** The advice when one happened; the reason when none did. */
    notes: string | null;
    recorded_by: string | null;
    recorded_at: string | null;
  };
  /** Not recoverable from the risk list: an empty register means
   * "reviewed and found nothing material" here, and that is a claim
   * somebody made. */
  risk_review: {
    conclusion: RiskConclusion;
    rationale: string | null;
    reviewed_by: string | null;
    reviewed_at: string | null;
  };
  risks: DpiaSnapshotRisk[];
  /** Kept because "we considered this and decided it was not a risk
   * here" is part of what an assessment concluded. */
  dismissed_risks: { title: string; reason: string }[];
  residual_risk: string | null;
  inherent_risk: string | null;
  approval: {
    action_type: string;
    status: string;
    decided_by: string | null;
    decided_at: string | null;
  } | null;
  evidence: { id: string; title: string; control_id: string }[];
};

export type DpiaWorkflow = {
  id: string;
  title: string;
  /** screening | draft | in_review | approved. A DPIA is not a draft
   * assessment until somebody decides one is required. */
  status: string;
  processing_activity_id: string | null;
  ai_system_id: string | null;

  /** What Veyntra counted against Article 35(3) and the EDPB criteria. */
  screening_outcome: string | null;
  screening_rationale_text: string | null;
  screening_criteria_met: string[];
  screened_at: string | null;

  /** And what a person decided about it — a different claim by a
   * different party, so stored and shown separately. */
  screening_decision: string | null;
  screening_decided_at: string | null;
  screening_decision_rationale: string | null;

  processing_description: string | null;
  necessity_assessment: string | null;
  proportionality_assessment: string | null;
  consultation_notes: string | null;

  /** Null means nobody has assessed it — which is what a DPIA with no
   * risks should say rather than "Low". */
  inherent_risk: string | null;
  residual_risk: string | null;
  risk_count: number;
  assessed_count: number;
  mitigated_count: number;
  can_calculate_residual: boolean;
  risk_blocked_reason: string | null;

  suggested_risks: DpiaSuggestedRisk[];
  completion_blockers: DpiaBlocker[];
  /** True when screening continued the assessment that already covered
   * this processing rather than opening a second one. */
  reused_existing: boolean;

  /** Which sections a person has actually signed off. Recorded rather
   * than inferred from whether the text still starts with Veyntra's
   * draft marker — agreeing with a draft is a decision, not an edit. */
  section_reviews: DpiaSectionReview[];

  /** The one consultation state. Derived server-side from the single
   * field that holds it, so the screen never reconciles two sources —
   * it used to show "No consultation performed" beside "Nobody has
   * approved the consultation record" about the same fact. */
  consultation_state: ConsultationState;
  consultation_performed: boolean | null;
  consulted_party: string | null;
  consulted_role: string | null;
  consulted_at: string | null;
  consultation_recorded_by_name: string | null;
  consultation_recorded_at: string | null;

  /** What the risk review concluded. Only the last two are a completed
   * review: a risk count of zero cannot tell "nobody looked" apart from
   * "looked, and found none material". */
  risk_conclusion: RiskConclusion;
  risk_conclusion_rationale: string | null;
  risk_reviewed_by_name: string | null;
  risk_reviewed_at: string | null;
  /** True when every suggestion is decided and no risk is on the
   * register — the only position from which "nothing material" is a
   * conclusion rather than a guess. */
  can_conclude_no_material_risks: boolean;

  /** Core processing facts the assessment needs and does not have.
   * Absent context is not a benign finding: a DPIA written against a
   * record with no data categories cannot say what it assessed. */
  missing_facts: DpiaMissingFact[];
  /** Article 9 hints Veyntra read out of the record. Detection only —
   * whether Article 9 applies is never decided by the product. */
  special_category_signals: DpiaSpecialSignal[];
  /** null = nobody has answered, which is distinct from a recorded
   * "not applicable, for this reason". */
  special_category_confirmed: boolean | null;
  special_category_rationale: string | null;
  /** Sections approved against processing details that have since moved. */
  stale_sections: string[];
  /** What each section is written against, kept apart from the answer so
   * it can never be approved as one. */
  section_guidance: Record<string, string>;
  /** Set when a completed DPIA was signed off on content that would not
   * pass today's gates. Never rewrites what it froze. */
  quality_review_reason: string | null;

  can_complete: boolean;
  completed_at: string | null;
  completed_by_name: string | null;
  /** What the assessment concluded, frozen at completion. Null until
   * then, and never re-derived afterwards. */
  snapshot: DpiaSnapshot | null;
  review_reason: string | null;
  review_flagged_at: string | null;
  /** Which statuses this DPIA can move to right now, so the UI offers
   * one lifecycle rather than a list of words. */
  allowed_transitions: DPIAStatus[];
};
