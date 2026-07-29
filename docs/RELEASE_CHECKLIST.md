# Release Checklist

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

See `docs/RESUME_BUILD.md` for the next phase.

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
