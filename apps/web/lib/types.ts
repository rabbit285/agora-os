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
  created_at: string;
};

export type Membership = {
  id: string;
  user_id: string;
  status: string;
  roles: string[];
};

export type Invitation = {
  id: string;
  email: string;
  role_key: string;
  accepted_at: string | null;
  expires_at: string;
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

export type Notification = {
  id: string;
  title: string;
  body: string | null;
  link: string | null;
  read_at: string | null;
  created_at: string;
};

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
};

export type DocumentStatus =
  | "pending"
  | "processing"
  | "ready"
  | "failed"
  | "unsupported_format";

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
};

export type Citation = {
  document_id: string;
  chunk_id: string;
  chunk_index: number;
  score: number;
};

export type CopilotAnswer = {
  text: string;
  provider: string;
  model: string;
  grounded: boolean;
  citations: Citation[];
};

export type Framework = {
  id: string;
  key: string;
  name: string;
  description: string | null;
};

export type Requirement = {
  id: string;
  reference_code: string;
  title: string;
  description: string | null;
};

export type ControlStatus = "not_started" | "in_progress" | "implemented" | "needs_review";

export type Control = {
  id: string;
  title: string;
  description: string | null;
  status: ControlStatus;
  owner_id: string | null;
  created_at: string;
};

export type ControlAssessment = {
  id: string;
  status: "pass" | "fail" | "partial" | "not_assessed";
  notes: string | null;
  assessed_by: string | null;
  created_at: string;
};

export type ControlDetail = Control & {
  requirements: Requirement[];
  assessments: ControlAssessment[];
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
  owner_id: string | null;
  created_at: string;
};

export type AIRiskClassification = "minimal" | "limited" | "high" | "unacceptable";
export type AISystemStatus = "in_review" | "approved" | "rejected" | "retired";

export type AISystem = {
  id: string;
  name: string;
  vendor: string | null;
  purpose: string;
  risk_classification: AIRiskClassification;
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
export type DPIAStatus = "draft" | "in_review" | "approved" | "rejected";

export type DPIA = {
  id: string;
  processing_activity_id: string | null;
  ai_system_id: string | null;
  title: string;
  risk_level: DPIARiskLevel;
  status: DPIAStatus;
  findings: string | null;
  approval_id: string | null;
  owner_id: string | null;
  created_at: string;
};

export type DSARRequestType = "access" | "deletion" | "rectification" | "portability";
export type DSARStatus = "received" | "in_progress" | "fulfilled" | "rejected";

export type DSAR = {
  id: string;
  requester_name: string;
  requester_email: string;
  request_type: DSARRequestType;
  status: DSARStatus;
  due_at: string;
  fulfilled_at: string | null;
  notes: string | null;
  assigned_to: string | null;
  created_at: string;
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
  owner_id: string | null;
  created_at: string;
};

export type VendorAssessment = {
  id: string;
  vendor_id: string;
  risk_conclusion: Severity;
  notes: string | null;
  related_risk_id: string | null;
  assessed_by: string | null;
  created_at: string;
};

export type VendorDetail = Vendor & {
  assessments: VendorAssessment[];
  evidence: Evidence[];
};

export type QuestionnaireSource = "customer_provided" | "internal_template";
export type QuestionnaireStatus = "draft" | "in_progress" | "completed";

export type Questionnaire = {
  id: string;
  title: string;
  source: QuestionnaireSource;
  status: QuestionnaireStatus;
  opportunity_id: string | null;
  owner_id: string | null;
  created_at: string;
};

export type QuestionCategory = "compliance" | "security";

export type QuestionnaireQuestion = {
  id: string;
  questionnaire_id: string;
  text: string;
  category: QuestionCategory;
  order_index: number;
  created_at: string;
};

export type AnswerStatus = "draft" | "approved" | "missing";
export type AnswerSourceType = "ai_suggested" | "manual" | "reused_from_library" | null;

export type QuestionnaireAnswer = {
  id: string;
  question_id: string;
  answer_text: string | null;
  status: AnswerStatus;
  source_type: AnswerSourceType;
  citations: Record<string, unknown>[] | null;
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
};

export type AuditStatus = "planned" | "in_progress" | "completed";

export type Audit = {
  id: string;
  title: string;
  framework_id: string | null;
  auditor_name: string | null;
  status: AuditStatus;
  scheduled_at: string | null;
  completed_at: string | null;
  owner_id: string | null;
  created_at: string;
};

export type FindingStatus = "open" | "remediated";

export type AuditFinding = {
  id: string;
  audit_id: string;
  control_id: string | null;
  title: string;
  description: string | null;
  severity: Severity;
  status: FindingStatus;
  related_task_id: string | null;
  created_at: string;
};

export type AuditDetail = Audit & {
  findings: AuditFinding[];
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

export type SecurityReview = {
  id: string;
  opportunity_id: string;
  questionnaire_id: string;
  approval_id: string | null;
  trust_package_file_id: string | null;
  status: SecurityReviewStatus;
  is_deal_blocker: boolean;
  created_at: string;
};

export type SecurityReviewDetail = SecurityReview & {
  opportunity_title: string;
  approval_status: string | null;
  gap_count: number;
  questionnaire: QuestionnaireDetail;
};

export type SecurityReviewSyncResult = {
  review: SecurityReviewDetail;
  tasks_created: number;
};

export type TransferMechanism = "adequacy_decision" | "sccs" | "bcrs" | "derogation";
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
  created_at: string;
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
  status: "open" | "investigating" | "resolved" | "false_positive" | "risk_accepted";
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
  created_at: string;
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
  created_at: string;
};

export type SalesLead = {
  id: string;
  source: string | null;
  status: "new" | "qualified" | "contacted" | "disqualified" | "converted";
  score: number | null;
  account_id: string | null;
  contact_id: string | null;
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

export type SupportCustomer = {
  id: string;
  name: string;
  email: string;
  plan: string | null;
  sales_account_id: string | null;
  status: "active" | "churned";
  created_at: string;
};

export type TicketCategory = "billing" | "technical" | "account" | "security" | "general";
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

export type WorkflowStepType = "create_task" | "send_notification" | "human_approval";

export type WorkflowStep = {
  step_type: WorkflowStepType;
  config: Record<string, unknown>;
};

export type WorkflowStatus = "draft" | "testing" | "active" | "paused" | "archived";

export type Workflow = {
  id: string;
  name: string;
  description: string | null;
  trigger_type: string;
  status: WorkflowStatus;
  steps: WorkflowStep[];
  version: number;
  owner_id: string | null;
  created_at: string;
};

export type WorkflowRunStatus = "running" | "succeeded" | "failed" | "awaiting_approval";

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
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
};
