# Implementation Plan

Phased delivery order per spec §79/§D1, adapted to concrete engineering
milestones. Each phase is only started once the previous phase's tests pass
and the app still boots from a clean database (spec §J Definition of Full
Completion).

## Phase 1 — Platform Foundation (in progress, this build)

- Monorepo, Docker Compose local infra (Postgres+pgvector, Redis, MinIO,
  Temporal)
- Environment/config validation, `.env.example`
- Core domain: organizations, legal entities, users, teams, memberships,
  roles, permissions
- Auth: signup, login, session, password reset (MFA schema present,
  enforcement flow deferred — see `KNOWN_LIMITATIONS.md`)
- Tenant-context middleware, RBAC dependency
- Audit log (append-only) wired into auth + org mutations
- Tasks, Approvals (shared primitives, generic UI)
- Files (upload/download via signed URLs)
- Notifications (in-app only; email/Slack adapters are Phase 2+)
- AI Model Gateway interface + Demo adapter + `AiRun` logging
- Next.js app shell (sidebar, nav, module switcher stub), auth pages,
  dashboard placeholder, settings (org/users)
- Seed script: "Acme AI Technologies" demo org, admin user, sample
  tasks/approvals
- Tests: tenant isolation, RBAC denial, auth flow
- Docs: this family of architecture docs, `RESUME_BUILD.md`,
  `DECISIONS.md`, `KNOWN_LIMITATIONS.md`, `SECURITY_ASSUMPTIONS.md`,
  `RELEASE_CHECKLIST.md`

## Phase 2 — Knowledge & AI Infrastructure (complete)

Done: knowledge bases, document upload/registration, parsing (PDF, DOCX,
CSV, TXT, Markdown — XLSX/PPTX/OCR not yet), chunking, embeddings (stored
as JSON — see `docs/DECISIONS.md` ADR-0007), a durable Temporal ingestion
workflow, tenant-isolated API + frontend, similarity search (cosine, in
Python — ADR-0012), and a retrieval-grounded AI Copilot (retrieve →
ground → generate → cite, with minimal prompt-injection defenses).

Not done, and deliberately deferred rather than blocking Phase 2 exit:
entity/relationship extraction (spec §11 knowledge graph — no module yet
needs it), the cross-module intent router (spec's cross-functional
Copilot examples pulling from Compliance/Security/Sales — none of those
modules exist yet either), and an AI Action Log UI (the data exists on
`AiRun`; no screen surfaces it). Pick these up when a concrete module
needs them rather than building ahead of demand.

## Phase 3 — Compliance (backbone in progress)

Done: the core spec §12 chain — Framework → Requirement → Control →
Evidence/Assessment → Risk — plus Policy, with GDPR/EU AI Act/ISO 27001
seeded as catalog data (ISO 42001/SOC 2/NIS2/DORA/custom frameworks follow
the same pattern, add rows when a concrete need arises rather than ahead
of it). A failed assessment auto-creates a remediation `Task` — the
cross-module hook required by spec §80.

Remaining: AI governance (AI system inventory, DPIA), privacy (RoPA, DSAR,
retention, transfers), vendor risk, questionnaires, audits (auditor
portal), Trust Center, regulatory intelligence feed. Each is a
substantial feature attaching to the backbone above, not a blocker to it
— see `docs/RESUME_BUILD.md` for suggested next-slice ordering.

## Phase 4 — Security (backbone in progress)

Done: asset inventory, findings (consolidating vulnerabilities/cloud
misconfigurations/identity findings — ADR-0017), alerts inbox, incident
workspace with a status workflow (detected→...→closed). The integration
with Compliance's GDPR-breach process (spec §19) is implemented as the
Phase 4 cross-module hook: a critical incident auto-creates a linked
Compliance Risk (ADR-0018).

