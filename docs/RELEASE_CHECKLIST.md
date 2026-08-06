# Release Checklist

**⚠ Superseded as a completeness source, 2026-08-04**: several items
below are stale in the *understating* direction — e.g. "Frontend
automated tests (Playwright/unit) — not yet written" (a real Playwright
E2E suite now exists and runs in CI) and "Invitation flow, MFA
enforcement — schema only, no flow" (both are real, tested flows). See
`docs/SPEC_TRACEABILITY_MATRIX.md` and `docs/REMAINING_PRODUCT_GAPS.md`
for current, authoritative status; this file is not corrected
line-by-line given how much has changed since 2026-07-30.

Honest status against the spec's "Definition of Full Completion" (§J) and
"Definition of Done" (§83). This is a **Phase 1 + Phase 2 + partial
Phases 3-9 / local-only** checkpoint, not a production release — most
items below are correctly unchecked.

## Phase 1 (platform foundation) — complete

- [x] Monorepo bootstrapped (`apps/api`, `apps/web`, `apps/worker`)
- [x] Local Docker Compose environment (Postgres+pgvector, Redis, MinIO, Temporal)
- [x] Clean-database migration works (`alembic upgrade head` from empty DB)
- [x] `alembic check` reports no model/migration drift
- [x] Seed script loads successfully and is idempotent
- [x] Auth: signup, login, logout, forgot/reset password
- [x] Tenant-context middleware + RBAC dependency enforced server-side
- [x] Audit log writes on every state-changing auth/task/approval/org action
- [x] Tasks, Approvals, Files, Notifications (shared primitives) — API + UI
- [x] AI Model Gateway + Demo adapter + real Anthropic/OpenAI adapter shells
- [x] Next.js app shell (sidebar, top nav, module switcher), auth pages, dashboard
- [x] Backend: ruff check, ruff format, mypy strict — all clean
- [x] Backend tests: 12 passing (auth flow, tenant isolation, RBAC denial)
- [x] Frontend: eslint, tsc --noEmit, production build — all clean
- [x] `.env.example` / `.env.test.example` / `docs/ENVIRONMENT_VARIABLES.md`
- [x] Missing AI/email credentials degrade gracefully (demo mode / logged email)
- [ ] Frontend automated tests (Playwright/unit) — not yet written
- [ ] Invitation flow, MFA enforcement — schema only, no flow

## Phase 2 (Knowledge & AI Infrastructure) — complete

- [x] KnowledgeBase, Document, DocumentChunk models + migration
- [x] Document parsing (text/plain, text/markdown, text/csv, PDF, DOCX)
- [x] Chunking + embedding (via AI gateway, graceful demo fallback)
- [x] Durable Temporal ingestion workflow (workflow/activity module split
      documented in `docs/DECISIONS.md` ADR-0009)
- [x] Tenant-isolated `/api/v1/knowledge` API + frontend (upload, list, detail)
- [x] Seed script uploads and fully ingests a real sample document
- [x] Similarity search over stored embeddings (cosine, tenant-scoped — ADR-0012)
- [x] AI Copilot: retrieve → ground → generate → cite (`/copilot` page + API)
- [x] Prompt injection defenses (source delimiting, tested against an actual injection attempt)
- [x] Backend tests: 26 passing total; ruff/mypy clean
- [ ] Entity/relationship extraction — deferred, no consumer needs it yet
- [ ] Cross-module intent router — deferred, no other modules exist yet to route across

## Phase 3 (Compliance) — backbone complete, sub-features remain

- [x] Framework/Requirement catalog (global, seeded: GDPR, EU AI Act, ISO 27001)
- [x] Control, ControlMapping, ControlAssessment, Evidence, Risk, Policy models + migration
- [x] Cross-module hook: failed assessment auto-creates a `core.Task` (tested)
- [x] Tenant-isolated `/api/v1/compliance` API + frontend (overview, control detail)
- [x] RBAC: `compliance_manager`/`dpo` roles granted compliance permissions, tested
- [x] Seed script: demo org controls, assessments, risk, evidence link
- [x] Backend tests: 35 passing total; ruff/mypy clean
- [ ] Audits, privacy workflows (RoPA/DPIA/DSAR), vendor
      risk, questionnaires, Trust Center, regulatory intelligence — not
      started, each a substantial feature in its own right
      (AI governance's AI System Inventory was added later — see the
      "Phase 3 extension" section below)

## Phase 4 (Security) — backbone complete, sub-features remain

- [x] SecurityAsset, SecurityFinding, SecurityAlert, SecurityIncident models + migration
- [x] Cross-module hook: critical incident auto-creates a linked Compliance Risk (tested)
- [x] Tenant-isolated `/api/v1/security` API + frontend (dashboard, incident detail)
- [x] RBAC: `security_manager` role granted security permissions, tested
- [x] Seed script: demo org assets, findings, alert, critical incident
- [x] Backend tests: 43 passing total; ruff/mypy clean
- [ ] Cloud/identity provider connectors, vulnerability scanner ingestion,
      incident timeline/evidence/playbooks — not started, need the
      connector SDK (Phase 9) to do properly

