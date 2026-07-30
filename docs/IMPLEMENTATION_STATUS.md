# Implementation Status

Legend: `[x]` Complete · `[~]` In Progress · `[ ]` Not Started · `[!]` Blocked

Last updated: 2026-07-30 (Phase 1 + Phase 2 complete; Phase 3 Compliance, Phase 4 Security, Phase 5 Sales, Phase 6 Customer Support, and Phase 7 Business Automation backbones; Phase 8's three Cross-Module Intelligence slices plus AI Governance (AI System Inventory + AI Incidents), Privacy (RoPA/DPIA/DSAR), and Vendor Risk Compliance extensions that together give a fourth Phase 8 scenario two of its steps; Phase 9's Webhook connector and provider-neutral OAuth2 framework completed with six real (credential-gated) adapters — HubSpot, Google, Microsoft, GitHub, Slack, Salesforce — Temporal-backed sync, and a frontend permission preview — verified end-to-end; Compliance/Trust program in progress: Vendor Risk done, Security Questionnaires done, Audits done, Trust Center/Enterprise Sales Security Review/Data Transfers next)

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
- [x] AI System Inventory: `AISystem`/`AIAssessment` models + migration — EU AI Act risk tiers (minimal/limited/high/unacceptable)
- [x] Cross-module hook: registering a `high`/`unacceptable`-risk AI system auto-creates a real `core.Approval`; the system cannot be marked `approved` until that Approval is granted (tested, ADR-0027)
- [x] `/api/v1/compliance/ai-systems` router — create/list/detail (with assessments), status transitions (422 if approval pending), assessment recording; tenant-isolated
- [x] RBAC: `ai_governance_manager` system role (dormant since Phase 1, first activated here) and `dpo` granted `compliance.ai_systems.manage`
- [x] Frontend: AI System Inventory section on `/compliance` (register form, list) + `/compliance/ai-systems/[id]` detail (status dropdown, linked-Approval banner, assessment list/form)
- [x] Seed script: 1 high-risk system (pending Approval), 1 minimal-risk system (approved, 1 passing assessment)
- [x] Privacy: `ProcessingActivity`/`DPIA`/`DSAR` models + migration — RoPA (GDPR Art. 30), DPIA (Art. 35), DSAR (Art. 15-20)
- [x] Cross-module hook: registering a `high`/`unacceptable`-risk AI system also creates a linked draft `DPIA` (the "New AI Tool Adoption" chain's Privacy-assessment step) sharing the AI system's own Approval rather than duplicating it (tested, ADR-0029)
- [x] Cross-module hook: a `DPIA` created directly with `risk_level="high"` gets its own real `core.Approval`, gated exactly like `AISystem` (tested, ADR-0029)
- [x] DSAR lifecycle: `due_at` set to 30 days from creation (GDPR Art. 12(3)), received→in_progress→fulfilled/rejected, `fulfilled_at` set on completion
- [x] `/api/v1/compliance/{processing-activities,dpias,dsars}` routes — create/list/detail/status; tenant-isolated, RBAC-gated
- [x] RBAC: new `compliance.privacy.manage` permission granted to `dpo` (extending its existing grant) and `legal` (dormant since Phase 1, first activated here)
- [x] Frontend: RoPA/DPIA/DSAR sections on `/compliance` (create forms, lists) + `/compliance/dpias/[id]` detail (status dropdown, linked-Approval banner, findings) + `/compliance/dsars/[id]` detail (status dropdown, due date, notes)
- [x] Seed script: 1 processing activity, 1 medium-risk standalone DPIA linked to it, 1 fulfilled DSAR, 1 open DSAR
- [x] AI Incidents: `AIIncident` model + migration — always tied to a specific `AISystem` (EU AI Act Art. 73 "serious incident")
- [x] Cross-module hook: a `critical`-severity AI incident reuses `SecurityIncident`'s exact chain — a linked Compliance `Risk`, a response `core.Task`, and an owner `core.Notification` if set (tested, ADR-0030)
- [x] `/api/v1/compliance/ai-incidents` routes — create/list/detail/status; tenant-isolated, RBAC-gated via the existing `compliance.ai_systems.manage` permission (no new permission minted)
- [x] Frontend: AI Incidents section on `/compliance` (log form with an AI-system picker, list) + `/compliance/ai-incidents/[id]` detail (status workflow, linked-Risk banner, linked-Task banner)
- [x] Seed script: 1 critical AI incident against the demo org's high-risk AI system (linked Risk + response Task)
- [x] Vendor Risk: `Vendor`/`VendorAssessment` models + migration; `Evidence.vendor_id` added as a second optional target alongside `control_id`
- [x] Cross-module hook: a `high`/`critical` vendor assessment auto-creates a linked Compliance `Risk` (`category="vendor"`) and updates the vendor's own `risk_tier` (tested, ADR-0031)
- [x] `/api/v1/compliance/vendors` routes — create/list/detail (with assessments + evidence)/status/assessments; tenant-isolated, RBAC-gated via `compliance.vendors.manage` (added to the existing `COMPLIANCE_PERMISSIONS` bundle — `compliance_manager`/`dpo` get it automatically)
- [x] Frontend: Vendors section on `/compliance` (create form, list) + `/compliance/vendors/[id]` detail (status dropdown, assessment form, assessment history, evidence list)
- [x] Seed script: 1 low-risk vendor, 1 vendor with a critical assessment + linked risk
- [x] Security Questionnaires: `Questionnaire`/`QuestionnaireQuestion`/`QuestionnaireAnswer` models + migration; every question gets an atomically-created `status="missing"` answer row; `Questionnaire.opportunity_id` is a forward-looking nullable FK to `sales_opportunities` for the Sales Security Review slice
- [x] Answer drafting: `suggest_questionnaire_answer` tries an org-wide exact-text match against previously-approved answers first (`source_type="reused_from_library"`), then falls back to a live `app.ai.copilot.ask_copilot` call (`source_type="ai_suggested"`, citations stored) — always lands as `status="draft"`, never auto-approved (tested, ADR-0032)
- [x] `/api/v1/compliance/questionnaires` routes — create/list/detail (questions + answers)/status/add-question/suggest-answer/update-answer; tenant-isolated, RBAC-gated via `compliance.questionnaires.manage` (added to the existing `COMPLIANCE_PERMISSIONS` bundle)
- [x] Frontend: Questionnaires section on `/compliance` (create form, list) + `/compliance/questionnaires/[id]` detail (status dropdown, missing-answer count banner, add-question form, per-question suggest/save-draft/approve actions)
- [x] Seed script: 1 questionnaire with 1 approved answer + 1 missing answer
- [x] Audits: `Audit`/`AuditFinding` models + migration; an `Audit` groups many findings under one auditor engagement (optionally against a catalog `Framework`), unlike the single-judgement `ControlAssessment`/`VendorAssessment`/`AIAssessment` shape
- [x] Cross-module hook: a `high`/`critical` finding auto-creates a remediation `core.Task`, reusing `record_assessment`'s hook shape for a fifth entity type — specifically its Task-creating half (tested, ADR-0033)
- [x] `/api/v1/compliance/audits` routes — create/list/detail (with findings)/status/findings/finding-status; tenant-isolated, RBAC-gated via `compliance.audits.manage` (added to the existing `COMPLIANCE_PERMISSIONS` bundle, and granted to the pre-seeded but previously-unused `auditor` system role)
- [x] Frontend: Audits section on `/compliance` (create form, list) + `/compliance/audits/[id]` detail (status dropdown, add-finding form, findings list with severity/status badges, mark-remediated action)
- [x] Seed script: 1 in-progress audit with 1 critical finding + linked remediation task, 1 remediated low-severity finding
- [ ] Framework/evidence versioning — not modeled
- [ ] Regulatory intelligence feed — not started
- [ ] Data transfers (the remaining Privacy sub-feature) — not started
- [ ] Trust Center — not started

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
- [x] "New AI Tool Adoption" (spec §69) partial: registering a
      high/unacceptable-risk AI system creates a real `core.Approval` and
      gates the `approved` status transition on it (tested, ADR-0027,
      counted in Compliance above) — the rest of the chain (vendor
      security questionnaire, Privacy/DPA review, approved-use policy
      publication) is not implemented
- [ ] Remaining spec §69 scenario ("Enterprise Sales Security Review") —
      not started, needs customer questionnaires, which don't exist yet
- [ ] AI daily briefing, business process discovery, AI recommendation
      engine, organization memory — not started
- [ ] Cross-module intent router for the AI Copilot — not started

## Integrations

- [x] IntegrationConnection, WebhookEvent, SyncRun models + migration — webhook connector (ADR-0024)
- [x] Cross-module hook: a verified webhook event on a connection linked to an `active`, `trigger_type="webhook"` Automation workflow triggers that workflow via the existing `start_run` (tested, ADR-0024)
- [x] Provider-neutral OAuth2 connector framework — `OAuthConnectorAdapter` Protocol mirroring the AI gateway's `ModelAdapter`/`DemoAdapter` pattern; six real adapters (HubSpot, Google, Microsoft, GitHub, Slack, Salesforce — each real HTTP calls against that provider's documented OAuth/API endpoints), each selected only when its own `*_CLIENT_ID`/`*_CLIENT_SECRET` are configured, otherwise `MockOAuthAdapter` labeled with the real provider key (tested, ADR-0026, ADR-0028)
- [x] Adding a seventh provider is one adapter module + one registry entry + three env vars — no change to the OAuth flow, router, service layer, or frontend (`app/integrations/adapters/__init__.py::_provider_specs`)
- [x] Permission preview: provider catalog exposes each provider's requested `scopes`; frontend shows them before the user clicks "Authorize", not just after connecting
- [x] Encrypted token storage: `app/core/crypto.py` (Fernet), `TOKEN_ENCRYPTION_KEY` with a dev-only fallback derived from `SECRET_KEY`
- [x] OAuth authorize (`POST /connections/oauth/{provider}/start`) + callback (`GET /connections/oauth/{provider}/callback`, no session — `oauth_state` is the CSRF/capability token) + refresh + health-check + disconnect/revoke + "sync now" endpoints
- [x] Sync runs as a durable Temporal workflow (`IntegrationSyncWorkflow`, `apps/worker`) rather than inline in the request — the endpoint creates the `SyncRun` row and returns immediately, the frontend polls to completion (tested, ADR-0028)
- [x] Audit logging for the full OAuth lifecycle: connect, refresh (success + failure), sync (started/succeeded/failed), disconnect (including whether the provider's own revoke call succeeded) — every failure path normalized to a 422, never an unhandled 500
- [x] Provider catalog endpoint (`GET /api/v1/integrations/providers`) reports `configured: bool` per provider — all six honestly show "Not configured" without real credentials, never a fake connected state
- [x] `/api/v1/integrations` router — connections (create/list/patch), events (list), OAuth lifecycle; tenant-isolated, RBAC-gated, **plus** two deliberately unauthenticated routes (webhook receiver, OAuth callback) whose security boundaries are HMAC verification and single-use state tokens respectively, not sessions
- [x] RBAC: `integrations.connections.manage` permission granted to `org_admin` and `automation_manager`
- [x] Frontend: `/settings/integrations` — provider catalog with a permission-preview step before Connect, OAuth connection cards (health/scopes/sync history with live polling, refresh/disconnect/sync-now buttons), webhook connections (copy URL + secret, link/unlink workflow, received events)
- [x] Frontend test suite (Vitest + React Testing Library) covering the provider catalog, permission preview, and OAuth connection lifecycle UI
- [x] `.env`/`.env.local` support (later overrides earlier); repo-root `.dockerignore` keeps both out of every Docker build context; `docs/ENVIRONMENT_VARIABLES.md` documents the intended (not yet built) AWS Secrets Manager/Parameter Store/ECS production shape
- [x] Seed script: 1 webhook-triggered workflow, 1 connection linked to it, 1 verified event that triggered a real run, 1 rejected event (bad signature) — deliberately no seeded OAuth connection for any provider, so the demo org shows the honest "Not configured" state rather than a fabricated connected one
- [ ] Every other spec §48 connector category (Email, Marketing, Customer Support beyond generic webhook, Cloud, remaining Identity/Engineering/Communication/Documents/Accounting categories) — not started, all need real OAuth apps/API keys
- [ ] `subscribe()`, `execute_action()`, `collect_evidence()` from spec §49's full Connector Contract — this slice only needed authorize/token-exchange/refresh/health/sync/revoke
- [ ] Sync safety (spec §G2: incremental cursors, checkpointing, replay safety, rate-limit handling) — sync is durable now but still on-demand only, no polling/scheduled sync
- [ ] AWS deployment itself (Secrets Manager/Parameter Store/ECS) — documented design, not built; Phase 10/AWS hasn't started
- [ ] API keys for outbound platform access — not started

## Enterprise

- [ ] Not started (Phase 10)

## Testing

- [x] Tenant isolation tests (3 tests, passing)
- [x] RBAC denial tests (2 tests, passing)
- [x] Auth flow tests (8 tests, passing)
- [x] Knowledge module tests (7 tests: chunking, ingestion, unsupported format, tenant isolation)
- [x] Copilot tests (7 tests: cosine similarity, prompt injection framing, insufficient-evidence, retrieval + citations, tenant isolation)
- [x] Compliance tests (60 tests: catalog, RBAC grant/denial, cross-module task creation, tenant isolation, risk lifecycle, 9 AI System Inventory tests, 12 Privacy tests, 8 AI Incident tests, 7 Vendor Risk tests, 7 Security Questionnaire tests — see prior entries for detail — plus 8 Audit tests: RBAC denial for `employee`, the `auditor` role's grant, the critical-finding-creates-remediation-task hook, the negative case for low severity, a finding attaching to a Control, the audit and finding status lifecycles (including `completed_at`), tenant isolation, and rejection of a foreign `framework_id`)
- [x] Security tests (10 tests: RBAC grant/denial, cross-module risk creation, cross-module task creation + owner notification, tenant isolation, status workflows)
- [x] Sales tests (11 tests: RBAC grant/denial, suppression blocks send, resend conflict, tenant isolation, opportunity lifecycle, closed_won creates customer+task, idempotent reopen/re-win, no-contact skip)
- [x] Support tests (10 tests: RBAC grant/denial, cross-module alert creation, ticket message thread, status transitions, tenant isolation, CSAT, knowledge article publish toggle)
- [x] Automation tests (9 tests: RBAC grant/denial, draft/active step-edit gate, run-only-if-active gate, full run execution, human_approval pause + resume + decision, rejected-approval failure, tenant isolation)
- [x] Cross-module intelligence tests (3 upsell-signal + 2 security-incident-chain tests, counted in their own modules' rows above, plus the 3 New Customer tests counted in Sales above)
- [x] Integrations tests (50 tests: webhook RBAC/link/signature-verify/tenant-isolation from Phase 9 slice 1; OAuth provider-catalog honesty across all six providers with scope previews, RBAC denial, full start→callback→connected round trip against the mock adapter (proven generic via a second, non-HubSpot provider), expired/unknown-state/unknown-provider rejection, refresh/health/sync/disconnect lifecycle with the durable-sync split (`create_sync_run`/`execute_sync_run`) exercised directly including its failure path, an audit-trail assertion across the full OAuth lifecycle, tenant isolation; plus pure adapter unit tests for every provider's authorization-URL construction, scope preview, mock-fallback labeling, and the two no-refresh providers' explicit errors — no network, no live credentials needed)
- [x] 179/179 total backend, ruff+mypy strict clean
- [x] Frontend: 16 Vitest + React Testing Library tests — 5 for `/settings/integrations`, 3 for Privacy sections, 2 for AI Incidents, 2 for Vendors (rendering with risk tier/status, adding a new vendor), 2 for Questionnaires (rendering with source/status, creating a new questionnaire), and 2 for Audits (rendering with auditor name/status, creating a new audit)
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
sub-features (audits, data transfers (Privacy's remaining sub-feature),
security questionnaires, Trust Center, identity/cloud provider
integrations, incident playbooks, sequences/campaigns, SLA/QA scoring,
the full workflow step vocabulary and most non-manual triggers). Phase 8
(Cross-Module Intelligence) has three full scenarios implemented (Support
Upsell Signal, Security Incident chain, New Customer) plus a partial
fourth (New AI Tool Adoption, now with both its register→Approval gate
and its Privacy-assessment DPIA step) out of spec §69's five named
scenarios, plus its open-ended AI features (daily briefing, recommendation
engine, organization memory) — none of that larger scope has started. Phase 9
(Integrations) has two connector shapes implemented — a generic inbound
Webhook receiver and a provider-neutral OAuth2 framework with six real
adapters (HubSpot, Google, Microsoft, GitHub, Slack, Salesforce), sync
running as a durable Temporal job — out of spec §48's dozen-plus
categories; every configured provider needs real third-party OAuth
credentials this environment doesn't have and won't fabricate (every one
reports honestly as "Not configured" until real credentials are
supplied, with a permission preview of the scopes it would request). The
cross-module intent router, Phase 10, and the AWS production deployment
have not started — the AWS Secrets Manager/Parameter Store/ECS design in
`docs/ENVIRONMENT_VARIABLES.md` is a documented commitment for that future
work, not yet built or tested.
