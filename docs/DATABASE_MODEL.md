# Database Model — Phase 1

PostgreSQL 16 + `pgvector`. SQLAlchemy 2 declarative models, Alembic
migrations. Conventions (spec §E6, §73):

- UUID primary keys (`uuid_generate_v4()` / Python `uuid4`)
- UTC timestamps: `created_at`, `updated_at` on every table
- `created_by` (nullable FK to `users.id`, null for system-generated rows)
- `organization_id` on every tenant-scoped table, indexed, non-nullable
- Foreign keys enforced at the DB level, `ON DELETE RESTRICT` by default for
  referential safety; explicit `CASCADE` only where the child truly cannot
  outlive the parent (e.g. `memberships` → `organizations`)
- No destructive delete on audit-relevant rows — `audit_events` has no
  UPDATE/DELETE grants for the application DB role at all
- Composite index `(organization_id, <common filter column>)` on
  high-traffic tables

## Tables (Phase 1)

```text
organizations
  id UUID PK
  name TEXT NOT NULL
  slug TEXT NOT NULL UNIQUE
  created_at, updated_at

legal_entities
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  name TEXT NOT NULL
  country CHAR(2)
  is_default BOOLEAN NOT NULL DEFAULT false
  created_at, updated_at
  UNIQUE (organization_id, name)

users
  id UUID PK
  email CITEXT NOT NULL UNIQUE
  hashed_password TEXT NOT NULL
  full_name TEXT
  is_active BOOLEAN NOT NULL DEFAULT true
  mfa_enabled BOOLEAN NOT NULL DEFAULT false
  mfa_secret_encrypted TEXT
  email_verified_at TIMESTAMPTZ
  created_at, updated_at

teams
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  name TEXT NOT NULL
  created_at, updated_at
  UNIQUE (organization_id, name)

roles
  id UUID PK
  organization_id UUID FK organizations NULL  -- null = system role, seeded
  key TEXT NOT NULL           -- e.g. "org_admin", "sales_manager"
  name TEXT NOT NULL
  is_system BOOLEAN NOT NULL DEFAULT false
  created_at, updated_at
  UNIQUE (organization_id, key)

permissions
  id UUID PK
  key TEXT NOT NULL UNIQUE    -- e.g. "sales.leads.view"
  description TEXT NOT NULL

role_permissions
  role_id UUID FK roles NOT NULL
  permission_id UUID FK permissions NOT NULL
  PRIMARY KEY (role_id, permission_id)

memberships
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  user_id UUID FK users NOT NULL
  team_id UUID FK teams NULL
  status TEXT NOT NULL DEFAULT 'active'  -- active | invited | suspended
  invited_by UUID FK users NULL
  created_at, updated_at
  UNIQUE (organization_id, user_id)

membership_roles
  membership_id UUID FK memberships NOT NULL
  role_id UUID FK roles NOT NULL
  PRIMARY KEY (membership_id, role_id)

sessions
  id UUID PK
  user_id UUID FK users NOT NULL
  organization_id UUID FK organizations NULL   -- active org context
  session_token_hash TEXT NOT NULL UNIQUE
  user_agent TEXT
  ip_address INET
  expires_at TIMESTAMPTZ NOT NULL
  revoked_at TIMESTAMPTZ
  created_at

tasks
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  title TEXT NOT NULL
  description TEXT
  module TEXT NOT NULL DEFAULT 'core'
  status TEXT NOT NULL DEFAULT 'open'   -- open | in_progress | done | cancelled
  priority TEXT NOT NULL DEFAULT 'normal'
  assignee_id UUID FK users NULL
  due_at TIMESTAMPTZ
  created_at, updated_at

approvals
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  task_id UUID FK tasks NULL
  action_type TEXT NOT NULL         -- e.g. "ai.sales.send_email"
  risk_class TEXT NOT NULL          -- read_only|low|moderate|high|critical
  status TEXT NOT NULL DEFAULT 'pending'  -- pending|approved|rejected|expired
  requested_by UUID FK users NOT NULL
  decided_by UUID FK users NULL
  decided_at TIMESTAMPTZ
  context JSONB NOT NULL DEFAULT '{}'
  created_at, updated_at

files
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  storage_key TEXT NOT NULL UNIQUE
  original_filename TEXT NOT NULL
  content_type TEXT NOT NULL
  size_bytes BIGINT NOT NULL
  classification TEXT NOT NULL DEFAULT 'internal'  -- public|internal|confidential|restricted
  uploaded_by UUID FK users NOT NULL
  created_at

audit_events           -- append-only; app DB role has INSERT+SELECT only
  id UUID PK
  organization_id UUID FK organizations NULL   -- null for platform-level events
  actor_user_id UUID FK users NULL
  action TEXT NOT NULL
  object_type TEXT NOT NULL
  object_id TEXT
  ip_address INET
  user_agent TEXT
  policy_decision TEXT
  before_state JSONB
  after_state JSONB
  correlation_id UUID NOT NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()

ai_runs
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  requested_by UUID FK users NULL
  task_type TEXT NOT NULL
  provider TEXT NOT NULL             -- "demo" | "anthropic" | "openai" | ...
  model TEXT NOT NULL
  prompt_template TEXT
  prompt_version TEXT
  input_classification TEXT NOT NULL DEFAULT 'internal'
  output JSONB
  citations JSONB NOT NULL DEFAULT '[]'
  confidence NUMERIC(4,3)
  latency_ms INTEGER
  policy_result TEXT NOT NULL DEFAULT 'allowed'
  error TEXT
  created_at

notifications
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  user_id UUID FK users NOT NULL
  channel TEXT NOT NULL DEFAULT 'in_app'
  title TEXT NOT NULL
  body TEXT
  link TEXT
  read_at TIMESTAMPTZ
  created_at
```