## Phase 5 (Sales) — backbone complete, sub-features remain

- [x] Account, Contact, Lead, Opportunity, OutreachMessage models + migration
- [x] Cross-module hook: suppressed contact blocks outreach send (tested, ADR-0019)
- [x] Tenant-isolated `/api/v1/sales` API + frontend (overview, account detail)
- [x] RBAC: `sales_manager`/`sales_representative` roles granted sales permissions, tested
- [x] Seed script: demo org account, contacts (1 suppressed), opportunity, outreach (1 sent, 1 blocked)
- [x] Backend tests: 51 passing total; ruff/mypy clean
- [ ] Sequences/campaigns, lead finder/enrichment, meetings, sales inbox —
      not started, need external connectors (Phase 9) for the real version

## Phase 6 (Support) — backbone complete, sub-features remain

- [x] Customer, Ticket, TicketMessage, KnowledgeArticle, CSATResponse models + migration
- [x] Cross-module hook: security-category ticket auto-creates a linked SecurityAlert (tested, ADR-0020)
- [x] Tenant-isolated `/api/v1/support` API + frontend (overview, ticket detail)
- [x] RBAC: `support_manager`/`support_agent` roles granted support permissions, tested
- [x] Seed script: demo org customer (linked to Sales account), resolved billing ticket + CSAT, security-flagged ticket + auto-created alert, 1 knowledge article
- [x] Backend tests: 61 passing total; ruff/mypy clean
- [ ] SLA policies/timers, QA review scoring, multi-channel connectors, AI-drafted
      replies — not started, need Phase 9 connectors and Copilot integration

## Phase 7 (Automation) — backbone complete, sub-features remain

- [x] Workflow, WorkflowRun, WorkflowStepRun models + migration
- [x] Cross-module hook: `human_approval` step creates a real core.Approval and pauses the run until decided (tested, ADR-0021)
- [x] Tenant-isolated `/api/v1/automation` API + frontend (workflow list/create, detail with run history)
- [x] RBAC: `automation_manager` role granted automation permissions, tested
- [x] Governance: steps lock once a workflow is published to active (spec §41)
- [x] Seed script: 2 active workflows (1 awaiting approval, 1 succeeded), 1 draft workflow
- [x] Backend tests: 70 passing total; ruff/mypy clean
- [ ] Full step vocabulary (Condition/Delay/Loop/Data Transform/Webhook/Subworkflow/AI Step),
      non-manual triggers, visual builder, templates, analytics — not started

All five primary product modules (Compliance, Security, Sales, Support,
Automation) now have a real, tested backbone.

## Phase 8 (Cross-Module Intelligence) — three scenarios complete, one partial, one remains

- [x] "Support Upsell Signal" (spec §69): flagging a ticket creates a real
      sales.Lead + notifies the linked account's owner (tested, ADR-0022)
- [x] "Security Incident" chain (spec §69): a critical incident (already
      linking a Compliance Risk since Phase 4) now also creates a response
      Task and notifies the incident owner (tested, ADR-0023)
- [x] "New Customer" (spec §69): a closed_won Opportunity creates a real
      Support Customer + a 7-day onboarding Task, idempotent, honestly
      skipped when there's no Contact to source an email from (tested, ADR-0025)
- [x] Backend tests: 85 passing total; ruff/mypy clean
- [x] "New AI Tool Adoption" (spec §69) partial: registering a high/
      unacceptable-risk AI system creates a real core.Approval and gates
      the `approved` status transition on it (tested, ADR-0027) — vendor
      questionnaire/Privacy review/policy-publication steps not built
- [ ] Enterprise Sales Security Review — not started, needs customer
      questionnaires, which don't exist yet
- [ ] AI daily briefing, business process discovery, AI recommendation
      engine, organization memory, cross-module intent router — not started

## Phase 9 (Integrations) — two connector shapes complete, OAuth framework complete for six providers

