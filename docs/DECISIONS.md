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
