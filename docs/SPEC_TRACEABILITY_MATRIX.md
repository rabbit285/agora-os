# Spec Traceability Matrix

Every row maps one requirement to `docs/AGORA_ORIGIN_MASTER_SPEC.md`. Statuses:
**VERIFIED** / **IMPLEMENTED_NOT_LIVE_VERIFIED** / **PARTIAL** / **MISSING** /
**AWS_EXCLUDED**. See `PRODUCT_COMPLETENESS_AUDIT.md` for methodology and final counts,
and `REMAINING_PRODUCT_GAPS.md` for the full prose detail behind every non-VERIFIED row.

**Table format note**: the audit brief asked for separate Backend / Migration / API /
Permission / Audit / Frontend / Test / Runtime / Documentation evidence columns. A
15-column markdown table renders unreadably, so this matrix consolidates those nine into
one labeled **Evidence** cell per row (`BE:` backend, `MIG:` migration, `API:` endpoint,
`PERM:` permission, `AUD:` audit event, `FE:` frontend, `TEST:` tests, `RUN:` runtime
evidence gathered in this audit, `DOC:` documentation) — every required evidence category
is still present per row, just labeled inline rather than column-separated.

---

## Platform Foundation (spec §50-59, §61)

| ID | Requirement | Status | Evidence | Exact missing work | AWS |
|---|---|---|---|---|---|
| PLAT-01 | Organization / Membership / Role / Permission core data model (§50, §54) | VERIFIED | BE: `app/core/models.py`; MIG: `a6029098477e`; API: `/organizations/current`; PERM: RBAC dependency-enforced; TEST: 206/206 suite incl. RBAC tests; RUN: live signup created Org B, membership row, `org_admin` role assignment (this audit) | — | No |
| PLAT-02 | Server-side tenant isolation via `X-Organization-Id` + mandatory active-Membership check (§53) | VERIFIED | BE: `app/dependencies.py` `get_org_context`; TEST: tenant-isolation tests in suite; RUN: this audit — Org B empty list on Org A's accounts, 404 on direct ID guess, 403 on header-spoof, all live | — | No |
| PLAT-03 | RBAC deny-by-default enforcement (§54) | VERIFIED | BE: `require_permission` dependency; PERM: `PERMISSIONS` dict, `ROLE_PERMISSION_GRANTS`; RUN: this audit — live `read_only` user got 403 "Missing permission: sales.accounts.manage" on write, 200 on read | — | No |
| PLAT-04 | All 16 spec system roles seeded | VERIFIED | BE: `app/core/rbac.py` `SYSTEM_ROLE_KEYS` (16 entries) | — | No |
| PLAT-05 | Every seeded role carries scoped permissions matching its business purpose | VERIFIED (fixed 2026-07-30) | BE: `app/core/rbac.py` `ROLE_PERMISSION_GRANTS` — `executive` (approvals + cross-cutting), `operations_manager` (tasks/approvals/automation/integrations + cross-cutting), `employee` (own tasks + cross-cutting) now scoped; `read_only` deliberately kept at zero grants by design; TEST: `test_read_only_role_cannot_create_tasks`, `test_employee_role_can_create_tasks_and_use_knowledge_and_copilot`; RUN: this audit — live-verified employee can create tasks/KB/ask Copilot but 403s on Sales | — | No |
| PLAT-06 | Knowledge/Copilot access is RBAC-permission-gated | VERIFIED (fixed 2026-07-30) | BE: added `knowledge.documents.manage` and `ai.copilot.ask` to `PERMISSIONS`, wired via `require_permission()` in `routers/knowledge.py` (create_knowledge_base, create_document) and `routers/ai.py` (copilot_ask); granted to every role except `read_only`; TEST: `test_read_only_role_cannot_upload_documents_or_ask_copilot`, `test_employee_role_can_upload_documents_and_ask_copilot`; RUN: this audit — live 403/201/200 proof against a fresh org | — | No |
| PLAT-07 | Append-only audit trail, DB-enforced | PARTIAL | BE: `app/audit/models.py` docstring claims `REVOKE`; MIG: zero `REVOKE` statements found in any of 21 migrations | Add real DB-level REVOKE migration or correct docstring | No |
| PLAT-08 | Audit event correctly links to the resource it concerns (`object_id`) | VERIFIED (fixed 2026-07-30) | BE: `await db.flush()` added at all 8 confirmed call sites (`sales.py`, `security.py`, `support.py`, `compliance.py`) plus a permanent `ValueError` guard in `app/audit/service.py record_event()`; TEST: `tests/test_audit_event_object_ids.py` (10 new tests, one per entity + guard unit test + cross-module sweep); RUN: this audit — live-reverified post-fix against the running Docker stack, all 8 previously-broken endpoints now write the real UUID | — (was: add flush before 8 call sites — done, see gaps doc §A1) | No |
| PLAT-09 | Task / Approval / Notification core workflow primitives (§44-45) | PARTIAL | BE: `app/core/models.py` — models exist, API exists, tested; missing `Task.created_by`/entity-link/checklist/evidence/comments/activity fields, `Approval.module`/AI-generated/due-date fields | Extend models with spec'd fields | No |
| PLAT-10 | Notification dispatch to real channels (email/Slack/Teams/webhook) | MISSING | Grep-confirmed `Notification.channel` constructed only as `"in_app"` everywhere; zero dispatch adapters | Build dispatch adapters per channel | No |
| PLAT-11 | User signup / login / session (§50) | VERIFIED | API: `/auth/signup`,`/auth/login`,`/auth/me`,`/auth/logout`; RUN: this audit — live signup + cookie-session login both succeeded | — | No |
| PLAT-12 | Password reset flow | VERIFIED | API: `/auth/forgot-password`, `/auth/reset-password`; FE: `/forgot-password`, `/reset-password/[token]` pages in build output | — | No |
| PLAT-13 | Email verification flow | MISSING | No `/verify-email/[token]` page in build; no backend trigger anywhere | Build verification token issuance + page + API | No |
| PLAT-14 | Invitation flow (invite a user to an org) | MISSING | No `/invite/[token]` page in build; no invite API; `organizations/current/members` is GET-only | Build invite issuance, accept endpoint, and page | No |
| PLAT-15 | MFA | MISSING | Schema-only; no challenge screen, no TOTP/WebAuthn code | Full MFA implementation | No |
| PLAT-16 | Multi-entity support (parent org / subsidiaries) | MISSING (spec's own "Future"/Phase 10 deferral, §53 & §79) | `LegalEntity`/`Team` models exist, zero CRUD endpoints; `Organization` has no parent FK | Consistent with spec's own deferral — not attempted-and-broken | No |
| PLAT-17 | Agency/consultant multi-client mode | MISSING (spec's own Phase 10 deferral, §79) | No implementation found | Consistent with spec's own deferral | No |
| PLAT-18 | SSO/SAML/SCIM | MISSING (spec's own Phase 10 deferral, §59, §79) | No implementation found | Consistent with spec's own deferral | No |
| PLAT-19 | Billing & entitlements | MISSING | No implementation found | Full build | No |
| PLAT-20 | Reporting module | MISSING | No implementation found | Full build | No |
| PLAT-21 | Global search | MISSING | FE: sidebar entry routes to honest coming-soon state; BE: no endpoint | Full build | No |
| PLAT-22 | Global Create button | MISSING | Not present in navigation/build output | Full build | No |
| PLAT-23 | Workflow engine decoupled from HTTP request cycle via Temporal (§61) | PARTIAL (Automation module specifically) | BE: Automation executes fully synchronously in-request, zero Temporal usage, contradicting §61; Knowledge and Integrations correctly use Temporal | Move Automation execution onto Temporal | No |
| PLAT-24 | CI/CD pipeline configuration exists in-repo | MISSING | No `.github/` directory found | Add CI workflow config (excludes live AWS deploy validation) | No |

## Knowledge & RAG (spec §7-11, §46)

| ID | Requirement | Status | Evidence | Exact missing work | AWS |
|---|---|---|---|---|---|
| KNOW-01 | Document upload → parsing → chunking → embedding pipeline | VERIFIED | BE: `app/knowledge/{parsing,chunking,retrieval,service}.py`; MIG: knowledge migration `532f9ba4848e`; API: `/knowledge/documents`; FE: `/knowledge`, `/knowledge/[id]`; TEST: suite | — | No |
| KNOW-02 | PDF/DOCX/TXT/MD ingestion | VERIFIED | BE: real extractor code confirmed by direct read | — | No |
| KNOW-03 | XLSX/HTML ingestion (claimed-supported) | PARTIAL | BE: no extractor code exists for either format despite being claimed-supported | Implement extractors or correct the claim | No |
| KNOW-04 | PPTX / OCR ingestion | MISSING (correctly disclosed as architecture-only) | `docs/DECISIONS.md` honestly discloses this | Full build | No |
| KNOW-05 | Retrieval via embedding similarity search | VERIFIED | BE: JSON-stored embeddings (ADR-0007), Python-scan cosine similarity (ADR-0012), both honestly documented; RUN: this audit — live Copilot ask returned real citations with document_id/chunk_id/score | — | No |
| KNOW-06 | Reranking | MISSING (honestly labeled) | `NotImplementedError` raised by both adapters, gracefully caught in `gateway.py:228` | Implement reranking for at least one provider | No |
| KNOW-07 | Organization Knowledge Graph / entity-relationship extraction (§10-11) | MISSING | No implementation; not disclosed in `docs/DECISIONS.md` | Full build | No |
| KNOW-08 | Global/unified search across modules (§47) | MISSING | No endpoint; sidebar routes to coming-soon | Full build | No |

## AI Gateway & Copilot (spec §55-58)

| ID | Requirement | Status | Evidence | Exact missing work | AWS |
|---|---|---|---|---|---|
| AI-01 | Single-choke-point Model Gateway for all LLM calls | VERIFIED | BE: `app/ai/gateway.py` `ModelGateway.generate`/`.embed` | — | No |
| AI-02 | Real Anthropic + OpenAI adapters | IMPLEMENTED_NOT_LIVE_VERIFIED | BE: real SDK calls confirmed (`anthropic.AsyncAnthropic`, `openai.AsyncOpenAI`), gated on `AI_PROVIDER` env + API key; `.env.example` ships empty keys — needs real credentials to live-verify against the actual provider | Run once with real API keys configured | No |
| AI-03 | Honest demo fallback when uncredentialed | VERIFIED | BE: `DemoAdapter`, provider label `"demo"`; RUN: this audit — live Copilot ask returned `"provider":"demo"` with explicit `[DEMO MODE — no AI provider configured]` text | — | No |
| AI-04 | Every AI call logged to `AiRun` including on error | VERIFIED | BE: `finally` block in gateway | — | No |
| AI-05 | Evidence-grounded Copilot Q&A with citations | VERIFIED | BE: `app/ai/copilot.py` retrieve→ground→generate→cite pipeline; RUN: this audit — live ask returned `grounded:true` + 2 citations with scores | — | No |
| AI-06 | Honest "no evidence" fallback message | VERIFIED | BE: `NO_EVIDENCE_MESSAGE` constant, used when retrieval empty | — | No |
| AI-07 | Prompt-injection resistance for retrieved content | PARTIAL | BE: `<source>` tag framing + untrusted-data warning present; TEST: only string-presence tested, no adversarial test | Add adversarial prompt-injection test cases | No |
| AI-08 | `generate_structured` wired into domain services | MISSING | Defined on Protocol/adapters, never called anywhere | Wire at least one real caller or remove dead plumbing | No |

## Compliance / GDPR / EU AI Act / AI Governance / Privacy (spec §12, §50, plus GDPR Art. 30/35/15-20)

| ID | Requirement | Status | Evidence | Exact missing work | AWS |
|---|---|---|---|---|---|
| COMP-01 | Control / Requirement / Framework model + assessment lifecycle | VERIFIED | BE: `app/compliance/{models,service}.py`; MIG: `0abd75fd3bd9`; API: `/compliance/controls`,`/frameworks`; FE: `/compliance/controls/[id]`; TEST: suite | — | No |
| COMP-02 | ≥8 named frameworks seeded with catalog content | PARTIAL | Only GDPR, EU AI Act, ISO 27001 (3 of 8) actually seeded | Seed remaining 5 catalogs | No |
| COMP-03 | Risk register + assessment→Risk hook (fail → Task) | VERIFIED | BE: `record_assessment` hook reused across 4+ modules; TEST: suite | — | No |
| COMP-04 | Evidence attachment | VERIFIED | BE/API/TEST present | — | No |
| COMP-05 | Policy management | PARTIAL | BE complete incl. RBAC permission + audit event; FE: zero page | Build frontend page | No |
| COMP-06 | AI System Inventory + EU AI Act risk tiers + Approval gate | VERIFIED | BE: `app/compliance/models.py` `AISystem`; MIG: `3358342814ae`; API/FE/TEST all present; approval-gate tested | — | No |
| COMP-07 | RoPA (processing activities, GDPR Art. 30) | VERIFIED | MIG: `7e4373ed23fd`; API `/compliance/processing-activities`; TEST suite | Standalone detail view is list-only, minor FE gap | No |
| COMP-08 | DPIA (GDPR Art. 35) | VERIFIED | Same migration; API `/compliance/dpias`; FE `/compliance/dpias/[id]`; high-risk approval-gate tested | — | No |
| COMP-09 | DSAR lifecycle (GDPR Art. 15-20) | VERIFIED | API `/compliance/dsars`; FE `/compliance/dsars/[id]`; RUN: this audit — live GET returned real seeded DSAR rows with due dates/status | — | No |
| COMP-10 | Data Transfers + derogation→Risk hook | VERIFIED | MIG: `a121c274b0ab` (head); API `/compliance/data-transfers`; TEST suite | — | No |
| COMP-11 | AI Incidents + critical→Risk+Task+Notification hook | VERIFIED | MIG: `b7dc4409d48d`; TEST suite | — | No |
| COMP-12 | Vendor Risk + high/critical→Risk hook | VERIFIED | MIG: `ada1f522aaf8`; TEST suite | — | No |
| COMP-13 | Security Questionnaires incl. AI-suggested answers | VERIFIED | MIG: `2f623cef5c7c`; API incl. `/suggest-answer`; FE detail page w/ missing-answer banner | — | No |
| COMP-14 | Audits + finding→Task hook | VERIFIED | MIG: `096ef4c61446`; TEST suite | — | No |
| COMP-15 | Trust Center, genuinely public unauthenticated page | VERIFIED | MIG: `b8b5df74e57d`; BE: `trust_center.py` router confirmed to have no `OrgContext` param; FE: `/trust/[org_slug]` | — | No |
| COMP-16 | Enterprise Sales Security Review, full 10-step flow | VERIFIED (minus 1 sub-step) | MIG: `a798cc5b8e8d`; all 10 spec steps confirmed except "Sales Copilot drafts follow-up" | Add the one missing sub-step | No |
| COMP-17 | Compliance as Governance Layer — synchronous pre-action checks FROM other modules INTO Compliance (§91) | MISSING | Only the inverse (event-reaction) pattern exists | Build synchronous pre-check API + call sites in Sales/Support/Automation | No |
| COMP-18 | Standalone Evidence Library / framework dashboards / Regulatory Intelligence pages | MISSING | No FE pages | Build pages | No |

## Security (spec §13-19)

| ID | Requirement | Status | Evidence | Exact missing work | AWS |
|---|---|---|---|---|---|
| SEC-01 | Security Asset inventory | VERIFIED | BE/MIG (`fe3ac9fbcce9`)/API/FE/TEST; RUN: this audit — live asset creation + (buggy) audit event confirmed | Fix PLAT-08 audit bug | No |
| SEC-02 | Security Findings | VERIFIED | Category-discriminator consolidation confirmed as a deliberate documented design choice | — | No |
| SEC-03 | Security Alerts | PARTIAL | BE/API exist; zero audit events, zero test coverage | Add audit events + tests | No |
| SEC-04 | Security Incidents + critical→Risk+Task+Notification hook | VERIFIED | TEST suite covers the hook chain | — | No |
| SEC-05 | Incident workspace (Timeline/Affected-Assets/Evidence/Communication/Root-Cause/Lessons-Learned) | PARTIAL | Only a status enum + 2 FK links exist; none of the named sub-structures | Extend model + UI | No |
| SEC-06 | Cloud Security (§15) | MISSING | Free-text category tag only | Full build | No |
| SEC-07 | Identity Security (§16) | MISSING | Free-text category tag only | Full build | No |
| SEC-08 | Security Overview dashboard | MISSING | FE is 4 flat CRUD lists, not a dashboard | Build dashboard | No |
| SEC-09 | Asset Detail / Alert Detail / Security Policies pages | MISSING | No FE pages | Build pages | No |

## Sales (spec §20-29)

| ID | Requirement | Status | Evidence | Exact missing work | AWS |
|---|---|---|---|---|---|
| SALES-01 | Account/Contact/Opportunity/Lead CRUD | VERIFIED | BE/MIG (`f4616d58455d`)/API/FE/TEST; RUN: this audit — live account/contact/opportunity creation | — | No |
| SALES-02 | `close_opportunity_won` → Customer + onboarding Task, idempotent | VERIFIED | BE: `app/sales/service.py`; RUN: this audit — live double-close proved exactly one Customer created, second call a true no-op | — | No |
| SALES-03 | Outreach compliance gate (suppression check, §91 simplest instance) | VERIFIED | BE: `send_outreach_message`; per-contact `do_not_contact` gate real and tested | — | No |
| SALES-04 | ICP scoring | MISSING | `icp_score` bare column, only ever hardcoded seed value 87.5 | Build scoring algorithm | No |
| SALES-05 | Lead Finder / Enrichment | MISSING | No implementation | Full build | No |
| SALES-06 | Sequences / Sequence Builder / Campaigns | MISSING | Only a single manual-send `OutreachMessage`, no cadence engine | Full build | No |
| SALES-07 | Sales Inbox / Meeting Assistant / Sales Intelligence | MISSING | No implementation | Full build | No |
| SALES-08 | Lead/Contact/Opportunity standalone detail pages | MISSING | Only Account detail exists | Build pages | No |
| SALES-09 | Security-review deal-blocker indicator on account detail | VERIFIED | RUN/code-confirmed genuinely real, not decorative | — | No |

## Support / Customer Support (spec §30-35)

| ID | Requirement | Status | Evidence | Exact missing work | AWS |
|---|---|---|---|---|---|
| SUPP-01 | Customer/Ticket/Message CRUD | VERIFIED | BE/MIG (`f603b3037fca`)/API/FE/TEST | — | No |
| SUPP-02 | Ticket → Upsell Lead flag hook | VERIFIED | MIG: `7959d34d194d` adds `upsell_lead_id` (resolved possible drift flag — column has its own dedicated migration, confirmed present in the clean-apply chain) | — | No |
| SUPP-03 | AI-grounded ticket response (§32) | MISSING | Grep-confirmed zero calls into `app/ai/copilot.py` or `app/knowledge/retrieval.py` from any support code | Wire Copilot into ticket response flow | No |
| SUPP-04 | Knowledge Base (support-specific) | PARTIAL | BE complete; zero FE page | Build page | No |
| SUPP-05 | Conversations (separate from Tickets) | MISSING | No implementation | Full build | No |
| SUPP-06 | AI Agent configuration | MISSING | No implementation | Full build | No |
| SUPP-07 | QA scoring / CSAT reporting dashboard | PARTIAL | Raw `POST /support/csat` endpoint exists; no dashboard/analytics | Build dashboard | No |

## Automation (spec §36-43, §61)

| ID | Requirement | Status | Evidence | Exact missing work | AWS |
|---|---|---|---|---|---|
| AUTO-01 | Workflow CRUD + step definitions | VERIFIED | BE/MIG (`1b637fc1f956`)/API/FE/TEST | — | No |
| AUTO-02 | `human_approval` pause/resume/reject | VERIFIED | Real behavioral tests for all 3 paths | — | No |
| AUTO-03 | Workflow execution decoupled via Temporal | MISSING | Executes fully synchronously in-request, contradicting §61 | Move to Temporal | No |
| AUTO-04 | WorkflowVersion / immutable publish history | MISSING | No such table | Build | No |
| AUTO-05 | ≥24 spec'd action types | PARTIAL | Only 3 executable | Build remaining action types | No |
| AUTO-06 | ≥16 spec'd trigger types | PARTIAL | Only 2 executable | Build remaining trigger types | No |
| AUTO-07 | Visual drag-and-drop Workflow Builder | MISSING | Current FE is a structured step-list form, not a visual builder | Build React Flow builder | No |
| AUTO-08 | Workflow Templates gallery / Connections page / analytics dashboard | MISSING | No implementation | Full build | No |

## Integrations (spec §48-49)

| ID | Requirement | Status | Evidence | Exact missing work | AWS |
|---|---|---|---|---|---|
| INTEG-01 | OAuth connection lifecycle (connect/refresh/disconnect/health/sync) for 6 providers | VERIFIED | BE: real adapters for HubSpot/Google/Microsoft/GitHub/Slack/Salesforce, real httpx calls, Fernet encryption; MIG: `cc2c444f0447`; FE: `/settings/integrations`; TEST suite | — | No |
| INTEG-02 | Honest mock fallback + "Not configured" UI state | VERIFIED | BE: `MockOAuthAdapter`, clearly labeled, no fabricated "connected" state | — | No |
| INTEG-03 | Temporal-backed durable sync | PARTIAL | Real Temporal usage confirmed; lacks cursors/checkpointing/tombstones (§G2) | Add checkpointing | No |
| INTEG-04 | Signed webhook → workflow trigger | VERIFIED | API: `/integrations/webhooks/{connection_id}/receive`; TEST suite | — | No |
| INTEG-05 | Connector coverage for Email/Marketing/Cloud/Identity/Engineering/Documents/Accounting/Support-competitor categories (§48) | MISSING | Zero code for any category beyond the 6 built providers; even "Email" is Calendar-shaped, not Mail | Build remaining connector categories | No |

## Cross-Module Scenarios (spec §69)

See gaps doc §A2 for the full step-by-step breakdown. Summary:

| ID | Scenario | Status | Exact missing work | AWS |
|---|---|---|---|---|
| SCEN-01 | Enterprise Sales Security Review (10 steps) | VERIFIED (9/10) | Add "Sales Copilot drafts follow-up" sub-step | No |
| SCEN-02 | New AI Tool Adoption (9 steps) | PARTIAL (4/9) | Already correctly flagged partial in KNOWN_LIMITATIONS.md | No |
| SCEN-03 | Security Incident Response (9 steps) | PARTIAL (3/9) | Build remaining 6 steps (timeline, affected assets, evidence, communication, root cause, lessons learned) | No |
| SCEN-04 | New Customer Onboarding (8 steps) | PARTIAL (2/8) | Build welcome email, billing update, scheduled check-in beyond the one task, assign account owner | No |
| SCEN-05 | Support Upsell Signal (4 steps) | PARTIAL (2/4) | Build Sales Copilot involvement + account-owner notification | No |

## Business Intelligence Layer (spec §86-90)

| ID | Requirement | Status | Evidence | Exact missing work | AWS |
|---|---|---|---|---|---|
| BIZ-01 | Business Process Discovery | MISSING | No implementation | Full build | No |
| BIZ-02 | AI Recommendation Engine | MISSING | No implementation | Full build | No |
| BIZ-03 | AI Daily Briefing | MISSING | No implementation | Full build | No |
| BIZ-04 | Business AI Memory | MISSING | No implementation | Full build | No |
| BIZ-05 | Business Rules Engine | MISSING | No implementation | Full build | No |

## AWS-Excluded (spec sections A-N)

| ID | Requirement | Status | AWS |
|---|---|---|---|
| AWS-01 | Live ECS container deployment | AWS_EXCLUDED | Yes |
| AWS-02 | Live RDS/ElastiCache/CloudFront/WAF/Route53 provisioning | AWS_EXCLUDED | Yes |
| AWS-03 | Production AWS backup/recovery execution | AWS_EXCLUDED | Yes |
| AWS-04 | Live AWS CI/CD deployment validation | AWS_EXCLUDED | Yes |
