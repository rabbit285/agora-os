# Implementation Status

Legend: `[x]` Complete · `[~]` In Progress · `[ ]` Not Started · `[!]` Blocked

Last updated: 2026-07-29 (Phase 1 + Phase 2 complete; Phase 3 Compliance, Phase 4 Security, Phase 5 Sales, Phase 6 Customer Support, and Phase 7 Business Automation backbones; Phase 8's three Cross-Module Intelligence slices; Phase 9's Webhook connector and provider-neutral OAuth2 framework with HubSpot — verified end-to-end)

## Platform

- [x] Monorepo structure
- [x] Docker Compose local infra (Postgres+pgvector, Redis, MinIO, Temporal) — all services healthy, verified via `docker compose ps`
- [x] Environment/config validation + `.env.example`
- [x] Core domain models (organizations, legal_entities, users, teams,
      memberships, roles, permissions)
- [x] Alembic migrations — generated, applied to real Postgres, `alembic check` reports no drift
- [x] Auth (signup/login/session/password reset) — verified via pytest and live curl smoke test
- [ ] MFA enforcement flow (schema present, flow not built)
- [x] Tenant-context middleware — verified: cross-org header spoofing rejected (test_tenant_isolation.py)
- [x] RBAC enforcement dependency — verified: employee role blocked from mutating actions (test_rbac.py)
- [x] Audit log (append-only at the application layer — see KNOWN_LIMITATIONS.md)
- [x] Tasks (shared primitive) — API + UI, live-tested
- [x] Approvals (shared primitive) — API + UI
- [x] Files (upload/download, signed URLs) — implemented, not live-tested against MinIO
- [x] Notifications (in-app only) — API + schema; no UI badge yet
- [x] Next.js app shell (sidebar/nav/module switcher stub) — production build verified
- [x] Seed script (Acme AI Technologies demo org) — idempotent, run twice successfully

## Knowledge

- [x] KnowledgeBase, Document, DocumentChunk models + migration
- [x] Document parsing: text/plain, text/markdown, text/csv, PDF, DOCX — genuine extractors, not stubs
- [x] Unsupported formats marked `unsupported_format` honestly, not faked as ready
- [x] Chunking (fixed-size with overlap) + embedding via AI gateway
- [x] Temporal `DocumentIngestionWorkflow` (durable, decoupled from the HTTP request)
- [x] `/api/v1/knowledge` router (knowledge bases, documents, chunks) — tenant-isolated, tested
- [x] Frontend: upload, list, detail pages with live status polling
- [x] Seed script uploads and fully ingests one real sample document
- [x] Similarity search (`search_chunks`, cosine similarity, tenant-scoped — see ADR-0012 for the not-pgvector-yet trade-off)
- [ ] Entity/relationship extraction (spec §11 knowledge graph) — not started

## AI

- [x] Model Gateway interface + Demo adapter
- [x] `AiRun` logging, including retrieval-sourced citations (not model-asserted)
- [x] `embed()` on the gateway (fixed 1536-dim, graceful demo fallback for non-embedding providers)
- [x] AI Copilot: retrieve → ground → generate → cite (`app/ai/copilot.py`), live-tested end to end
- [x] RAG / citations — implemented, tenant-isolated, tested
- [x] Prompt injection defenses — minimal (source delimiting + instruction, tested); no tool-execution allowlist yet (not needed until the Copilot can take actions)
- [ ] Cross-module intent router (Compliance/Security/Sales context beyond Knowledge) — not started

## Compliance

- [x] Framework/Requirement catalog (global, seeded: GDPR, EU AI Act, ISO 27001)
- [x] Control, ControlMapping, ControlAssessment models + migration
- [x] Evidence (reuses Phase 1 File primitive), Risk, Policy models
- [x] Cross-module hook: a `fail` assessment auto-creates a `core.Task` (tested)
- [x] `/api/v1/compliance` router — frameworks, controls, assessments, evidence, risks, policies; tenant-isolated, RBAC-gated
- [x] RBAC: `compliance_manager` / `dpo` system roles granted compliance permissions
- [x] Frontend: `/compliance` overview + `/compliance/controls/[id]` detail
- [x] Seed script: 2 controls, 2 assessments (one pass, one fail), 1 risk, 1 evidence link for the demo org
- [ ] Framework/evidence versioning — not modeled
- [ ] Audits (auditor portal), regulatory intelligence feed — not started
- [ ] AI Governance (ai_systems/ai_assessments/ai_incidents) — not started
- [ ] Privacy workflows (RoPA, DPIA, DSAR, retention, transfers) — not started
- [ ] Vendor risk, questionnaires, Trust Center — not started

