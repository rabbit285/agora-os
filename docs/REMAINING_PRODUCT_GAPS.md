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
- **[FIXED 2026-08-04]** ~~Reporting module~~ — spec §65's 14 named report types and 5
  export options are real. Every report is computed from this org's own live data: 8 types
  reuse an existing module's own dashboard/analytics function outright (Executive/Board ->
  Onboarding's readiness score, Security Posture -> the Security Overview aggregate — now
  extracted into `secops.service.get_security_overview` so that page and this report share
  one implementation, Sales Performance/Pipeline -> Sales Intelligence, Support Performance
  -> Support Analytics, Automation ROI -> Automation Analytics); the 6 with no prior
  aggregate (Compliance, GDPR, EU AI Act, AI Inventory, Risk, Vendor, Audit Evidence Pack)
  query the relevant Compliance tables directly. Rendered into genuinely openable files via
  real libraries (`reportlab`, `python-docx`, `openpyxl`, stdlib `csv`) — verified by
  downloading real PDF/DOCX/XLSX files and checking their actual format signatures, not just
  a 201 response. Spec's 5th export option, "Secure link," is realized as the same signed-
  URL download mechanism (`presign_download`, the existing `app.core.storage` primitive)
  every report uses to be fetched at all — disclosed as one honest delivery mechanism for
  all 4 formats rather than a distinct 5th format, since no report is ever inlined or
  emailed. New `/reports` page: generate-report form, past-reports list with status, secure
  download link. Wired into Global Create's "Report" option, previously deferred pending
  this module (see PLAT-22 above). 11 backend + 3 frontend tests — including one that
  creates a real Risk, generates a Risk Report, and asserts the risk's actual title appears
  in the downloaded CSV bytes; live-verified: all 14 report types × 4 formats generated
  successfully against both an empty org and the seeded demo org (56/56, zero failures).
  Automation ROI honestly reports real run volume/success rate rather than fabricating a
  dollar figure, since this build collects no per-workflow cost basis. See
  `SPEC_TRACEABILITY_MATRIX.md` PLAT-20.
- **MISSING (spec §57, surfaced while building the AI Providers status page above)**: Azure
  OpenAI has no adapter — the only spec §57 Model Gateway provider without an explicit
  "architecture"/"future" qualifier that still has zero implementation.
- **Business Intelligence layer (spec §86-90)**: **BIZ-01 Business Process Discovery is a
  spec-native deferral, not a gap** — §86 opens with "Long-term capability:" attached to
  the section's entire core mechanism, unlike §87-90, none of which carry any qualifier
  (see `SPEC_TRACEABILITY_MATRIX.md` BIZ-01).
- **[FIXED 2026-08-04]** ~~BIZ-02 AI Recommendation Engine — not implemented~~ — 5 real
  generators (compliance control gaps, critical/high security findings, ICP-fit sales
  accounts with no lead, automation failure-rate, support CSAT trend) scan this org's own
  data and only fire on a genuine, disclosed threshold; every recommendation names the
  exact source rows it came from, and `estimated_value` is left honestly unset except for
  the one case with a real historical basis to derive it from. Dismissing/actioning a
  recommendation is permanent — the next refresh never resurrects it. New `/recommendations`
  page. 6 backend + 3 frontend tests; live-verified against a fresh org and the seeded demo
  org (a live grammar bug found during verification — "1 account have" — was fixed on the
  spot). See `SPEC_TRACEABILITY_MATRIX.md` BIZ-02.
- **[FIXED 2026-08-04]** ~~BIZ-03 AI Daily Briefing — not implemented~~ — one real briefing
  per organization per calendar day (generated on first request, held stable for the rest
  of the day — spec's "daily" semantic). All 5 spec-named sections (Urgent/Revenue/
  Customers/Risk/Operations) are computed from real rows: open critical security alerts,
  real open-pipeline value, a real week-over-week ticket volume delta, DSARs due within 3
  days, workflow failures in the last 24h — never the spec's own literal example numbers,
  and each item links into the module that owns it. The "AI suggestion" line reuses BIZ-02's
  Recommendation Engine outright rather than a second generator. New `/briefing` page. 5
  backend + 2 frontend tests; live-verified against the seeded demo org. See
  `SPEC_TRACEABILITY_MATRIX.md` BIZ-03.
