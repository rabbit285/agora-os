# Known Limitations

Honest accounting of what Phase 1 does **not** do yet, per the spec's
"Definition of Done" (§83) and "No Fake Features" (§82) rules. This is not
a bug list — it's scope not yet built, tracked here so nothing is silently
implied to work.

## Product scope

- **Compliance**, **Security**, **Sales**, **Support**, and
  **Automation** — all five primary product modules — have their core
  backbones (see below) but not their larger sub-features. See
  `docs/IMPLEMENTATION_PLAN.md` for the phase order.
- **Integrations (Phase 9)**: only a generic inbound Webhook connector is
  implemented — see the dedicated bullet below. No CRM/Email/Cloud/
  Identity/Engineering/Communication/Documents/Accounting connectors
  exist (spec §48); all need real third-party OAuth apps or API keys this
  environment doesn't have.
- **Compliance**: an AI System Inventory (`AISystem`/`AIAssessment`, EU AI
  Act risk tiers) now exists — registering a high/unacceptable-risk system
  auto-creates a real Approval and gates its `approved` status on that
  Approval being granted (ADR-0027) — but no AI incidents (ai_incidents),
  no audits (auditor portal), no privacy workflows (RoPA/DPIA/DSAR), no
  vendor risk, questionnaires, or Trust Center.
- **Security**: no cloud provider connectors (AWS/Azure/GCP), no identity
  provider connectors (Okta/Entra/Google Workspace), no vulnerability
  scanner ingestion, no incident timeline/evidence/playbook sub-objects —
  the incident *workspace* has a status workflow, but not the richer
  structure spec §19 describes (Timeline, Affected Assets, Evidence,
  Communication, Root Cause, Lessons Learned tabs). These realistically
  need the connector SDK (Phase 9) to do properly rather than one-off
  per-provider integrations.
- **Sales**: outreach "sending" doesn't call a real email/LinkedIn
  provider — it only transitions the message's own status (`sent` or
  `blocked`), gated by a genuine compliance check
  (`Contact.do_not_contact`), not a stub of one. No sequences/campaigns
  (multi-step automation), no lead-finding/enrichment (needs external
  data connectors), no meetings or sales inbox. The suppression check
  itself is a single boolean, not the fuller jurisdiction/consent/
  marketing-basis engine spec §91 describes (ADR-0019). A `closed_won`
  Opportunity creates a real Support Customer + onboarding Task
  (ADR-0025), but not a real welcome email or a billing/accounting
  system update — no email provider or accounting connector exists yet.
  If the account has no Contact yet, onboarding is honestly skipped, not
  faked with a placeholder email.
- **Support**: tickets have a `channel` field (`email`/`chat`/`api`) but
  no real channel connectors — there's no inbound email parsing or chat
  widget, only the API. No SLA policies/timers, no QA review scoring, no
  AI-drafted replies or confidence-gated auto-resolution (spec §32 — the
  Copilot/retrieval infrastructure exists from Phase 2 but nothing wires
  Support into it yet), no knowledge-gap detection or FAQ generation. The
  security-category cross-module hook creates a `SecurityAlert` (Security's
  triage inbox), not a full `SecurityIncident` — see ADR-0020 for why.
  Flagging a ticket as an upsell signal creates a real Sales Lead and
  notifies the linked account's owner (or the flagging agent if there's no
  linked Sales Account or no account owner), but does not auto-create an
  Opportunity — that conversion is left to a human sales rep (ADR-0022).
