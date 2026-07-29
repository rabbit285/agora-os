# Implementation Status

Legend: `[x]` Complete · `[~]` In Progress · `[ ]` Not Started · `[!]` Blocked

Last updated: 2026-07-29 (Phase 1 + Phase 2 complete; Phase 3 Compliance, Phase 4 Security, Phase 5 Sales, Phase 6 Customer Support, and Phase 7 Business Automation backbones — verified end-to-end)

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
- [x] `/api/v1/security` router — assets, findings, alerts, incidents; tenant-isolated, RBAC-gated
- [x] RBAC: `security_manager` system role granted security permissions
- [x] Frontend: `/security` dashboard + `/security/incidents/[id]` detail with status workflow
- [x] Seed script: 2 assets, 2 findings, 1 alert, 1 critical incident (linked risk) for the demo org
- [ ] Identity provider integrations (Okta/Entra/Google Workspace) — not started
- [ ] Cloud provider connectors (AWS/Azure/GCP) — not started
- [ ] Incident timeline/evidence/playbooks sub-objects — not started
- [ ] Vulnerability scanner ingestion — not started

## Sales

- [x] Account, Contact, Lead, Opportunity, OutreachMessage models + migration
- [x] Cross-module hook: `Contact.do_not_contact` blocks outreach send, else it "sends" (tested, ADR-0019)
- [x] `/api/v1/sales` router — accounts (+ detail), contacts (+ suppression toggle), leads, opportunities, outreach (create + send); tenant-isolated, RBAC-gated
- [x] RBAC: `sales_manager` / `sales_representative` system roles granted sales permissions
- [x] Frontend: `/sales` overview (accounts, pipeline) + `/sales/accounts/[id]` detail (contacts with suppression toggle, compose/send outreach, opportunities)
- [x] Seed script: 1 account, 2 contacts (1 suppressed), 1 opportunity, 2 outreach attempts (1 sent, 1 blocked) for the demo org
- [ ] Sequences/campaigns (multi-step outreach automation) — not started
- [ ] Meetings, sales conversations/inbox, pipeline events, playbooks — not started
- [ ] Real lead-finding, enrichment, email/LinkedIn sending — depend on external connectors (Phase 9)

## Support

- [x] Customer, Ticket, TicketMessage, KnowledgeArticle, CSATResponse models + migration
- [x] Cross-module hook: a `security`-category ticket auto-creates a linked `SecurityAlert` and escalates the ticket to `urgent` priority (tested, ADR-0020)
- [x] `/api/v1/support` router — customers, tickets (+ detail with message thread, status transitions), knowledge articles, CSAT; tenant-isolated, RBAC-gated
- [x] RBAC: `support_manager` / `support_agent` system roles granted support permissions
- [x] Frontend: `/support` overview (customers, ticket creation/list) + `/support/tickets/[id]` detail (status workflow, linked security alert banner, message thread)
- [x] Seed script: 1 customer (linked to the Nordwind Robotics sales account), 1 resolved billing ticket with CSAT, 1 security-flagged ticket (auto-created SecurityAlert), 1 published knowledge article
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
- [ ] Only 3 of the spec's much larger step vocabulary implemented (create_task, send_notification, human_approval) — Condition/Delay/Loop/Data Transform/Webhook/Subworkflow/AI Step not started
- [ ] Only `manual` trigger type implemented — email/webhook/CRM-event/schedule triggers need Phase 9 connectors
- [ ] Visual drag-and-drop builder, templates, automation analytics — not started

## Integrations

- [ ] Not started (Phase 9)

## Enterprise

- [ ] Not started (Phase 10)

## Testing

- [x] Tenant isolation tests (3 tests, passing)
- [x] RBAC denial tests (2 tests, passing)
- [x] Auth flow tests (8 tests, passing)
- [x] Knowledge module tests (7 tests: chunking, ingestion, unsupported format, tenant isolation)
- [x] Copilot tests (7 tests: cosine similarity, prompt injection framing, insufficient-evidence, retrieval + citations, tenant isolation)
- [x] Compliance tests (9 tests: catalog, RBAC grant/denial, cross-module task creation, tenant isolation, risk lifecycle)
- [x] Security tests (8 tests: RBAC grant/denial, cross-module risk creation, tenant isolation, status workflows)
- [x] Sales tests (8 tests: RBAC grant/denial, suppression blocks send, resend conflict, tenant isolation, opportunity lifecycle)
- [x] Support tests (10 tests: RBAC grant/denial, cross-module alert creation, ticket message thread, status transitions, tenant isolation, CSAT, knowledge article publish toggle)
- [x] Automation tests (9 tests: RBAC grant/denial, draft/active step-edit gate, run-only-if-active gate, full run execution, human_approval pause + resume + decision, rejected-approval failure, tenant isolation)
- [x] 70/70 total, ruff+mypy strict clean
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
non-manual triggers, real external connectors). The cross-module intent
router, Phases 8–10, and the AWS production deployment have not started.