## Tables (Phase 2 — Knowledge)

```text
knowledge_bases
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  name TEXT NOT NULL
  description TEXT
  created_at, updated_at
  UNIQUE (organization_id, name)

documents
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  knowledge_base_id UUID FK knowledge_bases NOT NULL
  file_id UUID FK files NOT NULL UNIQUE   -- one Document per uploaded File
  title TEXT NOT NULL
  status TEXT NOT NULL DEFAULT 'pending'  -- pending|processing|ready|failed|unsupported_format
  error TEXT
  classification TEXT NOT NULL DEFAULT 'internal'
  created_by UUID FK users NULL
  created_at, updated_at

document_chunks
  id UUID PK
  organization_id UUID FK organizations NOT NULL   -- denormalized for tenant-isolation queries
  document_id UUID FK documents NOT NULL
  chunk_index INTEGER NOT NULL
  content TEXT NOT NULL
  embedding JSONB NOT NULL          -- list[float], length AI.EMBEDDING_DIMENSIONS (1536)
  token_count INTEGER NOT NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  UNIQUE (document_id, chunk_index)
```

`embedding` is a JSON float array, not a native `pgvector` column — see
`docs/DECISIONS.md` ADR-0007. Similarity search
(`app/knowledge/retrieval.py::search_chunks`) scores chunks in Python
rather than via a `<=>` query (ADR-0012); no ivfflat/HNSW index exists.
Fine at current chunk volumes, explicitly not fine at scale — see the
ADR for when this needs to become a real `vector(1536)` column.

## Tables (Phase 3 — Compliance)

