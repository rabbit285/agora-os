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
  [Update 2026-08-05: substantially extended by the
  `ui/public-site-and-auth-modernization` branch — real public
  marketing site at `/`, email verification, invitation
  accept/decline with a preview endpoint, redirect-back-after-login,
  and a full auth UX rebuild. See `docs/RELEASE_CHECKLIST.md`'s
  "Public site & auth modernization" section for the complete list.
  MFA enforcement remains deferred.]
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

Also done, added alongside Phase 8's cross-module work: the AI System
Inventory (`AISystem`/`AIAssessment`, EU AI Act risk tiers). Registering a
high/unacceptable-risk system auto-creates a real Approval and gates the
`approved` status transition on it (ADR-0027) — this build's third use of
the Approval primitive outside its own UI, and the first real primitive
behind spec §69's "New AI Tool Adoption" cross-module scenario.

Also done: Privacy's RoPA/DPIA/DSAR (`ProcessingActivity`/`DPIA`/`DSAR` —
spec §2/§12 frame these as Compliance sub-features, not a separate
module). A directly-created high-risk `DPIA` gets its own Approval gate,
this build's fourth reuse of that primitive; `register_ai_system` is
extended a second time so a high/unacceptable-risk registration also
creates a linked draft DPIA — "New AI Tool Adoption"'s Privacy-assessment
step (ADR-0029). DSAR gets a real 30-day due date (GDPR Article 12(3))
and a received→in_progress→fulfilled/rejected lifecycle.

Also done: AI Incidents (`AIIncident`, spec §50's "AI GOVERNANCE"
`ai_incidents` table). A `critical`-severity incident reuses
`SecurityIncident`'s exact critical-severity chain (linked Risk +
response Task + owner Notification) for a third time (ADR-0018,
ADR-0023, ADR-0030) rather than inventing a fourth mechanism.

Also done: Vendor Risk (`Vendor`/`VendorAssessment`, spec §12/§67
"Vendors"). A `high`/`critical` assessment conclusion reuses
`record_assessment`'s hook shape for a fourth entity type, auto-creating
a linked Risk (ADR-0031). `Evidence` gained a second optional target
(`vendor_id`) alongside `control_id`.

Also done: Security Questionnaires (`Questionnaire`/
`QuestionnaireQuestion`/`QuestionnaireAnswer`, spec §12/§67 "Security
Questionnaires"). Answers are drafted via an org-wide exact-text match
against previously-approved answers, then a live AI Copilot call as
fallback — always landing as `status="draft"`, never auto-approved
(ADR-0032). `Questionnaire.opportunity_id` is a forward-looking nullable
FK to Sales Opportunity for the not-yet-built Enterprise Sales Security
Review slice.

Also done: Audits (`Audit`/`AuditFinding`, spec §12/§67 "Audits"). An
`Audit` groups many findings under one auditor engagement, a different
shape from the single-judgement `ControlAssessment`/`VendorAssessment`/
`AIAssessment` pattern. A `high`/`critical` finding reuses
`record_assessment`'s Task-creating hook shape for a fifth entity type
(ADR-0033); the pre-seeded but previously-unused `auditor` system role
got its first real permission.

Also done: Trust Center (spec B4), in a new `app.trust_center` module
rather than `app.compliance` — its `GET /api/v1/trust-center/public/
{org_slug}` route is genuinely unauthenticated (no session dependency
at all), the same pattern already used by the Phase 9 webhook receiver
and OAuth callback (ADR-0024), a fundamentally different security model
from every other tenant-scoped Compliance sub-feature (ADR-0034).
`TrustCenterItem.policy_id` reuses the existing `Policy` for
"downloadable approved documents" rather than a new document table; a
public `EvidenceRequest` submission always creates a linked Task.

Also done: Enterprise Sales Security Review (`SecurityReview`, spec
§69's full 10-step flow), the payoff for `Questionnaire.opportunity_id`
having existed since ADR-0032 with no caller. Starting a review creates
or imports a Questionnaire against a Sales Opportunity, moves it to a
new `security_review` stage, and — for an opportunity at or above a
documented materiality threshold — opens a real Approval gating the
clear. Syncing reuses the Questionnaires slice's own answer-library + AI
Copilot logic, attaches Evidence for any Control-referencing answer with
none yet, and opens a remediation Task per gap. Clearing is refused
while gaps or the Approval remain, and generates a real trust-package
File (ADR-0035) — this is the scenario every other slice in this
sequence was quietly built to support.

Also done: Data Transfers (`DataTransfer`, GDPR Chapter V), the fourth
and last of Privacy's sub-features alongside RoPA/DPIA/DSAR, extending
`app.compliance` directly rather than becoming its own module and
reusing the existing `compliance.privacy.manage` permission. A
`transfer_mechanism="derogation"` transfer auto-creates a linked Risk —
Article 49 derogations are meant to be exceptional, not routine, making
them the risk-bearing choice among the four transfer mechanisms — the
seventh reuse of `record_assessment`'s hook shape (ADR-0036). This
completes all six Compliance/Trust items requested this session.

Remaining: regulatory intelligence feed (external updates), framework/
evidence versioning. Each is a substantial feature attaching to the
backbone above, not a blocker to it.

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

## Phase 8 — Cross-Module Intelligence (four of five named scenarios done)

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
- "Enterprise Sales Security Review" — the full 10-step flow.
  `app/compliance/service.py::start_security_review` creates/imports a
  Questionnaire against a Sales Opportunity and moves it into a
  `security_review` stage; `sync_security_review` retrieves approved
  answers and Evidence and opens a remediation Task per gap;
  `clear_security_review` is gated on zero gaps plus (above a
  materiality threshold) a real Approval, then generates a trust-package
  File and notifies the opportunity owner (ADR-0035).

Remaining: "New AI Tool Adoption" is still partial (its register→
Approval gate and Privacy-assessment DPIA step exist, ADR-0027/ADR-0029,
but not EU AI Act applicability/DPA review as distinct steps or
approved-use policy publication), plus the phase's more open-ended AI
features — shared knowledge graph queries across modules, AI daily
briefing, business process discovery, AI recommendation engine,
organization memory.

## Phase 9 — Integrations (two connector shapes; OAuth framework complete for six providers)

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
  `ModelAdapter`/`DemoAdapter` pattern) with **six real adapters** —
  HubSpot, Google, Microsoft, GitHub, Slack, Salesforce — genuine HTTP
  calls against each provider's documented OAuth/API endpoints, each only
  activated when its own `*_CLIENT_ID`/`*_CLIENT_SECRET` are configured;
  `MockOAuthAdapter` (labeled per provider) otherwise, which is also what
  the test suite exercises for all six. Encrypted token storage
  (`app/core/crypto.py`), a provider catalog endpoint reporting honest
  `configured: bool` status plus a permission preview of each provider's
  requested scopes, authorize/callback/refresh/health/disconnect/sync
  endpoints, full-lifecycle audit logging, and sync running as a durable
  Temporal job (`IntegrationSyncWorkflow`) rather than inline — all real,
  tenant-isolated, tested (ADR-0026, ADR-0028). Adding a seventh provider
  is one adapter module + one registry entry + three env vars, not a
  structural change.

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