## Security

- [x] SecurityAsset, SecurityFinding (consolidated category discriminator — ADR-0017), SecurityAlert, SecurityIncident models + migration
- [x] Cross-module hook: a `critical` incident auto-creates a linked Compliance `Risk` (tested, ADR-0018)
- [x] Cross-module hook (Phase 8 extension): the same `critical` incident also creates a response `core.Task` and notifies its owner via `core.Notification`, completing spec §69's "Security Incident" chain (tested, ADR-0023)
- [x] `/api/v1/security` router — assets, findings, alerts, incidents; tenant-isolated, RBAC-gated
- [x] RBAC: `security_manager` system role granted security permissions
- [x] Frontend: `/security` dashboard + `/security/incidents/[id]` detail with status workflow, linked risk banner, linked response task banner
- [x] Seed script: 2 assets, 2 findings, 1 alert, 1 critical incident (linked risk) for the demo org
- [ ] Identity provider integrations (Okta/Entra/Google Workspace) — not started
- [ ] Cloud provider connectors (AWS/Azure/GCP) — not started
- [ ] Incident timeline/evidence/playbooks sub-objects — not started
- [ ] Vulnerability scanner ingestion — not started

## Sales

- [x] Account, Contact, Lead, Opportunity, OutreachMessage models + migration
- [x] Cross-module hook: `Contact.do_not_contact` blocks outreach send, else it "sends" (tested, ADR-0019)
- [x] Cross-module hook (Phase 8): the first `closed_won` transition on an Opportunity creates a real Support `Customer` + a 7-day onboarding `Task`, idempotent on reopen/re-win, honestly skipped if the account has no Contact (tested, ADR-0025)
- [x] `/api/v1/sales` router — accounts (+ detail), contacts (+ suppression toggle), leads, opportunities (create/update, now with the closed_won hook), outreach (create + send); tenant-isolated, RBAC-gated
- [x] RBAC: `sales_manager` / `sales_representative` system roles granted sales permissions
- [x] Frontend: `/sales` overview (accounts, pipeline) + `/sales/accounts/[id]` detail (contacts with suppression toggle, compose/send outreach, opportunities with an "Onboarded as a Support customer" link once closed_won)
- [x] Seed script: 1 account, 2 contacts (1 suppressed), 1 opportunity, 2 outreach attempts (1 sent, 1 blocked) for the demo org
- [ ] Sequences/campaigns (multi-step outreach automation) — not started
- [ ] Meetings, sales conversations/inbox, pipeline events, playbooks — not started
- [ ] Real lead-finding, enrichment, email/LinkedIn sending — depend on external connectors (Phase 9)

## Support

- [x] Customer, Ticket, TicketMessage, KnowledgeArticle, CSATResponse models + migration
- [x] Cross-module hook: a `security`-category ticket auto-creates a linked `SecurityAlert` and escalates the ticket to `urgent` priority (tested, ADR-0020)
- [x] `/api/v1/support` router — customers, tickets (+ detail with message thread, status transitions), knowledge articles, CSAT; tenant-isolated, RBAC-gated
- [x] RBAC: `support_manager` / `support_agent` system roles granted support permissions
- [x] Frontend: `/support` overview (customers, ticket creation/list) + `/support/tickets/[id]` detail (status workflow, linked security alert banner, linked sales lead banner, message thread)
- [x] Cross-module hook: flagging a ticket as an upsell signal auto-creates a `sales.Lead` and notifies the linked account's owner (tested, ADR-0022, Phase 8's first slice)
- [x] Seed script: 1 customer (linked to the Nordwind Robotics sales account), 1 resolved billing ticket with CSAT, 1 security-flagged ticket (auto-created SecurityAlert), 1 upsell-flagged ticket (auto-created a Lead + notification), 1 published knowledge article
- [ ] SLA policies/timers, QA review scoring — not started
- [ ] Multi-channel ingestion (email/chat connectors), AI-drafted replies, confidence-gated auto-resolution — not started, needs Phase 9 connectors and Copilot integration
- [ ] Knowledge-gap detection, FAQ generation — not started

## Automation