- [x] IntegrationConnection, WebhookEvent, SyncRun models + migration — webhook connector (ADR-0024) + OAuth2 connector framework (ADR-0026, ADR-0028)
- [x] Cross-module hook: a verified webhook event triggers a linked, active, webhook-triggered Automation workflow (tested, ADR-0024)
- [x] Provider-neutral `OAuthConnectorAdapter` (mirrors the AI gateway's Demo/real-provider pattern); real `HubSpotAdapter`/`GoogleAdapter`/`MicrosoftAdapter`/`GitHubAdapter`/`SlackAdapter`/`SalesforceAdapter` + `MockOAuthAdapter` (labeled per provider) fallback when unconfigured (tested, ADR-0026, ADR-0028)
- [x] Encrypted token storage (Fernet), OAuth authorize/callback (no-session, state-verified)/refresh/health/disconnect/sync endpoints
- [x] Provider catalog reports `configured: bool` honestly for all six providers, plus a permission preview of each provider's requested scopes
- [x] Sync runs as a durable Temporal workflow (`IntegrationSyncWorkflow`) rather than inline; audit logging for refresh/sync/disconnect success and failure
- [x] Tenant-isolated `/api/v1/integrations` API (+ two deliberately unauthenticated routes: HMAC-verified webhook receiver, state-verified OAuth callback) + frontend (`/settings/integrations`, with a permission-preview step before Connect)
- [x] RBAC: `integrations.connections.manage` granted to `org_admin`/`automation_manager`, tested
- [x] Seed script: 1 webhook-triggered workflow, 1 connection, 1 verified event (triggered a real run), 1 rejected event — no seeded OAuth connection for any provider, so the demo org shows the honest "Not configured" state
- [x] Backend tests: 137 passing total; ruff/mypy clean
- [x] Frontend tests: 5 Vitest + React Testing Library tests (new test infra this slice) covering the provider catalog, permission preview, and OAuth connection lifecycle UI
- [ ] Every other spec §48 connector category (Email, Marketing, Cloud, remaining Identity/Engineering/
      Communication/Documents/Accounting categories) — not started, all need real OAuth apps/API keys
- [ ] `subscribe()`, `execute_action()`, `collect_evidence()` from spec §49's full Connector Contract,
      sync safety (spec §G2) — sync is durable now but still on-demand only, no polling/scheduled sync

## Phase 3 extension (AI System Inventory) — added alongside Phase 8/9

- [x] AISystem, AIAssessment models + migration — EU AI Act risk tiers (minimal/limited/high/unacceptable)
- [x] Cross-module hook: registering a high/unacceptable-risk system creates a real core.Approval; `approved` status is gated on it (tested, ADR-0027)
- [x] Tenant-isolated `/api/v1/compliance/ai-systems` API + frontend (inventory section on `/compliance`, `/compliance/ai-systems/[id]` detail)
- [x] RBAC: `ai_governance_manager` role (dormant since Phase 1) activated; `dpo` also granted
- [x] Seed script: 1 high-risk system (pending approval), 1 minimal-risk system (approved, 1 assessment)
- [x] Backend tests: 101 passing total; ruff/mypy clean
- [ ] The rest of the "New AI Tool Adoption" chain (vendor questionnaire,
      EU AI Act applicability/DPA review as distinct steps, approved-use
      policy) — not started (AI incidents are done — see below)

## Phase 3 extension (Privacy: RoPA/DPIA/DSAR) — added after the OAuth framework completion

- [x] ProcessingActivity, DPIA, DSAR models + migration — GDPR Articles 30, 35, 15-20
- [x] Cross-module hook: registering a high/unacceptable-risk AI system also creates a linked draft DPIA (the "New AI Tool Adoption" chain's Privacy-assessment step), sharing the AI system's own Approval rather than duplicating it (tested, ADR-0029)
- [x] Cross-module hook: a directly-created `risk_level="high"` DPIA gets its own real core.Approval, gated exactly like AISystem — this build's fourth reuse of that primitive (tested, ADR-0029)
- [x] DSAR lifecycle: `due_at` = created_at + 30 days (GDPR Art. 12(3)), received→in_progress→fulfilled/rejected, `fulfilled_at` set on completion
- [x] Tenant-isolated `/api/v1/compliance/{processing-activities,dpias,dsars}` API + frontend (RoPA/DPIA/DSAR sections on `/compliance`, `/compliance/dpias/[id]` and `/compliance/dsars/[id]` detail)
- [x] RBAC: new `compliance.privacy.manage` permission granted to `dpo` (extended) and `legal` (dormant since Phase 1, first activated here)
- [x] Seed script: 1 processing activity, 1 medium-risk standalone DPIA, 1 fulfilled DSAR, 1 open DSAR
- [x] Backend tests: 149 passing total; ruff/mypy clean
- [x] Frontend tests: 3 new Vitest tests (8 total) covering the RoPA/DPIA/DSAR sections, DSAR creation, and the AI-system-linked DPIA hint
- [ ] Data transfers (Privacy's remaining sub-feature) — not started

## Phase 3 extension (AI Incidents) — added after the Privacy slice

- [x] AIIncident model + migration — always tied to a specific AISystem (EU AI Act Art. 73 "serious incident")
- [x] Cross-module hook: a `critical`-severity AI incident reuses SecurityIncident's exact chain — linked Compliance Risk + response core.Task + owner core.Notification if set (tested, ADR-0030) — the third use of this specific chain shape (ADR-0018, ADR-0023)
- [x] Tenant-isolated `/api/v1/compliance/ai-incidents` API (reuses the existing `compliance.ai_systems.manage` permission, no new permission minted) + frontend (AI Incidents section on `/compliance`, `/compliance/ai-incidents/[id]` detail with linked-Risk and linked-Task banners)
- [x] Seed script: 1 critical AI incident against the demo org's high-risk AI system
- [x] Backend tests: 157 passing total; ruff/mypy clean
- [x] Frontend tests: 2 new Vitest tests (10 total) covering the AI Incidents section rendering and logging a new incident

## Phase 3 extension (Vendor Risk) — added after the AI Incidents slice

- [x] Vendor, VendorAssessment models + migration — spec §12/§67 "Vendors" screen
- [x] Cross-module hook: a `high`/`critical` vendor assessment reuses `record_assessment`'s hook shape a fourth time, auto-creating a linked Compliance Risk (`category="vendor"`) and updating the vendor's `risk_tier` (tested, ADR-0031)
- [x] `Evidence.vendor_id` added as a second optional target alongside `control_id` — no new evidence table
- [x] Tenant-isolated `/api/v1/compliance/vendors` API (RBAC via `compliance.vendors.manage`, added to the `COMPLIANCE_PERMISSIONS` bundle) + frontend (Vendors section on `/compliance`, `/compliance/vendors/[id]` detail with assessment form/history/evidence)
- [x] Seed script: 1 low-risk vendor, 1 vendor with a critical assessment + linked risk
- [x] Backend tests: 164 passing total; ruff/mypy clean
- [x] Frontend tests: 2 new Vitest tests (12 total) covering the Vendors section rendering and adding a new vendor

## Phase 3 extension (Security Questionnaires) — added after the Vendor Risk slice

- [x] Questionnaire, QuestionnaireQuestion, QuestionnaireAnswer models + migration — spec §12/§67 "Security Questionnaires" screen; every question gets an atomically-created `status="missing"` answer row; `Questionnaire.opportunity_id` is a forward-looking nullable FK to `sales_opportunities`
- [x] Answer drafting reuses the existing `app.ai.copilot.ask_copilot` retrieve→ground→generate→cite path as a fallback after an org-wide exact-text match against previously-approved answers; always lands as `status="draft"`, never auto-approved (tested, ADR-0032)
- [x] Tenant-isolated `/api/v1/compliance/questionnaires` API (RBAC via `compliance.questionnaires.manage`, added to the `COMPLIANCE_PERMISSIONS` bundle) + frontend (Questionnaires section on `/compliance`, `/compliance/questionnaires/[id]` detail with status workflow, missing-answer banner, add-question form, per-question suggest/save-draft/approve actions)
- [x] Seed script: 1 questionnaire with 1 approved answer + 1 missing answer
- [x] Backend tests: 171 passing total; ruff/mypy clean
- [x] Frontend tests: 2 new Vitest tests (14 total) covering the Questionnaires section rendering and creating a new questionnaire
- [x] Live Docker smoke test: created a second questionnaire with an identically-worded question and confirmed live reuse (`source_type="reused_from_library"`); confirmed the honest AI-Copilot fallback path on a genuinely novel question (with real retrieval citations against the seeded Knowledge document); confirmed manual answer approval and questionnaire status transition to `completed`; confirmed the full `compliance.questionnaire*` audit trail in Postgres; confirmed both `/compliance` (Questionnaires section) and `/compliance/questionnaires/[id]` return HTTP 200

## Phase 3 extension (Audits) — added after the Security Questionnaires slice

- [x] Audit, AuditFinding models + migration — spec §12/§67 "Audits" screen; an Audit groups many findings under one auditor engagement (optionally against a catalog Framework), a different shape from the single-judgement ControlAssessment/VendorAssessment/AIAssessment pattern
- [x] Cross-module hook: a `high`/`critical` finding reuses `record_assessment`'s hook shape a fifth time, auto-creating a remediation `core.Task` — specifically the Task-creating half a `fail` ControlAssessment uses, not the Risk-creating half VendorAssessment/AIIncident use (tested, ADR-0033)
- [x] Tenant-isolated `/api/v1/compliance/audits` API (RBAC via `compliance.audits.manage`, added to the `COMPLIANCE_PERMISSIONS` bundle, and granted to the pre-seeded but previously-unused `auditor` system role) + frontend (Audits section on `/compliance`, `/compliance/audits/[id]` detail with status workflow, add-finding form, findings list, mark-remediated action)
- [x] Seed script: 1 in-progress audit with 1 critical finding + linked remediation task, 1 remediated low-severity finding
- [x] Backend tests: 179 passing total; ruff/mypy clean
- [x] Frontend tests: 2 new Vitest tests (16 total) covering the Audits section rendering and creating a new audit
- [x] Live Docker smoke test: created a critical finding and confirmed a real linked remediation Task (title/module/priority verified via `/api/v1/tasks`); confirmed a low-severity finding creates no task; marked a finding remediated and completed the audit (`completed_at` set); confirmed the full `compliance.audit*` audit trail in Postgres; confirmed both `/compliance` (Audits section) and `/compliance/audits/[id]` return HTTP 200

## Phase 3 extension (Trust Center) — added after the Audits slice

- [x] New `app.trust_center` module (not `app.compliance`) — `TrustCenterItem` (one row per org per spec B4 category, `policy_id` optionally linking an existing `Policy`) + `EvidenceRequest` models + migration; separate module because its public surface is a fundamentally different security model from the rest of Compliance (ADR-0034)
- [x] Genuinely public, unauthenticated `GET /api/v1/trust-center/public/{org_slug}` (only `Depends(get_db)`, no `OrgContext` — same pattern as the Phase 9 webhook receiver/OAuth callback, ADR-0024) — returns only `is_public` items, and only surfaces a linked Policy when it's `published`; public `POST .../evidence-requests` always creates a linked `core.Task` (tested)
- [x] Authenticated management routes (`/api/v1/trust-center/items` upsert, `/evidence-requests` list + fulfill) — RBAC via `compliance.trust_center.manage`, added to the `COMPLIANCE_PERMISSIONS` bundle, + frontend (Trust Center management section on `/compliance`, genuinely public `/trust/[org_slug]` page outside the authenticated `(app)` route group with an evidence-request submission form)
- [x] Seed script: 3 public items (1 linked to a published Policy), 1 private item, 1 open evidence request + linked task
- [x] Backend tests: 189 passing total; ruff/mypy clean
- [x] Frontend tests: 3 new Vitest tests (19 total) covering Trust Center item rendering, saving an item, and fulfilling an evidence request
- [x] Live Docker smoke test: confirmed the public endpoint returns real data with **zero cookies sent**; confirmed a 404 for an unknown org slug; submitted a public evidence request with no auth and confirmed a real linked Task via `/api/v1/tasks`; confirmed authenticated management list/fulfill endpoints; confirmed the full `trust_center.*` audit trail in Postgres including anonymous (`actor_user_id IS NULL`) rows; confirmed both `/compliance` and `/trust/acme-ai-technologies` return HTTP 200

## Phase 8 (Enterprise Sales Security Review) — added after the Trust Center slice, the fourth of spec §69's five named cross-module scenarios

- [x] `SecurityReview` model + migration (`app/compliance/models.py`) — one row per Sales Opportunity (unique, 409 on a second attempt); starting a review creates/imports a `Questionnaire` and moves `Opportunity.stage` to a new `security_review` value, setting `is_deal_blocker=True` — the payoff for `Questionnaire.opportunity_id` existing since ADR-0032 with no caller until now
- [x] Materiality-threshold gate: an Opportunity at/above `SECURITY_REVIEW_MATERIALITY_THRESHOLD` (50,000) opens a real `core.Approval` at start, reusing the same primitive the AI System Inventory/DPIA gates use; clearing is refused until it's granted (tested, ADR-0035)
- [x] Sync reuses `suggest_questionnaire_answer` for every still-missing question, attaches the most relevant `Evidence` for any Control-referencing answer with none yet, and opens one deduplicated remediation `core.Task` per remaining gap — a sixth reuse of the "creates a tracked consequence" hook shape (tested)
- [x] Clear is refused (422) while gaps or a pending Approval remain; once satisfied, compiles every approved Q&A + Evidence titles into a real trust-package `core.File` and notifies the opportunity owner
- [x] Tenant-isolated `/api/v1/compliance/security-reviews` API (create/list/detail/status/sync/clear; RBAC via `compliance.security_reviews.manage`, added to the `COMPLIANCE_PERMISSIONS` bundle) + frontend (Security Reviews section on `/compliance` with a start-review form, `/compliance/security-reviews/[id]` detail with gap count/approval status/sync/clear actions, and a deal-blocker indicator on the Sales account detail page)
- [x] Seed script: 1 in-progress review for the seeded Nordwind Robotics opportunity, importing its existing questionnaire, with 1 remediation task from the sync
- [x] Backend tests: 198 passing total; ruff/mypy clean
- [x] Frontend tests: 2 new Vitest tests (21 total) covering the Security Reviews section rendering and starting a new review
- [x] Live Docker smoke test: confirmed the seeded review (imported questionnaire); created a high-value opportunity and confirmed a real Approval opened on start; confirmed sync suggests an answer and opens a remediation task; confirmed clear is refused (422) both for open gaps and, after resolving them, for the still-pending Approval; confirmed clear succeeds once the Approval is granted, generating a real trust-package File; confirmed the full `compliance.security_review.*` audit trail in Postgres; confirmed `/compliance`, `/compliance/security-reviews/[id]`, and `/sales/accounts/[id]` all return HTTP 200

## Phase 3 extension (Data Transfers) — added after the Enterprise Sales Security Review slice; the sixth and last item of this session's Compliance/Trust program

- [x] `DataTransfer` model + migration (GDPR Chapter V, Articles 44-49) — the fourth and last Privacy sub-feature alongside RoPA/DPIA/DSAR, extending `app.compliance` directly (not a new module, unlike Trust Center) and reusing the existing `compliance.privacy.manage` permission (no new RBAC grant needed)
- [x] Cross-module hook: a `transfer_mechanism="derogation"` transfer auto-creates a linked Compliance `Risk` — Article 49 derogations are meant to be exceptional, not routine, making them the risk-bearing choice among the four mechanisms; the seventh reuse of `record_assessment`'s hook shape (tested, ADR-0036)
- [x] Tenant-isolated `/api/v1/compliance/data-transfers` API (create/list/detail/status) + frontend (Data Transfers section on `/compliance` with a mechanism-select create form and an inline status dropdown per row — no dedicated detail page, given the shape's simplicity)
- [x] Seed script: 1 SCC-backed transfer linked to the seeded "Candidate application processing" activity, 1 derogation-based transfer + linked risk
- [x] Backend tests: 206 passing total; ruff/mypy clean
- [x] Frontend tests: 2 new Vitest tests (23 total) covering the Data Transfers section rendering and logging a new transfer
- [x] Live Docker smoke test: confirmed the seeded transfers (one linked to a real ProcessingActivity); created an adequacy-decision transfer and confirmed no risk was created; created a derogation transfer and confirmed a real linked Risk appeared in the Risk Register; confirmed the status lifecycle (active → under_review → terminated); confirmed the full `compliance.data_transfer.*` audit trail in Postgres; confirmed `/compliance` returns HTTP 200

**This completes all six items of the Compliance/Trust program**: Vendor Risk, Security Questionnaires, Audits, Trust Center, Enterprise Sales Security Review, Data Transfers.

## Public site & auth modernization (branch `ui/public-site-and-auth-modernization`, 2026-08-05)

Not a domain module — replaces the placeholder root route with a real
public marketing site and rebuilds the authentication UX. See
`docs/PUBLIC_SITE_AUDIT.md`, `docs/PUBLIC_SITE_DESIGN.md`,
`docs/AUTH_UX_AUDIT.md`, and `docs/PUBLIC_SITE_IMPLEMENTATION_PLAN.md`
for the full audit/design/plan trail.

- [x] Public marketing site: homepage, `/features`, `/solutions`,
      `/trust` (marketing trust/security content — distinct from the
      existing per-org `/trust/[org_slug]` Trust Center page above),
      `/pricing`, `/about`, `/contact` (real backend, see below),
      `/privacy`, `/terms`, `/cookies` — 22 reusable components, no
      fabricated logos/testimonials/metrics, no invented € pricing
      (`Starter` is genuinely free; `Growth`/`Business`/`Enterprise`
      route to "Contact sales" since no plan has a real price in
      `PLAN_CATALOG`)
- [x] `POST /api/v1/marketing/demo-requests` — public, persists to a new
      `DemoRequest` table, audited with `organization_id=None`; no list
      endpoint was built (a caught design flaw — see design doc's
      "Correction made during implementation" note — an org-scoped list
      endpoint would have let any org_admin see every other prospect's
      submission, since this codebase has no platform-superuser role)
- [x] Auth UX rebuild: sign-in, sign-up, forgot/reset-password,
      email-verification, invitation-acceptance (new preview + decline
      endpoints), MFA challenge — all restyled onto shared
      `AuthLayout`/`AuthCard`/`AuthField`/`PasswordField` components,
      preserving every existing backend contract, rate limit, and
      security property (no account enumeration, no open redirects —
      `isSafeRedirectTarget` unit-tested)
- [x] Dashboard relocated from `/` to `/dashboard` (root now serves the
      public homepage) — 9+ frontend call sites and one backend SSO
      redirect updated; caught and fixed one missed assertion in
      `test_billing.py` via the full pytest run
- [x] New `middleware.ts`: cookie-presence redirect logic only
      (auth-only paths redirect authenticated visitors away from
      `/login`/`/signup`; protected paths redirect to
      `/login?redirect=`); `AuthGuard` and per-request API authorization
      remain the real authorization boundary, unchanged
- [x] Marketing consent: new `User.marketing_consent` column, separate
      unchecked-by-default control on signup, deliberately not bundled
      with the required Terms/Privacy acceptance checkbox
- [x] Accessibility: new `public-site-and-auth-accessibility.spec.ts`
      (15 axe + keyboard-only tests, all passing) — fixed 9 real
      `--fg-subtle`→`--fg-muted` contrast violations and 2 unlabeled
      onboarding `<select>` elements found by the scan
- [x] SEO: `sitemap.xml`, `robots.txt`, blanket `noindex` on every
      authenticated route via `(app)/layout.tsx` metadata inheritance
- [x] New `public-site-and-auth.spec.ts` (7 tests covering the spec's
      17 named journeys: signup → email verification → onboarding →
      dashboard → sign-out → sign-in, forgot/reset-password,
      invite-accept, invalid-invitation, authenticated-user-redirected-
      away-from-login, redirect-back-after-login, mobile nav, keyboard-
      only signup)
- [x] Backend: 2 new migrations (`DemoRequest` table,
      `User.marketing_consent`), 11 new backend tests (marketing +
      invitation preview/decline + signup consent), full pytest/ruff/
      mypy clean
- [x] Full regression pass: existing `auth.spec.ts`, `onboarding.spec.ts`
      Playwright suites re-verified passing after the dashboard
      relocation and new middleware (20/20 in the combined run); a
      separate full pass over `sales-lead-finder.spec.ts`,
      `sales-lead-finder-accessibility.spec.ts`, `business-
      intelligence.spec.ts`, `modules.spec.ts`, `settings.spec.ts`
      surfaced and fixed 2 real bugs pre-dating this branch (see
      `docs/KNOWN_LIMITATIONS.md`'s Testing section: org-deletion's
      table-coverage safety net was missing 8 Sales Lead Finder tables,
      and the deletion-execute endpoint left a stale session cookie
      that this branch's new `middleware.ts` then mis-treated as "still
      authenticated") — both fixed, with a new regression test added
      for the cookie fix; the other 2 reported failures did not
      reproduce in isolated re-runs (resource contention with a
      concurrently running screenshot-capture script)
- [x] 12 screenshots captured (homepage desktop/mobile/product-preview,
      sign-in desktop/mobile, sign-up desktop/validation-state,
      forgot-password, email-verification, invitation-acceptance,
      onboarding, final onboarding step, authenticated dashboard
      transition) via a scratch Playwright script, deleted after use
- [x] Full monorepo Playwright suite (71 tests, every spec) run in one
      pass: 66/71 green, 5 failures — 4 sharing one signature (`signup()`
      helper timing out waiting for the post-signup `/onboarding`
      redirect) and 1 `net::ERR_NO_BUFFER_SPACE` (a Windows OS-level
      socket-exhaustion signal), consistent with ~90 sequential
      browser-driven tests over 15+ minutes on a single worker on this
      dev machine. None touch code changed by this branch or this
      session's org-deletion fix; all 5 passed cleanly when re-run in
      isolation, confirming environmental flakes, not regressions.
      Backend: full pytest suite 529 passed, 2 skipped; ruff and mypy
      clean across the whole `apps/api` tree. Frontend: `tsc --noEmit`
      clean, ESLint 0 errors (3 pre-existing informational
      `react-hooks/incompatible-library` notices on `useForm().watch()`
      in password-strength UIs — expected, not a defect), Vitest 75/75,
      production build succeeds for every route including `/dashboard`,
      `sitemap.xml`, `robots.txt`, and the new middleware. Docker smoke:
      all 7 compose services healthy, Alembic at head, homepage/login/
      dashboard/sitemap/robots/API health all return 200 through the
      live stack.
- [x] Merged to `main` via PR #10, 2026-08-06, after the complete
      verification suite above passed

## Homepage product-module carousel (branch `ui/homepage-module-carousel`, 2026-08-06)

Follow-on to the public site above — see `docs/PUBLIC_SITE_DESIGN.md` §11
for the full design and `docs/PUBLIC_SITE_IMPLEMENTATION_PLAN.md` Phase 8.

- [x] Six real photographs (Compliance, Security, Sales, Customer Support,
      Automation, AI Governance), converted from ~1.5MB PNGs to mozjpeg
      quality-82 JPEGs (~80-100KB each, no visible quality loss) — no
      generated/stock replacement images, no text baked into the images
- [x] Responsive carousel on `embla-carousel-react` (this codebase's first
      carousel dependency) — centered-active/partial-peek layout on
      tablet/desktop, full-width single-slide with a taller crop and a
      subject-preserving `object-position` bias on mobile; prev/next,
      pagination dots, live counter, keyboard (arrow-key) navigation,
      touch swipe
- [x] Optional autoplay (~7s), pausing on hover/focus/the visible
      play/pause control, never offered under `prefers-reduced-motion`
      (this codebase's first `matchMedia` check in application code —
      previously only a blanket CSS rule existed)
- [x] Real, working CTA per module into a newly-anchored `/features#<slug>`
      section (no decorative links — `/features`'s six sections had no
      `id` anchors before this branch)
- [x] Two real bugs found and fixed during implementation (neither
      pre-existing): `middleware.ts`'s matcher redirecting the new
      `/images/*` assets to `/login` (fixed generically for any
      extensioned path, not just images); Embla's own pointerdown
      handling silently swallowing clicks on in-slide CTA links before
      Next's `<Link>` ever saw them (fixed via Embla's `watchDrag`
      callback) — see `docs/PUBLIC_SITE_DESIGN.md` §11 for the full
      mechanism of each
- [x] 18 Vitest component tests (all 6 slides, content, next/prev,
      wraparound, pagination, keyboard nav, alt text, CTA hrefs, reduced
      motion, autoplay timer-wiring contract — see
      `docs/KNOWN_LIMITATIONS.md` for why full autoplay timing isn't
      asserted under jsdom)
- [x] 9 Playwright functional journeys + 2 additional axe/keyboard tests
      on top of the existing public-site accessibility suite — 0
      violations in both the default state and after navigating to a
      non-initial slide
- [x] `tsc --noEmit` clean, ESLint 0 errors (a real `react-hooks/
      set-state-in-effect` lint error was found and fixed properly —
      the reduced-motion check moved from `useState`+`useEffect` to
      `useSyncExternalStore` — not suppressed), Vitest 93/93 (whole
      frontend suite), production build succeeds for every route
- [x] Full monorepo Playwright suite: 77/82 passed on the first full
      sequential run; the 5 failures (one pre-existing big journey test,
      3 unrelated Sales Lead Finder tests, and the org-deletion test
      fixed earlier this session) all passed cleanly when re-run in
      isolation, confirming environmental flakes from the ~16-minute,
      82-test sequential run on this dev machine — none touch code this
      branch changed. All carousel-specific specs (9 functional + 2
      accessibility/keyboard) were green on every run, including the
      full-suite pass
- [x] Docker smoke: all 7 compose services healthy, Alembic at head,
      homepage/`/features`/carousel images/API health all return 200
      through the live stack
- [x] Merged to `main`, 2026-08-06, after the complete verification
      suite passed

## Shared interactive-card hover/focus/press system (branch `ui/interactive-card-system`, 2026-08-06)

Follow-on to the carousel above — see `docs/PUBLIC_SITE_DESIGN.md` §12
for the full design and `docs/PUBLIC_SITE_IMPLEMENTATION_PLAN.md`
Phase 9. No branch name or merge-to-main instruction was given for this
task (unlike the two above) — committed and pushed to its own branch,
left for review rather than self-merged.

- [x] Card audit completed first, before any code — of every public-
      site card-like component, only three had (or could honestly gain)
      a real per-card destination; the rest deliberately excluded
- [x] Shared tokens (`--shadow-glow`, `--transition-card`/`--ease-card`,
      `--transition-card-media`) and `InteractiveCard`/`CardMedia`/
      `CardActionArrow` primitives
- [x] Applied to the module carousel (neighboring slides are now real,
      click-to-select `<button>`s — a new capability, not just a visual
      restyle), `ModuleOverview` (gained real links into
      `/features#<slug>`, previously static), and `PricingPreview`
      (hover/focus-within only, no redundant interactive wrapper around
      its existing CTA button)
- [x] Confirmed `components/ui/card.tsx` and all 68 of its call sites
      (authenticated dashboard, auth card, shared panels) untouched — a
      new, separate component, not a change to the shared one
- [x] Two real, non-cosmetic bugs found and fixed: a CSS Cascade Layers
      bug in `globals.css` (an unlayered `border-color` reset was
      silently beating every `hover:border-*`/`focus-visible:border-*`
      utility app-wide, not just the new ones — fixed by moving it into
      `@layer base`), and a Tailwind v4 test-methodology trap
      (`scale`/`translate` utilities compile to those standalone CSS
      properties, not a composed `transform` string)
- [x] 32 new/updated Vitest tests (11 for the primitives, 3 for
      `ModuleOverview`, 3 added to the carousel suite, plus existing
      carousel tests re-verified passing), 9 new Playwright journeys
      (hover, keyboard focus, Enter-activation, neighbor-select,
      arrow-key nav, reduced motion, mobile tap, axe, non-clickable-card
      exclusion) — all green, including after fixing the two real bugs
      above and several test-methodology mistakes of its own (Tailwind
      v4's `scale`/`translate`, `:focus-visible` requiring genuine
      keyboard-driven focus not a bare scripted `.focus()`, and
      Playwright's `includeHidden` needed to reach the intentionally
      `aria-hidden` neighboring carousel slides)
- [x] Responsive verification across all 6 required breakpoints — zero
      horizontal overflow at any of them, including while the
      hover-grown active card visually overlaps its neighbors' peek
      area (expected at this scale, not a bug)
- [x] Full check suite: `tsc --noEmit` clean, ESLint 0 errors, Vitest
      109/109 (whole frontend suite — 2 separate runs each surfaced a
      different, unrelated set of pre-existing test flakes under load;
      all confirmed passing cleanly in isolation, none touch this
      branch's files), production build succeeds, full Playwright suite
      91/91 clean on the final run (the same environmental-timing class
      of issue this whole project has repeatedly documented — a keypress
      immediately after a confirmed-focused element occasionally landing
      before React's listeners settle post-hydration — hit two arrow-key
      tests, including one pre-existing; fixed both with a short settle
      delay after confirming the root cause via direct debugging, not by
      loosening the assertions), Docker smoke confirmed (all 7 services
      healthy, Alembic at head, homepage/`/features`/`/pricing`/API all
      return 200 through the live stack)
- [x] Committed and pushed to `origin/ui/interactive-card-system`

## Not started (tracked in docs/IMPLEMENTATION_PLAN.md)

- [ ] Phase 10 — Enterprise (SSO/SAML/SCIM)
- [ ] AWS Terraform, ECS, RDS, CloudFront, WAF, GitHub Actions CI/CD (spec §L/§M/§N)
- [ ] Trust Center
- [ ] Security release baseline (spec §H): CSRF, CSP, rate limiting, SSRF
      controls, malware scanning, brute-force protection

## Gate for calling *any* future milestone "production ready"

Before this checklist can claim more than Phase 1:

1. All items in `docs/KNOWN_LIMITATIONS.md` under "Security" resolved or
   explicitly risk-accepted with a named owner.
2. AWS deployment evidence recorded in `docs/DEPLOYMENT_EVIDENCE.md` and
   `docs/RECOVERY_TEST_RESULTS.md` (not yet created — see spec §N10).
3. Every domain module claims completion only per its own
   `docs/IMPLEMENTATION_STATUS.md` entry — no module is "done" because a
   route exists; it needs DB + service + API + RBAC + audit + UI + tests
   (spec §83).