```text
frameworks                -- catalog data, NOT tenant-scoped (like system roles)
  id UUID PK
  key TEXT NOT NULL UNIQUE          -- "gdpr" | "eu_ai_act" | "iso27001" | ...
  name TEXT NOT NULL
  description TEXT
  created_at, updated_at

requirements               -- catalog data, NOT tenant-scoped
  id UUID PK
  framework_id UUID FK frameworks NOT NULL
  reference_code TEXT NOT NULL      -- "Art. 30", "A.5.1", ...
  title TEXT NOT NULL
  description TEXT
  UNIQUE (framework_id, reference_code)

controls
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  title TEXT NOT NULL
  description TEXT
  status TEXT NOT NULL DEFAULT 'not_started'  -- not_started|in_progress|implemented|needs_review
  owner_id UUID FK users NULL
  created_at, updated_at

control_mappings           -- many-to-many: which catalog requirements a control satisfies
  control_id UUID FK controls NOT NULL
  requirement_id UUID FK requirements NOT NULL
  PRIMARY KEY (control_id, requirement_id)

control_assessments
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  control_id UUID FK controls NOT NULL
  status TEXT NOT NULL               -- pass|fail|partial|not_assessed
  notes TEXT
  assessed_by UUID FK users NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()

evidence
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  control_id UUID FK controls NULL   -- may stand alone in the evidence library
  file_id UUID FK files NOT NULL     -- reuses the Phase 1 File primitive
  title TEXT NOT NULL
  valid_until TIMESTAMPTZ NULL
  created_by UUID FK users NULL
  created_at, updated_at

risks
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  title TEXT NOT NULL
  description TEXT
  category TEXT NOT NULL DEFAULT 'general'
  likelihood TEXT NOT NULL           -- low|medium|high
  impact TEXT NOT NULL               -- low|medium|high
  status TEXT NOT NULL DEFAULT 'open'  -- open|mitigated|accepted
  control_id UUID FK controls NULL
  owner_id UUID FK users NULL
  created_at, updated_at

policies
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  title TEXT NOT NULL
  file_id UUID FK files NULL
  status TEXT NOT NULL DEFAULT 'draft'  -- draft|published
  owner_id UUID FK users NULL
  created_at, updated_at

ai_systems                 -- AI System Inventory (spec §12/§55, EU AI Act governance)
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  name TEXT NOT NULL
  vendor TEXT NULL
  purpose TEXT NOT NULL
  risk_classification TEXT NOT NULL DEFAULT 'minimal'  -- minimal|limited|high|unacceptable
  status TEXT NOT NULL DEFAULT 'in_review'  -- in_review|approved|rejected|retired
  owner_id UUID FK users NULL
  approval_id UUID FK approvals NULL   -- cross-module hook, see below
  created_at, updated_at

ai_assessments
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  ai_system_id UUID FK ai_systems NOT NULL
  status TEXT NOT NULL               -- pass|fail|partial|not_assessed
  notes TEXT
  assessed_by UUID FK users NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

A failed `control_assessments` row (`status = 'fail'`) automatically
creates a `core.tasks` row (`module = 'compliance'`) via
`app/compliance/service.py::record_assessment` — Phase 3's cross-module
hook (spec §80).

An `ai_systems` row with `risk_classification` of `high` or
`unacceptable` automatically creates a real `approvals` row and sets
`approval_id`, via `app/compliance/service.py::register_ai_system` —
Phase 8's third-and-a-half cross-module hook (spec §69 "New AI Tool
Adoption", ADR-0027). `decide_ai_system_status` refuses to set
`status = 'approved'` while that linked Approval hasn't itself been
granted.

## Tables (Phase 4 — Security)

Code lives in `app/secops/` (not `app/security/` — see `docs/DECISIONS.md`
ADR-0016, naming collision with the Phase 1 password/session module).

```text
security_assets
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  name TEXT NOT NULL
  asset_type TEXT NOT NULL   -- cloud_account|server|container|endpoint|application|api|repository|saas|database|domain|user|privileged_account
  environment TEXT NOT NULL DEFAULT 'production'
  provider TEXT NULL
  criticality TEXT NOT NULL DEFAULT 'medium'   -- low|medium|high|critical
  data_classification TEXT NOT NULL DEFAULT 'internal'
  internet_exposed BOOLEAN NOT NULL DEFAULT false
  status TEXT NOT NULL DEFAULT 'healthy'   -- healthy|at_risk|compromised
  owner_id UUID FK users NULL
  last_observed_at TIMESTAMPTZ NULL
  created_at, updated_at

security_findings        -- consolidates vulnerabilities/cloud_findings/identity_findings (ADR-0017)
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  asset_id UUID FK security_assets NULL
  category TEXT NOT NULL    -- vulnerability|cloud_misconfiguration|identity|other
  title TEXT NOT NULL
  description TEXT
  severity TEXT NOT NULL     -- low|medium|high|critical
  cve TEXT NULL
  status TEXT NOT NULL DEFAULT 'open'   -- open|investigating|resolved|false_positive|risk_accepted
  owner_id UUID FK users NULL
  due_at TIMESTAMPTZ NULL
  created_at, updated_at