- [x] Workflow, WorkflowRun, WorkflowStepRun models + migration
- [x] Cross-module hook: a `human_approval` step creates a real `core.Approval` and pauses the run until it's decided via the existing `/api/v1/approvals/{id}/decide` endpoint (tested, ADR-0021)
- [x] `/api/v1/automation` router — workflows (create, steps/status transitions), runs (trigger, detail with step log, resume); tenant-isolated, RBAC-gated
- [x] RBAC: `automation_manager` system role granted automation permissions
- [x] Frontend: `/automation` overview (workflow list + step-by-step create form) + `/automation/workflows/[id]` detail (status governance, run now, run history with expandable step log)
- [x] Seed script: 2 active workflows (1 run awaiting approval, 1 run succeeded), 1 draft workflow for the demo org
- [x] Workflow governance: steps can only be edited while `status = draft`; publishing to `active` locks them (spec §41)
- [x] `trigger_type` now supports `webhook` in addition to `manual` (Phase 9) — see Integrations section below
- [ ] Only 3 of the spec's much larger step vocabulary implemented (create_task, send_notification, human_approval) — Condition/Delay/Loop/Data Transform/Webhook/Subworkflow/AI Step not started
- [ ] Non-webhook non-manual triggers (email, CRM-event, schedule) — not started, need further Phase 9 connectors
- [ ] Visual drag-and-drop builder, templates, automation analytics — not started

## Cross-Module Intelligence

- [x] Slice 1: "Support Upsell Signal" (spec §69) — flagging a support
      ticket creates a real `sales.Lead` and a `core.Notification` to the
      linked account's owner, reusing existing primitives rather than a
      new signal entity (tested, ADR-0022)
- [x] Slice 2: "Security Incident" chain (spec §69) — a `critical`
      incident (already linking a Compliance Risk since Phase 4) now also
      creates a response `core.Task` and notifies the incident's owner,
      extending the existing hook rather than adding a new one (tested,
      ADR-0023)
- [x] Slice 3: "New Customer" (spec §69) — the first `closed_won`
      transition on a Sales Opportunity creates a real Support `Customer`
      and a 7-day onboarding `core.Task`, idempotent on reopen/re-win, and
      honestly skipped (not faked) if the account has no Contact yet
      (tested, ADR-0025)
- [ ] Remaining spec §69 scenarios (Enterprise Sales Security Review, New
      AI Tool Adoption) — not started, need modules/data that don't exist
      yet (customer questionnaires, AI system inventory)
- [ ] AI daily briefing, business process discovery, AI recommendation
      engine, organization memory — not started
- [ ] Cross-module intent router for the AI Copilot — not started

## Integrations

- [x] IntegrationConnection, WebhookEvent models + migration — webhook connector (ADR-0024)
- [x] Cross-module hook: a verified webhook event on a connection linked to an `active`, `trigger_type="webhook"` Automation workflow triggers that workflow via the existing `start_run` (tested, ADR-0024)
- [x] Provider-neutral OAuth2 connector framework — `OAuthConnectorAdapter` Protocol mirroring the AI gateway's `ModelAdapter`/`DemoAdapter` pattern; `HubSpotAdapter` (real HTTP calls to HubSpot's OAuth/CRM endpoints) selected only when `HUBSPOT_CLIENT_ID`/`HUBSPOT_CLIENT_SECRET` are configured, otherwise `MockOAuthAdapter` (tested, ADR-0026)
- [x] Encrypted token storage: `app/core/crypto.py` (Fernet), `TOKEN_ENCRYPTION_KEY` with a dev-only fallback derived from `SECRET_KEY`
- [x] OAuth authorize (`POST /connections/oauth/{provider}/start`) + callback (`GET /connections/oauth/{provider}/callback`, no session — `oauth_state` is the CSRF/capability token) + refresh + health-check + disconnect/revoke + "sync now" (logs a `SyncRun` row) endpoints
- [x] Provider catalog endpoint (`GET /api/v1/integrations/providers`) reports `configured: bool` per provider — HubSpot honestly shows "Not configured" without real credentials, never a fake connected state
- [x] `/api/v1/integrations` router — connections (create/list/patch), events (list), OAuth lifecycle; tenant-isolated, RBAC-gated, **plus** two deliberately unauthenticated routes (webhook receiver, OAuth callback) whose security boundaries are HMAC verification and single-use state tokens respectively, not sessions
- [x] RBAC: `integrations.connections.manage` permission granted to `org_admin` and `automation_manager`
- [x] Frontend: `/settings/integrations` — provider catalog (Connect/Not-configured), OAuth connection cards (health/scopes/sync history, refresh/disconnect/sync-now buttons), webhook connections (copy URL + secret, link/unlink workflow, received events)
- [x] Seed script: 1 webhook-triggered workflow, 1 connection linked to it, 1 verified event that triggered a real run, 1 rejected event (bad signature) — deliberately no seeded HubSpot connection, so the demo org shows the honest "Not configured" state rather than a fabricated connected one
- [ ] Every other spec §48 connector category (CRM beyond HubSpot, Email, Marketing, Customer Support, Cloud, Identity, Engineering, Communication, Documents, Accounting) — not started, all need real OAuth apps/API keys
- [ ] `subscribe()`, `execute_action()`, `collect_evidence()` from spec §49's full Connector Contract — this slice only needed authorize/token-exchange/refresh/health/sync/revoke
- [ ] Sync safety (spec §G2: incremental cursors, checkpointing, replay safety, rate-limit handling) — `run_sync` executes synchronously inline, not as a durable Temporal job
- [ ] API keys for outbound platform access — not started

