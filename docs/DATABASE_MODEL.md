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

## Migration policy

- Every schema change ships an Alembic revision with both `upgrade()` and
  `downgrade()` where feasible (spec §E6).
- No implicit schema changes at app startup — migrations run explicitly via
  `alembic upgrade head` (CI and deploy pipeline step).
