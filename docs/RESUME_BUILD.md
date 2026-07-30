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

All checks pass: **171 backend tests** (was 164), ruff + mypy --strict
clean; frontend eslint + tsc + production build clean; **14 frontend
tests** (was 12), all passing. Live Docker smoke test: created a second
questionnaire with an identically-worded question and confirmed live
library reuse (`source_type="reused_from_library"`); confirmed the honest
AI-Copilot fallback on a genuinely novel question (real retrieval
citations against the seeded Knowledge document, since this org — unlike
the automated test's fresh org — already has an indexed document);
confirmed manual answer approval and the questionnaire status transition
to `completed`; confirmed the full `compliance.questionnaire*` audit
trail in Postgres; confirmed both `/compliance` and
`/compliance/questionnaires/[id]` return HTTP 200 (required a `docker
restart` of the `web` container — the bind-mounted dev server did not
pick up the brand-new route directory on its own; see "Machine-specific
note" below).

**Remaining in this sequence, in order**: Audits, Trust Center, Enterprise
Sales Security Review, Data Transfers. See "Next highest-priority task"
below for the concrete plan for each, established before starting so the
whole sequence stays internally consistent (e.g. Questionnaires had to
exist before the Sales Security Review can create/import one — it now
does).

## Branch and commit

Branch: `main`. Nineteen substantive commits through the Vendor Risk
slice (Phase 1 through the AI Incidents slice, then that one); this
session adds the Security Questionnaires commit on top. See `git log`
for exact SHAs.

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
created while it was already running — confirmed twice now (once implicitly
during the Vendor Risk slice, explicitly during the Questionnaires slice,
where a new `/compliance/questionnaires/[id]` route 404'd until `docker
restart agora-origin-web-1`). If a newly-added dynamic route 404s in a live
smoke test, restart the `web` container before assuming the route itself is
broken.

## Exact commands already run (this session, Security Questionnaires slice)

```bash
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add security questionnaire tables"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 171 passed

docker compose run --rm --no-deps api python -m app.seed   # idempotent, confirmed 3x total across sessions

cd apps/web
npx tsc --noEmit
npx eslint .
npx vitest run   # -> 14 passed
npm run build

# live smoke test (after docker restart agora-origin-web-1 to pick up the new route)
docker exec agora-origin-api-1 sh -lc "curl -s -X POST http://localhost:8000/api/v1/auth/login ..."
docker exec agora-origin-api-1 sh -lc "curl -s -b /tmp/cookies.txt -X POST .../questionnaires ..."
docker exec agora-origin-postgres-1 psql -U agora -d agora -c "SELECT action, object_type FROM audit_events WHERE action LIKE 'compliance.questionnaire%';"
```

## Next highest-priority task: Audits (item 3 of 6)

- **Audit**: `Audit` (framework_id nullable, auditor_name, status:
  planned|in_progress|completed, scheduled_at/completed_at) +
  `AuditFinding` (control_id nullable, severity, status: open|remediated)
  — a `high`/`critical` finding creates a remediation Task, the same
  `record_assessment` hook shape reused a fifth time.
- RBAC: likely a new `compliance.audits.manage` permission added to the
  `COMPLIANCE_PERMISSIONS` bundle (same reasoning as every prior slice).
- Router endpoints on the existing `/api/v1/compliance` router; frontend:
  an Audits section on `/compliance` + `/compliance/audits/[id]` detail
  (findings list, remediation-task links).
- Full test/seed/smoke-test/doc/commit cycle, matching every prior slice
  this session.

## Then: Trust Center, Enterprise Sales Security Review, Data Transfers

- **Trust Center**: `TrustCenterItem` (category matching spec §B4's exact
  bullet list: security_overview/privacy_overview/subprocessors/
  data_locations/encryption_practices/availability/
  vulnerability_reporting/compliance_roadmap/dpa_availability/
  incident_communication/responsible_ai/ai_provider_disclosures/
  retention_deletion/business_continuity, status: planned|in_progress|
  implemented|independently_assessed|certified — spec's own status
  vocabulary, not invented — is_public bool). Genuinely public: one
  unauthenticated `GET /api/v1/trust-center/public/{org_slug}` route
  (same "deliberately unauthenticated, narrowly scoped" pattern as the
  webhook receiver/OAuth callback) exposing only `is_public=true` rows,
  plus published+`is_public` Policies as downloadable documents. An
  `EvidenceRequest` model (public POST, no auth) backs spec's "evidence
  request workflow," creating a `core.Task`.
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
docker compose run --rm --no-deps api pytest -q   # confirm still green (171 passed)
cd ../../apps/web && npx vitest run   # confirm still green (14 passed)
```
