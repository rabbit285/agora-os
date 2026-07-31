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
  { key: "find_more_customers", label: "Find more customers" },
  { key: "automate_customer_support", label: "Automate customer support" },
  { key: "automate_business_operations", label: "Automate business operations" },
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
  compliance: ReadinessDimension;
  security: ReadinessDimension;
  sales_automation: ReadinessDimension;
  support_automation: ReadinessDimension;
  process_automation: ReadinessDimension;
  opportunities: ReadinessOpportunity[];
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

export const NOTIFICATION_CHANNELS = ["email", "slack", "teams", "webhook"] as const;

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

export type Policy = {
  id: string;
  title: string;
  file_id: string | null;
  status: "draft" | "published";
  owner_id: string | null;
  created_at: string;
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

export type WorkflowStatus = "draft" | "testing" | "active" | "paused" | "archived";

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
};

export type SearchResponse = {
  query: string;
  results: SearchResult[];
};
