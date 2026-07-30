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
