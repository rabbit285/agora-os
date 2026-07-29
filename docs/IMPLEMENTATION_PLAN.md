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

## Phase 5 — Sales

ICP builder, lead finder, enrichment, accounts/contacts, outreach
sequences with compliance-gated sending, campaigns, sales inbox, meeting
assistant, pipeline intelligence, CRM connectors.

## Phase 6 — Customer Support

Support inbox (email/chat/API channels), AI support agent with
confidence-gated auto-reply, knowledge base, SLA monitoring, QA scoring,
support automations.

## Phase 7 — Business Automation

Visual workflow builder (React Flow), triggers, actions, AI steps, human
approval nodes, versioning (draft/testing/active/paused/archived),
templates, run history, automation analytics.

## Phase 8 — Cross-Module Intelligence

Shared knowledge graph queries across modules, the five cross-module use
cases in spec §69 (Enterprise Sales Security Review, New AI Tool Adoption,
Security Incident, New Customer, Support Upsell Signal), AI daily briefing,
business process discovery, AI recommendation engine, organization memory.

## Phase 9 — Integrations

Connector SDK implementation for CRM, email, support, cloud, identity,
engineering, documents, communication, accounting categories (spec §48),
each starting read-only per the progressive trust model (spec §B1).

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
