# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

Phase 1 (platform foundation) and Phase 2 (Knowledge & AI Infrastructure)
are complete. All five primary product modules — Compliance, Security,
Sales, Support, and Automation (Phases 3-7) — have a real, tested
backbone. Phase 8 (Cross-Module Intelligence) has three of spec §69's
five named scenarios fully implemented, plus a partial fourth ("New AI
Tool Adoption") with two of its steps done. Phase 9 (Integrations) has a
Webhook connector and a provider-neutral OAuth2 framework with six real
(credential-gated) adapters.

**Currently in progress**: the user asked to build out the remaining
Compliance/Trust capabilities in this order: (1) Vendor Risk, (2) Security
Questionnaires, (3) Audits, (4) Trust Center, (5) Enterprise Sales
Security Review, (6) Data Transfers — each connected to existing
Vendors/Risks/Controls/Evidence/Documents/Tasks/Approvals/Notifications/
Sales Opportunities/AI Copilot/audit systems, with the Enterprise Sales
Security Review implementing the full 10-step spec §69 flow. AWS
deployment must wait for explicit approval — infra code may be prepared
but no billable resources created.

**Completed so far in this sequence**:

**Vendor Risk** (`Vendor`/`VendorAssessment`, `app/compliance/models.py`,
ADR-0031). A `high`/`critical` assessment conclusion reuses
`record_assessment`'s "assessment creates a tracked consequence" hook
shape for a fourth entity type, auto-creating a linked Compliance `Risk`
(`category="vendor"`) and updating the vendor's own `risk_tier`.
`Evidence` gained a second optional target (`vendor_id`, alongside
`control_id`) rather than a new evidence table. RBAC:
`compliance.vendors.manage` added to the existing
`COMPLIANCE_PERMISSIONS` bundle. Frontend: a Vendors section on
`/compliance` (create form, list) + `/compliance/vendors/[id]` detail
(status dropdown, assessment form, assessment history, evidence list).
Seed data: 1 low-risk vendor, 1 vendor with a critical assessment (linked
Risk visible via `/api/v1/compliance/risks`).

**Security Questionnaires** (`Questionnaire`/`QuestionnaireQuestion`/
`QuestionnaireAnswer`, `app/compliance/models.py`, ADR-0032). Every
question gets an atomically-created `status="missing"` answer row.
`suggest_questionnaire_answer` tries an org-wide exact-text match against
previously-`approved` answers first (`source_type="reused_from_library"`),
then falls back to a live `app.ai.copilot.ask_copilot` call
(`source_type="ai_suggested"`, citations stored) — either way the result
always lands as `status="draft"`, never auto-approved.
`update_questionnaire_answer` handles manual edits and approval.
`Questionnaire.opportunity_id` is a deliberately forward-looking nullable
FK to `sales_opportunities`, unused by this slice but ready for the
Enterprise Sales Security Review slice. RBAC:
`compliance.questionnaires.manage` added to the existing
`COMPLIANCE_PERMISSIONS` bundle. Frontend: a Questionnaires section on
`/compliance` (create form, list) + `/compliance/questionnaires/[id]`
detail (status dropdown, missing-answer count banner, add-question form,
per-question suggest-answer/save-draft/approve actions). Seed data: 1
questionnaire ("Nordwind Robotics vendor security questionnaire") with 1
approved answer + 1 missing answer.

**Audits** (`Audit`/`AuditFinding`, `app/compliance/models.py`,
ADR-0033). An `Audit` groups many `AuditFinding` rows under one auditor
engagement (optionally against a catalog `Framework`) — a different
shape from the single-judgement `ControlAssessment`/`VendorAssessment`/
`AIAssessment` pattern. `record_audit_finding` reuses
`record_assessment`'s hook shape for a fifth entity type, specifically
its Task-creating half: a `high`/`critical` finding auto-creates a
remediation `core.Task`. RBAC: `compliance.audits.manage` added to the
existing `COMPLIANCE_PERMISSIONS` bundle, and also granted to the
pre-seeded but previously-unused `auditor` system role (its first real
permission). Frontend: an Audits section on `/compliance` (create form,
list) + `/compliance/audits/[id]` detail (status dropdown, add-finding
form, findings list with severity/status badges, mark-remediated
action). Seed data: 1 in-progress audit ("Annual ISO 27001 surveillance
audit") with 1 critical finding + linked remediation task, 1 remediated
low-severity finding.

All checks pass: **179 backend tests** (was 164 before Questionnaires,
171 after), ruff + mypy --strict clean; frontend eslint + tsc +
production build clean; **16 frontend tests** (was 12, then 14, now
16), all passing. Live Docker smoke test for Audits: created a critical
finding and confirmed a real linked remediation Task (title/module/
priority verified via `/api/v1/tasks`); confirmed a low-severity finding
creates no task; marked a finding remediated and completed the audit
(`completed_at` set); confirmed the full `compliance.audit*` audit trail
in Postgres; confirmed both `/compliance` and `/compliance/audits/[id]`
return HTTP 200 (again required a `docker restart` of the `web`
container for the brand-new route to be picked up — see
"Machine-specific note" below, now confirmed on three separate slices).

**Remaining in this sequence, in order**: Trust Center, Enterprise Sales
Security Review, Data Transfers. See "Next highest-priority task" below
for the concrete plan for each, established before starting so the whole
sequence stays internally consistent (e.g. Questionnaires had to exist
before the Sales Security Review can create/import one — it now does).

## Branch and commit

Branch: `main`. Nineteen substantive commits through the Vendor Risk
slice (Phase 1 through the AI Incidents slice, then that one), plus the
Security Questionnaires commit and now this session's Audits commit on
top. See `git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository. Agora
Origin's compose stack uses alternate host ports via a gitignored
`infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`).

Docker Desktop on this machine has intermittently stopped mid-session. If
`docker compose` commands fail with `failed to connect to the docker API
at npipe:////./pipe/dockerDesktopLinuxEngine`, launch it directly
(`"/c/Program Files/Docker/Docker/Docker Desktop.exe"`) and poll
`docker info` until it responds (~10-30s); containers restart
automatically.

The **api and worker containers share `requirements.txt` but are built as
separate Docker images** — a new Python dependency needs
`docker compose build api worker`, not just one.

The `web` container's bind-mounted Next.js dev server (Turbopack) has not
reliably picked up brand-new route directories (`app/(app)/.../[id]/page.tsx`)
created while it was already running — now confirmed on three separate
slices (Vendor Risk, Security Questionnaires, Audits), each time a new
`/compliance/.../[id]` route 404'd until `docker restart
agora-origin-web-1`. Treat this as routine: after adding any new dynamic
route, restart the `web` container before running its live smoke test,
rather than debugging the route itself when it 404s.

## Exact commands already run (this session, Audits slice)

```bash
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add audit tables"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 179 passed

docker compose run --rm --no-deps api python -m app.seed   # idempotent, confirmed 4x total across sessions

cd apps/web
npx tsc --noEmit
npx eslint .
npx vitest run   # -> 16 passed
npm run build

docker restart agora-origin-web-1   # pick up the new /compliance/audits/[id] route

# live smoke test
docker exec agora-origin-api-1 sh -lc "curl -s -X POST http://localhost:8000/api/v1/auth/login ..."
docker exec agora-origin-api-1 sh -lc "curl -s -b /tmp/audit_cookies.txt -X POST .../audits ..."
docker exec agora-origin-api-1 sh -lc "curl -s -b /tmp/audit_cookies.txt -X POST .../audits/{id}/findings -d '{\"severity\":\"critical\",...}'"
docker exec agora-origin-postgres-1 psql -U agora -d agora -c "SELECT action, object_type FROM audit_events WHERE action LIKE 'compliance.audit%';"
```

## Next highest-priority task: Trust Center (item 4 of 6)

- **TrustCenterItem** (category matching spec §B4's exact bullet list:
  security_overview/privacy_overview/subprocessors/data_locations/
  encryption_practices/availability/vulnerability_reporting/
  compliance_roadmap/dpa_availability/incident_communication/
  responsible_ai/ai_provider_disclosures/retention_deletion/
  business_continuity, status: planned|in_progress|implemented|
  independently_assessed|certified — spec's own status vocabulary, not
  invented — is_public bool).
- Genuinely public: one unauthenticated `GET
  /api/v1/trust-center/public/{org_slug}` route (same "deliberately
  unauthenticated, narrowly scoped" pattern as the webhook
  receiver/OAuth callback) exposing only `is_public=true` rows, plus
  published+`is_public` Policies as downloadable documents.
- An `EvidenceRequest` model (public POST, no auth) backs spec's
  "evidence request workflow," creating a `core.Task`.
- RBAC for the authenticated management side: likely
  `compliance.trust_center.manage`, added to the `COMPLIANCE_PERMISSIONS`
  bundle (same reasoning as every prior slice). The public endpoint has
  no RBAC — it's unauthenticated by design.
- Frontend: a Trust Center management section on `/compliance` +
  a genuinely public `/trust/[org_slug]` page (outside the authenticated
  `(app)` route group) that renders only `is_public` items, no login
  required — this is the one piece of this build's frontend meant to be
  reachable without a session, so it needs its own layout/route outside
  `app/(app)/`.
- Full test/seed/smoke-test/doc/commit cycle, matching every prior slice
  this session — the smoke test must include an actual unauthenticated
  `curl` (no cookie jar) against the public endpoint to prove it's really
  public, not just RBAC-permissive.

## Then: Enterprise Sales Security Review, Data Transfers

- **Enterprise Sales Security Review**: the big one. `SecurityReview`
  (opportunity_id FK sales_opportunities, questionnaire_id nullable,
  trust_package_file_id nullable FK files, status: in_progress|blocked|
  cleared, is_deal_blocker). Add a `security_review` stage to
  `Opportunity.stage` (between `proposal` and `negotiation`). Orchestrates
  the full spec §69 flow: create/import a Questionnaire → auto-suggest
  answers (reuse the Questionnaires slice's answer-library + AI Copilot
  logic) → auto-attach Evidence for answers referencing a Control →
  compute missing items → create a remediation Task per missing item →
  require an Approval before clearing when `Opportunity.value` is above a
  materiality threshold (a judgment call to document in the ADR, mirroring
  how every other high-stakes gate in this build uses Approval) → generate
  a real trust package (a compiled document of approved Q&A + evidence
  titles, stored as a File) → notify `Opportunity.owner_id` → keep
  `is_deal_blocker=true` until cleared, surfaced on the Sales account/
  opportunity detail page.
- **Data Transfers**: `DataTransfer` (processing_activity_id nullable,
  destination_country, transfer_mechanism: adequacy_decision|sccs|bcrs|
  derogation, safeguards_description, status), extending Privacy exactly
  like ProcessingActivity/DPIA/DSAR did (ADR-0029's pattern).

Each slice gets its own migration, full test coverage, seed data, a live
Docker smoke test, a full documentation-set update, and its own commit —
matching every slice completed this session. No AWS resources are to be
created without explicit approval; only prepare infra-as-code where it
naturally fits (none of these six slices inherently need new AWS
infrastructure, so this constraint is unlikely to come up before Phase 10
work begins).

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (179 passed)
cd ../../apps/web && npx vitest run   # confirm still green (16 passed)
```