## Enterprise

- [ ] Not started (Phase 10)

## Testing

- [x] Tenant isolation tests (3 tests, passing)
- [x] RBAC denial tests (2 tests, passing)
- [x] Auth flow tests (8 tests, passing)
- [x] Knowledge module tests (7 tests: chunking, ingestion, unsupported format, tenant isolation)
- [x] Copilot tests (7 tests: cosine similarity, prompt injection framing, insufficient-evidence, retrieval + citations, tenant isolation)
- [x] Compliance tests (9 tests: catalog, RBAC grant/denial, cross-module task creation, tenant isolation, risk lifecycle)
- [x] Security tests (10 tests: RBAC grant/denial, cross-module risk creation, cross-module task creation + owner notification, tenant isolation, status workflows)
- [x] Sales tests (11 tests: RBAC grant/denial, suppression blocks send, resend conflict, tenant isolation, opportunity lifecycle, closed_won creates customer+task, idempotent reopen/re-win, no-contact skip)
- [x] Support tests (10 tests: RBAC grant/denial, cross-module alert creation, ticket message thread, status transitions, tenant isolation, CSAT, knowledge article publish toggle)
- [x] Automation tests (9 tests: RBAC grant/denial, draft/active step-edit gate, run-only-if-active gate, full run execution, human_approval pause + resume + decision, rejected-approval failure, tenant isolation)
- [x] Cross-module intelligence tests (3 upsell-signal + 2 security-incident-chain tests, counted in their own modules' rows above, plus the 3 New Customer tests counted in Sales above)
- [x] Integrations tests (14 tests: webhook RBAC/link/signature-verify/tenant-isolation from Phase 9 slice 1, plus OAuth provider-catalog honesty, RBAC denial, full start→callback→connected round trip against the mock adapter, expired/unknown-state rejection, refresh/health/sync/disconnect lifecycle, tenant isolation)
- [x] 92/92 total, ruff+mypy strict clean
- [ ] Playwright E2E
- [ ] AI evaluation fixtures (Phase 3+)

## Infrastructure (AWS)

- [ ] Terraform bootstrap
- [ ] Network/security baseline
- [ ] Data services (RDS/ElastiCache/S3)
- [ ] Compute/edge (ECS/ALB/CloudFront/WAF)
- [ ] Observability
- [ ] CI workflows
- [ ] CD workflows
- [ ] Recovery validation

Only a local Docker Compose environment exists as of this writing. AWS
deployment has not been started — see `docs/RESUME_BUILD.md` for the exact
next steps and `docs/IMPLEMENTATION_PLAN.md` for phase ordering.

**Do not read this file as "the product is done."** It tracks a very large,
explicitly multi-phase build. As of this writing, Phase 1 (platform
foundation) and Phase 2 (Knowledge & AI Infrastructure) are complete;
Phases 3–7 (Compliance, Security, Sales, Support, Automation) have their
core backbones (see their sections above) but not their larger
sub-features (audits, AI governance, privacy workflows, vendor risk, Trust
Center, identity/cloud provider integrations, incident playbooks,
sequences/campaigns, SLA/QA scoring, the full workflow step vocabulary and
most non-manual triggers). Phase 8 (Cross-Module Intelligence) has three
real scenarios implemented (Support Upsell Signal, Security Incident
chain, New Customer) out of spec §69's five named scenarios plus its
open-ended AI features (daily briefing, recommendation engine,
organization memory) — none of that larger scope has started. Phase 9
(Integrations) has two connector shapes implemented — a generic inbound
Webhook receiver and a provider-neutral OAuth2 framework with HubSpot as
the first real provider — out of spec §48's dozen-plus categories; every
other category needs real third-party OAuth credentials this environment
doesn't have and won't fabricate (HubSpot itself reports honestly as
"Not configured" until real credentials are supplied). The cross-module
intent router, Phase 10, and the AWS production deployment have not
started.