Remaining: cloud security connectors (AWS/Azure/GCP — read-only, per the
progressive trust model in spec §B1), identity security connectors
(Okta/Entra/Google Workspace), vulnerability scanner ingestion, incident
timeline/evidence/playbooks as first-class sub-objects. Each requires the
Integrations/connector SDK (Phase 9) to do properly rather than one-off
per-provider code — see `docs/RESUME_BUILD.md`.

## Phase 5 — Sales (backbone in progress)

Done: accounts, contacts, leads, opportunities/pipeline, and
compliance-gated outreach sending (a suppressed contact cannot be sent
to — spec §91, ADR-0019). This is the "compliance-gated sending" item
from the original scope, implemented at the simplest real level (a
suppression flag) rather than the full jurisdiction/consent engine.

Remaining: ICP builder, lead finder, enrichment, outreach sequences
(multi-step automation), campaigns, sales inbox, meeting assistant,
richer pipeline intelligence, CRM connectors. Real lead-finding and
enrichment need external data sources; real sending needs an email/
LinkedIn provider — both are progressive-trust-model connector work
(Phase 9), not blockers to the backbone above.

## Phase 6 — Customer Support (backbone in progress)

Done: Customer, Ticket, TicketMessage, KnowledgeArticle, CSATResponse.
`Ticket.category` consolidates the spec's `support_intents` concept, and a
ticket *is* a conversation here (no separate `support_conversations`
table), same simplification as Security's finding categories (ADR-0017).
A ticket categorized `security` auto-creates a linked `SecurityAlert` and
escalates the ticket to `urgent` priority — the Phase 6 cross-module hook
(spec §35, ADR-0020). `Customer.sales_account_id` optionally links back to
a converted Sales Account (spec §69 "New Customer").

Remaining: SLA policies/timers, QA review scoring, multi-channel ingestion
(email/chat/API are channel tags today, not real connectors), AI-drafted
replies and confidence-gated auto-resolution (spec §32 — the Copilot/
retrieval infrastructure from Phase 2 could support this but nothing wires
Support into it yet), knowledge-gap detection, FAQ generation, support
analytics. Real multi-channel support needs the connector SDK (Phase 9);
AI-drafted replies need Support wired into the existing Copilot retrieval
path — see `docs/RESUME_BUILD.md`.

## Phase 7 — Business Automation (backbone in progress)

Done: Workflow (JSON-defined ordered steps, not a visual builder yet),
WorkflowRun, WorkflowStepRun. Governance states (draft/testing/active/
paused/archived, spec §41) are modeled; steps can only be edited while
draft, so publishing to active can never silently change behavior. Only
the `manual` trigger and three step types execute for real —
`create_task`, `send_notification`, `human_approval` — deliberately a
small fixed vocabulary rather than a stub of spec §37's much larger list
(Condition/Delay/Loop/Data Transform/Webhook/Subworkflow/AI Step). A
`human_approval` step creates a real Phase 1 `core.Approval` and pauses
the run until it's decided through the existing approvals endpoint — the
Phase 7 cross-module hook (spec §42, ADR-0021), and the first domain
module to actually exercise that primitive outside its own generic UI.

Remaining: the rest of the step vocabulary, non-manual triggers (new
email, webhook, CRM stage change, schedule — spec §38, need Phase 9
connectors), a real visual drag-and-drop builder (React Flow), workflow
templates, run history filtering/search, automation analytics (spec §43).

## Phase 8 — Cross-Module Intelligence (three slices in progress)

Spec §69 names five cross-module scenarios. Rather than stub all five,
this phase ships them as real, tested verticals one at a time — the same
discipline as every prior phase. Done:

- "Support Upsell Signal" — flagging a support ticket
  (`app/support/service.py::flag_upsell_signal`) creates a real
  `sales.Lead` and a `core.Notification` to the linked account's owner,
  reusing three primitives that already existed (Ticket, Lead,
  Notification) rather than inventing a new signal entity (ADR-0022).