security_alerts          -- inbox/triage (spec §18)
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  finding_id UUID FK security_findings NULL
  title TEXT NOT NULL
  description TEXT
  severity TEXT NOT NULL
  status TEXT NOT NULL DEFAULT 'new'   -- new|investigating|contained|resolved|false_positive
  created_at, updated_at

security_incidents       -- escalated workspace (spec §19)
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  title TEXT NOT NULL
  description TEXT
  severity TEXT NOT NULL
  status TEXT NOT NULL DEFAULT 'detected'  -- detected|triage|investigation|containment|eradication|recovery|postmortem|closed
  related_risk_id UUID FK risks NULL   -- cross-module link, see below
  related_task_id UUID FK tasks NULL   -- Phase 8 cross-module link, see below
  owner_id UUID FK users NULL
  closed_at TIMESTAMPTZ NULL
  created_at, updated_at
```

A `critical`-severity `security_incidents` row automatically creates a
`compliance.risks` row (`category='security'`) and sets
`related_risk_id`, via `app/secops/service.py::create_incident` — Phase
4's cross-module hook (spec §19, ADR-0018). The same call also creates a
`tasks` row (`module='security'`, `priority='urgent'`) and sets
`related_task_id`, and sends a `notifications` row to `owner_id` if one
is set — Phase 8's extension of the same hook, completing spec §69's
"Security Incident" chain (ADR-0023).

## Tables (Phase 5 — Sales)

```text
sales_accounts
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  name TEXT NOT NULL
  industry TEXT NULL
  website TEXT NULL
  employee_count INTEGER NULL
  icp_score NUMERIC(5,2) NULL
  status TEXT NOT NULL DEFAULT 'prospect'   -- prospect|customer|churned
  owner_id UUID FK users NULL
  created_at, updated_at

sales_contacts
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  account_id UUID FK sales_accounts NULL
  full_name TEXT NOT NULL
  email TEXT NOT NULL
  job_title TEXT NULL
  do_not_contact BOOLEAN NOT NULL DEFAULT false   -- suppression flag, see below
  created_at, updated_at

sales_leads
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  account_id UUID FK sales_accounts NULL
  contact_id UUID FK sales_contacts NULL
  source TEXT NULL
  status TEXT NOT NULL DEFAULT 'new'   -- new|qualified|contacted|disqualified|converted
  score NUMERIC(5,2) NULL
  created_at, updated_at

sales_opportunities
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  account_id UUID FK sales_accounts NOT NULL
  title TEXT NOT NULL
  stage TEXT NOT NULL DEFAULT 'prospecting'  -- prospecting|qualification|proposal|negotiation|closed_won|closed_lost
  value NUMERIC(12,2) NULL
  probability NUMERIC(5,2) NULL
  expected_close_at TIMESTAMPTZ NULL
  owner_id UUID FK users NULL
  onboarding_customer_id UUID FK support_customers NULL   -- Phase 8 cross-module hook, see below
  created_at, updated_at

sales_outreach_messages
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  contact_id UUID FK sales_contacts NOT NULL
  channel TEXT NOT NULL DEFAULT 'email'   -- email|linkedin
  subject TEXT NULL
  body TEXT NOT NULL
  status TEXT NOT NULL DEFAULT 'draft'   -- draft|sent|blocked
  blocked_reason TEXT NULL
  created_by UUID FK users NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  sent_at TIMESTAMPTZ NULL
```

## Tables (Phase 6 — Customer Support)

```text
support_customers
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  sales_account_id UUID FK sales_accounts NULL   -- links a converted Sales Account, spec §69
  name TEXT NOT NULL
  email TEXT NOT NULL
  plan TEXT NULL
  status TEXT NOT NULL DEFAULT 'active'   -- active|churned
  created_at, updated_at

