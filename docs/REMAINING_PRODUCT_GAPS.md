# Remaining Product Gaps

Companion to [`PRODUCT_COMPLETENESS_AUDIT.md`](PRODUCT_COMPLETENESS_AUDIT.md) and
[`SPEC_TRACEABILITY_MATRIX.md`](SPEC_TRACEABILITY_MATRIX.md). This document lists every
requirement that is not VERIFIED, with the exact missing work. AWS-excluded items are
listed in their own section at the end for completeness, not because they need action now.

Audit date: 2026-07-30. Verified against commit `e5fa62d` (working tree clean, no product
code changed by this audit).

---

## A. Headline cross-cutting findings

These are not single-module gaps; they affect how to read every other finding in this
document.

### A1. Audit-event `object_id` is written as the literal string `"None"` for ~8 of ~17 "created" event types

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

**Exact missing work**: add `await db.flush()` before every `record_event(...,
object_id=str(newly_added_object.id))` call for the 8 confirmed-broken action types above;
add a regression test asserting `object_id` is a well-formed UUID (not the string
`"None"`) for each "created" audit action.

**Impact**: does not affect security (the row IS written, tenant-scoped correctly,
append-only) — but breaks the ability to correlate an audit-log entry back to the specific
resource it concerns for these 8 event types, which is a real defect against the audit
trail requirement (spec §57, §93).

### A2. `docs/KNOWN_LIMITATIONS.md` overstates completeness of 3 of spec §69's 5 named cross-module scenarios

`KNOWN_LIMITATIONS.md` states "four of the five [§69] scenarios are now fully
implemented." Direct comparison against the spec's literal step lists (§69, lines
6599-6760) shows:

| Scenario | Spec steps | Steps actually implemented | 
|---|---|---|
| Enterprise Sales Security Review | 10 | 10 (minus one sub-step: "Sales Copilot drafts follow-up") — genuinely near-complete |
| New AI Tool Adoption | 9 | 4 — already correctly flagged as partial in KNOWN_LIMITATIONS.md |
| Security Incident Response | 9 | 3 (create incident → link risk → create response task) |
| New Customer Onboarding | 8 | 2 (create Customer → create onboarding Task; no welcome email, billing update, or scheduled check-in beyond the one task) |
| Support Upsell Signal | 4 | 2 (flag ticket → create Lead; no Sales Copilot involvement, no notification to account owner) |