- "Security Incident" chain — extends the existing Phase 4
  Incident→Risk hook (`app/secops/service.py::create_incident`) so the
  same `critical`-severity incident also creates a response `core.Task`
  and notifies the incident's owner via `core.Notification`, completing
  the chain spec §69 describes without adding a second hook (ADR-0023).
- "New Customer" — the first `closed_won` transition on a Sales
  Opportunity (`app/sales/service.py::close_opportunity_won`) creates a
  real Support `Customer` and a 7-day onboarding `core.Task`, collapsing
  spec §69's nine-step chain into two existing primitives; idempotent on
  reopen/re-win, and honestly skipped (not faked) if the account has no
  Contact yet to source an email from (ADR-0025).

Remaining: the other two named scenarios (Enterprise Sales Security
Review, New AI Tool Adoption), plus the phase's more open-ended AI
features — shared knowledge graph queries across modules, AI daily
briefing, business process discovery, AI recommendation engine,
organization memory. Both remaining named scenarios need modules or data
that don't exist yet (customer questionnaires, an AI system inventory) —
see `docs/RESUME_BUILD.md` for suggested ordering.

## Phase 9 — Integrations (two connector shapes in progress)

Spec §48 lists a dozen-plus provider categories (CRM, Email, Marketing,
Customer Support, Cloud, Identity, Engineering, Communication, Documents,
Accounting). Every one of them needs a real third-party OAuth app or API
key this environment doesn't have and shouldn't fabricate (spec §82 "No
Fake Features", §C2 secrets contract). Done:

- A generic inbound **Webhook** connector — the one category buildable
  with zero external credentials. `IntegrationConnection` (HMAC-SHA256
  secret per connection) and `WebhookEvent` (an audit trail of every
  inbound call, verified or not) are real, tenant-isolated, tested. A
  verified event on a connection linked to an `active` Automation
  workflow with `trigger_type="webhook"` triggers that workflow through
  the existing execution engine (`app.automation.service.start_run`) —
  Automation's first non-manual trigger, and the Security Release
  Baseline's "webhook signature verification" requirement (spec §H),
  both satisfied by the same slice (ADR-0024).
- A provider-neutral **OAuth2 connector framework**
  (`OAuthConnectorAdapter`, mirroring the AI gateway's
  `ModelAdapter`/`DemoAdapter` pattern) with **HubSpot** as the first real
  provider — genuine HTTP calls to HubSpot's OAuth/CRM endpoints, only
  activated when `HUBSPOT_CLIENT_ID`/`HUBSPOT_CLIENT_SECRET` are
  configured; `MockOAuthAdapter` otherwise, which is also what the test
  suite exercises. Encrypted token storage (`app/core/crypto.py`), a
  provider catalog endpoint reporting honest `configured: bool` status,
  authorize/callback/refresh/health/disconnect/sync endpoints, and a
  `SyncRun` log — all real, tenant-isolated, tested (ADR-0026).

Remaining: every other connector category, the rest of spec §49's
Connector Contract (`subscribe()`, `execute_action()`,
`collect_evidence()`), sync safety (spec §G2: incremental cursors,
checkpointing, replay safety), API keys for outbound access. Each real
connector needs its own OAuth app registration and a concrete consuming
feature to justify building it — not attempted speculatively, per the
same "don't build ahead of demand" principle used since Phase 2.

## Phase 10 — Enterprise

SSO/SAML, SCIM, regional hosting configuration, enterprise RBAC extensions,
public API + webhooks, advanced audit export, multi-entity/agency mode.

## AWS Production Deployment (spec §L/§M/§N)

Runs in parallel once Phase 1 is stable enough to containerize
meaningfully: Terraform bootstrap → network/security baseline → data
services → compute/edge → observability → CI → CD → recovery validation.
Tracked separately in `IMPLEMENTATION_STATUS.md` under "Infrastructure" —
not started as of this writing; a local Docker Compose environment is the
Phase 1 deliverable.
