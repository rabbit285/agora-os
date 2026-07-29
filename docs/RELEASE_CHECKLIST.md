# Release Checklist

Honest status against the spec's "Definition of Full Completion" (§J) and
"Definition of Done" (§83). This is a **Phase 1 + Phase 2 + partial
Phases 3-8 / local-only** checkpoint, not a production release — most
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
- [ ] Audits, AI governance, privacy workflows (RoPA/DPIA/DSAR), vendor
      risk, questionnaires, Trust Center, regulatory intelligence — not
      started, each a substantial feature in its own right

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

## Phase 8 (Cross-Module Intelligence) — first scenario complete, four remain

- [x] "Support Upsell Signal" (spec §69): flagging a ticket creates a real
      sales.Lead + notifies the linked account's owner (tested, ADR-0022)
- [x] Backend tests: 73 passing total; ruff/mypy clean
- [ ] Enterprise Sales Security Review, New AI Tool Adoption, the rest of
      the Security Incident chain, New Customer — not started, most need
      modules/data that don't exist yet (questionnaires, AI system inventory)
- [ ] AI daily briefing, business process discovery, AI recommendation
      engine, organization memory, cross-module intent router — not started

See `docs/RESUME_BUILD.md` for the next phase (Phase 9 — Integrations, or
another Phase 8 scenario).

## Not started (tracked in docs/IMPLEMENTATION_PLAN.md)

- [ ] Phase 9 — Integrations / connectors
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
