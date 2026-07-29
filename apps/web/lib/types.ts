// Mirrors apps/api/app/identity/schemas.py and app/core/schemas.py.
// Phase 2+ should generate this from the OpenAPI schema instead of hand
// maintaining it (see docs/PLATFORM_ARCHITECTURE.md packages/sdk note).

export type User = {
  id: string;
  email: string;
  full_name: string | null;
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
