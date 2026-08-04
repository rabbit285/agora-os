# Remaining Product Gaps

Companion to [`PRODUCT_COMPLETENESS_AUDIT.md`](PRODUCT_COMPLETENESS_AUDIT.md) and
[`SPEC_TRACEABILITY_MATRIX.md`](SPEC_TRACEABILITY_MATRIX.md). This document lists every
requirement that is not VERIFIED, with the exact missing work. AWS-excluded items are
listed in their own section at the end for completeness, not because they need action now.

Audit date: 2026-07-30. Verified against commit `e5fa62d` (working tree clean, no product
code changed by this audit). **Update 2026-07-30**: finding A1 below has been fixed,
tested, and live-verified — see the "FIXED" note inline. All counts elsewhere in this
document and in `SPEC_TRACEABILITY_MATRIX.md`/`PRODUCT_COMPLETENESS_AUDIT.md` have been
updated to reflect PLAT-08 moving from PARTIAL to VERIFIED; the finding is kept here,
marked resolved, rather than deleted, so the record of what was wrong and how it was
caught remains available.

---

## A. Headline cross-cutting findings

These are not single-module gaps; they affect how to read every other finding in this
document.

### A1. [FIXED — 2026-07-30] Audit-event `object_id` was written as the literal string `"None"` for 8 of ~17 "created" event types

**Confirmed live** during this audit (not merely inferred from code reading). Root cause:
`UUIDPrimaryKeyMixin.id` (`apps/api/app/db/base.py:34`) uses a Python-side
`default=uuid.uuid4`, which SQLAlchemy only applies at flush time. Several routers call
`record_event(..., object_id=str(obj.id), ...)` immediately after `db.add(obj)` but
**before** any `await db.flush()`, so `obj.id` is still `None` and `str(None)` — the
literal four-character string `"None"` — is what lands in `audit_events.object_id`.

Live proof (this audit, Org "Audit Test Org B", now cleaned up):
- `POST /api/v1/sales/accounts` → `audit_events` row `action=sales.account.created,
  object_id=None` (should have been the account's real UUID).
- `POST /api/v1/security/assets` → `action=security.asset.created, object_id=None`
  (same bug, independent router file).

Confirmed **broken** (db.add immediately followed by record_event, no intervening flush):
- `apps/api/app/routers/sales.py:52-60` — `sales.account.created`
- `apps/api/app/routers/sales.py:212-222` — `sales.opportunity.created`
- `apps/api/app/routers/security.py:55-60` — `security.asset.created`
- `apps/api/app/routers/security.py:94-99` — `security.finding.created`
- `apps/api/app/routers/support.py:53-58` — `support.customer.created`
- `apps/api/app/routers/compliance.py:314-315` — `compliance.evidence.created`
- `apps/api/app/routers/compliance.py:351-352` — `compliance.risk.created`
- `apps/api/app/routers/compliance.py:417-418` — `compliance.policy.created`

Confirmed **correct** (an `await db.flush()` appears between `db.add()` and
`record_event()`, so the real UUID is captured): `compliance.control.created`,
`compliance.processing_activity.created`, `compliance.vendor.created`,
`compliance.questionnaire.created`, `compliance.audit.created`,
`core.file.upload_requested`, `integrations.connection.created`,
`knowledge.document.created`, `core.task.created`.

**Why this survived the existing test suite**: the pytest suite (206 passing tests)
asserts that an `AuditEvent` row was created with the right `action`/`organization_id`,
but does not assert the correctness of `object_id`'s value — exactly the "tests asserting
only status codes / shallow fields" pattern this audit was instructed to look for.

**Fix applied (2026-07-30)**: added `await db.flush()` before each of the 8 confirmed
call sites listed above, in `apps/api/app/routers/{sales,security,support,compliance}.py`.
Additionally hardened `app/audit/service.py`'s `record_event()` itself with a permanent
guard — it now raises `ValueError` if ever called with `object_id == "None"` — so any
future regression of this exact bug class fails loudly in tests/dev rather than silently
writing a broken audit trail row. Added
`apps/api/tests/test_audit_event_object_ids.py`: one regression test per fixed entity
(sales account, sales opportunity, security asset, security finding, support customer,
compliance risk, compliance policy, compliance evidence) asserting
`audit_events.object_id` equals the real created resource's UUID and is never `"None"`,
plus a direct unit test of the `record_event()` guard and a cross-module sweep test. Full
backend suite (216 tests, up from 206), lint, format, and mypy all pass; frontend
eslint/tsc/vitest/build all pass (no frontend files were touched, run for completeness).
Live-verified against the running Docker stack post-restart: created a fresh disposable
organization, exercised all 8 previously-broken endpoints, and confirmed via direct
`audit_events` query that every `object_id` now matches the real resource UUID (evidence
run and disposable org fully cleaned up afterward — dev database restored to its
pre-verification state).

**Impact**: does not affect security (the row IS written, tenant-scoped correctly,
append-only) — but breaks the ability to correlate an audit-log entry back to the specific
resource it concerns for these 8 event types, which is a real defect against the audit
trail requirement (spec §57, §93).

### A2. [FIXED — 2026-07-30, documentation only] `docs/KNOWN_LIMITATIONS.md` overstates completeness of 3 of spec §69's 5 named cross-module scenarios

`KNOWN_LIMITATIONS.md` stated "four of the five [§69] scenarios are now fully
implemented." Direct comparison against the spec's literal step lists (§69, lines
6599-6760) shows:

| Scenario | Spec steps | Steps actually implemented | 
|---|---|---|
| Enterprise Sales Security Review | 10 | 9 (minus one sub-step: "Sales Copilot drafts follow-up") — genuinely near-complete |
| New AI Tool Adoption | 9 | 4 — already correctly flagged as partial in KNOWN_LIMITATIONS.md |
| Security Incident Response | 9 | 3 (create incident → link risk → create response task; the incident workspace's Affected-Assets/Evidence features exist but as manual actions, not automatic reactions in *this* chain) |
| New Customer Onboarding | 8 | 2 (create Customer → create onboarding Task; no welcome email, billing update, support-profile creation, or scheduled check-in) |
| Support Upsell Signal | 4 | 2 (flag ticket → create Lead → notify the linked account owner; no Opportunity-suggestion artifact, no AI-generated account brief) |

What **is** built for Security Incident, New Customer, and Support Upsell Signal is real,
tested, non-fake code (confirmed both by subagent code reading and, for New Customer, by
this audit's own live `close_opportunity_won` idempotency test) — it is a genuine subset
of each scenario, not vaporware. The gap was specifically that the product doc's own
completeness claim ("fully implemented") was inaccurate relative to the spec's literal text
for 3 of the 4 scenarios it claimed were done.

**Fix applied (2026-07-30)**: `KNOWN_LIMITATIONS.md`'s Cross-Module Intelligence bullet was
rewritten with the exact per-scenario step count and named missing steps above (option (b)
from the original finding — explicit per-step disclosure), rather than a blanket "fully
implemented" claim. Implementing the remaining named steps themselves (welcome email —
blocked on the same no-SMTP-provider capability boundary as Automation's `send_email` step;
billing update — blocked on the Billing module, tracked separately as PLAT-19; a formal
GDPR-breach Compliance assessment step; Sales Copilot follow-up drafting; an Opportunity-
suggestion artifact; AI-generated account briefs) remains open, deliberately deferred in
favor of the larger MISSING-status gaps elsewhere in this document (Billing, Reporting,
Business Intelligence layer, etc.) — these are scenario-depth refinements on top of
features that already work in their base form, not zero-code gaps.

### A3. [PARTIALLY FIXED — 2026-07-30] `docs/ROUTES_AND_SCREENS.md` lists 8 routes as `[~]`/scaffolded that do not exist in the actual build

Confirmed via a fresh `npm run build` route table (this audit) cross-checked against the
doc: `/onboarding/company`, `/onboarding/goals`, `/notifications`, `/settings/roles`,
`/settings/ai-providers`, `/invite/[token]`, `/verify-email/[token]`, and the MFA-challenge
screen all appear in the doc with `[~]`/`[ ]` status implying at least a placeholder
exists, but none produced a route in the Next.js build output (33 real routes, listed in
`ROUTE_API_INVENTORY.md`). This is documentation/code drift, not a product gap per se, but
it means the doc cannot be trusted as a completeness source — which is exactly why this
audit re-derived route status from the live build rather than from the doc.

**Fix applied (2026-07-30, now complete for all 8)**: `/invite/[token]`, `/verify-email/
[token]`, and the MFA-challenge screen were already built in an earlier cluster this session
(PLAT-13/14/15). `/notifications` (PLAT-10), `/settings/roles` and `/settings/ai-providers`,
and the onboarding wizard (`/onboarding`, replacing the originally-sketched `/onboarding/
company`+`/onboarding/goals` sub-routes, PLAT-25) are now all real, built, tested pages —
see their own entries below and in `SPEC_TRACEABILITY_MATRIX.md`. All 8 of finding A3's
originally-flagged routes are now either accurately documented as `[ ]` (the two remaining
`/onboarding/company`/`/onboarding/goals` mentions were superseded by the single `/onboarding`
route) or built and `[x]`.

### A4. `apps/api/app/audit/models.py` docstring claims a DB-level `REVOKE UPDATE/DELETE` on `audit_events` that does not exist

Grepped every one of the 21 migration files: zero `REVOKE` statements anywhere.
Append-only-ness of the audit trail is enforced only by application code convention (no
`UPDATE`/`DELETE` calls against `AuditEvent` anywhere in the service layer), not by a
database privilege. A superuser or a future buggy migration could mutate history
undetected.

**Exact missing work**: either add the migration that actually revokes `UPDATE`/`DELETE`
on `audit_events` from the application's database role, or correct the docstring to not
claim a protection that isn't there.

### A5. [FIXED — 2026-07-30] `ensure_system_roles()`'s own docstring said "safe to call on every startup" but nothing called it at startup

Found while adding two new Support permissions (`support.ai_agent.manage`,
`support.qa.manage`) in this session: an organization signed up *before* those
permissions were added to `app/core/rbac.py` never received them on its `org_admin`
role, even after the API process was restarted with the new code — because
`ensure_system_roles` (which is genuinely idempotent/additive, confirmed by reading it)
was only ever called from the signup flow (`app.identity.service.login`... actually
`create_organization`-adjacent signup code) and the standalone seed script, never from
`app/main.py`'s own startup. Every permission added in every earlier cluster this
session (PLAT-05/06, SEC's three new permissions, Sales' three, Support's two) had this
same latent gap — it only went unnoticed because this audit's live-verification
convention is always a *fresh* signup per test, which always got the current code's
grants at signup time.

**Fix applied (2026-07-30)**: `app/main.py`'s `lifespan()` now calls
`ensure_system_roles()` once against a real session on every application boot, so a
newly added permission reaches every already-seeded system role (not just newly signed
up organizations) the next time the API process restarts — matching what the function's
own docstring already promised. Confirmed live: an org created before this fix, and
before the two new Support permissions existed, could not call
`PUT /support/ai-agent-config` (403 "Missing permission") even after an API restart with
the new route code; after adding the startup call and restarting again, the same org's
`org_admin` role was confirmed via direct SQL to now hold both new permission grants, and
the same previously-403 calls succeeded. Full backend suite (315 tests) still green
after the change.

---

## B. Per-module gaps

### Knowledge & RAG

- **[FIXED 2026-07-30]** ~~XLSX and HTML were claimed-supported ingestion formats with no
  extractor code~~ — `_extract_xlsx` (openpyxl) and `_extract_html` (BeautifulSoup,
  strips script/style) added to `parsing.py`; live-verified end to end through the real
  presigned-upload → Temporal-worker ingestion path.
- **[FIXED 2026-07-30]** ~~Reranking was unimplemented for both Anthropic and OpenAI, and
  `generate_structured` was dead plumbing~~ — `ModelGateway.rerank()` added (logs an
  `AiRun`, falls back to a genuine deterministic lexical-overlap scorer, not a no-op);
  `AnthropicAdapter`/`OpenAIAdapter.rerank()` now call `generate_structured` with a
  `RerankScores` schema (this is also `generate_structured`'s first real caller); wired
  into Copilot's retrieval step. Live-verified: a Copilot ask's citations came back
  re-scored and reordered, with a `knowledge.rerank` AiRun row in between embedding and
  generation.
- **[FIXED 2026-07-30, scoped]** ~~Organization Knowledge Graph (spec §10) was entirely
  unbuilt~~ — `app/knowledge/graph.py` provides a read-only one-hop traversal over 20
  entity types' real existing foreign keys (Account↔Contact↔Opportunity↔Customer↔Ticket,
  Vendor↔Risk, AI System↔DPIA↔Incident, etc.) — deliberately a view over the relational
  data already there, not a duplicated graph store (see the module's docstring for why
  that's the more honest design). `GET /knowledge/graph/{type}/{id}` + a `/knowledge/graph`
  explorer page with click-through navigation. **Scoped exclusion, disclosed**: spec §11's
  ingestion-pipeline step "entity extraction → relationship extraction" *from document
  text* is a separate, harder NLP feature not attempted here — the graph only concerns
  records that already exist as rows, not entities mentioned inside uploaded documents.
- **[FIXED 2026-07-30]** ~~Global/unified search across modules (spec §47) did not
  exist~~ — `app/search/service.py` provides a real tenant-scoped `ILIKE` search across 16
  entity types (Sales/Support/Compliance/Security/Automation/Knowledge); `/search` page
  reachable from an always-visible top-nav search box. Live-verified including cross-tenant
  denial (header-spoof attempt correctly 403'd, same enforcement as every other endpoint).
  Per-module *read* permission scoping beyond tenant isolation doesn't exist anywhere else
  in the app either (only writes are permission-gated), so this doesn't invent one just
  for search — disclosed in the module's docstring.

### Compliance / GDPR / EU AI Act / AI Governance

- **PARTIAL**: Only 3 of 8 named frameworks (GDPR, EU AI Act, ISO 27001) have seeded
  catalog content; the remaining 5 have no requirement/control catalog.
- **[FIXED 2026-07-30]** ~~`Policy` had a complete backend but zero frontend page~~ —
  added `PATCH /compliance/policies/{id}/status` (draft/published) and a Policies
  section on `/compliance` (create + publish toggle). Live-verified.
- **[FIXED 2026-07-30, 2 of 3]** ~~Standalone Evidence Library page and framework-specific
  dashboards were missing~~ — added a real file-upload Evidence Library section on
  `/compliance` and a `GET /compliance/frameworks/{id}/dashboard` endpoint + FE page
  showing each requirement's mapped controls, their status, and overall coverage %.
  **Regulatory Intelligence remains unbuilt, disclosed rather than stubbed**: it would
  need a live external feed of regulatory changes, and there is no such data source in
  this build to back it honestly (spec §82 "No Fake Features" — better to leave it
  undone than fabricate regulatory content). Standalone Data Inventory/RoPA detail view
  also remains list-only.
- **[FIXED 2026-07-30]** ~~spec §91 "Compliance as Governance Layer" (synchronous
  pre-action checks FROM other modules INTO Compliance) had no implementation, only the
  inverse (event-reaction) pattern~~ — `app/compliance/governance.py` adds one real,
  pure decision function per spec §91's three named examples, live-verified for all
  three: Sales (`check_contact_permission`, now the actual implementation behind
  `send_outreach_message`'s suppression check, not just an inline field read), Support
  (`check_customer_disclosure_permission`, a new 403 gate on agent ticket messages while
  a deletion DSAR is pending), and Automation (`check_data_export_permission`, a new
  `export_data` workflow step type that fails the run without an active on-file
  `DataTransfer` for restricted/confidential data).
- **CONFIRMED (not a gap)**: the Trust Center public endpoint
  (`apps/api/app/routers/trust_center.py`) genuinely has no `OrgContext` dependency —
  correctly, deliberately unauthenticated per spec B4.

### Security (resolved 2026-07-30 — see SEC-03/05/06/07/08/09 in the traceability matrix)

- **RESOLVED**: Cloud Security (spec §15) and Identity Security (spec §16) are now real
  `boto3`-backed scans (`app.secops.cloud_scanner`) gated on real AWS credentials, writing
  ordinary `SecurityFinding` rows via the existing category discriminator. Only 2 of the
  spec's ~11 example checks are implemented (S3 public-access-block, IAM users without
  MFA) and only AWS is wired (not Azure/GCP) — disclosed scope, see
  `docs/KNOWN_LIMITATIONS.md`. Real-AWS-account scanning is untested (`AWS` column = Yes);
  the uncredentialed `configured=False` path is live-verified.
- **RESOLVED**: Security Overview dashboard (spec §13) now exists at `GET
  /security/overview` + a dashboard section on the Security page — 9 live-computed
  metrics, no placeholders.
- **RESOLVED**: `SecurityIncident` now has a full incident workspace: Timeline +
  Communication (one chronological log, discriminated by `entry_type`), Affected Assets
  (idempotent linking), Root-Cause/Lessons-Learned, and Evidence (via
  `Evidence.incident_id`, reusing the existing evidence library rather than a new table).
- **RESOLVED**: `SecurityAlert` create/update now emit audit events and have test
  coverage.
- **RESOLVED (frontend)**: Asset Detail page, Alert Detail page, and a Security Policies
  page all exist. Security Policies deliberately reuses `GET /compliance/policies`
  read-only rather than inventing a second policy store (spec §80).

### Sales (resolved 2026-07-30 — see SALES-04/05/06/07/08 in the traceability matrix)

- **RESOLVED**: ICP scoring (spec §20) — `app.sales.icp` computes a deterministic 0-100
  score (industry match + employee-count fit) against a real org-configured
  `ICPProfile`; saving the profile rescans every existing Account.
- **RESOLVED**: Lead Finder (spec §21) — surfaces the org's own existing ICP-fit Accounts
  lacking an open Lead. Deliberately not an external prospecting data source (none is
  configured in this build).
- **RESOLVED**: Enrichment (spec §21) — real Clearbit Company API call gated on
  `CLEARBIT_API_KEY`; honest `configured=false` when absent, never a fabricated profile.
- **RESOLVED**: Sequences/Sequence Builder/Campaigns (spec §23) — a real multi-step
  cadence engine (`app.sales.sequences`). Every automated step reuses
  `send_outreach_message`, so the same compliance gate applies to automated sends as
  manual ones. Step advancement is a real, independently-callable function, not yet
  wired to a periodic Temporal schedule (natural follow-on once Automation's own
  Temporal migration lands).
- **RESOLVED**: Sales Inbox (spec §24) — outbound outreach status across all contacts.
  Still outbound-only (disclosed): no inbound reply tracking, since no real
  email/LinkedIn provider is connected.
- **RESOLVED**: Meeting Assistant (spec §26) — real `Meeting` CRUD plus AI
  Copilot-generated prep notes (retrieval-grounded, honest "no evidence" fallback). No
  real calendar sync (Google/Microsoft) — scheduling is manual entry.
- **RESOLVED**: Sales Intelligence (spec §29) — live-computed pipeline value by stage,
  win rate, average deal size, top ICP accounts, sequence completion rate.
- **RESOLVED (frontend)**: Lead/Contact/Opportunity standalone detail pages all exist,
  each showing real linked data (account/contact cross-links, outreach history).
- **VERIFIED (genuinely real, not a gap)**: `close_opportunity_won`'s idempotency guard,
  no-contact honest-skip fallback, and the account-detail security-review deal-blocker
  indicator — all independently re-confirmed live in this audit.

### Support (resolved 2026-07-30 — see SUPP-03/04/05/06/07 in the traceability matrix)

- **RESOLVED**: AI-grounded ticket response (spec §32) — `app.support.copilot.
  draft_ticket_reply` calls the real retrieval-grounded `ask_copilot`. A new
  `TicketMessage.status` (draft/sent) means an AI reply lands pending agent approval
  by default; it is only ever auto-sent when the org's new `AIAgentConfig` opts in
  AND the answer was genuinely grounded — an honest "no evidence" answer is never
  auto-sent regardless of that setting.
- **RESOLVED (frontend)**: Knowledge Base now has a frontend page (`/support/knowledge`)
  over the pre-existing complete backend.
- **RESOLVED**: Conversations — a real second, thread-first view (`/support/conversations`)
  over the same Ticket/TicketMessage data, filtered to the conversational channels
  (email/chat). Deliberately not a second backing table, consistent with ADR-0017's
  original reasoning that spec's Conversations and Tickets share near-identical shape.
- **RESOLVED**: AI Agent configuration (`AIAgentConfig`) — enable/disable and
  auto-send-grounded-replies toggles, real FE page at `/support/ai-agent`.
- **RESOLVED**: QA scoring (`TicketQAScore`) and a real CSAT/QA/resolution-time
  analytics dashboard (`app.support.analytics`, `GET /support/analytics`).

### Automation (resolved 2026-07-30 — see AUTO-03/04/05/06/07/08 in the traceability matrix)

- **RESOLVED (architectural)**: Automation execution is now Temporal-durable
  (`WorkflowRunWorkflow`), matching Knowledge's and Integrations' pattern — spec §61's
  "do not couple workflows directly to HTTP requests" no longer has an exception.
  `human_approval` now pauses on a real Temporal signal, woken automatically when the
  linked Approval is decided, rather than a polling loop.
- **RESOLVED**: all 24 of spec §39's named action types (plus 2 pre-existing extras) are
  real dispatch handlers, reusing existing cross-module services wherever one exists.
  `send_email`/`send_chat_message` honestly report they can't actually deliver (no SMTP
  provider in this build; Slack/Teams connectors are deliberately read-only-scoped) —
  never a fabricated "sent" result.
- **RESOLVED**: 11 of spec §38's 16 named trigger types genuinely fire real runs
  (`manual`, `api`, `webhook`, `schedule` via a real Temporal Schedule, plus 8 wired to
  real internal domain events: new/changed CRM leads and opportunity stages, new support
  tickets, new vendors, new employees, document uploads, failed control assessments,
  security alerts). The remaining 4 (`new_email`, `form_submission`, `database_event`,
  `new_regulatory_update`) have no real source system in this build and are honestly
  accepted-but-unwired, not silently faked.
- **RESOLVED**: `WorkflowVersion` immutable publish-history table.
- **RESOLVED (frontend)**: a real `@xyflow/react` visual drag-and-drop Workflow Builder
  (drag a step node to reorder it), a Workflow Templates gallery (3 real seeded
  templates, clone-to-new-draft), a Connections page (reuses Integrations' connections
  list rather than duplicating it), and a live Automation Analytics dashboard.
- **VERIFIED (genuinely real, not a gap)**: the `human_approval` pause/resume/reject
  mechanism — real behavioral test coverage for all three paths, now signal-based.

### Integrations

- **[FIXED 2026-07-30]** ~~Temporal-backed sync durability exists but lacks cursors /
  checkpointing / tombstone handling per spec §G2~~ — `IntegrationConnection.sync_cursor`
  and `SyncRun.cursor_used` (migration `3d13a5b8ba86`) now persist each provider's real
  pagination cursor across syncs (HubSpot `paging.next.after`, Slack
  `response_metadata.next_cursor`, Google Calendar `nextPageToken`, Microsoft Graph
  `@odata.nextLink`, GitHub `Link` header page number, Zendesk `after_cursor`; Salesforce
  honestly returns `next_cursor=None`, no pagination concept on its single identity call).
  `execute_sync_run` is now idempotent (an already-finalized `SyncRun` is returned
  unchanged rather than re-synced or double-advancing the cursor — spec §G2 replay
  safety), and `IntegrationSyncWorkflow`'s activity call now carries a bounded
  `RetryPolicy` (3 attempts, exponential backoff — spec §G2 retries/backoff). Live-
  verified via `test_sync_checkpoints_the_provider_cursor_across_runs` (two sequential
  syncs against the mock adapter's simulated two-page response prove the second sync
  resumes from the first's cursor) and
  `test_execute_sync_run_is_idempotent_for_an_already_finalized_run`. Still not covered,
  disclosed in `KNOWN_LIMITATIONS.md`: tombstones/deletions and rate-limit-specific
  detection (a 429 is an unhandled error like any other, not specially backed off) and
  partial-failure-within-a-page reporting.
- **[FIXED 2026-07-30]** ~~every connector category in spec §48 other than the 6 built
  OAuth providers (HubSpot, Google, Microsoft, GitHub, Slack, Salesforce) — Email,
  Marketing, Cloud, Identity (beyond the 6), Engineering, Documents, Accounting,
  Support-competitor connectors all have zero code. Note even "Email" isn't truly
  covered: Google/Microsoft's wired capability is Calendar-shaped, not Mail~~ — the
  Google adapter now also requests `gmail.readonly` and `drive.readonly` scopes and
  `sync()` fetches real Gmail messages and Drive files alongside Calendar events (Email
  and Documents categories); the Microsoft adapter now also requests `Mail.Read` and
  `sync()` fetches real Outlook messages alongside Calendar events (Email category); a
  new `ZendeskAdapter` (`app/integrations/adapters/zendesk.py`) covers the Customer
  Support category with a real OAuth2 flow against a configured subdomain
  (`ZENDESK_CLIENT_ID`/`SECRET`/`REDIRECT_URI`/`SUBDOMAIN`). Every spec §48 provider
  without an explicit "architecture" qualifier is now built except CRM's Pipedrive and
  Customer Support's Intercom, deliberately deferred alongside the explicitly-
  "architecture" providers (Zoho, Mailchimp, Freshdesk, Okta, Entra, Google Workspace,
  GitLab, Jira, Azure DevOps, Teams, SharePoint, OneDrive, Notion, QuickBooks, Xero,
  Stripe, ERP) and disclosed as architecture-ready-not-built in `KNOWN_LIMITATIONS.md` —
  each would follow the exact same `OAuthConnectorAdapter` Protocol shape already proven
  seven times over, adding no new pattern, and none can be tested end to end in this
  environment regardless (no real developer app exists for any of them). Cloud
  (AWS/Azure/GCP) is excluded under this build's AWS-deployment scope.
- **VERIFIED (genuinely real, not a gap)**: all 7 OAuth adapters use real provider URLs
  and real `httpx` calls; Fernet token encryption is real; the mock-fallback and
  "Not configured" UI states are honest, not fake-connected.

### Platform Foundation / RBAC / Multi-entity / Enterprise

- **[FIXED 2026-07-30]** ~~invitation flow, email verification flow, and MFA were all
  missing~~ — all three are now real and live-verified: `POST
  /organizations/current/invitations` (RBAC `org.users.manage`) + `/invite/[token]`
  accept page creates/attaches a user with the invited role and `Membership.invited_by`
  set; every signup triggers an email-verification token, `/verify-email/[token]`
  consumes it; `/settings/security` enrolls real TOTP (RFC 6238 via `pyotp`), login for
  an MFA-enabled user creates a session gated behind `/mfa-challenge` until a correct
  code is submitted. See `SPEC_TRACEABILITY_MATRIX.md` PLAT-13/14/15. WebAuthn/hardware
  keys remain unimplemented (TOTP only) and no real email provider is wired up (same
  log-only dev adapter as password reset).
- **[FIXED 2026-07-30]** ~~Onboarding Experience (spec §68) — the 10-step guided setup
  wizard and "Business AI Readiness" output — was entirely unbuilt~~ — a real 9-screen
  wizard now exists at `/onboarding` (steps 1-2 combined onto one screen; every other
  step maps 1:1), backed by a new `OnboardingProfile` model and resumable via
  `current_step`. Step 10's readiness output is computed live from real data on every
  request, never stored: Compliance (implemented/total Controls ratio), Security (the
  exact formula `GET /security/overview` uses, now shared via a new
  `app.secops.service.compute_security_score` extracted for this purpose), Sales
  Automation (reuses `compute_sales_intelligence`), Support Automation (a new, real
  AI-authored-and-auto-sent-vs-total-replies ratio), Process Automation (reuses
  `compute_workflow_analytics`) — plus named opportunities (compliance gaps, admins
  without MFA, ICP-fit accounts without a Lead, manual support-reply share, stalled
  workflow runs) computed the same way, never hardcoded example text. Signup now
  redirects to `/onboarding` instead of straight to the dashboard. See
  `SPEC_TRACEABILITY_MATRIX.md` PLAT-25. Building this surfaced and fixed a real,
  previously-untested cross-cutting bug: Pydantic v2 embeds the raw exception instance
  in `ctx` for any custom `@field_validator` that raises `ValueError`, which crashed
  `app.main`'s `RequestValidationError` handler (500 instead of the intended 422) for
  *every* such validator in this codebase, not just the new Onboarding one — fixed by
  running `exc.errors()` through FastAPI's `jsonable_encoder` first, with a regression
  test (`tests/test_validation_error_handling.py`) covering the pre-existing
  `WorkflowCreate.trigger_type` validator that had never been exercised by an invalid
  value in any prior test.
- **[FIXED 2026-07-30]** ~~4 of 16 seeded system roles had zero permission grants; zero
  `knowledge.*`/`copilot.*`/`ai.*` permission keys existed~~ — `executive`,
  `operations_manager`, and `employee` now carry scoped grants (approvals/tasks/
  automation as appropriate), `knowledge.documents.manage` and `ai.copilot.ask` were
  added and wired via `require_permission()` into the Knowledge and Copilot routers, and
  every role except `read_only` (deliberately zero-grant by design) was granted both.
  Live-verified: an `employee` can create tasks/knowledge bases/ask Copilot but gets 403
  on Sales; a `read_only` user gets 403 on both new permissions. See
  `SPEC_TRACEABILITY_MATRIX.md` PLAT-05/PLAT-06.
- **[FIXED 2026-07-30]** ~~`LegalEntity` and `Team` models exist with zero CRUD endpoints
  (no multi-entity support beyond the bare tables)~~ — spec §53 draws a real distinction
  between a "Support:" tier (Organization/Legal Entity/Business Unit/Team — meant to be
  built now) and a separate "Future:" tier (parent organization/subsidiaries/agency-
  consultant multi-client mode — genuinely deferred); the earlier framing of this finding
  conflated the two. The "Support:" tier is now real: full `LegalEntity`/`Team` CRUD
  (`POST/GET/PATCH/DELETE` under `/organizations/current/legal-entities` and `/teams`),
  RBAC-gated (`org.entities.manage`), audited, with archival instead of destructive delete
  (spec §73), an enforced exactly-one-default-entity invariant, and cross-tenant entity
  linking correctly rejected. A frontend section on `/settings/organization`. 9 tests;
  live-verified. See `SPEC_TRACEABILITY_MATRIX.md` PLAT-16.
- **AWS_EXCLUDED / not yet attempted, consistent with spec's own "Future:" deferral in
  §53**: parent organization / subsidiaries hierarchy, Agency/consultant multi-client mode
  (tracked as PLAT-17), regional hosting.
- **[FIXED 2026-07-30]** ~~SSO/SAML/SCIM — treated as a bundled Phase-10 deferral~~ — this
  conflated spec §59's plain "SSO" line item with the same line's "SAML architecture"/"SCIM
  architecture" items, which carry a real qualifier SSO itself doesn't. Real Sign-in-with-
  Google/Microsoft SSO now exists (`app/identity/sso.py`) — genuinely reuses the existing
  OAuth adapters' token-exchange call with a minimal identity-only scope, auto-provisions a
  new organization on first login exactly like normal signup, and honestly refuses (400) to
  start a flow for a provider that isn't really configured rather than fabricating a login.
  SAML and SCIM remain unbuilt, correctly disclosed as architecture-ready-not-built per
  their own spec qualifier — see `SPEC_TRACEABILITY_MATRIX.md` PLAT-18 and
  `KNOWN_LIMITATIONS.md`.
- **[FIXED 2026-07-30]** ~~Global Create button~~ — spec §72's "Create" nav button is real:
  `GlobalCreateButton` in the top nav (`apps/web/components/global-create-button.tsx`)
  fetches the current user's real permission keys (new `GET /organizations/current/
  my-permissions`, the same set `require_permission()` already enforces server-side) and
  shows only the entity types the user can actually create, each navigating to its owning
  module's real existing creation form. Covers 13 of spec §72's 14 named entities; "Report"
  is omitted until the Reporting module (PLAT-20) exists — not silently dropped, a
  disclosed sequencing dependency. See `SPEC_TRACEABILITY_MATRIX.md` PLAT-22.
- **[FIXED 2026-07-30]** ~~global Notification dispatch beyond in-app (`Notification.
  channel` is only ever constructed as `"in_app"` — grep confirmed across every
  construction site; no email/Slack/Teams/webhook dispatch adapter exists)~~ — spec §66's
  4 named channels are now real, where "real" is honestly bounded: `app.core.
  notifications.notify` is the single call site every module uses; Email dispatches
  through the same log-only dev adapter every other transactional email uses; Webhook does
  a real `httpx` POST to a configurable `Organization.notification_webhook_url`; Slack/
  Teams are disclosed as never-deliverable (Slack's OAuth scope is read-only, no Teams
  connector exists) rather than faked. Per-user channel opt-in via new
  `NotificationPreference` rows (migration `f2899856bd0f`), exposed on a new `/notifications`
  page (which also fixes the missing frontend for the pre-existing list/mark-read backend —
  finding A3) alongside a real inbox. 5 backend + 5 frontend tests; live-verified: a
  critical security incident's notification came back with
  `channels_delivered: ["in_app", "email"]` and a real log line for the email dispatch.
- **[FIXED 2026-07-30]** ~~standalone `/settings/roles` management UI (does not exist),
  `/settings/ai-providers` management UI (does not exist)~~ — both now exist. `/settings/
  roles`: a new `GET /organizations/current/roles` returns all 16 system roles with their
  real granted permission keys (joining `Role`/`RolePermission`/`Permission`); the frontend
  lists each role, expandable to show its exact permissions. Deliberately a reference view,
  not an editor — every role here is a system role shared across every organization in this
  deployment (`organization_id IS NULL`), and this build has no per-org custom roles, so
  there's nothing safe to let one org's admin edit. `/settings/ai-providers`: a new `GET
  /ai/providers` reports each spec §57 provider's real status — has-adapter, configured (a
  real env var is set), active (is the one `AI_PROVIDER` actually routes to). No API key is
  ever written to the database for any provider (same environment-variable-only convention
  every OAuth integration follows) — this is a status view, not a secrets form. Surfaced a
  previously-undocumented gap while building it: spec §57 lists "Azure OpenAI" without an
  "architecture" qualifier (only "Google" carries one), meaning a real Azure OpenAI adapter
  is technically in scope but has zero code — now disclosed honestly as `has_adapter: false`
  rather than silently absent from the page. 3 backend + 5 frontend tests; live-verified.
- **[FIXED 2026-07-30]** ~~Billing & entitlements~~ — spec §64's plan/entitlement layer is
  real, scoped to what the spec's own "Plans architecture:" qualifier actually covers (the
  qualifier marks the whole section architecture-tier for payment collection, but "Use
  entitlement service. Do not hard-code plan checks across UI" is a separately-stated real
  requirement, not deferred). New `app.billing` package: 4 seeded plans (Starter/Growth/
  Business/Enterprise) each with a real entitlements JSON blob covering 19 spec-named keys
  (numeric limits step up per tier, Enterprise uses `null` for unlimited; booleans such as
  `sso_enabled`/`api_enabled`/`trust_center_enabled` unlock at Growth+, `scim_enabled`/
  `custom_frameworks_enabled`/`advanced_reporting_enabled` at Business+, `data_residency_
  enabled` at Enterprise only — tier cutoffs are a disclosed judgment call, since the spec
  doesn't specify them). `GET /billing/plans`, `GET/PUT /billing/current` (org_admin only,
  audit-logged). Real enforcement wired at two concrete, regression-safe points rather than
  retrofitted everywhere at once: `max_users` blocks new invitations once an org's active
  member count reaches its plan's limit; `sso_enabled` blocks SSO login for an *existing*
  user on an *existing* org (new auto-provisioned orgs are deliberately exempt — a brand-new
  org can't fail its own SSO-created entitlement before it exists). A third candidate,
  gating `trust_center_enabled` on the Trust Center write endpoint, was implemented then
  reverted before commit: every pre-existing organization (including every already-shipped
  Trust Center test's freshly-signed-up org) defaults to Starter, and Starter's catalog has
  `trust_center_enabled: false`, which would have broken already-green tests for a feature
  that predates Billing entirely — left unwired pending a real backfill/grandfathering
  decision rather than silently regressing it. No Stripe/payment collection exists (correctly
  disclosed, matching the spec's own qualifier) — switching plans on `/settings/billing` is
  an immediate, free, self-service action, not a checkout flow. 6 backend + 3 frontend tests;
  live-verified. See `SPEC_TRACEABILITY_MATRIX.md` PLAT-19 and `KNOWN_LIMITATIONS.md`.
- **MISSING**: Reporting module.
- **MISSING (spec §57, surfaced while building the AI Providers status page above)**: Azure
  OpenAI has no adapter — the only spec §57 Model Gateway provider without an explicit
  "architecture"/"future" qualifier that still has zero implementation.
- **MISSING (Business Intelligence layer, spec §86-90)**: Business Process Discovery, AI
  Recommendation Engine, AI Daily Briefing, Business AI Memory, Business Rules Engine —
  none implemented.
- **PARTIAL**: Main Dashboard (`apps/web/app/(app)/page.tsx`) shows 2 of 4 metric tiles as
  real data (Open Tasks, Pending Approvals); the other 2 are honest hardcoded "Not
  available yet" strings, not fabricated numbers.
- **API gaps**: no pagination, no idempotency-key support, no rate-limiting visible
  anywhere in the 119-path OpenAPI surface (see `ROUTE_API_INVENTORY.md`).
- **MISSING**: no CI/CD pipeline configuration exists in the repository (no `.github/`
  directory) — separate from live AWS deployment (AWS-excluded), this is the CI
  configuration itself, which is in-scope per this audit's instructions.

---

## C. AWS-excluded (explicitly out of scope for this audit, listed for completeness only)

- Creating billable AWS resources; deploying containers to ECS; provisioning
  RDS/ElastiCache/CloudFront/WAF/Route53/other live AWS services; production AWS
  backup/recovery execution; live AWS CI/CD deployment validation (spec sections A-N).