support_tickets
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  customer_id UUID FK support_customers NOT NULL
  subject TEXT NOT NULL
  description TEXT NULL
  channel TEXT NOT NULL DEFAULT 'email'   -- email|chat|api
  category TEXT NOT NULL DEFAULT 'general'   -- billing|technical|account|security|general
  priority TEXT NOT NULL DEFAULT 'medium'   -- low|medium|high|urgent
  status TEXT NOT NULL DEFAULT 'open'   -- open|pending|resolved|closed
  owner_id UUID FK users NULL
  related_alert_id UUID FK security_alerts NULL   -- Phase 6 cross-module hook, see below
  upsell_lead_id UUID FK sales_leads NULL   -- Phase 8 cross-module hook, see below
  resolved_at TIMESTAMPTZ NULL
  created_at, updated_at

support_ticket_messages
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  ticket_id UUID FK support_tickets NOT NULL
  sender_type TEXT NOT NULL   -- customer|agent|ai
  author_id UUID FK users NULL
  body TEXT NOT NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()

support_knowledge_articles
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  title TEXT NOT NULL
  body TEXT NOT NULL
  category TEXT NULL
  published BOOLEAN NOT NULL DEFAULT false
  created_at, updated_at

support_csat_responses
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  ticket_id UUID FK support_tickets NOT NULL
  score INTEGER NOT NULL   -- 1-5
  comment TEXT NULL
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

`support_conversations` and `support_intents` from the spec's data model
(§46) are deliberately not separate tables — a conversation *is* a ticket
here, and intent is `Ticket.category`, the same consolidation already
applied to Security's findings (ADR-0017). `support_slas` and
`support_qa_reviews` are not modeled yet; see `docs/KNOWN_LIMITATIONS.md`.

`Ticket.upsell_lead_id` is set by `app/support/service.py::flag_upsell_signal`
(Phase 8, spec §69 "Support Upsell Signal", ADR-0022) — it creates a real
`sales_leads` row (`source = 'support_upsell_signal'`) and a Notification
to the linked account's owner, reusing Sales' and Phase 1's existing
tables rather than a new signal-specific one.

An outreach message can only move from `draft` to `sent` if
`sales_contacts.do_not_contact` is false at send time; otherwise it moves
to `blocked` instead, via `app/sales/service.py::send_outreach_message`
— Phase 5's cross-module hook (spec §91, ADR-0019). No real email/
LinkedIn provider is wired up yet — sending only transitions this row.

