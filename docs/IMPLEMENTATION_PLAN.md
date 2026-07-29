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

## Phase 2 — Knowledge & AI Infrastructure

Documents, parsing (PDF/DOCX/XLSX/CSV/TXT/HTML), chunking, `pgvector`
embeddings, entity/relationship extraction, knowledge bases, AI Copilot
foundation (intent router, context builder, citations), AI Action Log UI.

## Phase 3 — Compliance

Frameworks (GDPR, EU AI Act, ISO 27001, ISO 42001, SOC 2, NIS2, DORA),
controls, evidence, AI governance (AI system inventory, DPIA), privacy
(RoPA, DSAR, retention, transfers), risk register, vendor risk,
questionnaires, policies, audits, Trust Center, regulatory intelligence.

## Phase 4 — Security

Asset inventory, cloud security (AWS/Azure/GCP read-only connectors),
identity security (Okta/Entra/Google Workspace), vulnerability management,
alerts, incident response workspace + playbooks, integration with
Compliance's GDPR-breach process.

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
