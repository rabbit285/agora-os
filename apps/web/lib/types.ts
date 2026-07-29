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