- **[FIXED 2026-08-04]** ~~BIZ-04 Business AI Memory — not implemented~~ — real structured
  memory across all 7 spec-named categories, every entry carrying real `provenance_type`/
  `provenance_id` rather than raw conversation history treated as ground truth. One real
  automatic hook (publishing a Policy creates a deduplicated `policy`-type entry); every
  other category is administrator-curated by design, matching spec's own "Create
  organization memory carefully" caution against indiscriminate automatic capture.
  Correct/delete are real, permission-gated (new `business_memory.manage`, narrower than
  the cross-cutting BIZ-02/03 permission since this defines organizational ground truth),
  and audit-logged with real before/after content; deletion is a soft flip, not a row
  removal. New `/settings/memory` page. 7 backend + 3 frontend tests; live-verified. **Not
  yet done, disclosed**: wiring this memory into AI Copilot's own retrieval/grounding
  context — the storage/provenance/correction subsystem is complete, but wasn't threaded
  into `app.ai.copilot`'s already-tested prompt-construction path in this pass. See
  `SPEC_TRACEABILITY_MATRIX.md` BIZ-04.
- **[FIXED 2026-08-04]** ~~BIZ-05 Business Rules Engine — not implemented~~ — a real
  structured condition (field/operator/value against a real event's payload) plus a real
  action (require an Approval, or notify every member holding a role) — genuinely separate
  from AI prompts, per spec's own words. Evaluation reuses `app.automation.triggers.
  dispatch_event` outright — the exact real event-dispatch point Automation workflows
  already use — so every existing event source automatically evaluates Business Rules too,
  with no second parallel hook system; one new real event source (AI system registration)
  was added to directly support spec's own "High-risk AI requires DPO + AI Governance
  approval" example. Both of spec's own literal examples were live-verified word-for-word
  against the running stack: a critical security alert notifying the security manager role,
  and a high-risk AI system registration creating a real pending Approval. New
  `/settings/business-rules` page. 7 backend + 3 frontend tests. **Disclosed scope**:
  "Refunds over €500" and "Critical vendors require annual reassessment" remain valid,
  configurable trigger types with no real event source yet — no Refund/payment concept
  exists anywhere in this build (Billing's own "Plans architecture" qualifier), and "annual"
  is a time-based condition this build's event-driven dispatch doesn't evaluate — the same
  honest precedent Automation itself already established for 4 of its 16 named trigger
  types with no real source. See `SPEC_TRACEABILITY_MATRIX.md` BIZ-05.
- **[FIXED 2026-08-04]** ~~Data export/deletion execution capability — spec §B3/§B5
  "support export and deletion" was previously only DSAR *status tracking* (COMP-09):
  "fulfilled" flipped an enum with no real data operation behind it~~ — real execution now
  exists as new PLAT-26. **Export**: `GET /organizations/current/data-export?format=` reuses
  the Reporting module's own rendering pipeline outright (no second export implementation)
  to bundle 20 real sections of this organization's own data — members, compliance, security,
  sales, support, knowledge, automation, business memory, business rules — into a genuine
  downloadable PDF/DOCX/XLSX/CSV. **Deletion**: a real, two-step, org-name-confirmed flow —
  `POST .../deletion-request` sets a visible, cancellable, audited precursor state;
  `POST .../deletion-request/execute` performs a genuine, irreversible cascade delete across
  every one of the 70+ organization-scoped tables in one transaction (PostgreSQL's
  `session_replication_role = replica`, rather than hand-ordering every table by FK
  dependency), including that organization's own `audit_events` — a real erasure has to erase
  its own audit trail too, not leave it permanently stuck. A schema-drift safety check fails
  loudly rather than silently under-deleting if a future migration adds an org-scoped table
  this doesn't know about yet. `User` accounts are deliberately never deleted (a login
  identity is separate from organization membership everywhere in this codebase). New
  `/settings/data-management` page (the exact spec §67 screen name). 8 backend + 4 frontend
  tests; live-verified against real Postgres — created a test org, deleted it, confirmed via
  direct `psql` every row (including its own audit trail) was actually gone; downloaded and
  confirmed a real 16.6KB XLSX export. Two real bugs found and fixed during verification:
  SQLite can't bind a raw `uuid.UUID` parameter in raw SQL (and separately, a dashed
  `str(uuid)` silently matched zero rows against SQLAlchemy's actual non-dashed storage
  format — both fixed by using `.hex`), and stale ORM identity-map objects after raw-SQL
  bulk deletes (fixed with `db.expire_all()`). **Disclosed scope**: no automated scheduled
  purge after a grace window exists — execution is explicit (organization-name-confirmed),
  not automatically triggered by a Temporal schedule after N days. See
  `SPEC_TRACEABILITY_MATRIX.md` PLAT-26 and the clarified COMP-09.
- **[FIXED 2026-08-04]** ~~Main Dashboard shows 2 of 4 metric tiles as real data (Open
  Tasks, Pending Approvals); the other 2 are honest hardcoded "Not available yet"
  strings~~ — all 4 are now real. Compliance Health fetches `GET /compliance/controls`
  and computes the same implemented/total percentage Onboarding's readiness score already
  uses (`app.onboarding.service._compliance_percent`'s formula, so the two numbers never
  independently drift), with an honest "No controls yet" state instead of a misleading 0%
  for a brand-new org. Security Posture fetches the existing `GET /security/overview` and
  shows its real `security_score` (e.g. "80/100"). Both endpoints only require org
  membership (no elevated permission), matching the Dashboard's own visibility to every
  role. 2 new frontend tests; live-verified against the seeded demo org (1 of 2 controls
  implemented -> 50%, security score 80/100, both matching the live API response).
- **[FIXED 2026-08-04, scoped]** ~~API gaps: no pagination, no idempotency-key support, no
  rate-limiting visible anywhere in the API surface~~ — spec §E7 "API Quality" is a real,
  unqualified cross-cutting requirement; 3 of its items were genuine gaps (the rest —
  consistent error envelope, request/correlation IDs, OpenAPI docs, input limits via
  Pydantic field constraints, permission failures returning 404 rather than leaking
  existence — were already real). **Rate limiting**: real, Redis-backed, per-client-IP
  fixed-window limiter (`app.core.rate_limit`), applied globally to every request via
  middleware — full API-wide coverage, not a token endpoint. **Idempotency for side
  effects**: real, Redis-backed `Idempotency-Key` header support (`app.core.idempotency`),
  also global middleware — opt-in (a request without the header behaves exactly as before;
  a retried request with the same key, from the same session, replays the cached response
  instead of re-executing the side effect) so it never changes behavior for the hundreds of
  existing call sites that don't send it. Both fail open on a Redis outage (availability of
  the rest of the API matters more than perfect enforcement of either control) and are
  positioned so CORS stays outermost, so a 429 or a replayed response still carries CORS
  headers instead of surfacing to a browser as an opaque CORS failure. **Pagination +
  sorting**: a real, additive `limit`/`offset` mechanism (`app.core.pagination`) — omitting
  both preserves every list endpoint's existing bare-array response shape exactly, so no
  frontend caller needed to change; passing them applies a real SQL `LIMIT`/`OFFSET` and
  reports the true row count via an `X-Total-Count` header. Applied to 18 of the API's list
  endpoints — the ones most likely to grow unbounded in real usage: Compliance (controls,
  evidence, risks, vendors, audits), Sales (accounts, contacts, leads, opportunities),
  Support (customers, tickets), Security (assets, findings, alerts), Automation (runs),
  Notifications, Knowledge (documents), Reporting. Deliberately not applied to the
  remaining ~42 list endpoints, most of which are small, inherently-bounded catalogs
  (Frameworks, Plans, Roles, Permissions, AI Provider status, Report types) or child
  collections scoped by a parent (a Ticket's messages, a Workflow's versions) rather than
  organization-wide unbounded growth — a disclosed scope boundary, not a silent gap. 8
  backend tests (5 for rate-limit/idempotency, 3 for pagination); live-verified against the
  running dev stack (a real 429 with `Retry-After` once the per-minute cap is hit, a real
  replayed response with `Idempotency-Replayed: true` and no duplicate row created, real
  `X-Total-Count` headers and page slicing on `/compliance/controls`).
- **[FIXED 2026-08-04]** ~~No CI/CD pipeline configuration exists in the repository (no
  `.github/` directory)~~ — a real `.github/workflows/ci.yml` now runs on every push to
  `main` and every pull request. **Backend job**: builds the real `api` image, brings up
  Postgres/Redis/MinIO via the exact same `infra/docker/docker-compose.yml` used in local
  dev (no separate CI-only service definitions to drift from what's actually run day to
  day), applies migrations via a one-off container *before* the long-running `api` service
  starts (its own startup queries real tables that don't exist yet on a fresh CI volume —
  this exact ordering was dry-run-verified against a throwaway compose project to confirm
  the naive "just docker compose up" ordering crash-loops instead), then runs `alembic
  check` (schema-drift detection), the full `pytest` suite, `mypy --strict`, and `ruff`.
  **Frontend job**: `npm ci`, `tsc --noEmit`, `eslint`, `vitest run`, and a real production
  `next build` — the same 4 checks this session's own workflow ran by hand after every
  cluster. This is CI configuration only (AWS deployment itself remains AWS-excluded); no
  CD/deploy step exists since there's no AWS target to deploy to in this build.
- **[FIXED 2026-08-04]** ~~No real end-to-end suite — only unit/component tests exist, none
  of which drive a real browser against the real running stack~~ — a real Playwright suite
  (`apps/web/e2e/`, 18 tests across 5 spec files) now drives an actual Chromium browser
  against the actual running dev stack (real Postgres, real API, real Next.js dev server —
  no mocked network layer anywhere in these specs). Coverage: signup/login/wrong-password
  (`auth.spec.ts`); the full 9-screen onboarding wizard including its real, live-computed
  Business AI Readiness screen and resume-after-reload (`onboarding.spec.ts`); a
  create-record journey through Tasks, Compliance, Security, Sales, Support (customer then
  ticket), and Automation (`modules.spec.ts`); Business Rules create/deactivate, Business
  Memory manual-entry creation, a real compliance-gap-to-Recommendation journey, and all 5
  spec §88 Daily Briefing sections rendering real data (`business-intelligence.spec.ts`);
  and Billing plan-switching plus Data Management's real export download and real two-step
  name-confirmed organization deletion ending in an actual forced logout
  (`settings.spec.ts`). Runs from the Windows host against the docker-compose host-mapped
  port (the web container's slim image has no Chromium system dependencies), and now also
  runs in CI as a fifth `e2e` job (`.github/workflows/ci.yml`) against the same full stack
  brought up via the same compose file, uploading the Playwright HTML report as a build
  artifact on any failure. One real infra gotcha found and fixed during this work: adding
  new page routes to an already-running `next dev` container doesn't always get picked up
  by its route manifest — a container restart was required before 5 new routes
  (`/recommendations`, `/briefing`, `/settings/business-rules`, `/settings/memory`,
  `/settings/data-management`) stopped 404ing; documented here since it could otherwise
  look like a real app bug during future local verification. Playwright's `workers` is
  pinned to `1` (not just serial within a file) — running multiple specs concurrently
  against a single dev-mode server caused compile/hydration contention where a click could
  race ahead of React attaching its handlers, observed as a signup falling through to a
  native HTML form GET submission instead of the client-side handler; this is a dev-server
  concurrency artifact, not a product bug, and does not reproduce running serially or
  against a production build.

---

## C. AWS-excluded (explicitly out of scope for this audit, listed for completeness only)

- Creating billable AWS resources; deploying containers to ECS; provisioning
  RDS/ElastiCache/CloudFront/WAF/Route53/other live AWS services; production AWS
  backup/recovery execution; live AWS CI/CD deployment validation (spec sections A-N).
