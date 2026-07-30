# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

Phase 1 (platform foundation) and Phase 2 (Knowledge & AI Infrastructure)
are complete. All five primary product modules — Compliance, Security,
Sales, Support, and Automation (Phases 3-7) — have a real, tested
backbone. Phase 8 (Cross-Module Intelligence) now has four of spec §69's
five named scenarios fully implemented (as of this session's Enterprise
Sales Security Review slice), plus a partial fifth ("New AI Tool
Adoption") with two of its steps done. Phase 9 (Integrations) has a
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

**Trust Center** (spec B4, ADR-0034) — the first slice in this sequence
to get its own module (`app/trust_center/`) rather than living inside
`app/compliance/`: its defining feature, `GET /api/v1/trust-center/public/
{org_slug}`, is genuinely unauthenticated (only `Depends(get_db)`, no
`OrgContext` at all) — the same "no session, a different capability
boundary" pattern the Phase 9 webhook receiver/OAuth callback already
established (ADR-0024), a fundamentally different security model from
every other tenant-scoped Compliance sub-feature built this session.
`TrustCenterItem` is one row per organization per spec B4's 14 fixed
categories (`uq_trust_center_item_org_category`), upserted rather than
duplicated; `policy_id` optionally links an existing `compliance.Policy`
for "downloadable approved documents," but the public endpoint only ever
surfaces it when that Policy is `status="published"` — even an
`is_public` item never leaks a still-draft linked policy. `EvidenceRequest`
backs spec B4's public "evidence request workflow": a public,
unauthenticated POST that always creates a linked `core.Task`
(`actor_user_id=None` on its audit event, since there's no authenticated
actor). RBAC: `compliance.trust_center.manage` added to the existing
`COMPLIANCE_PERMISSIONS` bundle for the authenticated management side;
the public routes have no RBAC by design. Frontend: an authenticated
Trust Center management section on `/compliance` (upsert form, items
list, evidence-request list with fulfill action) + a genuinely public
`/trust/[org_slug]` page — a new top-level route *outside* the
`app/(app)/` route group entirely (so it isn't wrapped by `AuthGuard`),
rendering only `is_public` items plus an evidence-request submission
form. Seed data: 3 public items (one linked to a real published Policy,
one still `planned`), 1 private item, 1 open evidence request with its
linked task.

**Enterprise Sales Security Review** (`SecurityReview`,
`app/compliance/models.py`, ADR-0035) — the payoff for
`Questionnaire.opportunity_id` having existed since ADR-0032 with no
caller: this is that caller, and the fourth of spec §69's five named
cross-module scenarios to reach full implementation. One
`SecurityReview` row per Sales Opportunity (unique constraint; the
router returns 409 on a second attempt rather than a raw DB error).
`start_security_review` creates or imports a `Questionnaire` against the
opportunity, moves `Opportunity.stage` to a new `security_review` value,
sets `is_deal_blocker=True` immediately, and — for an opportunity at or
above `SECURITY_REVIEW_MATERIALITY_THRESHOLD` (50,000, a documented
judgment call) — opens a real `core.Approval` gating the eventual clear,
reusing the same primitive `register_ai_system`/`create_dpia` already
gate on. `sync_security_review` reuses `suggest_questionnaire_answer`
for every still-`missing` question, attaches the most relevant
`Evidence` for any answer whose `control_id` has none yet, and opens a
deduplicated remediation `core.Task` per remaining gap (a sixth reuse of
this build's "creates a tracked consequence" hook shape). A "gap" is any
answer not yet `approved`, or an approved one referencing a Control with
still no Evidence. `clear_security_review` refuses (422) while gaps or
the Approval remain, then compiles every approved Q&A + Evidence titles
into a real trust-package `core.File` and notifies the opportunity
owner. RBAC: `compliance.security_reviews.manage` added to the existing
`COMPLIANCE_PERMISSIONS` bundle. Frontend: a Security Reviews section on
`/compliance` (start-review form with opportunity + optional
questionnaire-import selects, list) + `/compliance/security-reviews/[id]`
detail (gap count, approval status, sync/clear actions, linked
questionnaire card) + a deal-blocker indicator on the Sales account
detail page's opportunity cards. Seed data: 1 in-progress review for the
seeded Nordwind Robotics opportunity, importing its existing
questionnaire (from the Questionnaires slice), with 1 remediation task
from the sync (its one question honestly still `draft` after the AI
Copilot's demo-mode fallback, not fabricated as `approved`).

All checks pass: **198 backend tests** (was 164 before Questionnaires,
171, 179, 189 after Trust Center), ruff + mypy --strict clean; frontend
eslint + tsc + production build clean; **21 frontend tests** (was 12,
14, 16, 19), all passing. Live Docker smoke test for Enterprise Sales
Security Review: confirmed the seeded review's imported questionnaire;
created a high-value (150,000) opportunity and confirmed a real Approval
opened automatically on start; added a question, synced, and confirmed
a real AI-Copilot-suggested draft answer plus a linked remediation Task;
confirmed clearing was refused (422) with the gap open, refused again
(422) after manually approving the answer but before the Approval was
granted, then succeeded once the Approval was granted via
`/api/v1/approvals/{id}/decide` — generating a real trust-package File;
confirmed the full `compliance.security_review.*` audit trail in
Postgres; confirmed `/compliance`, `/compliance/security-reviews/[id]`,
and `/sales/accounts/[id]` all return HTTP 200 (again required a `docker
restart` of the `web` container — now confirmed on five separate
slices; see "Machine-specific note" below).

**Remaining in this sequence**: Data Transfers (item 6 of 6, the last
one). See "Next highest-priority task" below for the concrete plan.

## Branch and commit

Branch: `main`. Nineteen substantive commits through the Vendor Risk
slice (Phase 1 through the AI Incidents slice, then that one), plus the
Security Questionnaires commit, the Audits commit, the Trust Center
commit, and now this session's Enterprise Sales Security Review commit
on top. See `git log` for exact SHAs.

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
reliably picked up brand-new route directories (`app/(app)/.../[id]/page.tsx`,
and a brand-new top-level `app/trust/[org_slug]/page.tsx`) created
while it was already running — now confirmed on five separate slices
(Vendor Risk, Security Questionnaires, Audits, Trust Center, Enterprise
Sales Security Review), each time a new route 404'd until `docker
restart agora-origin-web-1`. Treat this as routine: after adding any new
dynamic route, restart the `web` container before running its live smoke
test, rather than debugging the route itself when it 404s.

A new top-level module needs a manual registration step beyond just
writing the model file: `app/db/register_all_models.py` side-effect-
imports every domain's `models.py` so Alembic autogenerate (and any
script/activity that flushes without going through `app.main`'s import
graph) can resolve its tables and foreign keys. Forgetting this produces
a *silently empty* migration (`alembic revision --autogenerate` runs
clean but generates a no-op `upgrade()`/`downgrade()`) rather than an
error — always sanity-check a freshly generated migration actually
contains `op.create_table(...)` before formatting/applying it, especially
for a slice that introduces a genuinely new `app/<module>/` package
rather than extending an existing one.

## Exact commands already run (this session, Enterprise Sales Security Review slice)

```bash
# SecurityReview lives in app.compliance.models (already registered in
# register_all_models.py), so no new registration step was needed this
# time — unlike Trust Center's brand-new app.trust_center module.

docker compose run --rm --no-deps api alembic revision --autogenerate -m "add security review tables"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 198 passed

docker compose run --rm --no-deps api python -m app.seed   # idempotent, confirmed 6x total across sessions

cd apps/web
npx tsc --noEmit
npx eslint .
npx vitest run   # -> 21 passed
npm run build

docker restart agora-origin-web-1   # pick up /compliance/security-reviews/[id]

# live smoke test — full 10-step flow against a fresh high-value opportunity
curl -s -b cookies.txt -X POST .../sales/accounts -d '{"name":"Smoke Test Enterprises"}'
curl -s -b cookies.txt -X POST .../sales/opportunities -d '{"account_id":"...","title":"...","value":150000}'
curl -s -b cookies.txt -X POST .../compliance/security-reviews -d '{"opportunity_id":"..."}'   # opens a real Approval (value >= 50,000)
curl -s -b cookies.txt -X POST .../compliance/questionnaires/{qid}/questions -d '{...}'
curl -s -b cookies.txt -X POST .../compliance/security-reviews/{id}/sync   # suggests an answer, opens a remediation Task
curl -s -b cookies.txt -X POST .../compliance/security-reviews/{id}/clear   # 422: gap still open
curl -s -b cookies.txt -X PATCH .../compliance/questionnaires/{qid}/questions/{qqid}/answer -d '{"status":"approved",...}'
curl -s -b cookies.txt -X POST .../compliance/security-reviews/{id}/clear   # 422: Approval still pending
curl -s -b cookies.txt -X POST .../approvals/{approval_id}/decide -d '{"approve":true}'
curl -s -b cookies.txt -X POST .../compliance/security-reviews/{id}/clear   # 200: cleared, trust package generated
docker exec agora-origin-postgres-1 psql -U agora -d agora -c "SELECT action FROM audit_events WHERE action LIKE 'compliance.security_review%';"
```

## Next highest-priority task: Data Transfers (item 6 of 6, last in this sequence)

- **Data Transfers**: `DataTransfer` (processing_activity_id nullable,
  destination_country, transfer_mechanism: adequacy_decision|sccs|bcrs|
  derogation, safeguards_description, status), extending Privacy exactly
  like ProcessingActivity/DPIA/DSAR did (ADR-0029's pattern) — lives in
  `app/compliance/models.py` alongside the rest of Privacy, not a new
  module (unlike Trust Center's special case: Data Transfers has no
  public/unauthenticated surface).
- RBAC: likely `compliance.privacy.manage` already covers it (the
  existing Privacy permission bundle), rather than minting a new
  permission — Data Transfers is a Privacy sub-feature per spec §12, the
  same reasoning ProcessingActivity/DPIA/DSAR already established.
- Router endpoints on the existing `/api/v1/compliance` router; frontend:
  a Data Transfers section on `/compliance` (create form, list) — a
  detail page is optional given the shape's simplicity (no nested
  child entities the way Questionnaire/Audit/SecurityReview have).
- Full test/seed/smoke-test/doc/commit cycle, matching every prior slice
  this session. This is the last of the six items — after it, do a final
  full-sequence documentation pass (confirm `docs/IMPLEMENTATION_STATUS.md`'s
  "5/6 done" framing becomes "6/6 done" and update the top-level summary
  in every doc that still lists Data Transfers as remaining).

No AWS resources are to be created without explicit approval; only
prepare infra-as-code where it naturally fits (Data Transfers doesn't
inherently need new AWS infrastructure, so this constraint is unlikely
to come up).

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (198 passed)
cd ../../apps/web && npx vitest run   # confirm still green (21 passed)
```