What **is** built for Security Incident, New Customer, and Support Upsell Signal is real,
tested, non-fake code (confirmed both by subagent code reading and, for New Customer, by
this audit's own live `close_opportunity_won` idempotency test) — it is a genuine subset
of each scenario, not vaporware. The gap is specifically that the product doc's own
completeness claim ("fully implemented") is inaccurate relative to the spec's literal text
for 3 of the 4 scenarios it claims are done.

**Exact missing work**: correct `docs/KNOWN_LIMITATIONS.md`'s claim, and either (a)
implement the remaining named steps (welcome email, billing update, scheduled check-in,
full incident timeline/communication steps, Sales Copilot follow-up drafting, upsell
notification to account owner) or (b) explicitly document them as deferred per-step,
matching the honesty standard the rest of that document otherwise holds to.

### A3. `docs/ROUTES_AND_SCREENS.md` lists 8 routes as `[~]`/scaffolded that do not exist in the actual build

Confirmed via a fresh `npm run build` route table (this audit) cross-checked against the
doc: `/onboarding/company`, `/onboarding/goals`, `/notifications`, `/settings/roles`,
`/settings/ai-providers`, `/invite/[token]`, `/verify-email/[token]`, and the MFA-challenge
screen all appear in the doc with `[~]`/`[ ]` status implying at least a placeholder
exists, but none produced a route in the Next.js build output (33 real routes, listed in
`ROUTE_API_INVENTORY.md`). This is documentation/code drift, not a product gap per se, but
it means the doc cannot be trusted as a completeness source — which is exactly why this
audit re-derived route status from the live build rather than from the doc.

**Exact missing work**: update `ROUTES_AND_SCREENS.md` to `[ ]` for all 8, or build the
pages.

### A4. `apps/api/app/audit/models.py` docstring claims a DB-level `REVOKE UPDATE/DELETE` on `audit_events` that does not exist

Grepped every one of the 21 migration files: zero `REVOKE` statements anywhere.
Append-only-ness of the audit trail is enforced only by application code convention (no
`UPDATE`/`DELETE` calls against `AuditEvent` anywhere in the service layer), not by a
database privilege. A superuser or a future buggy migration could mutate history
undetected.

**Exact missing work**: either add the migration that actually revokes `UPDATE`/`DELETE`
on `audit_events` from the application's database role, or correct the docstring to not
claim a protection that isn't there.

---

## B. Per-module gaps

### Knowledge & RAG

- **MISSING**: Organization Knowledge Graph (spec §10) — entity/relationship extraction
  pipeline (spec §11 steps) absent entirely; no acknowledgment in `docs/DECISIONS.md`.
- **PARTIAL**: XLSX and HTML are claimed-supported ingestion formats with no actual
  extractor code (`apps/api/app/knowledge/parsing.py`) — unlike PPTX/OCR, which are
  correctly marked architecture-only, this gap is undisclosed.
- **MISSING**: Global/unified search across modules (spec §47) — not implemented; sidebar
  "Global search" entry routes to the honest coming-soon state.
- **PARTIAL**: Reranking is unimplemented for both the Anthropic and OpenAI adapters
  (`apps/api/app/ai/adapters/{anthropic,openai}.py`); the gateway catches
  `NotImplementedError` gracefully and continues without reranking — honest, but the
  retrieval quality feature itself does not exist.
- **PARTIAL**: `generate_structured` is defined on the model-adapter Protocol and every
  adapter, but is never called by any domain service (dead plumbing).

### Compliance / GDPR / EU AI Act / AI Governance

- **PARTIAL**: Only 3 of 8 named frameworks (GDPR, EU AI Act, ISO 27001) have seeded
  catalog content; the remaining 5 have no requirement/control catalog.
- **MISSING (frontend)**: `Policy` has a complete backend (model, service, API, RBAC
  permission, audit event) but zero frontend page.
- **MISSING (frontend)**: standalone Evidence Library page, framework-specific
  (GDPR/EU-AI-Act individual) dashboards, standalone Data Inventory/RoPA detail view
  (list-only today), Regulatory Intelligence.
- **MISSING**: spec §91 "Compliance as Governance Layer" — synchronous pre-action
  permission checks **from** other modules **into** Compliance — has no implementation;
  only the inverse pattern (Compliance reacting to events from other modules) exists.
- **CONFIRMED (not a gap)**: the Trust Center public endpoint
  (`apps/api/app/routers/trust_center.py`) genuinely has no `OrgContext` dependency —
  correctly, deliberately unauthenticated per spec B4.

### Security

- **MISSING**: Cloud Security (spec §15) and Identity Security (spec §16) — entirely
  unbuilt beyond a free-text category tag on `SecurityFinding`.
- **MISSING (frontend)**: Security Overview dashboard (spec §13) — actual frontend is 4
  flat CRUD lists, not the dashboard described.
- **PARTIAL**: `SecurityIncident` has no Timeline / Affected-Assets / Evidence /
  Communication / Root-Cause / Lessons-Learned fields — just a status enum plus 2 FK
  links (to a Risk and a Task).
- **MISSING (tests + audit)**: `SecurityAlert` create/update have zero audit events and
  zero test coverage.
- **MISSING (frontend)**: standalone Asset Detail page, Alert Detail page, Security
  Policies page.

### Sales

- **MISSING**: ICP scoring algorithm — `icp_score` is a bare column, only ever set via a
  hardcoded seed demo value (87.5); no scoring logic exists.
- **MISSING**: Lead Finder, Lead/Contact/Opportunity detail pages, Sequences/Sequence
  Builder, Campaigns, Sales Inbox, Meetings, Sales Intelligence — all entirely absent
  beyond bare CRUD (Sequences has a single manual-send `OutreachMessage`, no automated
  cadence).
- **VERIFIED (genuinely real, not a gap)**: `close_opportunity_won`'s idempotency guard,
  no-contact honest-skip fallback, and the account-detail security-review deal-blocker
  indicator — all independently re-confirmed live in this audit.

### Support

- **MISSING**: zero AI involvement anywhere in the module — no call into
  `app/ai/copilot.py` or `app/knowledge/retrieval.py` from any support code path (grounded
  ticket response, spec §32, does not exist).
- **MISSING (frontend)**: Knowledge Base has a working backend
  (`support_knowledge_articles`) but no frontend page.
- **MISSING**: Conversations (separate from Tickets), AI Agent configuration, QA scoring
  dashboard, CSAT reporting/analytics beyond the raw `POST /support/csat` endpoint.

### Automation

- **PARTIAL**: only 3 of ~24 spec'd action types and 2 of ~16 spec'd trigger types are
  executable.
- **ARCHITECTURAL GAP**: Automation executes fully synchronously inside the HTTP
  request/response cycle with zero Temporal usage, directly contradicting spec §61 ("do
  not couple workflows directly to HTTP requests") — Knowledge and Integrations both
  correctly use Temporal; Automation does not.
- **MISSING**: `WorkflowVersion` / immutable publish-history table.
- **MISSING (frontend)**: visual drag-and-drop Workflow Builder (React Flow), Workflow
  Templates gallery, dedicated Connections page, automation analytics dashboard.
- **VERIFIED (genuinely real, not a gap)**: the `human_approval` pause/resume/reject
  mechanism — real behavioral test coverage for all three paths.

### Integrations

- **MISSING**: every connector category in spec §48 other than the 6 built OAuth
  providers (HubSpot, Google, Microsoft, GitHub, Slack, Salesforce) — Email, Marketing,
  Cloud, Identity (beyond the 6), Engineering, Documents, Accounting, Support-competitor
  connectors all have zero code. Note even "Email" isn't truly covered: Google/Microsoft's
  wired capability is Calendar-shaped, not Mail.
- **PARTIAL**: Temporal-backed sync durability exists but lacks cursors / checkpointing /
  tombstone handling per spec §G2.
- **VERIFIED (genuinely real, not a gap)**: all 6 OAuth adapters use real provider URLs
  and real `httpx` calls; Fernet token encryption is real; the mock-fallback and
  "Not configured" UI states are honest, not fake-connected.

### Platform Foundation / RBAC / Multi-entity / Enterprise

- **MISSING**: invitation flow (`/invite/[token]` has no page or API), email verification
  flow (`/verify-email/[token]` has no page or API — and is never triggered anywhere in
  the backend), MFA (schema-only: no challenge screen, no TOTP/WebAuthn enrollment code).
- **PARTIAL/INERT**: 4 of 16 seeded system roles (`executive`, `operations_manager`,
  `employee`, `read_only`) have zero permission grants in
  `ROLE_PERMISSION_GRANTS` — they exist and can be assigned, but carry no capability
  beyond whatever RBAC's default-deny leaves them (confirmed live in this audit:
  `read_only` correctly gets 403 on writes and 200 on reads, so the *enforcement*
  mechanism works — the gap is that most business roles have never had scoped
  permissions written for them beyond the modules already granting them).
  Zero `knowledge.*` / `copilot.*` / `ai.*` permission keys exist in `PERMISSIONS` at all
  — Knowledge and Copilot access is not RBAC-gated, only tenant-membership-gated.
- **MISSING**: `LegalEntity` and `Team` models exist with zero CRUD endpoints (no
  multi-entity support beyond the bare tables) — consistent with spec §53's own "Future:"
  marker and §79's "Phase 10" placement, i.e. not yet attempted, not attempted-and-broken.
- **AWS_EXCLUDED / not yet attempted, consistent with spec's own deferral**: SSO/SAML/SCIM
  (spec §59, explicitly Phase 10), Agency/consultant multi-client mode (spec §53 "Future"),
  regional hosting.
- **MISSING**: Billing & entitlements, Reporting module, global Notification dispatch
  beyond in-app (`Notification.channel` is only ever constructed as `"in_app"` — grep
  confirmed across every construction site; no email/Slack/Teams/webhook dispatch adapter
  exists), Global Create button, standalone `/settings/roles` management UI (read-only
  view only), `/settings/ai-providers` management UI (status display only, no
  configuration UI).
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