- **Cross-Module Intelligence (Phase 8)**: three of spec §69's five
  named cross-module scenarios are fully implemented ("Support Upsell
  Signal", the "Security Incident" chain, and "New Customer"), plus a
  partial fourth: "New AI Tool Adoption" now has its register→Approval
  gate hook (ADR-0027, counted under Compliance above), but not the rest
  of that scenario's chain — vendor security questionnaire, Privacy/DPA
  review, approved-use policy publication. The remaining scenario
  (Enterprise Sales Security Review) is not started — it needs customer
  questionnaires, which don't exist yet. No AI daily briefing, business
  process discovery, AI recommendation engine, or organization memory
  exist either. The Security Incident chain's Task/Notification are only
  created for `critical`-severity incidents, same gate as the
  pre-existing Risk link — there's no separate configurable threshold.
- **Automation**: only three step types actually execute
  (`create_task`, `send_notification`, `human_approval`) out of spec §37's
  much larger vocabulary (Condition, Delay, Loop, Data Transform, Webhook,
  Subworkflow, AI Step are not implemented). `manual` and `webhook`
  triggers work (the latter added in Phase 9 — see below); email,
  CRM-stage-change, and schedule triggers (spec §38) still need
  connectors that don't exist. There's no visual drag-and-drop builder —
  workflows are defined as a JSON-backed ordered step list via a plain
  form. No templates, no automation analytics (spec §43), no
  retry/backoff policies beyond "a failed step fails the run." Workflow
  governance is real but simple: a workflow's steps can only be edited
  while `status = draft`; there's no parallel draft/published dual-version
  editing of an already-active workflow (spec §41's fuller versioning
  model).
- **Integrations**: `IntegrationConnection.connector_key` supports
  `"webhook"` and `"hubspot"` — every other spec §48 category (CRM
  beyond HubSpot, Email, Marketing, Customer Support, Cloud, Identity,
  Engineering, Communication, Documents, Accounting) needs a real
  third-party OAuth app or API key this environment doesn't have, and
  none are stubbed as "connected" (spec §82) — the provider catalog
  endpoint reports `configured: bool` honestly, and HubSpot itself shows
  "Not configured" without real `HUBSPOT_CLIENT_ID`/`HUBSPOT_CLIENT_SECRET`.
  A mock OAuth adapter (mirroring the AI gateway's `DemoAdapter`) lets the
  full authorize→callback→connected→sync→disconnect flow be exercised for
  testing/demo purposes even without real credentials — this is what the
  automated test suite runs against, and the demo seed data deliberately
  does *not* create a "connected" HubSpot row, to avoid any appearance of
  a fabricated live connection. Stored OAuth tokens are encrypted at rest
  (Fernet, `app/core/crypto.py`), but the encryption key falls back to one
  derived from `SECRET_KEY` when `TOKEN_ENCRYPTION_KEY` is unset — fine
  for dev/test, but a real deployment must set its own key (rotating
  `SECRET_KEY` would otherwise silently break every stored token). A
  webhook connection's `webhook_secret` is still returned in plain text by
  the API to whoever can read the connection (session-authenticated,
  tenant-isolated, but not masked/rotatable) — no secrets vault exists
  yet. `subscribe()`, `execute_action()`, and `collect_evidence()` from
  spec §49's full Connector Contract aren't implemented — this slice only
  needed authorize/token-exchange/refresh/health/sync/revoke. "Sync now"
  (`run_sync`) executes synchronously inline, not as a durable Temporal
  job, and fetches a small page of HubSpot contacts purely to prove
  connectivity — it doesn't import them into Sales yet. No sync safety
  features (spec §G2: incremental cursors, checkpointing, replay safety,
  rate-limit handling) since there's no polling/scheduled sync, only
  on-demand. No API keys for outbound platform access.
- **The AI Copilot only knows about the Knowledge module.** It retrieves
  and cites uploaded documents (spec §8–9's basic case works end to end),
  but the cross-functional examples in spec §8 (pulling from Compliance,
  Security, Sales, and Support context in one answer) can't work yet —
  that data all exists now but nothing wires any of it into Copilot
  retrieval. There's also no cross-module intent router —
  every question goes through the same single retrieval path over
  Knowledge chunks only.
- **Compliance frameworks/requirements are a fixed seeded catalog**, not
  an editable admin feature — GDPR, EU AI Act, and ISO 27001 are seeded
  with a handful of representative requirements each (not the complete
  regulatory text), enough to demonstrate the Framework → Requirement →
  Control chain genuinely, not exhaustively. Adding a framework today
  means adding a Python dict entry (`app/seed.py::CATALOG_FRAMEWORKS`),
  not a UI action.
- **No framework/evidence versioning**, no audits (auditor portal), no
  regulatory-update feed. See `docs/DOMAIN_MODEL.md`'s Phase 3 section for
  the full list of what the Compliance backbone doesn't cover yet.
- **Document parsing supports text/plain, text/markdown, text/csv, PDF,
  and DOCX only.** XLSX, PPTX, images/OCR are not implemented; uploading
  them marks the document `unsupported_format` honestly rather than
  pretending to extract text (spec §82).
- **No entity/relationship extraction** (spec §11's knowledge graph).
  Chunks are stored flat with no cross-linking to other entities yet.
- **Similarity search is a Python-side linear scan** (cosine similarity
  over every chunk in the organization), not a native `pgvector` ANN
  query — correct today, but explicitly not built to scale past a
  moderate number of chunks per organization. See `docs/DECISIONS.md`
  ADR-0012 for the migration path.
- **Prompt injection defense is prompt-level only** (retrieved content is
  delimited and framed as untrusted data — spec §F5). There's no tool-
  execution allowlist because the Copilot can't take actions yet, only
  answer questions; that becomes necessary before any AI-triggered action
  ships.
- **No invitation flow.** New members can only join today via signup
  (which creates a new organization) or direct database insertion (see
  `tests/test_rbac.py` for the pattern). `/invite/[token]` is not built.
- **MFA is schema-only.** `users.mfa_enabled` / `mfa_secret_encrypted`
  columns exist; there is no enrollment or challenge flow yet.
- **No SSO/SAML/SCIM.** Reserved for Phase 10 per the spec.

## Trust and progressive access model (spec §B)

- **No outbound (read) connectors exist yet**, so Stage 1–4 of the
  progressive trust model (read-only → scoped write → approved automation
  → bounded auto-execution) has nothing to apply to for the "connect a
  source read-only" onboarding flow (spec §I1). The one Phase 9 connector
  (generic inbound Webhook) is a different shape — it *receives* external
  events rather than reading from a third-party API — and its own
  guardrail is which Automation workflow it's allowed to trigger (only
  `active` workflows with `trigger_type="webhook"`), not the Stage
  1–4 ladder. The `Approval` primitive and risk-classification fields
  exist and are wired into the Tasks/Approvals UI (and now exercised by
  Automation's `human_approval` step, ADR-0021) so the pattern is ready
  for the first real outbound connector.
- **No Trust Center page.** Reserved for the Compliance module (Phase 3).

## Security

- **Audit log append-only-ness is enforced at the application layer only**,
  not the database level yet — see ADR-0004 in `docs/DECISIONS.md`. No
  code path issues `UPDATE`/`DELETE` against `AuditEvent`, but a bug or a
  future contributor could still write one; a DB-level `REVOKE` requires
  the app to connect as a non-owning role, planned for the AWS/RDS phase.
- **No CSRF/CSP/rate limiting/SSRF middleware yet.** These matter once
  there are state-changing browser forms beyond auth and outbound-fetching
  features (connectors) to protect. Auth endpoints rely on the session
  cookie's `SameSite=Lax` plus JSON-only bodies (not form-encoded) as a
  baseline CSRF mitigation, not a complete one.
- **Cross-subdomain cookie sharing is unresolved for production.** Locally,
  the session cookie (host-only, domain=`localhost`) happens to be sent to
  both `localhost:3000` and `localhost:8000` because browsers don't scope
  cookie storage by port. A production deployment with `app.` / `api.`
  subdomains needs an explicit shared `Domain` attribute (e.g.
  `.agora-origin.example`) — not yet configurable via an environment
  variable.
- **No malware scanning on uploaded files.** `files.classification` and
  signed URLs exist; the "malware-scanning workflow" from spec §L3 is not
  implemented.
- **No rate limiting or brute-force protection on login/signup.**

## Email

- **No real transactional email provider.** Password reset logs the reset
  link instead of emailing it (see ADR-0003). Amazon SES integration is
  planned alongside the AWS deployment phase.

## Infrastructure

- **No AWS deployment exists.** Everything in spec §L/§M/§N (Terraform,
  ECS, RDS, CloudFront, WAF, GitHub Actions CI/CD) is documented as a plan
  in `docs/IMPLEMENTATION_PLAN.md` but not implemented. Only a local Docker
  Compose environment runs today.
- **No CI pipeline configured** (no `.github/workflows/*` yet).
- **Local port conflicts**: this development machine has other unrelated
  Docker projects (`compliance-os`, `ai-sales-os`) bound to the default
  ports; Agora Origin's compose stack uses an `infra/docker/.env`
  override (gitignored) for non-standard host ports on this machine only.
  See `docs/ENVIRONMENT_VARIABLES.md`.
- **The web container's Turbopack dev server doesn't reliably detect new
  route files added while it's already running**, on this Windows +
  Docker Desktop bind-mount setup (`next dev` itself warns "Slow
  filesystem detected"). Editing existing files hot-reloads fine; adding
  a brand-new page under `app/` needed `docker compose restart web` to be
  picked up. Not a code bug — a note for whoever's developing against
  this stack locally.
- **npm audit reports 12 high-severity advisories** in Next.js's bundled
  build-time dependencies (postcss, sharp, and eslint's transitive
  minimatch). All are build-tool-only (no runtime/user-facing exposure);
  `npm audit fix --force` would downgrade Next.js to version 9, which is
  actively harmful — not applied. Revisit when Next.js ships a patch.

## Testing

- **No Playwright/E2E tests yet.** Backend has tenant-isolation, RBAC, and
  auth-flow tests (pytest, 12 passing). Frontend has typecheck/lint/build
  verification but no browser-driven tests.
- **No AI evaluation fixtures.** Planned for Phase 2 once RAG exists.
- **The SQLite-backed unit test suite did not catch two real bugs that
  only surfaced during a live Docker smoke test**: (1) the MinIO bucket
  was never created outside the seed script, so the first real upload
  404'd; (2) the worker process crashed on its first real activity
  because it had never imported `app.identity.models`, so SQLAlchemy
  couldn't resolve a foreign key into the `users` table (fixed via
  `app/db/register_all_models.py`, see ADR-0010). Both are now fixed and
  covered by a live smoke test, but neither would have been caught by
  pytest alone — a reminder that fast in-memory tests validate logic, not
  cross-service integration.
- **The full-stack smoke test was API-level (curl), not a real browser
  click-through.** Verified: signup → session cookie → `/me` → create task
  → list tasks → AI gateway demo response, all through the live API
  container; CORS preflight confirmed for the web origin; the login page
  HTML renders with the correct title through the web container. Not
  verified: actually clicking through the React app in a browser (React
  Query fetching, the auth-guard redirect, form validation UX). No browser
  automation tool was available in this environment — this is a gap to
  close with real Playwright E2E tests, not just curl.