`sales_opportunities.onboarding_customer_id` is set by
`app/sales/service.py::close_opportunity_won` the first time an
opportunity transitions to `closed_won` (Phase 8, spec §69 "New
Customer", ADR-0025) — it creates a real `support_customers` row (using
the account's earliest Contact for the required email) and a `tasks` row
due in 7 days, reusing Phase 6's and Phase 1's existing tables. Its
presence is also the idempotency guard: a later closed_won transition is
a no-op.

## Tables (Phase 7 — Business Automation)

```text
automation_workflows
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  name TEXT NOT NULL
  description TEXT NULL
  trigger_type TEXT NOT NULL DEFAULT 'manual'   -- manual|webhook (Phase 9)
  status TEXT NOT NULL DEFAULT 'draft'   -- draft|testing|active|paused|archived
  steps JSON NOT NULL DEFAULT '[]'   -- ordered [{step_type, config}, ...]
  version INTEGER NOT NULL DEFAULT 1
  owner_id UUID FK users NULL
  created_at, updated_at

automation_workflow_runs
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  workflow_id UUID FK automation_workflows NOT NULL
  status TEXT NOT NULL DEFAULT 'running'   -- running|succeeded|failed|awaiting_approval
  trigger_payload JSON NULL
  triggered_by UUID FK users NULL
  started_at TIMESTAMPTZ NOT NULL DEFAULT now()
  completed_at TIMESTAMPTZ NULL

automation_workflow_step_runs
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  run_id UUID FK automation_workflow_runs NOT NULL
  step_index INTEGER NOT NULL
  step_type TEXT NOT NULL
  status TEXT NOT NULL   -- succeeded|failed|awaiting_approval
  output JSON NULL
  approval_id UUID FK approvals NULL   -- cross-module hook, see below
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
```

`Workflow.steps` only supports three step types in this build —
`create_task`, `send_notification`, `human_approval` — out of the much
larger vocabulary spec §37 describes (Condition/Delay/Loop/Data
Transform/Webhook/Subworkflow/AI Step are not implemented; see
`docs/KNOWN_LIMITATIONS.md`). A `human_approval` step run creates a real
row in the existing `approvals` table (Phase 1) and pauses the run at
`awaiting_approval` until that Approval is decided through
`/api/v1/approvals/{id}/decide` — ADR-0021. Workflow steps can only be
edited via `PATCH /workflows/{id}/steps` while `status = 'draft'`.

## Tables (Phase 9 — Integrations)

```text
integration_connections
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  connector_key TEXT NOT NULL DEFAULT 'webhook'   -- "webhook" | "hubspot"
  name TEXT NOT NULL
  status TEXT NOT NULL DEFAULT 'active'
    -- webhook: active|disabled — oauth2: not_connected|connected|error|disconnected
  webhook_secret TEXT NULL   -- HMAC-SHA256 key, webhook connections only
  linked_workflow_id UUID FK automation_workflows NULL   -- webhook cross-module hook, see below
  encrypted_access_token TEXT NULL    -- Fernet-encrypted, oauth2 connections only
  encrypted_refresh_token TEXT NULL   -- Fernet-encrypted, oauth2 connections only
  token_expires_at TIMESTAMPTZ NULL
  scopes JSON NULL                    -- list[str]
  external_account_id TEXT NULL       -- e.g. HubSpot portal ("hub") id
  oauth_state TEXT NULL               -- single-use CSRF token, cleared after callback
  oauth_state_created_at TIMESTAMPTZ NULL
  health_status TEXT NULL             -- ok|error, set by the health-check endpoint
  last_health_check_at TIMESTAMPTZ NULL
  last_synced_at TIMESTAMPTZ NULL
  last_error TEXT NULL
  created_by UUID FK users NULL
  created_at, updated_at

integration_webhook_events
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  connection_id UUID FK integration_connections NOT NULL
  verified BOOLEAN NOT NULL
  payload JSON NULL
  triggered_run_id UUID FK automation_workflow_runs NULL
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()

integration_sync_runs
  id UUID PK
  organization_id UUID FK organizations NOT NULL
  connection_id UUID FK integration_connections NOT NULL
  status TEXT NOT NULL DEFAULT 'running'   -- running|succeeded|failed
  items_synced INTEGER NULL
  error TEXT NULL
  started_at TIMESTAMPTZ NOT NULL DEFAULT now()
  completed_at TIMESTAMPTZ NULL
```

Every inbound call to `POST /api/v1/integrations/webhooks/{connection_id}/receive`
is recorded as a `WebhookEvent`, verified or not (spec §49's "Last sync,
Last error" requirement, at individual-event granularity). A verified
event on a connection whose `linked_workflow_id` points at an `active`
workflow with `trigger_type='webhook'` triggers that workflow via
`app.automation.service.start_run`, giving Automation its first
non-manual trigger without a second execution engine —
`app/integrations/service.py::receive_webhook_event`, ADR-0024.

The OAuth2 connector shape (`connector_key='hubspot'` today) stores
encrypted access/refresh tokens rather than plaintext (`app/core/crypto.py`,
Fernet). `oauth_state` is the authorize→callback round trip's own
single-use CSRF token — the callback route has no session, so this
column (checked for a 10-minute TTL) is what proves a callback belongs to
a pending connection, not a cookie. `integration_sync_runs` records each
"sync now" execution (spec §49's `sync()`), run synchronously inline
rather than as a durable Temporal job — see ADR-0026 and
`docs/KNOWN_LIMITATIONS.md`.

## Migration policy

- Every schema change ships an Alembic revision with both `upgrade()` and
  `downgrade()` where feasible (spec §E6).
- No implicit schema changes at app startup — migrations run explicitly via
  `alembic upgrade head` (CI and deploy pipeline step).
