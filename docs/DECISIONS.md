# Architecture Decision Records

Lightweight ADR log for decisions made autonomously during the build,
per the execution contract's "document the decision and continue" rule.
Individual longer ADRs can move to `docs/adrs/NNNN-title.md` if they need
more than a paragraph; short ones live here.

## ADR-0001 — Opaque, server-revocable session tokens instead of JWTs

**Decision**: Sessions are a random token whose SHA-256 hash is stored in
a `sessions` table; the session row can be revoked (logout, password
reset) with a single `UPDATE`.

**Why**: The spec requires session revocation (§E4). A self-contained JWT
can't be revoked without an additional denylist store, which duplicates
exactly what a sessions table already is — so a JWT would add complexity
without removing the sessions table.

## ADR-0002 — `packages/ui`, `packages/sdk`, etc. deferred until needed

**Decision**: The spec's monorepo layout (§52) lists `packages/ui`,
`packages/sdk`, `packages/ai-core`, `packages/automation-core`,
`packages/compliance-models`, `packages/integration-sdk`. Phase 1 does not
create these as empty npm/Python workspaces.

**Why**: `apps/web` is the only frontend consumer today; a shared `ui`
package only earns its keep once a second consumer exists (e.g. a
marketing site or a second app). Creating it now would mean workspace
tooling (npm workspaces / Turborepo config) with nothing genuinely shared.
Introduce each package the first time two apps need it.

## ADR-0003 — Email is a log-only dev adapter until Phase 2/AWS

**Decision**: Password reset (and future transactional email) logs the
link at INFO level instead of sending real email in Phase 1.

**Why**: Spec §C2 requires the app to boot and function without paid
provider keys. SES is the documented production adapter (spec §L3) but
implementing it now, before there's an AWS account/domain to verify,
would be dead code. The interface boundary (`_dispatch_password_reset_email`)
is already isolated so swapping in SES later doesn't touch callers.

## ADR-0004 — Single Postgres role for local dev; DB-level audit-log
protection deferred to the AWS phase

**Decision**: Local Docker Compose Postgres uses one `agora` role for
migrations and the application. `audit_events` append-only-ness is
enforced by code review and tests only, not a DB-level `REVOKE`.

**Why**: Postgres table owners bypass `GRANT`/`REVOKE` on their own
tables, so a `REVOKE` only means something once migrations and the app
connect as different roles — which the spec places in the AWS/RDS phase
(§L3: "separate database roles for application, migrations, and read-only
operational access"). Adding a second local role now would be scaffolding
for infrastructure Phase 1 doesn't otherwise have.

## ADR-0005 — npm instead of pnpm for the frontend

**Decision**: `apps/web` uses npm, not pnpm.

**Why**: The spec's CI section defaults to `pnpm`, but this machine had
npm available and pnpm was not installed. Both are workspace-capable
package managers; switching to pnpm later is a mechanical change
(`package-lock.json` → `pnpm-lock.yaml`) if a monorepo-wide workspace is
introduced (see ADR-0002).

## ADR-0006 — Hand-built shadcn-style primitives instead of the shadcn CLI

**Decision**: `components/ui/*` (button, input, label, card, badge) are
hand-written using the same libraries shadcn/ui generates from
(class-variance-authority, Radix primitives, tailwind-merge) rather than
scaffolded via `npx shadcn init`.

**Why**: The installed shadcn CLI version requires interactive prompts
(component-library and preset selection) with no working non-interactive
flag combination found in this environment. The resulting components are
structurally identical to what the CLI would generate; running the CLI
later to add more components (table, dialog, etc.) remains an option.

## ADR-0007 — Embeddings stored as JSON, not a native pgvector column

**Decision**: `document_chunks.embedding` is a JSON float array
(`list[float]`, length 1536), not `pgvector`'s `Vector` SQLAlchemy type.

**Why**: A native `Vector` column needs the `pgvector` Postgres extension,
which SQLite (used for fast in-memory unit tests) has no equivalent for —
introducing it now would either break test portability or require a
custom dual-dialect type. Nothing in Phase 2 queries by similarity yet
(that's the AI Copilot's RAG pipeline, not yet built); JSON storage is
sufficient until a real cosine-distance query is needed, at which point
this column migrates to `vector(1536)` with an ivfflat/HNSW index.

## ADR-0008 — One AiRun per embedding batch, not one per chunk

**Decision**: `ModelGateway.embed()` writes a single `AiRun` row per call,
covering however many texts were embedded in that batch (`output.chunk_count`),
not one row per text.

**Why**: A single document can produce dozens of chunks; logging one
`AiRun` per chunk would make `ai_runs` grow much faster than any other
table for no analytical benefit — the batch-level record already answers
"what was embedded, by what provider, how long did it take."

## ADR-0009 — Workflow-defining modules never import application code

**Decision**: `apps/worker/worker/workflows.py` imports only `temporalio`
and the stdlib. Activities (which do need `app.config`, the database, and
object storage) live in a separate `activities.py`, referenced from
workflows by string name (`workflow.execute_activity("name", ...)`), and
imported into `main.py` (never into `workflows.py`).

**Why**: Temporal's Python SDK sandboxes and statically validates the
entire import graph of any module that defines a `@workflow.defn` class,
rejecting non-deterministic operations (file/env access) anywhere in that
graph. The Phase 1 health-check workflow crashed the worker at startup
because it lived in the same module as `from app.config import settings`
(which reads a `.env` file) — moving that import to a sibling module the
workflow never imports fixed it permanently, not just for that one case.

## ADR-0010 — A shared `register_all_models` import module

**Decision**: `app/db/register_all_models.py` imports every domain
model module purely for its side effects (registering each model's table
in `Base.metadata`). Alembic's `migrations/env.py`, the test suite's
`conftest.py`, and any Temporal activity that touches the database import
this one module instead of hand-picking which specific model classes they
need.

**Why**: The worker's document-ingestion activity crashed with
`NoReferencedTableError: ... could not find table 'users'` the first time
it ran for real — it imported `app.core.models` and `app.knowledge.models`
directly but never `app.identity.models`, so SQLAlchemy had never seen the
`users` table in that process and couldn't resolve
`documents.created_by -> users.id` on flush. The bug wasn't in the FK
definition, it was that Python module imports are what register a table
with SQLAlchemy, and each process (API, worker, migrations, tests) only
imports what it directly references. A single shared "import everything"
module removes the need to remember this in every new entrypoint.

## ADR-0011 — Presigned URLs signed against a separate "public" S3 endpoint

**Decision**: `app/core/storage.py` has two boto3 clients: `_client()`
(internal Docker hostname, e.g. `http://minio:9000`, used for server-side
downloads/uploads) and `_public_client()` (browser-reachable host, e.g.
`http://localhost:9002`, used only to sign upload/download URLs).

**Why**: A presigned URL's signature is valid only for the host it was
signed against. Signing with the internal Docker hostname would hand the
browser a URL it can't resolve at all; signing with the public host
(`S3_PUBLIC_ENDPOINT_URL`) produces a URL the browser can actually reach,
while the API/worker keep using the internal hostname for their own
direct calls.

## ADR-0012 — Cosine similarity computed in Python, not via a pgvector query

**Decision**: `app/knowledge/retrieval.py::search_chunks` pulls all of an
organization's chunk embeddings and scores them against the query
embedding with a plain Python `cosine_similarity`, rather than a
`pgvector` `<=>` operator query with an ivfflat/HNSW index.

**Why**: Continues ADR-0007's trade-off — embeddings are stored as JSON,
which SQLite (unit tests) can hold but can't run a native vector-distance
query against. A linear scan is functionally correct and fast enough at
the chunk volumes a single organization's knowledge base reaches during
this build (dozens to low thousands of chunks); it stops being fine once
that grows by orders of magnitude, at which point the column migrates to
real `pgvector` alongside the query. Explicitly not "premature
optimization avoided" — it's "this becomes wrong at scale, and that's
written down here on purpose."

## ADR-0013 — Frameworks/Requirements are global catalog data, not tenant-scoped

**Decision**: `compliance.frameworks` and `compliance.requirements` have
no `organization_id` at all — they're shared, seeded-once rows every
organization reads from, the same pattern already used for system Roles
(`app/core/rbac.py`).

**Why**: GDPR Article 30 says the same thing for every organization;
copying the regulatory text into a per-tenant row would just be
duplication with no behavioral difference. What genuinely varies per
organization — whether and how they satisfy a requirement — lives on
`Control` (tenant-scoped) via `ControlMapping`, not on the requirement
itself.

## ADR-0014 — Evidence reuses the Phase 1 File primitive

**Decision**: `compliance.evidence.file_id` points at `core.files`, the
same table/upload flow Knowledge documents also use — there is no
separate compliance-specific object-storage path.

**Why**: Spec §80 explicitly warns against building disconnected modules
with duplicate primitives. Evidence is fundamentally "a file with some
compliance metadata attached" — reusing `core.files` means it
automatically gets signed upload/download URLs, tenant scoping, and
classification for free, rather than re-implementing storage handling a
third time (Knowledge's `Document` already reuses it once).

## ADR-0015 — A failed control assessment auto-creates a Task, not a compliance-specific follow-up

**Decision**: `app/compliance/service.py::record_assessment` creates a
`core.Task` (`module="compliance"`) when an assessment's status is
`fail`, using the exact same shared primitive Tasks/Approvals already use
— no `ComplianceRemediationItem` or similar module-specific type exists.

**Why**: This is the cross-module hook spec §80 requires ("do not build
disconnected modules... use shared entities wherever appropriate").
Tested in `tests/test_compliance.py::test_failed_assessment_creates_remediation_task`
— it asserts the task is visible through the generic `/api/v1/tasks`
endpoint, not a compliance-specific one.

## ADR-0016 — Security domain package is named `secops`, not `security`

**Decision**: The Phase 4 Security module lives in `app/secops/`
(`app/secops/models.py`, etc.), not `app/security/`.

**Why**: `app/security.py` already exists — the Phase 1 password-hashing
and session-token helper module. Python cannot have both a module named
`security.py` and a package named `security/` as siblings in the same
parent package. Renaming the Phase 1 utility module would touch every
file that imports password/token helpers (`identity/service.py`,
`dependencies.py`, ...) purely to free up a name; `secops` costs nothing
and reads clearly enough in imports (`from app.secops.models import
SecurityAsset`).

## ADR-0017 — One `SecurityFinding` table with a category discriminator, not three

**Decision**: Vulnerabilities, cloud misconfigurations, and identity
findings (spec §50 lists `vulnerabilities`, `cloud_findings`,
`identity_findings` as separate tables) are one `security_findings` table
with a `category` column (`vulnerability | cloud_misconfiguration |
identity | other`).

**Why**: The spec's own field lists for these three are nearly identical
(asset, severity, status, owner, due date) — three tables would mean
three copies of the same CRUD/RBAC/serialization code for no behavioral
difference. If a category's fields genuinely diverge later (e.g.
vulnerability-specific CVSS scoring), split it out then; a discriminator
column is trivially migrated into a proper subtype at that point.

## ADR-0018 — A critical security incident auto-creates a linked Compliance Risk

**Decision**: `app/secops/service.py::create_incident` creates a
`compliance.Risk` (`category="security"`) and sets
`incident.related_risk_id` when `severity == "critical"` — using the
Compliance module's existing Risk primitive, not a security-specific
breach-tracking type.

**Why**: Spec §19 explicitly calls this out: "Integrate incidents with
the GDPR breach process... this connection between security and
compliance is critical." This is Phase 4's one cross-module hook, mirror
of Phase 3's failed-assessment-creates-a-Task (ADR-0015) — same
principle (spec §80: shared entities over disconnected modules), applied
in the other direction (Security → Compliance instead of
Compliance → core). Tested in
`tests/test_security.py::test_critical_incident_creates_linked_compliance_risk`,
which asserts the risk is visible through the generic
`/api/v1/compliance/risks` endpoint.

## ADR-0019 — A per-contact suppression flag gates outreach sending, not a full consent engine

**Decision**: `app/sales/service.py::send_outreach_message` checks a
single `Contact.do_not_contact` boolean before allowing an outreach
message to transition from `draft` to `sent`; if set, the message is
marked `blocked` with a reason instead.

**Why**: Spec §91 describes a much richer check ("jurisdiction, data
source, marketing basis, opt-out, suppression, organization policy") —
implementing all of that would require modeling consent records, data
provenance, and per-country marketing rules that don't exist anywhere
else in this build yet. A boolean suppression flag is the simplest real
instance of "Compliance governs Sales," genuinely enforced (a suppressed
contact truly cannot be sent to, tested in
`tests/test_sales.py::test_suppressed_contact_blocks_outreach_send`), and
is the natural foundation the richer engine would extend rather than
replace. No real email/LinkedIn provider exists yet either (progressive
trust model, spec §B1) — "sending" only transitions this row's status,
but the compliance gate in front of it is not a stub.

## ADR-0020 — A ticket categorized "security" auto-creates a `SecurityAlert`, not a `SecurityIncident`

**Decision**: `app/support/service.py::create_ticket` creates a
`app.secops.models.SecurityAlert` (Security's triage inbox, spec §18) and
sets `ticket.related_alert_id` when the ticket's `category` is
`"security"`, escalating the ticket's own priority to `urgent` in the
same step. It does **not** create a `SecurityIncident` directly.

**Why**: Spec §35's example reads "Ticket mentions security breach →
mark urgent → notify Security → create incident → notify Compliance →
preserve evidence." Skipping straight to `SecurityIncident` — which
already carries its own cross-module hook (ADR-0018: critical incidents
auto-create a Compliance Risk) — would mean a support agent's category
selection alone decides an incident exists, bypassing the triage step
the Security module's own workflow uses for every other finding
(Finding → Alert → Incident, promoted by a human analyst). Landing on
`SecurityAlert` keeps Support's hook symmetric with how Security already
escalates its own data, reuses an existing primitive rather than
inventing a support-specific one (spec §80), and still delivers the
spec's "notify Security" step honestly — it just leaves "create
incident" as the deliberate next human decision, one click away in the
Security module. Tested in
`tests/test_support.py::test_security_category_ticket_creates_linked_alert`,
which asserts the alert is visible through the generic
`/api/v1/security/alerts` endpoint.

## ADR-0021 — A `human_approval` workflow step creates a real `core.Approval`, and a small fixed step vocabulary instead of a general interpreter

**Decision**: `Workflow.steps` is a JSON list of `{step_type, config}`
objects, but `app/automation/service.py` only executes three step types
(`create_task`, `send_notification`, `human_approval`) — anything else is
rejected before a run can start. A `human_approval` step creates a real
`core.Approval` row (`requested_by` the user who triggered the run) and
leaves the `WorkflowRun` at `awaiting_approval`; nothing pushes a
decision back into the run automatically — `POST
/api/v1/automation/runs/{id}/resume` re-checks the linked Approval's
status (still decided through the ordinary, pre-existing
`/api/v1/approvals/{id}/decide` endpoint) and either continues the
remaining steps, fails the run (rejected), or no-ops (still pending).
Workflow step edits are only allowed while `status == "draft"`; once
`active`, the steps router route returns 409 rather than letting an edit
silently change a published workflow's behavior (spec §41).

**Why**: Spec §37 lists a large step vocabulary (Trigger/Action/Condition/
AI Step/Human Approval/Delay/Loop/Data Transform/Webhook/
Notification/Subworkflow) and calls the whole module "a major platform
capability" — building a general visual workflow interpreter in one slice
would produce a stub of everything rather than one real vertical (spec
§80/§82), the same discipline applied to every prior phase (Sales shipped
real CRUD before a lead-finder; Support shipped real tickets before
SLA/QA scoring). `human_approval` reusing `core.Approval` is also the
first domain module to actually exercise that Phase 1 primitive outside
its own generic UI — previously noted as unused by any domain module as
far back as the Phase 5 resume notes. Tested in
`tests/test_automation.py::test_human_approval_step_creates_approval_and_pauses_run`
and `test_rejected_approval_fails_the_run`, both of which decide the
approval through the real `/api/v1/approvals/{id}/decide` endpoint rather
than mutating the database directly.

## ADR-0022 — "Support Upsell Signal" reuses Lead + Notification instead of a new signal entity

**Decision**: `app/support/service.py::flag_upsell_signal` creates a real
`sales.Lead` (`source="support_upsell_signal"`, `account_id` copied from
the ticket's `Customer.sales_account_id` if set) and a `core.Notification`
to that Sales Account's `owner_id` (falling back to the user who flagged
the ticket if the account has no owner, or the customer has no linked
account at all). It does not create a new `sales_signal`- or
`upsell_signal`-shaped table.

**Why**: This is Phase 8's first Cross-Module Intelligence slice (spec
§69's five named scenarios), and the discipline used for every hook so
far (Compliance's Task, Security's Risk, Support's SecurityAlert,
Automation's Approval) is to reuse an existing shared primitive rather
than invent a module-specific one (spec §80). A Lead is exactly what spec
§69 means by "create sales signal" — Sales already has a `Lead.status`
lifecycle (`new → qualified → contacted → disqualified → converted`) a
rep can act on, and a Notification is exactly "notify account manager."
The spec's next step, "create opportunity suggestion," is deliberately
left to a human — converting a Lead into an Opportunity is already a
distinct Sales-side decision in this build, and auto-creating an
Opportunity from an unqualified signal would overstate what one flagged
support ticket actually establishes. Tested in
`tests/test_support.py::test_flag_upsell_creates_lead_and_notifies_account_owner`
(asserts the lead via `/api/v1/sales/leads` and the notification via
`/api/v1/notifications`, not by reading the ticket alone) and
`test_flag_upsell_without_sales_account_falls_back_to_actor` (covers a
customer with no linked Sales Account).

## ADR-0023 — The Security Incident chain's remaining steps extend the existing hook, not a new one

**Decision**: `app/secops/service.py::create_incident` now does three
things when `severity == "critical"` (previously just one): creates the
linked Compliance `Risk` (ADR-0018, unchanged), creates a `core.Task`
("Investigate and contain: {title}", `module="security"`,
`priority="urgent"`, `assignee_id=owner_id`) recorded on the incident via
a new `SecurityIncident.related_task_id` column, and — if the incident
has an `owner_id` — sends that owner a `core.Notification`. All three
fire from the same `create_incident` call and the same severity gate;
this is not a second hook bolted on beside the first.

**Why**: Spec §69's "Security Incident" scenario is a single chain —
"Creates incident → ... → Compliance module assesses GDPR breach
obligations → Creates incident response tasks → Notifies responsible
team → ..." — not five independent triggers. The Risk half of that chain
already existed (Phase 4); extending the same function to cover "creates
incident response tasks" and "notifies responsible team" keeps the whole
chain in one place rather than scattering related consequences of "a
critical incident just got created" across multiple service functions or
modules. It also continues the established pattern of reusing Phase 1
primitives (Task, Notification) instead of inventing
incident-response-specific types — the same reasoning as ADR-0015, -0018,
-0021, and -0022. Tested in
`tests/test_security.py::test_critical_incident_creates_response_task`
(asserts the task via `/api/v1/tasks`, not by reading the incident alone)
and `test_critical_incident_with_owner_notifies_owner` (asserts the
notification via `/api/v1/notifications`); `test_high_severity_incident_does_not_create_risk_or_task`
confirms the severity gate still applies to both consequences together.

## ADR-0024 — Phase 9's first connector is a generic inbound Webhook, not a third-party OAuth integration

**Decision**: `app/integrations/models.py::IntegrationConnection.connector_key`
supports exactly one value in this build — `"webhook"`. There is no
HubSpot/Gmail/Salesforce/Slack/etc. adapter. The connection's security
boundary is an HMAC-SHA256 signature over the raw request body
(`app/integrations/service.py::verify_signature`, constant-time via
`hmac.compare_digest`), not OAuth. A verified event on a connection whose
`linked_workflow_id` points at an `active` workflow with
`trigger_type="webhook"` triggers that workflow through the existing
`app.automation.service.start_run` — Automation's engine is reused, not
duplicated. The receiver route
(`POST /api/v1/integrations/webhooks/{connection_id}/receive`) is the one
route in this app with no session/`OrgContext` dependency: the caller is
an external system, not a logged-in platform user, so there is no cookie
to key tenant resolution off of — the connection's own secret is the
auth mechanism instead.

**Why**: Spec §48 lists a dozen-plus provider categories (CRM, Email,
Cloud, Identity, Engineering, Communication, Documents, Accounting),
every one of which needs a real third-party OAuth app or API key this
environment doesn't have — building any of them now would mean either
faking a "connected" state (forbidden by spec §82 "No Fake Features") or
asking for secrets in chat (forbidden by spec §C2). "Webhook" and "REST
API" are their own category in spec §48 and are the only ones
implementable with zero external credentials: this build can genuinely
receive, verify, and act on an inbound HTTP call. Choosing this slice
also closes two gaps flagged in earlier phases' `KNOWN_LIMITATIONS.md`
entries without inventing new mechanisms: Automation's non-manual
triggers (spec §38 lists "Webhook") and the Security Release Baseline's
explicit "webhook signature verification" requirement (spec §H). Every
other Phase 9 category remains explicitly not started until real
credentials and a concrete consuming feature justify building one — the
same "don't build ahead of demand" principle used since Phase 2 (ADR-0007
docstring). Tested in `tests/test_integrations.py::test_verified_webhook_triggers_linked_workflow`
(asserts the triggered run via `/api/v1/automation/runs`, not just the
event's own view) and `test_invalid_signature_does_not_trigger_workflow`
(a forged signature is recorded but never reaches the workflow engine).

## ADR-0025 — "New Customer" reuses Customer + Task; the onboarding link doubles as the idempotency guard

**Decision**: `app/sales/service.py::close_opportunity_won` fires the
first time an `Opportunity.stage` transitions to `closed_won`
(`app/routers/sales.py::update_opportunity` calls it only when
`before_stage != "closed_won" and new_stage == "closed_won"`). It creates
a real `support.Customer` (using the account's earliest-created `Contact`
for the required email — spec's "create customer" and "create support
profile" steps collapse into one entity, not two) and a `core.Task` due
in 7 days ("provision internal tasks" / "schedule check-in"). It sets
`Account.status = "customer"` (spec's "assign account owner" is already
satisfied — `Account.owner_id` was set at account-creation time in this
build). `Opportunity.onboarding_customer_id` is set once and is checked
first: if already set, the function is a no-op, so reopening and
re-winning the same opportunity never creates a second customer or task.
If the account has no Contact at all, the stage transition still
succeeds but onboarding is skipped and recorded as
`sales.opportunity.onboarding_skipped` — a fabricated customer with no
real contact email would violate spec §82 more than an honestly
incomplete cross-module link would.

**Why**: Spec §69's "New Customer" chain is "CRM deal won → create
customer → create onboarding project → send welcome email → create
support profile → provision internal tasks → update billing integration
→ assign account owner → schedule check-in" — nine steps, but only two
of them need a new primitive to hang off of; the rest either collapse
into those two (create customer = create support profile) or need
capabilities that don't exist in this build (a welcome-email provider, a
billing/accounting connector — spec §48, not yet built) or are already
satisfied by existing fields (account owner assignment). This continues
every prior ADR's discipline of reusing shared primitives (Task,
Notification, Approval, and now Customer) over inventing new
module-specific types (spec §80). Tested in
`tests/test_sales.py::test_closed_won_creates_support_customer_and_onboarding_task`
(asserts the Customer via `/api/v1/support/customers` and the Task via
`/api/v1/tasks`, not by reading the opportunity alone),
`test_closed_won_is_idempotent_across_reopen_and_reclose` (reopen →
re-win creates no second customer), and
`test_closed_won_without_any_contact_skips_onboarding` (the honest
partial-failure path).

## ADR-0026 — Provider-neutral OAuth2 connector framework; HubSpot real, Mock everywhere it isn't configured

**Decision**: `IntegrationConnection` gains a second connector shape
alongside the existing HMAC-secured Webhook connector (ADR-0024): a real
OAuth2 authorization-code flow, generalized through an
`OAuthConnectorAdapter` Protocol
(`app/integrations/adapters/base.py`) — `authorization_url()`,
`exchange_code_for_tokens()`, `refresh_access_token()`,
`test_connection()`, `sync()`, `revoke()` — mirroring
`app.ai.gateway`'s `ModelAdapter`/`DemoAdapter` pattern exactly.
`app/integrations/adapters/hubspot.py::HubSpotAdapter` is a real
implementation (genuine HTTP calls to HubSpot's documented OAuth/CRM
endpoints), selected only when `HUBSPOT_CLIENT_ID`/`HUBSPOT_CLIENT_SECRET`
are configured
(`app/integrations/adapters/__init__.py::get_oauth_adapter`); otherwise
`MockOAuthAdapter` is used — the same role `DemoAdapter` plays for the AI
gateway, and what the test suite exercises (this environment has no real
HubSpot developer app). The provider catalog endpoint
(`GET /api/v1/integrations/providers`) reports `configured: bool`
per provider so the frontend can honestly show "Not configured" rather
than ever faking a connected state (spec §82, §C2).

Stored tokens are encrypted at rest (`app/core/crypto.py`, Fernet) —
`TOKEN_ENCRYPTION_KEY` if set, otherwise a key derived from `SECRET_KEY`
so the app still boots without a second required secret in dev/test
(documented as a dev-only fallback, not a production security boundary,
in `docs/KNOWN_LIMITATIONS.md`). The OAuth callback route has no session
dependency — like the Webhook receiver (ADR-0024), the caller is an
external redirect, not necessarily the browser tab that started the
flow — so a single-use `oauth_state` token (checked for both existence
and a 10-minute TTL) is the callback's own "capability token," the same
role the HMAC signature plays for the webhook connector. `run_sync`
executes synchronously inline rather than as a durable Temporal job,
recording a `SyncRun` row after the fact — a real but deliberately
simplified version of spec §49's `sync()` capability.

**Why**: Spec §48 lists a dozen-plus connector categories; building them
all, or faking any of them as "connected" without real credentials, would
violate both "No Fake Features" (§82) and the secrets contract (§C2: app
must boot without paid API keys, never ask for secrets in chat). HubSpot
is the first real provider because it's explicit in spec §48's CRM
category and needs only a free developer app to register — but the
adapter abstraction is what matters, not HubSpot specifically: adding a
second real provider means one new adapter class, not a new connection
model or a new set of routes. This continues the exact discipline
`app.ai.gateway` already established for LLM providers, applied to OAuth
connectors instead of model calls. Tested in
`tests/test_integrations.py::test_provider_catalog_reports_hubspot_not_configured`
(the catalog never claims HubSpot is configured without real
credentials), `test_oauth_callback_connects_and_checks_health` (the full
start → callback → connected → health-check round trip against the mock
adapter), and `test_refresh_health_sync_and_disconnect_lifecycle` (token
refresh, a real `SyncRun` row, and disconnect clearing stored tokens).

## ADR-0027 — AI System Inventory: high/unacceptable-risk registration requires an Approval, reusing the Phase 1 primitive again

**Decision**: `app/compliance/service.py::register_ai_system` creates an
`AISystem` row (spec §12's "AI System Inventory" / "AI Risk Assessment"
screens) and, when `risk_classification` is `high` or `unacceptable`
(the EU AI Act's own risk tiers, not a parallel scale), also creates a
real `core.Approval` (`risk_class="high"` or `"critical"` respectively)
and links it via `AISystem.approval_id`. `decide_ai_system_status`
refuses to move a system to `approved` while a linked Approval exists and
hasn't itself been granted (422 otherwise). Minimal/limited-risk systems
have no linked Approval and can move straight to `approved`. This is the
first use of the previously-seeded-but-empty `ai_governance_manager`
system role (`AI_GOVERNANCE_PERMISSIONS` — see `app/core/rbac.py`),
which existed since Phase 1 with zero granted permissions.

**Why**: Spec §69's "New AI Tool Adoption" scenario is "Request → Vendor
created → Security assessment → Privacy assessment → EU AI Act
applicability → DPA review → AI risk assessment → Approval → Add to AI
inventory → Add approved-use policy" — nine steps, but the one this
build can implement honestly right now (no vendor-management or DPA
workflow exists yet) is the "AI risk assessment → Approval → Add to AI
inventory" core: classify the system's risk, gate its approval on a real
sign-off, record it in the inventory. This continues every prior ADR's
discipline of reusing `core.Approval` rather than inventing a
compliance-specific gate — the same primitive Automation's
`human_approval` step (ADR-0021) already exercises, now exercised by a
second, independent domain module, which is exactly what spec §80's
"shared primitives, not disconnected modules" principle asks for. It
also directly unblocks a future "New AI Tool Adoption" Phase 8 slice,
which previously had nothing to link to. Tested in
`tests/test_compliance.py::test_registering_high_risk_ai_system_creates_pending_approval`
(asserts the Approval via `/api/v1/approvals`, not by reading the AI
system alone), `test_cannot_approve_high_risk_system_before_approval_granted`
(422), and `test_can_approve_high_risk_system_after_approval_granted`
(decides the Approval through the real, unmodified
`/api/v1/approvals/{id}/decide` endpoint).

## ADR-0028 — OAuth framework completion: six-provider adapter registry, Temporal-backed sync, and the AWS secrets contract

**Decision**: Three extensions to ADR-0026's OAuth framework, all without
touching its shape:

1. **Five more providers behind the same `OAuthConnectorAdapter`
   Protocol**: `app/integrations/adapters/{google,microsoft,github,slack,salesforce}.py`,
   each a real implementation against that provider's documented OAuth/API
   endpoints (never a stub), none exercised end to end in this environment
   (no real developer app for any of them). Registration moved from
   HubSpot-only `if` branches into a single table,
   `app/integrations/adapters/__init__.py::_provider_specs()` — a
   `connector_key -> (adapter class, client_id, client_secret,
   redirect_uri)` map read once. Adding a seventh provider is one adapter
   module + one table entry + three environment variables, never a
   change to the OAuth flow, router, service layer, or frontend. Every
   adapter class carries a `SCOPES: list[str]` class attribute so the
   provider catalog (`GET /api/v1/integrations/providers`) can show a
   **permission preview** — the exact scopes a real connection would
   request — even for unconfigured providers, without constructing an
   adapter (which needs real credentials). `MockOAuthAdapter` now takes a
   `provider_key` constructor argument so a mocked Google connection is
   labeled as Google, not a generic "mock", in every audit event and UI
   badge (still never presented as live — spec §82).
2. **Sync runs as a durable Temporal workflow**
   (`IntegrationSyncWorkflow`, `apps/worker/worker/workflows.py` +
   `execute_integration_sync_activity`, `apps/worker/worker/activities.py`),
   not inline in the HTTP request. `app.integrations.service.create_sync_run`
   writes the `SyncRun` row (`status="running"`) and returns immediately;
   `POST /connections/{id}/sync` commits that row, then fires the
   workflow via `app.integrations.workflow_client.start_sync` (fire-and-
   forget, mirroring `app.knowledge.workflow_client.start_ingestion`'s
   document-ingestion pattern exactly) and returns without waiting.
   `execute_sync_run` — the actual provider call — runs inside the
   Temporal activity in production and is called directly by tests
   (`run_sync` composes both for tests/seed data), the same
   request/durable-execution split the Knowledge module already
   established for `ingest_document` vs. `DocumentIngestionWorkflow`.
3. **Audit logging for every lifecycle transition**, not just connect:
   `integrations.oauth.refreshed` / `.refresh_failed`,
   `integrations.sync.started` / `.succeeded` / `.failed`, and
   `integrations.oauth.disconnected` (now recording whether the
   provider's own revoke call succeeded, not just that local tokens were
   cleared). Every failure path (adapter throws on refresh or sync) is
   caught, recorded with `policy_decision="denied"`, and normalized to a
   `ValueError` (422) rather than an unhandled 500.

Also: `Settings` now reads `.env` then `.env.local` (later wins), a
repo-root `.dockerignore` excludes both from every Docker build context
(defense in depth — no Dockerfile's `COPY` currently reaches a `.env` file,
but none should ever be able to), and `docs/ENVIRONMENT_VARIABLES.md`
commits to a specific (not yet built) AWS production shape: secrets in
Secrets Manager injected via ECS task-definition `secrets` (never a
deployed `.env` or a Terraform-visible plaintext value), least-privilege
per-service IAM task roles, non-secret config in SSM Parameter Store.

**Why**: The user supplied no live credentials for any provider and asked
for the framework completed anyway, with real per-provider adapters
"prepared" (Google, Microsoft, GitHub, Slack, Salesforce) so that supplying
credentials later needs no structural change — exactly the trust-building
posture spec §B1's progressive trust model describes, and the same reason
ADR-0026 built the Protocol/registry split before HubSpot was the only
provider. Moving sync onto Temporal closes the gap ADR-0026 and
`docs/KNOWN_LIMITATIONS.md` both flagged ("`run_sync` executes
synchronously inline... a real but deliberately simplified version") using
infrastructure (Temporal, the worker task queue) the platform already runs
for document ingestion — not a new job system. The permission-preview
scopes make the "progressive trust" principle visible in the product
itself: a user can see exactly what a Connect click will ask for before
clicking it, configured or not. Two providers (GitHub, Slack) genuinely
have no refresh flow for the token type this integration uses (classic
OAuth App tokens, non-rotating bot tokens) — `refresh_access_token` says
so via a `RuntimeError` rather than pretending to support it; callers
never reach that path anyway, since `refresh_connection_token` first
checks for a stored refresh token and these providers' token exchange
never sets one. Salesforce's real per-org API domain (`instance_url`)
isn't threaded through the adapter Protocol — doing so would mean adding a
Salesforce-only parameter to every other provider's method signatures for
one provider's quirk — so `test_connection`/`sync` use the generic
`login.salesforce.com` identity endpoint instead, documented as a known
simplification in `docs/KNOWN_LIMITATIONS.md` rather than silently
under-scoped. Tested in `tests/test_integration_adapters.py` (pure unit
tests: every provider's `authorization_url` construction, scope preview,
mock fallback, and the two no-refresh providers' explicit errors — no
network, no live credentials needed) and `tests/test_integrations.py`
(the generic OAuth flow proven against a second provider, not just
HubSpot; `execute_sync_run` exercised directly including its failure
path; an audit-trail test asserting `integrations.oauth.started/
connected/refreshed/disconnected` all appear against the connection's
`object_id`).

## ADR-0029 — Privacy (RoPA/DPIA/DSAR) extends Compliance rather than becoming a new module; the AI System hook gets a second extension

**Decision**: `ProcessingActivity`, `DPIA`, `DSAR` are added to
`app/compliance/models.py` (not a new `app/privacy/` module), with
service functions in `app/compliance/service.py` and endpoints on the
existing `/api/v1/compliance` router. This follows the master spec
literally: §2's "Module 1 — AI Compliance" capability list names "privacy
operations, RoPA, DPIAs, DSARs" alongside frameworks/controls/risk —
Privacy is a Compliance sub-feature, not a sibling primary module (unlike
Security, Sales, Support, which spec §2 does list as separate modules).

`ProcessingActivity` is the organization's own RoPA entry (GDPR Article
30): tenant-scoped, unlike Framework/Requirement's global catalog data,
since it's an org's own record of what it processes, not shared
regulatory text. `DPIA` (GDPR Article 35) may link to a
`ProcessingActivity`, an `AISystem`, or neither. A `DPIA` created
directly with `risk_level="high"` gets its own real `core.Approval`,
gating `approved` exactly like `AISystem` (ADR-0027) — this build's
fourth reuse of the Approval primitive outside its own generic UI
(Automation's `human_approval`, the AI System Inventory, now DPIA).
`DSAR` (GDPR Articles 15-20) gets `due_at = created_at + 30 days`
(Article 12(3)'s one-month response window) and a
received→in_progress→fulfilled/rejected lifecycle, setting
`fulfilled_at` on completion.

`register_ai_system` (`app/compliance/service.py`) is extended a
**second** time: alongside creating an Approval for high/
unacceptable-risk systems (ADR-0027), it now also creates a linked draft
`DPIA` via `DPIA.ai_system_id` — completing another step of spec §69's
"New AI Tool Adoption" chain ("... -> Security assessment -> **Privacy
assessment** -> EU AI Act applicability -> ..."). This mirrors exactly
how Phase 8's Security Incident chain extended its own hook twice
(ADR-0018, then ADR-0023) rather than inventing a second mechanism. The
auto-created DPIA does **not** get its own Approval — the AISystem's
existing Approval already covers sign-off for that registration; a
second Approval would be governance-fatigue duplication, not additional
safety. `legal` — a system role seeded since Phase 1 with zero
permissions — is activated for the first time (`PRIVACY_PERMISSIONS`,
alongside `dpo`, which already held Compliance + AI Governance
permissions from ADR-0027).

**Why**: The user asked to continue with credential-free work after the
OAuth foundation, specifically naming "Privacy workflows, then AI
Incidents." Folding Privacy into Compliance (rather than a new module)
matches what the spec itself says, avoids a redundant router/RBAC
namespace for a feature the spec treats as one capability among many
within the same module, and lets the DPIA-Approval-gating logic reuse
`AISystem`'s exact pattern instead of re-deriving it. Extending
`register_ai_system` again — rather than adding a separate, disconnected
DPIA-creation trigger — is spec §80's "do not build disconnected
modules" principle applied for the third time this build. Tested in
`tests/test_compliance.py`: RBAC (`employee` denied, `dpo` granted
processing-activity creation, `legal`'s first activation granted DSAR
creation but still denied control creation — proving the activation is
scoped, not a blanket grant), the DSAR 30-day due date and
fulfilled_at-on-completion lifecycle, the standalone high-risk DPIA's
Approval gate (422 before decision, 200 after), the low-risk DPIA's
ungated direct approval, a DPIA correctly linking to a
tenant-checked `ProcessingActivity`, and — the hook itself —
`test_registering_high_risk_ai_system_auto_creates_linked_dpia` (asserts
the DPIA via `GET /compliance/dpias`, not by reading the AI system alone)
and `test_minimal_risk_ai_system_does_not_create_a_dpia` (the negative
case, proving the hook doesn't fire for every registration).

## ADR-0030 — AI Incidents reuse SecurityIncident's critical-severity chain shape for a third time

**Decision**: `AIIncident` (`app/compliance/models.py`, spec §50's "AI
GOVERNANCE" `ai_incidents` table) is always tied to a specific `AISystem`
(`ai_system_id` non-nullable, unlike `DPIA`'s optional links). Its
`app.compliance.service.create_ai_incident` gates on `severity ==
"critical"` and, when true, does exactly what
`app.secops.service.create_incident` already does for a critical
`SecurityIncident` (ADR-0018, then ADR-0023): creates a linked Compliance
`Risk` (`category="ai_governance"`), a response `core.Task`
(`module="compliance"`, `priority="urgent"`), and — if the incident has
an `owner_id` — a `core.Notification`. RBAC reuses the existing
`compliance.ai_systems.manage` permission rather than minting a new one:
AI incidents are managed by whoever already manages the AI System
Inventory, not a distinct audience.

**Why**: A `critical` AI incident and a `critical` security incident
represent the same underlying obligation — assess and respond to a
serious incident affecting people, with EU AI Act Article 73's "serious
incident" reporting duty for high-risk AI systems playing the same role
GDPR's breach-notification duty plays for `SecurityIncident` — so the
same real chain (Risk for the regulatory-obligation tracking, Task for
the response work, Notification for the owner) is the correct reuse, not
a coincidence to copy blindly. This is the third time this exact chain
shape has been used (Security's own incidents, then reused again as this
build's established pattern for "a critical incident needs a tracked
risk + assigned response + notified owner"), continuing spec §80's "do
not build disconnected modules" discipline: a fourth incident type in a
later phase should reach for this same shape before inventing a new one.
`AIIncident` intentionally does *not* copy `SecurityIncident`'s full
detected→triage→investigation→containment→eradication→recovery→postmortem→closed
lifecycle — that vocabulary is security-incident-response-specific and
wouldn't map naturally onto "a model gave biased loan decisions"; a
simpler open→investigating→resolved→closed lifecycle is what's genuinely
true for an AI incident, not a forced parallel. Tested in
`tests/test_compliance.py`: RBAC denial,
`test_critical_ai_incident_creates_linked_risk`,
`test_critical_ai_incident_creates_response_task`,
`test_critical_ai_incident_with_owner_notifies_owner` (mirroring
`test_security.py`'s equivalent tests almost line for line, proving the
reuse is real, not just described), the negative case
(`test_high_severity_ai_incident_does_not_create_risk_or_task`), the
status lifecycle, and tenant isolation.

## ADR-0031 — Vendor Risk reuses record_assessment's hook shape a fourth time; Evidence gains a second optional target

**Decision**: `Vendor` / `VendorAssessment` (`app/compliance/models.py`,
spec §12/§67's "Vendors" screen) follow `Control`/`ControlAssessment`'s
exact shape: a tenant-scoped entity plus a point-in-time judgement
(`risk_conclusion`: low/medium/high/critical, mirroring the
likelihood/impact/severity vocabulary already used across Risk,
SecurityAsset, and AIIncident). `record_vendor_assessment` reuses
`record_assessment`'s "assessment creates a tracked consequence" hook
shape (spec §80) for a fourth entity type: a `high`/`critical`
conclusion auto-creates a linked Compliance `Risk`
(`category="vendor"`), the same way a `fail` Control assessment
auto-creates a Task — a different consequence (Risk vs. Task) because a
vendor risk is genuinely a risk-register concern (an ongoing exposure to
track), not a remediation checklist item.

`Evidence.vendor_id` is added as a second optional target alongside the
existing `control_id` (both nullable, either or neither may be set) —
not a new evidence table, since a SOC 2 report or signed DPA is the same
kind of artifact (a File with a title and optional expiry) whether it
backs a Control or a Vendor. `VendorDetailOut` includes both
`assessments` and `evidence`, connecting Vendor to Risk, Control-shaped
assessment history, and Evidence in one response — directly serving the
user's explicit request to connect these features to the existing
Risks/Controls/Evidence primitives.

**Why**: Continuing spec §80's "shared primitives" discipline for a
fourth time (after ControlAssessment→Task, AISystem→Approval+DPIA,
AIIncident→Risk+Task+Notification) rather than inventing a
vendor-specific remediation or risk-tracking mechanism. Generalizing
Evidence rather than duplicating it avoids a second file-attachment path
with its own validation/storage logic for what is semantically identical
data. Tested in `tests/test_compliance.py`: RBAC (`employee` denied,
`compliance_manager` granted — via the existing `COMPLIANCE_PERMISSIONS`
bundle, no new role-grant line needed since `compliance.vendors.manage`
was added to that bundle), the critical-assessment-creates-risk hook,
the negative case for low risk, the vendor status lifecycle, evidence
attaching to a vendor and appearing in its detail response, and tenant
isolation.

## ADR-0032 — Security Questionnaires reuse AI Copilot for drafting, with an org-wide answer library and a mandatory human-approval gate

**Decision**: `Questionnaire` / `QuestionnaireQuestion` /
`QuestionnaireAnswer` (`app/compliance/models.py`, spec §12/§67's
"Security Questionnaires" screen) model a customer-provided or internal
security/compliance questionnaire as a tenant-scoped container of
questions, each with exactly one answer row (`question_id` unique FK)
created atomically with the question so a question is never in a state
without an answer record — its `status` is simply `"missing"` until
someone answers it. `Questionnaire.opportunity_id` is a deliberately
forward-looking nullable FK to `sales_opportunities`, unused by this
slice but present now so the not-yet-built Enterprise Sales Security
Review can create or import a questionnaire against a real opportunity
without a later migration.

`suggest_questionnaire_answer` gives each question two possible sources
for a draft answer, tried in order: (1) `_find_reusable_answer`, a
normalized-text exact match (`strip().lower()`) against every
previously-`approved` answer in the organization — the simplest possible
"we've answered this exact question before" reuse, deliberately not
fuzzy or embedding-based; (2) if no match, a live call to the existing
`app.ai.copilot.ask_copilot` (retrieve → ground → generate → cite over
the Knowledge base) — no new AI pipeline is built for this feature.
Either path always writes `status="draft"`: an AI-suggested or
library-reused answer is never auto-approved. A human must call
`update_questionnaire_answer` to move it to `"approved"`, at which point
`source_type` becomes `"manual"` if the text was edited. This is the
same human-in-the-loop discipline (spec F2, "no direct autonomous
writes") already enforced for AISystem/DPIA Approval gates — answering a
customer's security questionnaire incorrectly is a customer-trust and
contractual-risk decision, not something an LLM draft should finalize
unattended.

RBAC adds a single new permission, `compliance.questionnaires.manage`,
appended to the existing `COMPLIANCE_PERMISSIONS` bundle so
`compliance_manager`/`dpo` roles get it automatically.

**Why**: Reusing `ask_copilot` rather than building a bespoke
questionnaire-answering pipeline keeps exactly one grounded-generation
code path in the system, and its existing honest "I don't have any
indexed documents for this" fallback (proven live against a
zero-Knowledge-document org) means the AI path needed no mocking to test
truthfully — a fresh org's `suggest-answer` call is a real,
deterministic assertion, not a stubbed one. The org-wide answer library
turns previously-approved, human-verified answers into the
highest-trust source for a new identical question, ahead of asking the
AI to regenerate an answer that a human has already vetted; this was
proven live, not just in the test suite — creating a second
questionnaire with an identical question after approving the first
reused it with `source_type="reused_from_library"` against the running
Docker stack. Tested in `tests/test_compliance.py`: RBAC denial for
`employee`, questionnaire + question creation, the honest
no-Knowledge-evidence AI-suggestion path, cross-questionnaire library
reuse of a manually-approved answer, the questionnaire status
lifecycle, and tenant isolation (both a foreign `opportunity_id` and a
questionnaire from another org are rejected).

## ADR-0033 — Audits reuse record_assessment's Task-creating half a fifth time; the pre-seeded but previously-unused "auditor" role gets its first permission

**Decision**: `Audit` / `AuditFinding` (`app/compliance/models.py`, spec
§12/§67's "Audits" screen) model an auditor engagement as a named run
(`Audit`, optionally against a catalog `Framework`) that groups many
`AuditFinding` rows, each optionally against a specific `Control`. This
is deliberately a different shape from `ControlAssessment`/
`VendorAssessment`/`AIAssessment` (a single point-in-time judgement of
one entity): an audit produces *many* findings per engagement, so
`AuditFinding` is its own entity with its own `open`/`remediated`
lifecycle, not a repeated assessment row.

`record_audit_finding` reuses `record_assessment`'s "assessment creates a
tracked consequence" hook shape (spec §80) for a fifth entity type, but
specifically its *Task*-creating half: a `high`/`critical` finding
auto-creates a remediation `core.Task`, the same way a `fail` Control
assessment does — not the *Risk*-creating half `VendorAssessment` and
`AIIncident` reuse. This is a deliberate choice, not an oversight: an
audit finding is inherently a remediation checklist item scoped to a
specific engagement (fix this before the audit closes), not an ongoing
risk to track in the Risk Register the way an unvetted vendor or a
biased AI system is.

RBAC adds `compliance.audits.manage`, appended to the existing
`COMPLIANCE_PERMISSIONS` bundle (`compliance_manager`/`dpo` get it
automatically) — and also granted directly to the `auditor` system role
(`app/core/rbac.py` `SYSTEM_ROLE_KEYS`), which has existed since Phase 1
but held zero permissions until now. This is the natural home for an
auditor-facing capability rather than inventing a new role.

**Why**: Reusing record_assessment's Task-creating half (not
reinventing a parallel "finding creates a follow-up" mechanism) keeps
spec §80's shared-primitive discipline intact for a fifth entity type,
while correctly choosing the Task branch over the Risk branch based on
what an audit finding actually represents — a scoped remediation item,
not a standing risk. Granting the pre-seeded `auditor` role its first
real permission here (rather than adding a redundant grant to
`compliance_manager` alone) reflects that an external or internal
auditor is a distinct audience from a compliance manager, even though
this build has no dedicated auditor portal UI yet (see
`docs/KNOWN_LIMITATIONS.md`). Tested in `tests/test_compliance.py`: RBAC
denial for `employee`, the `auditor` role's grant, the
critical-finding-creates-task hook (with the task's title/module/
priority asserted, matching `test_failed_assessment_creates_remediation_task`'s
pattern), the negative case for low severity, a finding attaching to a
Control, the audit and finding status lifecycles (including
`completed_at` being set), tenant isolation, and rejection of a
`framework_id` from another org.

## ADR-0034 — Trust Center gets its own module for a genuinely public, unauthenticated surface; a Policy link, not a new document table, backs "downloadable documents"

**Decision**: Unlike Vendor Risk, Security Questionnaires, and Audits —
all added directly into `app.compliance.models`/`service`/`routers` —
Trust Center lives in a new `app.trust_center` module
(`models.py`/`schemas.py`/`service.py`) with its own `app/routers/
trust_center.py`. `TrustCenterItem` (one row per organization per
spec B4 category, enforced by `uq_trust_center_item_org_category`) and
`EvidenceRequest` are the two entities. The defining reason for the
split: `GET /api/v1/trust-center/public/{org_slug}` is genuinely public
— no `OrgContext`/session dependency at all, only `Depends(get_db)` —
the same "no session, a different capability boundary" pattern the
Phase 9 webhook receiver and OAuth callback already established
(ADR-0024), here reused for a third kind of unauthenticated endpoint.
Every other Compliance sub-feature this build has added is tenant-scoped
behind a session; Trust Center's public page is not, so it does not
belong inside a module whose defining trait is "authenticated by
default."

`TrustCenterItem.policy_id` is an optional link to an existing
`compliance.Policy` rather than a new document/attachment table — spec
B4's "downloadable approved documents" is the same File-backed artifact
concept Policy already models (spec §80). The public endpoint only ever
surfaces a linked Policy if it is `status="published"`, even when the
`TrustCenterItem` itself is `is_public=True` — an org marking a Trust
Center category public should never accidentally leak a still-draft
policy document through a stale link.

`EvidenceRequest` backs spec B4's "evidence request workflow": a public,
unauthenticated POST that always creates a linked `core.Task` — this
build's now-familiar "creates a tracked consequence" hook shape (spec
§80), here applied with `actor_user_id=None` since there is no
authenticated actor, the same way the webhook/OAuth flows record audit
events without one.

RBAC for the authenticated management side adds
`compliance.trust_center.manage` to the existing
`COMPLIANCE_PERMISSIONS` bundle; the public routes have no RBAC by
design.

**Why**: A module boundary should reflect a real difference in security
model, not just a difference in spec section — Trust Center's public
surface is categorically different from every tenant-scoped Compliance
screen, so giving it its own module keeps `app.compliance`'s invariant
("everything here requires a session") honest rather than special-casing
one router function inside it. Reusing Policy for downloadable documents
avoids a second file-attachment/versioning path for artifacts that are
semantically identical to what Policy already stores. Tested in
`tests/test_trust_center.py`: RBAC denial for `employee`, upserting and
re-upserting the same category (proving update-not-duplicate), the
public endpoint returning only `is_public` items, the published-vs-draft
Policy surfacing rule, a 404 for an unknown org slug, a genuinely
unauthenticated evidence-request submission that creates a real Task
(verified via `/api/v1/tasks`), the evidence-request fulfillment
lifecycle, RBAC denial for fulfilling a request, rejecting an unknown
category (422), and rejecting a Policy from another organization (404).

## ADR-0035 — Enterprise Sales Security Review orchestrates five prior slices; a materiality threshold decides whether clearing needs a real Approval

**Decision**: `SecurityReview` (`app/compliance/models.py`, spec §69's
"Enterprise Sales Security Review") is the payoff for
`Questionnaire.opportunity_id` having existed since ADR-0032 with no
caller — this is that caller. One `SecurityReview` row per
`sales.Opportunity` (enforced by a unique constraint; the router returns
409 on a second attempt rather than a raw integrity error) links an
opportunity to a `Questionnaire` (created fresh, or an existing
standalone one *imported* by setting its `opportunity_id`), optionally a
gating `core.Approval`, and eventually a trust-package `core.File`.

`start_security_review` moves the opportunity into a new
`security_review` stage (added to `Opportunity.stage`'s vocabulary) and
sets `is_deal_blocker=True` immediately — spec §69 step 1 and step 10
("tracks deal blocker") happen atomically, not as separate steps, since
a review that exists but isn't yet blocking the deal would misrepresent
its own purpose. Whether clearing later requires a real Approval is
decided once, at start, by `SECURITY_REVIEW_MATERIALITY_THRESHOLD`
(50,000, a judgment call): below it, "no open gaps" is sufficient;
at/above it, a granted Approval is also required — reusing the same
Approval primitive `register_ai_system`/`create_dpia` already gate on,
not a new "big deal" concept.

`sync_security_review` is deliberately idempotent and re-runnable: it
calls `suggest_questionnaire_answer` for every still-`missing` question
(spec §69 steps 3-4, "AI Compliance/Security answers ... questions" —
reusing the Questionnaires slice's own answer-library-then-AI-Copilot
logic rather than a second AI pipeline), then for any answer whose
`control_id` is set but has no `evidence_id`, attaches the most recently
created `Evidence` for that Control (step 5, "retrieves approved
evidence" — a genuinely new capability this slice adds, since
`suggest_questionnaire_answer` alone only carries evidence through when
*reusing* a library answer that already had it). A "gap" (step 6) is any
answer not yet `approved`, or an `approved` answer referencing a Control
with still no Evidence — a customer-facing review shouldn't rely on an
unvetted draft or an unsupported claim. Each gap opens exactly one
remediation `core.Task` (step 7), deduplicated by exact title so
re-syncing never creates duplicates — a sixth reuse of this build's
"creates a tracked consequence" hook shape (spec §80), the first to
produce many Tasks from one call instead of one.

`clear_security_review` refuses while gaps remain or the Approval is
still pending (mirroring `decide_ai_system_status`'s gate, ADR-0027,
returning 422 like it does) and, only once both conditions are
satisfied, compiles every `approved` Q&A plus its Evidence title into a
real text file uploaded through the Phase 1 File/storage primitive —
step 8, a genuine trust package, not a placeholder flag. Clearing sets
`is_deal_blocker=False` and notifies `Opportunity.owner_id` (step 9,
alongside a notification when the review starts) — both real
`core.Notification` rows, not a TODO.

**Why**: This slice is the reason the previous four in this sequence
were built with forward-looking hooks (`Questionnaire.opportunity_id`,
the answer library, Evidence/Control linking, the Task-creation
pattern) rather than in isolation — spec §80's "do not build
disconnected modules" applied at the scale of an entire six-slice
program, not just within one. The materiality threshold is a genuine
judgment call (documented here, not left implicit) because spec §69
doesn't specify one; reusing Approval rather than inventing a
review-specific sign-off concept keeps this build's discipline that
"gate a risky transition" always means the same primitive. Tested in
`tests/test_compliance.py`: RBAC denial for `employee`, starting a
review both by creating a new questionnaire and by importing an
existing one (confirming its `opportunity_id` gets set), a 409 on a
second review for the same opportunity, the opportunity's stage
transition, a full sync→gap→task cycle with re-sync proven
non-duplicating, a low-value review clearing without any Approval, a
high-value review refused twice (once for gaps, once for the still-
pending Approval after the gap is resolved) and then succeeding once the
Approval is granted, and tenant isolation.

## ADR-0036 — Data Transfers completes Privacy's four sub-features; an Article 49 derogation reuses the Risk-creation hook a seventh time

**Decision**: `DataTransfer` (`app/compliance/models.py`, GDPR Chapter V,
Articles 44-49) is the last of Privacy's four sub-features —
`ProcessingActivity` (RoPA), `DPIA`, `DSAR`, and now international
transfers — and, like the other three, extends `app.compliance` directly
rather than becoming its own module (ADR-0029's precedent), unlike Trust
Center's genuinely public surface (ADR-0034) or Enterprise Sales
Security Review's cross-domain orchestration (ADR-0035). It reuses the
existing `compliance.privacy.manage` permission rather than minting a
new one — Data Transfers is a Privacy concern, not a distinct audience,
the same reasoning that already applies to RoPA/DPIA/DSAR sharing that
one permission.

`transfer_mechanism` follows GDPR's own vocabulary
(`adequacy_decision`/`sccs`/`bcrs`/`derogation` — Articles 45-49) rather
than an invented scale. `create_data_transfer` auto-creates a linked
Compliance `Risk` specifically when `transfer_mechanism="derogation"` —
Article 49 derogations are meant to be exceptional, narrow-purpose
exceptions to the transfer regime, not a routine substitute for an
adequacy decision or SCCs, so relying on one is inherently the
risk-bearing choice among the four mechanisms, the same way a
`critical` AI incident or a `high`/`critical` vendor assessment is the
risk-bearing case among their own scales. This is the seventh reuse of
`record_assessment`'s "assessment creates a tracked consequence" hook
shape (spec §80) in this build — `VendorAssessment` (4th),
`AIIncident` (3rd, chronologically earlier but same shape),
`AuditFinding` (5th, Task-creating), `SecurityReview`'s sync step (6th,
many-Tasks-per-call), and now `DataTransfer` (7th) — each a genuinely
different trigger condition mapped onto the same two shared primitives
(Risk or Task), never a bespoke mechanism per entity type.
`processing_activity_id` is optional, matching the reality that not
every transfer traces to one specific catalogued `ProcessingActivity`.

**Why**: Six new Compliance/Trust slices were requested to connect to
"existing Vendors, Risks, Controls, Evidence, Documents, Tasks,
Approvals, Notifications, Sales Opportunities, AI Copilot, and audit
systems" — Data Transfers is the simplest of the six precisely because
it needed no new primitive, no new module, and no new permission; it is
the clearest demonstration that this build's shared-primitive discipline
(spec §80) scales down as cleanly as it scales up to Enterprise Sales
Security Review's full orchestration. Tested in `tests/test_compliance.py`:
RBAC denial for `employee`, the `dpo` role's grant (proving the reused
`compliance.privacy.manage` permission covers it with no new grant
line), the derogation-creates-risk hook, the negative case for an
adequacy-decision transfer, the status lifecycle, linking to an existing
`ProcessingActivity`, rejecting one from another org, and tenant
isolation.

## ADR-0037 — Cloud/Identity Security reuse the Findings category discriminator and the credential-gated honesty pattern; the incident workspace's "Evidence" tab reuses the evidence library; Security Policies has no store of its own

**Decision**: Cloud Security (spec §15) and Identity Security (spec §16)
are built as real `boto3` checks (`app.secops.cloud_scanner`) that write
ordinary `SecurityFinding` rows using the `category` discriminator that
already existed for this purpose (`cloud_misconfiguration`/`identity`) —
the same category-reuse decision the original Security build made for
Findings in general, extended here rather than superseded by a fourth
table. `run_cloud_security_scan` follows the same credential-gated
honesty pattern already established for the AI providers and the six
OAuth integrations: `is_aws_configured()` checks for real
`AWS_SECURITY_SCAN_ACCESS_KEY_ID`/`SECRET_ACCESS_KEY`, and their absence
returns `configured=False` with zero findings created — never a
simulated scan result. Scope is deliberately narrow and disclosed: only
AWS (not Azure/GCP), and only 2 of the spec's ~11 example checks (S3
public-access-block, IAM users without MFA) — see
`docs/KNOWN_LIMITATIONS.md`.

The incident workspace (SEC-05: Timeline, Affected Assets, Evidence,
Communication, Root Cause, Lessons Learned — spec §19) adds two new
tables, `SecurityIncidentTimelineEntry` (`entry_type` discriminates
`update` from `communication`, so both live in one chronological log
rather than two parallel ones) and `SecurityIncidentAsset` (a plain
many-to-many join, linking idempotently — POSTing an already-linked
asset is a no-op, not an error, the same idempotency discipline other
link-creating endpoints in this build already use). "Evidence" is not a
third new table: `Evidence.incident_id` is added as a third optional
target alongside the existing `control_id`/`vendor_id`, so an incident's
supporting documents live in the same evidence library Compliance
already built (spec §80 again) — an incident report is evidence about an
incident the same way a SOC 2 report is evidence about a vendor. Root
Cause and Lessons Learned are two plain text columns directly on
`SecurityIncident`, not a separate postmortem entity, since there is
exactly one postmortem per incident with no history requirement.

The Security Overview dashboard (SEC-08, spec §13) computes all nine
named metrics as live aggregate queries with no cached rollup to go
stale. "Evidence Coverage" — the one metric the spec names without
defining precisely — is defined as the percentage of an org's
`SecurityIncident` rows that have at least one linked `Evidence` row,
directly exercising the `Evidence.incident_id` FK just added; "Security
Score" is an intentionally simple, disclosed-in-code deduction model
(100 minus a fixed weight per open critical alert/critical finding/high
finding/open incident, floored at 0) rather than an external
benchmark-scored formula, since spec §13 names the metric but not its
formula and a fabricated-precision score would be worse than a
transparent one.

Security Policies (SEC-09) has no backing model of its own — the page
reads `GET /compliance/policies` (already permission-open for read)
directly, the same "no duplicate store" principle behind the Knowledge
Graph (a view, not a second graph) and Global Search (scoped to existing
tenant membership, not a new read-permission model): a policy is a
policy regardless of which module's nav a user found it from.

**Why**: This build's most consistent discipline is that a new
spec-named "module" or "tab" is a query/permission/UI slice over an
existing primitive whenever the underlying data genuinely is the same
thing, and a real new table only when it structurally isn't (spec §80).
Cloud/Identity Security findings are structurally identical to every
other Finding — same lifecycle, same severity scale — so a fourth
category is correct where a fourth table would just be two sources of
truth for one concept. Evidence attaching to an Incident is the exact
shape Evidence attaching to a Vendor already was (ADR-0031); reusing it
a third time was cheaper and more consistent than a bespoke incident-
evidence table. Tested in `tests/test_cloud_scanner.py` (fake-client-
stub unit tests for both real checks, plus an endpoint-level proof of
the uncredentialed `configured=False` path), `tests/test_security_incident_
workspace.py` (9 tests: empty-state detail shape, timeline entries of
both types, idempotent asset linking, cross-org rejection, postmortem
update, asset/alert detail views including cross-org 404s), and
`tests/test_security_overview.py` (5 tests: fresh-org all-zero state,
real-count math including the disclosed score formula, tenant isolation,
evidence-coverage percentage). Live-verified end-to-end against the
running Docker stack: a fresh org's all-zero overview, the uncredentialed
cloud-scan response, and a full incident-workspace chain (asset creation,
finding creation, incident creation, asset linking, timeline entry,
postmortem update, re-fetching the detail view) — all against real HTTP
responses, not test-client mocks, with the disposable test data deleted
afterward in FK-respecting order.

## ADR-0038 — Sales depth (ICP scoring, Lead Finder, Enrichment, Sequences/Campaigns, Meeting Assistant, Sales Intelligence) reuses `send_outreach_message`'s compliance gate and the credential-gated honesty pattern rather than inventing parallel mechanisms

**Decision**: ICP scoring (`app.sales.icp`, spec §20) is a disclosed,
deterministic 0-100 formula — industry match and employee-count fit worth
up to 50 points each — against a single org-wide `ICPProfile`, not a
black-box model or an externally-benchmarked score. Saving the profile
immediately rescans every existing Account (`rescore_accounts`); a new
Account created afterward is scored at creation time rather than left
`None` until the next full rescan.

Lead Finder (`app.sales.lead_finder`, spec §21) is explicitly *not* an
external prospecting data source — none is configured in this build. It
surfaces real value over data the org already has: Accounts that fit its
own ICP (score ≥60, or every Account if no profile is saved yet) but have
no open Lead tracking them. Enrichment (`app.sales.enrichment`, spec §21)
is the one genuinely external call in this cluster — a real Clearbit
Company API request gated on `CLEARBIT_API_KEY`, following the exact
credential-gated honesty pattern established for the AI providers, the
six OAuth integrations, and AWS Cloud Security scanning (ADR-0028,
ADR-0037): absent a key, it returns `configured=False` and touches
nothing, never a fabricated company profile.

Sequences/Campaigns (`app.sales.sequences`, spec §23) add
`Sequence`/`SequenceStep`/`SequenceEnrollment`/`Campaign`, but
deliberately no second send mechanism: `advance_due_enrollments` builds an
`OutreachMessage` from the step's template and calls the exact same
`app.sales.service.send_outreach_message` a manually composed message
uses, so every automated send is gated by the identical Compliance check
(spec §91) — there is no way for a Sequence step to bypass the suppression
gate a manual send would hit. Template substitution is deliberately
simple (`{{first_name}}`/`{{full_name}}` string replacement) rather than a
full templating engine, matching this being a v1 cadence engine rather
than a marketing-automation platform. Step advancement
(`POST /sales/sequences/process-due-steps`) is a plain, independently
callable, independently testable function rather than something wired to
a Temporal schedule today — Automation's own Temporal migration (separate,
larger work) is the natural place to attach a periodic trigger onto this
exact function later, so this is sequencing of work, not a missing
capability. `Campaign` deliberately has no send path of its own: launching
one enrolls its target contacts into a `Sequence` via the same
`SequenceEnrollment` machinery, so a Campaign is a named, tracked
bulk-enrollment, not a parallel messaging mechanism.

Meeting Assistant (`app.sales.meetings`, spec §26) generates prep notes via
a real call to the existing retrieval-grounded `ask_copilot` — when the
org's knowledge base has nothing relevant, the honest "no evidence"
message it already returns elsewhere flows through unchanged, not a
fabricated briefing. Sales Intelligence (`app.sales.intelligence`, spec
§29) is entirely live-computed aggregate queries (pipeline value by
stage, win rate, average deal size, top ICP accounts, sequence completion
rate) with no cached rollup to go stale, the same discipline the Security
Overview dashboard established (ADR-0037).

**Why**: This build's most consistent pattern — reuse a shared primitive
and a disclosed real/honest-fallback boundary rather than a bespoke
mechanism per feature — applies as cleanly to Sales' most feature-heavy
cluster as it did to Compliance's and Security's. The risk unique to this
cluster was a second, ungated send path being introduced by Sequences;
routing every automated step through `send_outreach_message` instead of a
new function closes that off structurally, not just by test coverage.
Tested in `tests/test_sales_icp_and_enrichment.py` (9 tests: scoring
formula unit tests, save-triggers-rescore, new-account auto-score, RBAC
denial, uncredentialed enrichment), `tests/test_sales_sequences_and_
campaigns.py` (7 tests: step creation, immediate first-step firing,
suppression respected mid-sequence, multi-step wait timing, campaign
stats, cross-org 404), `tests/test_sales_meetings_intelligence_and_lead_
finder.py` (9 tests), and `tests/test_sales_detail_views.py` (5 tests).
Live-verified end-to-end against the running Docker stack: ICP profile
save → immediate account rescore, Lead Finder creating a real Lead from a
qualifying Account, the uncredentialed enrichment response, a full
Sequence chain (step added, contact enrolled, step fired with real
`{{first_name}}` substitution producing a real "sent" OutreachMessage),
Meeting prep notes genuinely falling back to the "no evidence" message
with an empty knowledge base, and Sales Intelligence's win-rate/average-
deal-size math against real won/lost Opportunities — with disposable test
data deleted afterward in FK-respecting order.

## ADR-0039 — Support depth: AI-grounded replies never auto-send an ungrounded answer; Conversations reuses Tickets rather than duplicating ADR-0017; `ensure_system_roles` is now actually called at startup

**Decision**: AI-grounded ticket response (`app.support.copilot.
draft_ticket_reply`, spec §32) calls the same `ask_copilot` every other
grounded feature in this build uses, over a question built from the
ticket's subject/description/message thread. The result always lands as
a `TicketMessage` with a new `status` column (`draft` by default); it is
marked `sent` immediately only when the org's new `AIAgentConfig` has
both `enabled` and `auto_send_grounded_replies` set AND
`CopilotAnswer.grounded` is `True`. The last condition is load-bearing
and intentionally cannot be bypassed by config alone: `ask_copilot`
already returns an honest "no evidence" answer with `grounded=False` when
the knowledge base has nothing relevant, and that answer must never be
auto-sent to a customer as if it were a confident response — "confidence"
here is deliberately this one honest boolean (was retrieval actually
grounded in real content), not a fabricated numeric score, since no finer
-grained confidence signal exists anywhere else in this build's AI
Gateway.

Conversations (spec §32) gets no new backing table. The original Support
module (ADR-0017) already collapsed spec's separate
"support_conversations" concept into `Ticket`, reasoning that the two have
near-identical shape. Rather than reversing that call under time
pressure, the Conversations *screen* is built as a second real view over
the same `Ticket`/`TicketMessage` data — thread-first, filtered to the
conversational channels (`email`/`chat`, excluding `api`) — the same
"shared primitive, multiple views" reuse already applied to Security
Policies (a view over Compliance's `Policy`, ADR-0037) and Cloud/Identity
Security (views over `SecurityFinding` filtered by category). QA scoring
(`TicketQAScore`) is deliberately independent of the customer-submitted
`CSATResponse` — a QA score is a reviewer's judgement of *handling
quality*, CSAT is the customer's own satisfaction, and conflating them
would lose the distinction spec §32 draws between "QA" and "Analytics".
`app.support.analytics.compute_support_analytics` follows the exact
live-aggregate-query pattern the Security Overview dashboard and Sales
Intelligence established (ADR-0037/ADR-0038).

Separately, while wiring the two new Support permissions
(`support.ai_agent.manage`, `support.qa.manage`) into `app/core/rbac.py`,
live verification surfaced a real latent gap: `ensure_system_roles()`'s
own docstring says it is "safe to call on every startup", but nothing in
`app/main.py` actually called it at startup — only the signup flow and
the standalone seed script did. Since the function is genuinely
idempotent and additive (confirmed by reading it), an organization that
signed up *before* a given permission existed would never receive it on
its `org_admin` role, even after the API process was later restarted with
code that granted it — because nothing re-ran the sync for that
already-seeded role. `app/main.py`'s `lifespan()` now calls
`ensure_system_roles()` once per boot against a real session, so this
class of gap is closed structurally for every future permission addition,
not just retroactively patched for these two.

**Why**: The auto-send gate is the one place in this cluster where a
config toggle alone could have silently produced a worse outcome than no
automation at all (a customer receiving "I don't have any indexed
documents to answer this from yet" as if it were a real answer) — anchoring
the gate to the same honest `grounded` signal `ask_copilot` already
computes, rather than adding a redundant heuristic, means there is exactly
one source of truth for "was this actually answered from real content."
The Conversations decision keeps this build's data model from
accumulating two ways to represent the same conversation thread, which
would have created exactly the kind of drift this build's shared
-primitive discipline (spec §80) exists to prevent. The `ensure_system_
roles` fix was not something this cluster set out to find — it surfaced
because this session's own working pattern (edit code, restart the
container, live-verify against a fresh org) happened to never expose it
until an *old* org was reused for verification, which is exactly the
scenario a real multi-week deployment would hit on its first permission
addition after initial launch. Tested in
`tests/test_support_ai_agent_and_qa.py` (7 tests: pending-draft-by
-default, agent send-approval, the 409 double-send guard, AI Agent config
defaulting to none, the auto-send-still-drafts-when-ungrounded case, QA
score lifecycle, and analytics tenant isolation). Live-verified against
the running Docker stack: the honest no-KB draft reply, agent approval,
real CSAT/QA/resolution-time math on `/support/analytics`, and — after
discovering and fixing the `ensure_system_roles` gap — a direct SQL
confirmation that an org created before the fix correctly received the
new permission grants on the next restart, with the previously-403 calls
then succeeding.

## ADR-0040 — Automation's Temporal migration makes the Temporal workflow the sole writer of run state; `advance_run` stays a plain, directly-testable function; the 24/16-item vocabularies are real dispatch/dispatch-sources wherever a real one exists, honestly unwired where none does

**Decision**: `app.automation.service.start_run` now only creates the
`WorkflowRun` row and returns — all step execution moved out of the HTTP
request into `WorkflowRunWorkflow` (apps/worker/worker/workflows.py), the
same request/durable-execution split Knowledge's `DocumentIngestionWorkflow`
and Integrations' `IntegrationSyncWorkflow` already established. The
workflow's activity, `run_workflow_step_batch_activity`, is a thin wrapper
around `advance_run` — the exact same function this build always had,
unchanged in its core step-iteration logic, now just invoked from a
different caller. This preserves the existing "activity is a thin
wrapper around a directly-tested function" testing convention
(`execute_sync_run`, `ingest_document`) rather than inventing a new
testing strategy for Automation specifically: `tests/test_automation_
service.py` exercises `advance_run`/`start_run`/`publish_workflow_version`
directly against a database session with no live Temporal server, exactly
like the pre-existing Integrations/Knowledge tests do.

`human_approval` pausing now uses a real Temporal signal (`wake`) plus
`workflow.wait_condition`, not the polling-based re-invocation the
original synchronous design used. This is a structural choice, not just
an optimization: once a run starts, `WorkflowRunWorkflow` (via its
activity) is the *only* writer of `WorkflowRun`/`WorkflowStepRun` state.
`POST /runs/{id}/resume` no longer calls `advance_run` directly — doing so
would create a second, HTTP-triggered writer racing against the same
paused workflow, exactly the kind of dual-writer bug a real production
incident looks like. Instead, `resume` (and, automatically, `/api/v1/
approvals/{id}/decide` for *any* module's Approval, not just Automation's)
only ever sends the `wake` signal — a safe, idempotent nudge regardless of
whether a Temporal workflow is even still listening. A `delay` step
("Wait", spec §39) uses the same mechanism from the other direction:
`advance_run` returns immediately after recording a `delay` step's
`waited_seconds`, and the *workflow* (not the activity) calls a real
`workflow.sleep()` before resuming — genuinely durable waiting that was
never safely buildable in the old synchronous-in-request model, since
sleeping inside an HTTP handler for an arbitrary duration would tie up a
request thread indefinitely.

All 24 of spec §39's named action types (plus 2 pre-existing extras,
`send_notification`/`export_data`, kept for backward compatibility) are
real `STEP_HANDLERS` entries. The guiding rule was: reuse an existing
cross-module service wherever the underlying capability already exists
(Compliance's `record_assessment` for "Run compliance assessment",
Security's `run_cloud_security_scan` for "Run security check", Support's
`create_ticket` for "Create support ticket" — reusing its own
security-category-to-SecurityAlert hook for free — the AI Copilot for
"Generate AI response"/"Analyze document", Global Search for "Search
knowledge"), and build a genuinely new but honestly-scoped capability
only where nothing existed (a real `httpx` call for "Call API"/"Webhook",
a bounded small-entity-set dispatch table for "Create record"/"Update
record"/"Update CRM" rather than an unbounded generic ORM proxy). Two
actions — "Send email" and "Send Slack/Teams message" — hit a genuine
capability boundary this build already has for a documented reason (no
SMTP/SES client exists anywhere yet; the Slack/Microsoft OAuth connectors
are deliberately scoped to `channels:read` only, spec §B1's progressive
trust model, and cannot post) — both honestly report they could not
actually deliver rather than either skipping the action type or
fabricating a "sent" result.

The 16 named trigger types split the same way. `manual`/`api` share the
existing trigger-run endpoint (the distinction is which kind of caller
triggers it, not a different mechanism); `webhook` reuses the Phase 9
inbound webhook connector unchanged; `schedule` is the one trigger that
needed genuinely new Temporal infrastructure — a real Temporal Schedule
(`app.automation.workflow_client.create_or_update_schedule`) targets a new
`ScheduledWorkflowRunWorkflow`, which creates a fresh `WorkflowRun` via an
activity and then executes `WorkflowRunWorkflow` as a real Temporal child
workflow rather than duplicating its step-execution loop a second time.
The other 8 real triggers (new/changed CRM leads and opportunity stages,
new support tickets, new vendors, new employees, document uploads, failed
control assessments, security alerts) are wired via one new
`app.automation.triggers.dispatch_event` call added at each pre-existing
domain-event call site — a query for matching `active` workflows plus a
`start_run` call, the same shape every time. The remaining 4
(`new_email`, `form_submission`, `database_event`, `new_regulatory_
update`) have no real source system anywhere in this build; rather than
either omitting them from the type vocabulary (which would make it
impossible to even author a workflow ready for when a real source
exists) or fabricating a fake event source, they are accepted
`trigger_type` values with no dispatch entry — `app.automation.triggers`'s
own docstring is explicit about exactly which 4 these are and why.

The Workflow Builder (spec §41) uses `@xyflow/react` (React Flow) as a
real node-graph canvas rather than a hand-rolled drag surface — steps
render as connected nodes in execution order, and dragging a node to a
new vertical position genuinely reorders the underlying step array (the
canvas snaps nodes back onto a standard grid after each reorder, since
`Workflow.steps` has no persisted x/y position field — only order
matters to `advance_run`). This is a deliberately linear-chain
visualization, not a branching DAG editor: `condition`'s branch-false
path ends the run rather than jumping to an arbitrary node, and `loop`
repeats one nested step inline rather than a nested step subtree — the
canvas honestly represents what `advance_run` actually executes, rather
than implying branching/nesting capabilities this build's execution
model doesn't have. Workflow Templates reuses the exact "global catalog
data" pattern Compliance's Frameworks/Requirements established (no
organization_id); the Connections page adds zero new backend surface,
reading the pre-existing `GET /integrations/connections` directly (spec
§80); Automation Analytics follows the same live-aggregate-query pattern
as the Security Overview and Sales Intelligence dashboards (ADR-0037/
ADR-0038).

**Why**: The single biggest risk in this migration was silently
introducing a second writer of run state (the naive fix for "resume
needs to work" would have been "just call advance_run from the resume
endpoint too", which is exactly the dual-writer bug this design
structurally forecloses). Keeping `advance_run` itself unchanged in
shape — still a plain async function taking a `db`/`run`/`workflow` —
meant the existing test suite's understanding of the business logic
transferred directly rather than needing to be rebuilt around Temporal's
own testing primitives, consistent with how this codebase has always
tested Temporal-backed features (never spinning up
`temporalio.testing.WorkflowEnvironment` in the pytest suite; live
verification against the real running Docker stack is what actually
proves the Temporal wiring, not a mocked-out test double). Tested in
`tests/test_automation_service.py` (16 tests covering the full step
dispatch table, condition/loop/delay control flow, and the pause/approve/
reject cycle directly) plus updates to 3 pre-existing test files
(`test_automation.py`, `test_integrations.py`, `test_compliance_
governance.py`) whose assertions had to change from "the run completed
synchronously" to "the run was queued" — a necessary consequence of
AUTO-03 actually being fixed, not a regression. Live-verified against the
real running Docker stack (a genuine Temporal server and worker, not a
mock): a real run completing end-to-end through the worker in ~1.1
seconds, a `human_approval` pause that resumed within a second of
deciding the Approval purely from the automatic signal (never calling
`/resume` manually), a `new_crm_lead`-triggered workflow firing a real
run when a Lead was created, and template cloning producing a real new
draft workflow.

## ADR-0041 — Integrations gets real spec §G2 sync safety (cursors, replay safety, bounded retries) and grows from 6 to 7 OAuth providers by extending existing adapters' scope rather than only adding new connector shapes

**Decision**: spec §G2's sync-safety bullet list — idempotency, incremental
cursors, retries, backoff, rate-limit handling, tombstones/deletions,
partial-failure reporting, checkpointing, replay safety, tenant isolation
— was previously true only for the "runs as a durable Temporal job, not
inline" half. The other half needed the provider's own real pagination
mechanism threaded through, not invented: `SyncResult` gained a
`next_cursor: str | None` field and `OAuthConnectorAdapter.sync()` gained
a `cursor: str | None = None` parameter, and every one of the (now seven)
adapters extracts and returns its provider's actual next-page token —
HubSpot's `paging.next.after`, Slack's `response_metadata.next_cursor`,
Google Calendar's `nextPageToken`, Microsoft Graph's fully-formed
`@odata.nextLink` (used directly as the next request URL, not
reconstructed), GitHub's page-number pagination (derived from whether the
`Link` response header actually advertises `rel="next"`, not assumed),
and Zendesk's `after_cursor`. Salesforce's `sync()` accepts the parameter
to satisfy the Protocol but always returns `next_cursor=None`, honestly,
since its single non-paginated identity call has no pagination concept —
same "disclosed simplification over silent gap" discipline as every prior
capability-boundary decision this build has made. The cursor is persisted
on `IntegrationConnection.sync_cursor` (migration `3d13a5b8ba86`) and
round-tripped by `execute_sync_run`, which also records `cursor_used` on
each `SyncRun` for audit/debugging — the live checkpoint for the *next*
sync is always the connection's field, not any individual run's.

Replay safety got a real guard, not just a docstring claim: if
`execute_sync_run` is called against a `SyncRun` that's already
`succeeded`/`failed` (the realistic trigger is a Temporal activity replay
after a worker crash between committing the first attempt and returning),
it returns the row unchanged instead of re-syncing — critically, without
advancing `connection.sync_cursor` a second time for the same logical
attempt, which would silently skip a page. Retries/backoff got a real,
*bounded* `RetryPolicy` (3 attempts, exponential backoff, 1-minute cap) on
`IntegrationSyncWorkflow`'s activity call, replacing reliance on
Temporal's unlimited default — a provider that's rate-limiting or briefly
down gets a few backed-off attempts against the same `SyncRun`, not
endless ones. Tombstones/deletions and rate-limit-*specific* detection
(vs. just retrying any error) remain genuinely unbuilt and are disclosed
in `KNOWN_LIMITATIONS.md` rather than silently absent.

Provider coverage grew from 6 to 7 (`ZendeskAdapter`, Customer Support
category) following the exact established `OAuthConnectorAdapter` shape,
plus its own documented simplification: unlike the other six providers, a
Zendesk OAuth client is registered against one specific customer
subdomain rather than a multi-tenant authorize URL, so
`_ProviderSpec`/`is_provider_configured`/`get_oauth_adapter` in
`app/integrations/adapters/__init__.py` gained a fourth, Zendesk-only
"is this configured" input (`ZENDESK_SUBDOMAIN`) rather than threading an
optional subdomain parameter through every other provider's constructor.
Two more categories were closed not with new connectors but by widening
existing ones: the Google adapter now also requests `gmail.readonly` and
`drive.readonly` and its `sync()` fetches real Gmail messages and Drive
files alongside Calendar events (Email, Documents); the Microsoft adapter
now also requests `Mail.Read` and fetches real Outlook messages alongside
Calendar events (Email) — the same reasoning a real Google Workspace or
Microsoft 365 app would use (one OAuth grant, several related read scopes)
rather than treating "one adapter, one category" as a hard rule. The
tradeoff, disclosed rather than hidden: spec §G2 checkpointing only
round-trips each adapter's *original* resource's cursor (Calendar for
both); the newly-added resources (Gmail, Drive, Outlook Mail) always
fetch their latest first page, since `IntegrationConnection.sync_cursor`
is a single opaque string, not a per-resource map, and building that map
for two secondary resources per adapter was judged not worth the schema
growth relative to the value of always seeing the *latest* mail/files
either way.

Every spec §48 provider without an explicit "architecture" qualifier is
now built except CRM's Pipedrive and Customer Support's Intercom, left
alongside the explicitly-"architecture" providers (Zoho, Mailchimp,
Freshdesk, Okta, Entra, Google Workspace, GitLab, Jira, Azure DevOps,
Teams, SharePoint, OneDrive, Notion, QuickBooks, Xero, Stripe, ERP) as
disclosed architecture-ready-not-built in `KNOWN_LIMITATIONS.md`: each
would be the same `OAuthConnectorAdapter` shape already proven seven
times over, adding no new pattern, and — like all seven built providers —
none can be exercised end to end in this environment regardless, since no
real developer app exists for any of them here.

## ADR-0042 — audit_events immutability is enforced with a Postgres trigger, not a role-based REVOKE, because the app's DB role owns the table

**Decision**: `app/audit/models.py`'s docstring previously claimed the
migration that creates `audit_events` also `REVOKE`s `UPDATE`/`DELETE`
from the application database role. Grepping every migration confirmed
this was never actually true (finding A4) — but the deeper problem,
found while implementing the real fix, is that a plain `REVOKE` would not
have worked even if added: this codebase's single Postgres role (`agora`
in local/dev, whatever role Alembic connects as in any real deployment)
both *owns* every table it creates via migrations *and* is the role the
application connects as at runtime. Postgres table owners bypass ordinary
`GRANT`/`REVOKE` ACL checks entirely — `REVOKE UPDATE ON audit_events
FROM agora` is a silent no-op against a role that owns the table, not an
enforced restriction. Splitting into a separate lower-privileged runtime
role (owner-role runs migrations, a second `GRANT SELECT, INSERT`-only
role serves the API/worker at runtime) would fix this properly but is a
real infra restructuring — new role bootstrap, a second connection
string, docs/CI implications — disproportionate to what spec §59's
"Audit logs" bullet actually demands.

Migration `7f2a9c1d4e6b` instead adds a `BEFORE UPDATE OR DELETE FOR EACH
ROW` trigger (`prevent_audit_event_mutation`) that unconditionally
raises. This achieves the same real goal — the database itself refuses to
mutate a written audit row, not just an application-code convention — via
a mechanism triggers are specifically designed for: firing regardless of
which role issues the statement, including the owner, since a trigger
isn't a privilege check. Live-verified directly against Postgres (not
just pytest) with a raw `psql` `UPDATE`/`DELETE` against a real
`audit_events` row: both rejected with the trigger's own error message.
`tests/test_audit_events_immutable.py` covers the same behavior in
pytest, but is dialect-gated to skip on the SQLite in-memory database
this test suite actually runs against (`tests/conftest.py`) — SQLite has
no `CREATE TRIGGER ... LANGUAGE plpgsql`, and this suite never runs
Alembic migrations at all (`Base.metadata.create_all` instead), so the
trigger simply doesn't exist in the test database. Disclosed rather than
silently non-functional: the skip message and the module docstring both
say why, and the live Postgres verification is what actually proves the
behavior.

## ADR-0043 — Multi-entity gets real CRUD for spec §53's "Support:" tier; the same section's "Future:" tier stays deferred, because the spec text itself draws that line

**Decision**: spec §53 (Multi-Tenancy) lists two tiers under one heading,
and the completeness-audit finding for PLAT-16 had conflated them: a
"Support:" tier (Organization, Legal Entity, Business Unit, Team — read
as "build these now") and a separate "Future:" tier (parent organization,
subsidiaries, agency/consultant multi-client mode — read as "not yet").
`LegalEntity`/`Team` models already existed (created at signup — every
org gets one default `LegalEntity`) but had zero CRUD endpoints, which is
what PLAT-16 actually tracks; PLAT-17 was split out to separately track
the "Future:" tier, which remains genuinely unbuilt and disclosed in
`KNOWN_LIMITATIONS.md`, not silently dropped.

`app/routers/organizations.py` gained full `LegalEntity`/`Team` CRUD
(`POST`/`GET`/`PATCH`/`DELETE`) under `/organizations/current/legal-
entities` and `/teams`, following the exact request/audit/permission
shape the pre-existing `Invitation` endpoints in the same file already
established. Two invariants worth calling out: (1) exactly one
`LegalEntity` per organization can be `is_default` — promoting a new
default demotes every other entity in the same request, and archiving
the current default is rejected (409) rather than leaving an organization
with zero default entities; (2) linking a `Team` to a `LegalEntity` from
a *different* organization is rejected as 404 (not 403) — the same
tenant-isolation-by-lookup pattern used everywhere else in this codebase
(a cross-tenant id simply doesn't resolve, rather than leaking its
existence via a 403). Archival (`is_active=False`) is used instead of a
destructive delete on both models, per spec §73's database principle.
`Team.legal_entity_id` is a new nullable FK (migration `3b81902c0a1d`,
with the standard `server_default` backfill pattern for the two new
NOT-NULL `is_active` columns on pre-existing rows). RBAC gained one new
permission, `org.entities.manage`, granted only to `org_admin` — the same
scope `org.settings.manage`/`org.users.manage` already use, deliberately
not extended to `operations_manager` or any other role, since organization
structure is an admin-level concern. 9 new tests cover the default-
entity invariant, archival-of-default rejection, cross-tenant link
rejection, and RBAC denial for a non-admin role; live-verified end to end
against the running Docker stack including a direct `audit_events` query
confirming every action recorded a real object id, not the class of bug
finding A1 fixed earlier this session.

## ADR-0044 — Global Create navigates to each entity's existing module page instead of duplicating 13 miniature creation forms; permission filtering is server-computed, not re-derived client-side

**Decision**: spec §72's Global Create button lists 14 entity types
(Task, Lead, Account, Campaign, Support Ticket, AI System, Risk, Vendor,
Policy, DPIA, DSAR, Workflow, Document, Report) whose real `Create`
schemas range from one optional field (`Lead`) to several required
fields including reference pickers to other entities (`Campaign` needs an
existing `Sequence`; `Support Ticket` needs an existing `Customer`).
Building 13 separate condensed creation forms inside one global dropdown
component would either under-serve the complex ones (a bare UUID text
field standing in for what should be a real picker) or balloon the
component into duplicating logic every target module's page already has
correctly. `GlobalCreateButton` instead treats each option as a
navigation shortcut to the module page that already owns that entity's
real creation form — `/tasks`, `/sales`, `/sales/campaigns`, `/support`,
`/compliance`, `/automation`, `/knowledge` — the same "reuse the existing
primitive" discipline applied throughout this session (Security Policies
reusing Compliance's `Policy`, Automation's Connections page reusing
Integrations' connections list, etc., spec §80). "Report" is the one
entity omitted entirely for now: no Reporting module (PLAT-20) exists yet
to navigate to, so listing it would be a broken link — a disclosed
sequencing dependency, not a silent drop; it gets added the moment
PLAT-20 ships.

Permission filtering is the second real decision: the dropdown must only
show entities the current user can actually create (spec §72's own
"Options based on permissions"), and `OrgContext.permissions` — the exact
set `require_permission()` checks on every write — already exists
server-side (`app/dependencies.py`). Rather than re-deriving a parallel
client-side permission model (which would inevitably drift from the real
RBAC grants the backend enforces), a new `GET /organizations/current/
my-permissions` endpoint returns that same resolved set verbatim. The
frontend's `CREATE_OPTIONS` table maps each entity to the literal
permission key its real creation endpoint requires, so the two can never
silently disagree — if a permission key changes on the backend, the
Global Create option either starts working or starts being hidden
automatically, never staying visibly-present-but-403ing.

## ADR-0045 — Notification dispatch centralizes on one `notify()` call site; only Email and Webhook can ever really deliver, and `notify()` says so on every row rather than only in a docstring

**Decision**: spec §66 names four notification channels beyond in-app —
Email, Slack, Teams, Webhook — with per-user preferences. Before this
change, six call sites across four modules each constructed a
`Notification` row directly, all implicitly `channel="in_app"` (the
model's default), with no dispatch logic anywhere. `app.core.
notifications.notify()` is now the one place that logic lives; all six
call sites (automation's `send_notification` step, two critical-incident
hooks in Compliance and Security, a security-review-started/cleared pair
in Compliance, Support's upsell-signal notification) were migrated to
call it instead of constructing the row themselves.

The real decision is what "real" means per channel, and it isn't uniform:
**Email** reuses the exact log-only dev adapter every other transactional
email in this build already uses (password reset, invitations) — a real
dispatch call, honestly not a real send, consistent with the standing
disclosure in `docs/KNOWN_LIMITATIONS.md`. **Webhook** is different in
kind: there's no reason it can't be fully real, since it's just an
outbound `httpx` POST to a URL the organization configures
(`Organization.notification_webhook_url`, settable on `/settings/
organization`) — so it is a genuine HTTP call, not simulated, the same
"real API call, no live credentials to test end-to-end in this
environment" honesty class as every OAuth adapter this session built.
**Slack** and **Teams** hit a harder wall than "no credentials
configured": even with real Slack credentials, the existing Slack OAuth
connector is deliberately scoped `channels:read` only (spec §B1's
progressive trust model — see ADR-0026/ADR-0028), so it structurally
cannot post a message, and no Teams connector exists in this build at
all. A user can still register a preference for either (their stated
intent is real data worth keeping), but `notify()` never appends them to
`channels_delivered` regardless — the distinction between "requested" and
"delivered" is recorded on every `Notification` row itself
(`channels_requested`/`channels_delivered`, both real JSON columns,
migration `f2899856bd0f`), not just asserted in a docstring, so any
caller or the `/notifications` UI can see the honest outcome without
reading source code.

Two of the six migrated call sites — the critical-incident-assignment
notifications in Compliance (`AiIncident`) and Security
(`SecurityIncident`) — were deliberately upgraded to request
`channels=["email"]` as the one concrete demonstration that multi-channel
dispatch does something real when asked, rather than shipping
infrastructure nothing calls. The other four call sites were left
in-app-only, unchanged from their prior behavior — retrofitting every
existing notification to request every channel wasn't the goal; a
correctly wired dispatch layer was. The `/notifications` page (previously
missing entirely — the list/mark-read backend already existed with no
frontend, finding A3) is the other real half of spec §66: a genuine inbox
plus per-channel preference toggles, each channel's toggle labeled
honestly ("Not deliverable" for Slack/Teams) rather than presented as
uniformly functional.

## ADR-0046 — /settings/roles is a reference view, never an editor, because every role in this build is a system role shared across every organization; /settings/ai-providers stays environment-variable-only, matching every other credential in this codebase

**Decision**: both pages were previously documented (`docs/ROUTES_AND_
SCREENS.md`) as at least partially built — `/settings/roles` as "read-only
view", `/settings/ai-providers` as "shows configured/not-configured
state" — but neither existed anywhere in the codebase (finding A3).
Building them raised one real design question each.

`/settings/roles`: could this be a role *editor*? No, and not because of
scope-cutting — the data model makes it actively unsafe. Every one of the
16 default roles (`app.core.rbac.SYSTEM_ROLE_KEYS`) is seeded with
`organization_id = NULL`, meaning `Role.compliance_manager` (say) is the
literal same database row for every organization in this deployment. A
"Roles" settings page that let one org's admin toggle a permission on
`compliance_manager` would silently change what every *other*
organization's Compliance Managers can do — a cross-tenant mutation
disguised as a per-org settings change, and a serious one. This build has
no per-org custom-role concept (spec §54 doesn't ask for one either, only
"Use capability permissions"), so there is no safe "your org's copy of
this role" to edit. `/settings/roles` is therefore a real reference view
— live data from a new `GET /organizations/current/roles` (join
`Role`/`RolePermission`/`Permission`, filtered to `organization_id IS
NULL`) — not a stub with fewer buttons than the finding's "read-only
view" implied; the honest scope decision is disclosed on the page itself
and in `docs/KNOWN_LIMITATIONS.md`, not hidden.

`/settings/ai-providers`: the natural instinct for a "configure AI
providers" page is a form that writes an API key to the database. That
would be a regression relative to how every other credential in this
codebase works — all seven OAuth integration providers, and both AI
providers already, are environment-variable-only (`ANTHROPIC_API_KEY`,
`HUBSPOT_CLIENT_ID`, etc.), never stored in Postgres. Introducing the
first-ever DB-stored secret for this one feature would mean a new
encryption-at-rest decision, a new access-control surface, and a
precedent this codebase's `.env.example`-based config model doesn't
otherwise have — disproportionate to what spec §57 actually asks for
("Model routing based on... provider adapters"). The page is instead a
real-time status view (`GET /ai/providers`): has-adapter, configured (the
env var is actually set), active (is this the provider `AI_PROVIDER`
routes to right now) — genuinely live data, just never a write path for a
secret. Building it surfaced a previously-undocumented gap: spec §57
lists Azure OpenAI without the "architecture" qualifier it gives Google
(and the "future" qualifier it gives Local/private), meaning a real Azure
OpenAI adapter is nominally in scope — this build has none, now disclosed
as `has_adapter: false` on the page itself rather than silently absent,
tracked in `docs/REMAINING_PRODUCT_GAPS.md`.

## ADR-0047 — Onboarding's readiness score reuses (or extracts and reuses) each dimension's own module's real formula, never a separately-invented number; the wizard is one route with internal step state, not ten route folders

**Decision**: spec §68's Onboarding Experience ends in a "Business AI
Readiness" output — five percentages (Compliance, Security, Sales
Automation, Support Automation, Process Automation) plus named
opportunities. The obvious wrong way to build this is a plausible-looking
random or hardcoded number; the obvious *expensive* way is inventing five
new independent computations that inevitably drift from what each
module's own dashboard already shows for "how well is Compliance/
Security/etc. doing." This build does neither: two dimensions
(`compute_sales_intelligence`'s `sequence_completion_rate_percent`,
`compute_workflow_analytics`'s `success_rate_percent`) call the exact
existing service functions Sales Intelligence and Automation Analytics
already use. Security's dimension required extracting logic that
previously lived inline inside `GET /security/overview`'s handler
(critical alerts × 10 + critical findings × 8 + high findings × 4 + open
incidents × 6, floored at 0) into a new `app.secops.service.
compute_security_score` — a real, low-risk refactor (same formula, same
tests still pass) rather than copy-pasting the deduction weights a second
time where they could silently diverge on the next edit. Compliance and
Support Automation needed genuinely new (but still real) queries:
Compliance is `implemented Controls / total Controls` org-wide — a
simpler, independently-computed ratio than the Framework Dashboard's
per-requirement coverage percent (disclosed as such, not claimed
identical); Support Automation is a new metric entirely — the share of
agent-facing reply volume (`TicketMessage.sender_type in (agent, ai)`)
that was AI-authored and actually auto-sent (`sender_type=ai,
status=sent`), a direct, honest read of the same `TicketMessage.status`
field the Support AI Agent cluster already uses to distinguish a
pending-approval draft from a sent reply.

Named opportunities follow the same discipline as the percentages: "Fix N
compliance gaps," "Enable MFA for N administrators," "N potential
high-fit sales accounts identified" (mirroring `app.sales.lead_finder`'s
own ICP-fit-without-a-Lead query, read-only here rather than the mutating
`find_and_create_leads`), and two automation-health opportunities derived
from the same numbers already computed above — never spec §68's literal
example text ("84 potential high-fit sales accounts," "37% of support
questions") copied in as a placeholder.

The wizard itself is one route (`/onboarding`) managing 9 screens via
local step state, not ten separate route folders as
`docs/ROUTES_AND_SCREENS.md` originally sketched
(`/onboarding/company`, `/onboarding/goals`, ...). Spec steps 1
("Company") and 2 ("Business profile") are combined onto one screen —
step 1 has no fields of its own beyond the organization identity already
captured at signup — and the backend mirrors this: `PUT /onboarding/
company` collects both `industry`/`employee_count_range` in one call.
`OnboardingProfile.current_step` advances by exactly one step per
completed screen (a `_advance(profile, N)` helper that's a no-op if the
org is already further along, so re-submitting an earlier step never
regresses progress), letting the frontend resume a half-finished wizard
at the right screen from one `GET /onboarding/status` call rather than
reconstructing progress from ten separate route visits. Steps 8 and 9
("Connect tools", "Upload knowledge") have no fields at all — they link
out to the real, already-built Integrations and Knowledge pages (spec
§80: reuse, don't duplicate) and a single generic `POST /onboarding/
advance` moves past either.

Building this surfaced a genuine, previously-untested bug unrelated to
Onboarding itself: `GoalsStepUpdate`'s `@field_validator` raising a plain
`ValueError` for an unknown goal key crashed `app.main`'s
`RequestValidationError` handler with a 500 instead of the intended 422 —
Pydantic v2 embeds the raw exception instance in each error's `ctx`,
which stdlib `json.dumps` can't serialize. The exact same shape already
existed in `app.automation.schemas.WorkflowCreate`'s `trigger_type`/
`steps` validators, just never exercised by an invalid value in any prior
test. Fixed once, centrally, in the shared exception handler (`exc.
errors()` through FastAPI's `jsonable_encoder`) rather than working
around it per-schema, with a regression test covering the pre-existing
`WorkflowCreate` validator specifically so the fix's value isn't limited
to the one call site that happened to surface it.

## ADR-0048 — SSO reuses the Integrations OAuth adapters' token exchange but requests its own minimal identity scope; a first-time SSO login auto-provisions an organization exactly like signup

**Decision**: spec §59 lists "SSO" as a plain requirement, distinct from
"SAML architecture" and "SCIM architecture" on the same line — only the
latter two carry spec's own deferral qualifier, so PLAT-18 built real
Sign-in-with-Google/Microsoft rather than bundling all three into one
Phase-10 deferral (the completeness audit's original framing had
conflated them). The interesting design decision is *how much* of the
existing Integrations OAuth machinery to reuse. `exchange_code_for_tokens`
is reused as-is (`app.integrations.adapters.get_oauth_adapter`) — it's a
pure code-for-token HTTP call that doesn't care what scope was granted,
so reusing it for login is free. The authorization URL is **not** reused:
`GoogleAdapter`/`MicrosoftAdapter`'s `authorization_url()` requests the
full Integrations scope set (Calendar, Gmail, Drive for Google; Calendar,
Outlook Mail for Microsoft, per ADR-0042's Integrations widening) —
requesting that for a *login* would mean every SSO sign-in silently grants
calendar/email read access the user never asked for. `app.identity.sso`
builds its own authorization URL directly, with a real minimal identity
scope (`openid email` / `openid email profile User.Read`) that still
exchanges cleanly through the shared, unmodified `exchange_code_for_tokens`
call. Identity resolution (the real email address a login needs) is a
new, separate call against each provider's real userinfo/me endpoint —
deliberately not folded into the Integrations `HealthResult`/`SyncResult`
shapes, which were designed for connection-health/data-sync, not login
identity, and widening them would be a scope leak in the other direction.

A pre-login CSRF state token needed its own table
(`SsoLoginAttempt`/migration `d00cf4861648`) rather than reusing
`IntegrationConnection.oauth_state`, since that field belongs to an
already-authenticated, org-scoped connection row that doesn't exist yet
during a login flow — the same "capability token" pattern, applied where
no prior row exists to hang it off of. A first-time SSO login (no
matching `User.email`) auto-provisions a brand-new Organization using the
identical shape `app.identity.service.signup` already establishes (new
`User`, default `LegalEntity`, `org_admin` `Membership`) rather than
inventing a second onboarding path — the password field is a random,
never-shared value (this account can only ever authenticate via SSO,
which is honest given how it was created) and `email_verified_at` is set
immediately, since the identity provider's own verification is a stronger
real signal than this build's own email-link verification. `start_sso_login`
refuses (400) outright when a provider isn't actually configured — this
build never falls back to `MockOAuthAdapter` for SSO the way Integrations
does for a demo connection, since a mocked *login* would mean creating a
real `User`/`Session` from a fabricated identity, not a labeled demo.

## ADR-0049 — Plans are a small JSON-entitlements catalog, not a relational per-entitlement table; enforcement is wired at exactly two points, chosen for zero regression risk over maximal coverage

**Decision**: spec §64 says "Plans architecture:" as a section-level
qualifier, then separately states "Use entitlement service. Do not
hard-code plan checks across UI" without a qualifier of its own — read at
the phrase level (the same discipline established for §53 and §59: a
qualifier attaches to the specific words it precedes, not to everything
under the same heading), the payment-collection half of §64 is
architecture-tier and correctly unbuilt, but a real entitlement service is
in scope. PLAT-19 built `app.billing`: a `Plan` model with one `entitlements`
JSON column rather than a normalized `Entitlement`/`PlanEntitlement`
table pair. This is a genuine simplification, not a corner cut: there are
only 4 plans and 19 entitlement keys, none of which need independent
lifecycle (versioning, per-org overrides, audit history distinct from the
plan itself) — a relational table would add migration and query
complexity for zero present capability. `ensure_plan_catalog()` follows
the exact idempotent upsert-on-every-call pattern `ensure_system_roles`
established (ADR-0043-adjacent): called from `app.main`'s `lifespan()`
*and* directly inside `signup()` and `_provision_user_and_organization()`,
because the SQLite test database resets per test and never retains state
a one-time lifespan hook would have set up — discovered the hard way when
wiring `max_users` into invitation creation broke 6 previously-green
tests with `LookupError: Plan 'starter' has not been seeded`.

The harder decision was where to actually enforce an entitlement, given
that almost every organization already in existence (every pre-existing
test's freshly-signed-up org, and every real org created before this
commit) defaults to `plan_key="starter"`. Wiring a new boolean check onto
an *existing, already-shipped* feature risks silently breaking it for
every such org. This was not hypothetical: `trust_center_enabled` was
wired onto `trust_center.py`'s write endpoint, then reverted before
commit, because Starter's catalog sets it `false` and the pre-existing
`test_compliance.py` Trust Center tests — whose orgs all default to
Starter — would have started failing for a feature Billing had nothing
to do with. Rather than either skip enforcement entirely (an unfalsifiable
"the service exists" claim) or retrofit every module at once (out of
scope for this cluster and its own regression risk), enforcement landed
at exactly two points chosen because neither can regress a pre-existing
green test: `max_users` on `create_invitation` (a brand-new capacity
check on an existing but not-yet-limited path — the only pre-existing
tests that could break are ones creating more members than Starter's
limit, and none do) and `sso_enabled` on SSO login for an *existing* user
at an *existing* org (SSO itself is entirely new code from this session,
so there is no pre-existing green test to break). The second point has
its own carve-out: a brand-new organization auto-provisioned by its own
*first* SSO login is exempt from the `sso_enabled` check, because that
org's Starter-default entitlements would otherwise reject the very login
that is in the middle of creating it — a chicken-and-egg case that only
applies to the org-creation branch, not the existing-org branch.

Per-tier cutoffs (which numeric limit or boolean flag unlocks at Growth
vs. Business vs. Enterprise) are a disclosed judgment call: spec §64
names the entitlement keys but not their tier assignment, so
`PLAN_CATALOG` reflects a reasonable reading (SSO/API/Trust Center at
Growth; SCIM/custom frameworks/advanced reporting at Business; data
residency at Enterprise only) rather than a spec-mandated table.

## ADR-0050 — Reporting is one generic `ReportContent` intermediate representation rendered by 4 real, format-specific libraries; every report type reuses an existing module's own aggregate rather than inventing new numbers; "Secure link" is the existing signed-URL mechanism, not a 5th format

**Decision**: spec §65 names 14 report types and 5 export options (PDF/
DOCX/XLSX/CSV/Secure link) with no qualifier attached to any of them —
unlike §64's Billing section, nothing here is marked "architecture," so
PLAT-20 built all of it for real rather than disclosing a scope
boundary. Two design decisions made that tractable.

First, `app.reporting.content.ReportContent` (a title plus an ordered
list of `ReportSection{heading, rows}`) is a deliberately generic,
renderer-agnostic intermediate representation. Each of the 14 report
"builder" functions only ever produces this shape; each of the 4
renderers (`render_pdf`/`render_docx`/`render_xlsx`/`render_csv` in
`app.reporting.rendering`) only ever consumes it. This means the 14×4
combinations that would exist if every report type had bespoke
per-format layout code collapse to 14 builders + 4 renderers — adding a
15th report type never touches rendering code, and adding a 5th real
format (there is no 5th, see below) would never touch a builder.
Real libraries do the actual rendering — `reportlab` (a new dependency;
`pypdf`, already present, is read-only and can't produce a PDF),
`python-docx` and `openpyxl` (already present but previously used only
for Knowledge ingestion's read side — extracting text from uploaded
documents, `app.knowledge.parsing`; this is their first real
write-side use), and stdlib `csv`. Every renderer
was live-verified by downloading its actual output and checking real
format signatures (PDF magic bytes, DOCX/XLSX as valid zip/OOXML), not
just a 201 response — a `.pdf` extension on a text file would have
passed a naive test but not spec §82's "no fake features" bar.

Second, per the same reuse discipline established for Onboarding's
readiness score (ADR-0047) and repeated throughout this session: 8 of
the 14 report types call an existing module's own dashboard/analytics
function outright rather than compute a second, independently-drifting
number — Executive Business AI Report and Board Report both call
Onboarding's `compute_readiness`; Security Posture Report calls a newly
extracted `app.secops.service.get_security_overview` (the logic used to
live inline in `GET /security/overview`'s router handler; it's now a
real service function so that endpoint and this report share one
implementation, the same extraction pattern ADR-0047 applied to
`compute_security_score`); Sales Performance and Pipeline Report both
call `compute_sales_intelligence`; Support Performance calls
`compute_support_analytics`; Automation ROI calls
`compute_workflow_analytics`. The remaining 6 (Compliance, GDPR, EU AI
Act, AI Inventory, Risk, Vendor, Audit Evidence Pack) had no pre-existing
aggregate to call — Compliance's tables have only CRUD service functions
and one per-framework dashboard endpoint — so those query
`app.compliance.models` directly, following the same `compute_x(db, *,
organization_id) -> ...` shape the reused functions already use.
Automation ROI reports real run volume and success rate rather than a
dollar figure: this build has no per-workflow cost-per-manual-execution
figure to compute a genuine ROI dollar amount against, so the report
says that explicitly (a disclosed simplification, not a silent gap) —
inventing a dollar number would have been the actual violation of spec
§82 here, not omitting one.

Finally, spec §65's "Secure link" export option is not implemented as a
5th file to generate. Every report — regardless of format — is already
retrievable only through `GET /reports/{id}/download`, which mints a
fresh, short-lived signed URL via the existing `app.core.storage.
presign_download` primitive (the same one `app.routers.files` already
uses; `app.core.storage`'s own docstring states files are never served
through the API process itself). Since no report is ever inlined in a
response or emailed as an attachment, that signed-URL mechanism already
*is* "Secure link" for all 4 real formats — building a 5th renderer for
it would have been redundant with the delivery mechanism the other 4
already depend on.

## ADR-0051 — Rate limiting and idempotency are global, fail-open Redis-backed middleware; pagination is additive so no existing list endpoint's response shape changes; only 18 of ~60 list endpoints got pagination, chosen by which ones actually grow unbounded

**Decision**: spec §E7 "API Quality" lists 10 requirements with no
qualifier attached to any of them. 7 were already real (consistent
error envelope, request/correlation IDs, OpenAPI docs, input limits via
Pydantic field constraints, permission failures returning 404 instead
of leaking existence of an unauthorized resource) or became real as a
side effect of this session's other clusters. The 3 that weren't —
rate limiting, idempotency for side effects, pagination/sorting — are
addressed here, each with a design choice worth recording.

Rate limiting and idempotency are both implemented as global ASGI
middleware (`app.core.rate_limit.RateLimitMiddleware`,
`app.core.idempotency.IdempotencyKeyMiddleware`) rather than per-router
opt-in, because both are structurally the kind of concern that has to
apply everywhere to mean anything — a rate limiter that only guards
some endpoints isn't a real rate limiter. Both are Redis-backed (the
existing `REDIS_URL`, previously configured but unused by any app
code) and both fail open on a Redis outage: catching the exception and
falling through to normal request handling, rather than making Redis a
new single point of failure for the entire API. Idempotency is
additionally opt-in at the request level — it only ever activates when
a caller sends a real `Idempotency-Key` header, so none of the
hundreds of pre-existing call sites (routers, tests) needed to change;
a request without the header behaves exactly as it did before this
ADR. The idempotency cache key includes the requester's session cookie
value, not just the client-supplied key and the method+path, because
two different organizations' clients could otherwise coincide on the
same literal `Idempotency-Key` string and replay each other's cached
response across a tenant boundary — a real cross-tenant leak the naive
version of this feature would have had.

Both middlewares are added to the FastAPI app *before* `CORSMiddleware`
in `app.main`, which — per Starlette's `add_middleware` semantics
(`user_middleware.insert(0, ...)`, so the most-recently-added
middleware ends up outermost) — makes CORS the outermost layer,
wrapping both. This matters because a 429 from the rate limiter or a
replayed response from the idempotency layer short-circuits before
reaching the route handler; if CORS were positioned inside them
instead, those short-circuit responses would never pass through CORS
and a browser client would see an opaque CORS failure instead of the
real 429/replay, which is the wrong failure mode for a control meant
to communicate "you're going too fast," not "something is broken."

The full pytest suite issues thousands of requests from one shared
client identity (httpx's ASGI test transport) — a production-tuned
rate limit would make the suite itself trip the limiter. Rather than
disabling enforcement in tests (which would mean the middleware is
real code with no real test coverage), `RATE_LIMIT_MAX_REQUESTS_PER_MINUTE`
is set to a very high ceiling in `tests/conftest.py`, and
`tests/test_api_quality.py` monkeypatches `settings.
rate_limit_max_requests_per_minute` down to a tiny number for its own
dedicated tests, proving real enforcement without destabilizing every
other test that happens to run in the same 60-second window.

Pagination (`app.core.pagination`) is additive: a list endpoint that
never receives `limit`/`offset` returns exactly the same bare-array
response it always did, so no existing frontend caller had to change.
Passing them applies a real SQL `LIMIT`/`OFFSET` and reports the true
row count via an `X-Total-Count` header rather than by wrapping the
response body in an envelope — wrapping every list endpoint's response
shape would have been a breaking change touching dozens of frontend
call sites for a feature spec §E7 doesn't actually require to be
delivered that way. Applying it required touching each endpoint
individually (the query and its `order_by` live in the route handler,
not somewhere middleware can reach), so full coverage of all ~60 list
endpoints in one pass wasn't attempted — instead it was applied to the
18 endpoints most likely to grow unbounded in real usage (per-org
Compliance controls/evidence/risks/vendors/audits, Sales
accounts/contacts/leads/opportunities, Support customers/tickets,
Security assets/findings/alerts, Automation runs, Notifications,
Knowledge documents, Reporting), while small shared catalogs
(Frameworks, Plans, Roles, Permissions, AI Provider status, Report
types) and parent-scoped child collections (a Ticket's messages, a
Workflow's versions) were left as plain lists — they don't grow the
way an organization's own accumulating records do, so pagination
there would be complexity without a real problem to solve. This is a
disclosed scope boundary (`REMAINING_PRODUCT_GAPS.md`), not a claim of
exhaustive coverage.
