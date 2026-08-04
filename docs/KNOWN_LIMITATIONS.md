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
- **AI Model Gateway (spec §57)**: Anthropic and OpenAI have real, live
  adapters (`app.ai.adapters`), each activating only when its API key is
  set via environment variable (`ANTHROPIC_API_KEY`/`OPENAI_API_KEY`) and
  selected via `AI_PROVIDER` — otherwise the gateway honestly runs
  `DemoAdapter`, never a fabricated response. Real-time status for every
  named provider (has-adapter / configured / active) is visible at
  `/settings/ai-providers` (fixed 2026-07-30). **Azure OpenAI has no
  adapter** — the only provider spec §57 lists without an explicit
  "architecture"/"future" qualifier that still has zero implementation,
  surfaced while building that status page (`has_adapter: false`,
  disclosed on the page itself, not silently omitted). Google carries the
  spec's own "architecture" qualifier; "Local/private" carries "future" —
  both legitimately unbuilt.
- **Integrations (Phase 9)**: a generic inbound Webhook connector plus a
  seven-provider OAuth2 framework (HubSpot, Google, Microsoft, GitHub,
  Slack, Salesforce, Zendesk) are implemented — see the dedicated bullet
  below.
  Every other spec §48 category (Email, Marketing, Cloud, remaining
  Identity/Engineering/Communication/Documents/Accounting connectors)
  still needs a real third-party OAuth app or API key this environment
  doesn't have.
- **Compliance**: an AI System Inventory (`AISystem`/`AIAssessment`, EU AI
  Act risk tiers) now exists — registering a high/unacceptable-risk system
  auto-creates a real Approval and gates its `approved` status on that
  Approval being granted (ADR-0027). Privacy sub-features also now exist —
  a RoPA register (`ProcessingActivity`), DPIAs (`DPIA`, with the same
  high-risk-gates-on-Approval pattern for directly-created ones, and
  auto-created linked to a high/unacceptable-risk `AISystem` — ADR-0029),
  and DSARs (`DSAR`, 30-day due date, received→in_progress→fulfilled/
  rejected lifecycle). AI Incidents (`AIIncident`) also now exist — a
  `critical`-severity incident reuses `SecurityIncident`'s exact
  critical-severity chain (linked Risk + response Task + owner
  Notification, ADR-0030). Vendor Risk (`Vendor`/`VendorAssessment`) also
  now exists — a `high`/`critical` assessment conclusion auto-creates a
  linked Risk, reusing `record_assessment`'s hook shape for a fourth
  entity type (ADR-0031); `Evidence` can now attach to a Vendor as well
  as a Control. Security Questionnaires (`Questionnaire`/
  `QuestionnaireQuestion`/`QuestionnaireAnswer`) also now exist — answers
  are drafted via an org-wide exact-text match against previously
  approved answers, then a live AI Copilot call as fallback, always
  landing as `status="draft"` until a human approves (ADR-0032). The
  answer-library match is a simplified, non-fuzzy comparison
  (`strip().lower()` equality) — two questions that are semantically
  identical but worded differently will not match and will fall through
  to the AI Copilot path instead of reusing the human-approved answer; a
  future iteration could reuse Knowledge's embeddings for a similarity
  match instead. Audits (`Audit`/`AuditFinding`) also now exist — a
  `high`/`critical` finding auto-creates a remediation Task, reusing
  `record_assessment`'s hook shape for a fifth entity type (ADR-0033);
  the pre-seeded `auditor` system role got its first real permission.
  This is audit-run *tracking*, not a full auditor portal — there is no
  separate auditor-facing login/experience, evidence request workflow
  scoped to an audit, or read-only external-auditor access; the
  `auditor` role currently gets the same full manage permission an
  internal user would. Trust Center (`app.trust_center`, `TrustCenterItem`/
  `EvidenceRequest`) also now exists — a genuinely public, unauthenticated
  `GET /api/v1/trust-center/public/{org_slug}` page (spec B4) plus a
  public evidence-request submission that auto-creates a Task (ADR-0034).
  There is no rich Markdown/rich-text editor for item `content` (plain
  text only), no email notification when an evidence request is
  submitted (the org must check its Task queue), and no per-item revision
  history — updating a category's content overwrites it in place.
  Enterprise Sales Security Review (`SecurityReview`) also now exists —
  starting one creates/imports a Questionnaire against a Sales
  Opportunity, gates clearing on a materiality threshold + real Approval,
  and generates a real trust-package File (ADR-0035). One review per
  opportunity only — a deal that needs a second review after the first
  clears would need a new row type this build doesn't have (a real
  re-review workflow), and the trust package is a plain-text compilation
  with no PDF formatting, letterhead, or e-signature. Data Transfers
  (`DataTransfer`) also now exists — GDPR Chapter V, extending Privacy
  directly (like RoPA/DPIA/DSAR) rather than a new module; a `derogation`
  transfer auto-creates a linked Risk (ADR-0036). This completes all six
  items of the Compliance/Trust program requested this session — see
  `docs/RESUME_BUILD.md` for the full sequence and what (if anything) is
  next.
- **Security**: the incident workspace now has the full structure spec §19
  describes (Timeline + Communication as one chronological log
  discriminated by `entry_type`, Affected Assets linking, Evidence via
  `Evidence.incident_id`, Root Cause/Lessons Learned). Cloud Security
  (spec §15) and Identity Security (spec §16) now run real `boto3` checks
  against a real AWS account (`app.secops.cloud_scanner`), gated on
  `AWS_SECURITY_SCAN_ACCESS_KEY_ID`/`AWS_SECURITY_SCAN_SECRET_ACCESS_KEY`
  — absent credentials return `configured=False` and create nothing,
  never a fabricated scan result. Remaining gaps: only AWS is wired, not
  Azure/GCP; only 2 of the spec's ~11 example checks are implemented (S3
  public-access-block, IAM users without MFA) — no encryption, logging,
  security-group, unused-credential, key-rotation, or root-account
  checks yet; no third-party vulnerability-scanner ingestion (Qualys,
  Tenable, Snyk, etc.); no identity-provider connectors (Okta/Entra/
  Google Workspace) — Identity Security only reads AWS IAM. Real-AWS-
  account scanning has not been live-verified (no AWS account available
  in this environment) — only the uncredentialed path and the two check
  functions (against fake client stubs) have been.
- **Sales**: outreach "sending" (manual or via a Sequence/Campaign step)
  doesn't call a real email/LinkedIn provider — it only transitions the
  message's own status (`sent` or `blocked`), gated by a genuine
  compliance check (`Contact.do_not_contact`), not a stub of one.
  Sequences/Campaigns now exist (`app.sales.sequences`) — multi-step
  cadences with simple `{{first_name}}` template substitution, advanced
  by a real, independently-callable function
  (`POST /sales/sequences/process-due-steps`) rather than a Temporal
  schedule (Automation's own Temporal migration is the natural place to
  wire a periodic trigger onto it later). ICP scoring
  (`app.sales.icp`) is a deterministic, disclosed 0-100 formula (industry
  match + employee-count fit, 50 points each), not a black-box model.
  Lead Finder (`app.sales.lead_finder`) surfaces the org's own existing
  ICP-fit Accounts lacking an open Lead — it is not an external
  prospecting data source. Company Enrichment (`app.sales.enrichment`)
  is real when a `CLEARBIT_API_KEY` is configured, honestly
  `configured=false` otherwise — the same credential-gated pattern as
  the AI providers, OAuth integrations, and AWS Cloud Security scanning.
  Meetings exist with a real AI Copilot-generated prep-notes feature
  (`app.sales.meetings`, honestly falls back to "no evidence" when the
  knowledge base has nothing relevant) — there is no real calendar sync
  (Google/Microsoft Calendar), so scheduling is manual entry only. Sales
  Inbox shows outbound outreach status only — no inbound reply tracking,
  since no real email/LinkedIn provider is connected. The suppression
  check itself is a single boolean, not the fuller jurisdiction/consent/
  marketing-basis engine spec §91 describes (ADR-0019). A `closed_won`
  Opportunity creates a real Support Customer + onboarding Task
  (ADR-0025), but not a real welcome email or an accounting-system
  update — no email provider or accounting connector exists yet (the
  Billing module added 2026-07-30 covers plan/entitlements, not
  invoice/accounting sync).
  If the account has no Contact yet, onboarding is honestly skipped, not
  faked with a placeholder email.
- **Support**: tickets have a `channel` field (`email`/`chat`/`api`) but
  no real channel connectors — there's no inbound email parsing or chat
  widget, only the API. AI-grounded ticket replies now exist
  (`app.support.copilot.draft_ticket_reply`) — a real retrieval-grounded
  Copilot call landing as a pending draft, auto-sent only when the org's
  `AIAgentConfig` opts in AND the answer was genuinely grounded (an
  honest "no evidence" answer is never auto-sent). QA review scoring
  (`TicketQAScore`) and a CSAT/QA/resolution-time analytics dashboard
  (`app.support.analytics`) also now exist. Still missing: SLA
  policies/timers, knowledge-gap detection, FAQ generation. "Conversations"
  is a real second FE view over the same Ticket data (filtered to
  email/chat channels), not a separate backing table — see ADR-0017's
  original reasoning, extended in ADR-0039. The security-category
  cross-module hook creates a `SecurityAlert` (Security's triage inbox),
  not a full `SecurityIncident` — see ADR-0020 for why. Flagging a ticket
  as an upsell signal creates a real Sales Lead and notifies the linked
  account's owner (or the flagging agent if there's no linked Sales
  Account or no account owner), but does not auto-create an Opportunity —
  that conversion is left to a human sales rep (ADR-0022).
- **Cross-Module Intelligence (Phase 8), corrected 2026-07-30 (finding
  A2 — this section previously overstated 3 of the 5 scenarios as "fully
  implemented")**: comparing each scenario's real step count against
  spec §69's literal step list —
  - **Enterprise Sales Security Review** (10 steps): 9 of 10 real
    (`SecurityReview`, ADR-0035) — genuinely near-complete. Missing: step
    9, "Sales Copilot drafts follow-up."
  - **New AI Tool Adoption** (9 steps): 4 of 9 real — vendor
    request→Approval gate (ADR-0027) and an auto-created Privacy DPIA
    (ADR-0029, counted under Compliance above). Missing: security
    assessment, EU AI Act applicability and DPA review as distinct
    steps, the AI risk assessment step itself (as opposed to the DPIA),
    and approved-use policy publication.
  - **Security Incident** (9 steps): 3 of 9 real — create incident, link
    a Risk (personal-data-impact-adjacent, not a formal GDPR breach
    assessment), create a response Task (only for `critical` severity,
    no separate configurable threshold). The incident workspace built
    separately (spec §19, ADR-0037) adds real Affected-Assets linking
    and an Evidence tab, but neither is *automatically* triggered by
    this scenario's chain — both are manual actions available on the
    incident page, not steps 3 ("finds affected assets")/9 ("preserves
    evidence") of this specific automated reaction chain. Missing as
    automatic reactions: AI summary, a formal Compliance GDPR-breach-
    obligations assessment, notifying the responsible team, and
    generating draft communications.
  - **New Customer** (8 steps): 2 of 8 real — create Customer, create an
    onboarding Task. Missing: welcome email (no SMTP/SES path exists
    anywhere in this build, same capability boundary as Automation's
    `send_email` step), billing update (no Billing module exists),
    support-profile creation, additional internal tasks, and a scheduled
    check-in.
  - **Support Upsell Signal** (4 steps): 2 of 4 real — create a Sales
    Lead, notify the linked account's owner (or the flagging agent if
    none). Missing: an explicit Opportunity *suggestion* as its own
    artifact (a human still converts the Lead manually, ADR-0022) and an
    AI-generated account brief.

  No AI daily briefing, business process discovery, AI recommendation
  engine, or organization memory exist either (spec §86-90, tracked
  separately as BIZ-01 through BIZ-05).
- **Automation**: execution is now Temporal-durable (`WorkflowRunWorkflow`,
  spec §61) — `app.automation.service.start_run` only creates the
  `WorkflowRun` row; a real worker executes it. All 24 of spec §39's named
  action types (plus 2 pre-existing extras) are real dispatch handlers
  (`app.automation.service.STEP_HANDLERS`), reusing existing cross-module
  services (Compliance's control assessments, Security's cloud scanner,
  Support's ticket creation, the AI Copilot, Global Search) rather than
  stubs. `send_email` and `send_chat_message` are honestly
  credential/scope-gated: this build has no real SMTP/SES dispatch path
  anywhere, and the Slack/Microsoft OAuth connectors are deliberately
  scoped read-only (`channels:read` only — see
  `app.integrations.adapters.slack`), so both always report they could not
  actually deliver rather than fabricating a "sent" result. 11 of spec
  §38's 16 named trigger types genuinely fire real runs — `manual`, `api`,
  the pre-existing `webhook` connector, a real Temporal Schedule for
  `schedule`, and 8 more wired to real internal domain events (new/changed
  CRM leads and opportunity stages, new support tickets, new vendors, new
  employees, document uploads, failed control assessments, security
  alerts). The remaining 4 (`new_email`, `form_submission`,
  `database_event`, `new_regulatory_update`) have no real source system
  anywhere in this build (no inbound email parsing, no form-building
  feature, no DB-watching connector, no Regulatory Intelligence feed) and
  are accepted `trigger_type` values that are honestly never dispatched,
  not silently faked. The Workflow Builder is now a real
  `@xyflow/react` drag-and-drop node canvas (draft workflows only, per
  spec §41's edit-lock); a Workflow Templates gallery (3 seeded templates,
  clone-to-draft), a Connections page (reusing Integrations' own
  connections list), and a live Automation Analytics dashboard
  (`app.automation.analytics`) all exist. `WorkflowVersion` provides real
  immutable publish-history snapshots. Still missing: retry/backoff
  policies beyond "a failed step fails the run", and Data Transform/
  Subworkflow as their own named spec §37 step categories (the closest
  equivalents here are `extract_data`/`classify_data` for data
  transformation and nothing yet for true nested subworkflows).
- **Integrations**: `IntegrationConnection.connector_key` supports
  `"webhook"` plus seven OAuth2 providers — HubSpot, Google (Calendar +
  Gmail + Drive), Microsoft (Calendar + Outlook Mail), GitHub, Slack,
  Salesforce, Zendesk (ADR-0026, ADR-0028, ADR-0041) — covering every spec
  §48 category that doesn't carry an explicit "architecture" qualifier
  except Cloud (AWS/Azure/GCP, excluded with AWS deployment per this
  build's scope) and CRM's Pipedrive/Customer Support's Intercom (deferred
  alongside the explicitly-"architecture" providers below for the same
  reason: no real OAuth app exists in this environment to build or test
  against, and a same-shaped adapter for a ninth or tenth provider adds no
  new pattern). Still not built, all disclosed as architecture-ready-not-
  built rather than silently missing: CRM's Pipedrive/Zoho, Marketing's
  Mailchimp, Customer Support's Intercom/Freshdesk, Identity's Okta/Entra/
  Google Workspace, Engineering's GitLab/Jira/Azure DevOps, Communication's
  Teams, Documents' SharePoint/OneDrive/Notion, and Accounting's
  QuickBooks/Xero/Stripe/ERP — each would follow the exact same
  `OAuthConnectorAdapter` Protocol shape already proven seven times over.
  The provider catalog endpoint reports `configured: bool` honestly per
  provider (all seven show "Not configured" without real
  `<PROVIDER>_CLIENT_ID`/`<PROVIDER>_CLIENT_SECRET`, and Zendesk
  additionally needs `ZENDESK_SUBDOMAIN` since a Zendesk OAuth app is
  registered against one specific customer subdomain rather than a
  multi-tenant authorize URL) and additionally exposes each provider's
  requested `scopes` as a permission preview. A mock OAuth adapter
  (mirroring the AI gateway's `DemoAdapter`, labeled with the real
  `provider_key`) lets the full authorize→callback→connected→sync→
  disconnect flow be exercised for testing/demo purposes for every
  provider even without real credentials — this is what the automated
  test suite runs against, and the demo seed data deliberately does *not*
  create a "connected" row for any provider, to avoid any appearance of a
  fabricated live connection. Three providers (GitHub classic OAuth Apps,
  Slack bot tokens without rotation, Zendesk OAuth tokens without
  rotation) genuinely have no refresh flow for the token type used here —
  `refresh_access_token` raises a clear error rather than faking support,
  but callers never reach it since no refresh token is ever stored for
  them in the first place. Salesforce's adapter is a documented
  simplification: it calls the generic `login.salesforce.com` identity
  endpoint rather than the org's own instance-specific API domain
  (`instance_url`, returned at token exchange but not persisted), since
  threading that through would mean a Salesforce-only parameter on every
  other provider's adapter methods — a real Salesforce connector needs to
  store and use `instance_url` for anything beyond identity/revoke.
  Google's and Microsoft's `sync()` cover more than one spec §48 category
  on a single connection (Calendar+Gmail+Drive; Calendar+Outlook Mail) —
  spec §G2 incremental cursor/checkpointing round-trips only the original
  Calendar resource's pagination token; Gmail/Drive/Outlook Mail always
  fetch their latest first page rather than each carrying an independent
  checkpoint, since `IntegrationConnection.sync_cursor` is a single opaque
  string, not a per-resource map — a disclosed scope decision, not a
  silent gap. Stored OAuth tokens are encrypted at rest (Fernet,
  `app/core/crypto.py`), but the encryption key falls back to one derived
  from `SECRET_KEY` when `TOKEN_ENCRYPTION_KEY` is unset — fine for
  dev/test, but a real deployment must set its own key (rotating
  `SECRET_KEY` would otherwise silently break every stored token). A
  webhook connection's `webhook_secret` is still returned in plain text by
  the API to whoever can read the connection (session-authenticated,
  tenant-isolated, but not masked/rotatable) — no secrets vault exists
  yet. `subscribe()`, `execute_action()`, and `collect_evidence()` from
  spec §49's full Connector Contract aren't implemented — this slice only
  needed authorize/token-exchange/refresh/health/sync/revoke. "Sync now"
  runs as a durable Temporal workflow (`IntegrationSyncWorkflow`, with a
  bounded `RetryPolicy` — 3 attempts, exponential backoff — spec §G2
  retries/backoff), and fetches a page of the provider's own read-only
  data (contacts, calendar events, public repos, channels, tickets, etc.
  depending on provider) purely to prove connectivity — it doesn't import
  any of it into Sales/Support/Knowledge yet. Sync safety (spec §G2) now
  covers incremental cursors/checkpointing (`IntegrationConnection.
  sync_cursor` persists each provider's real pagination cursor —
  HubSpot's `after`, Slack's `next_cursor`, Google Calendar's
  `nextPageToken`, Microsoft Graph's `@odata.nextLink`, GitHub's `Link`
  header page number, Zendesk's `after_cursor`; Salesforce's single
  identity call honestly has none), replay safety (`execute_sync_run`
  is idempotent — a `SyncRun` that's already finalized is returned
  unchanged rather than re-synced or double-advancing the cursor), and
  retries/backoff (above). Still not covered: tombstones/deletions and
  rate-limit-specific handling (a 429 is just an unhandled error like any
  other failure, not specially detected or backed off differently) and
  partial-failure-within-a-page reporting (a page either fully succeeds or
  the whole `SyncRun` fails). No API keys for outbound platform access. No
  AWS infrastructure exists yet to exercise the Secrets Manager/Parameter
  Store/ECS secret-injection design documented in
  `docs/ENVIRONMENT_VARIABLES.md` — it's a commitment for whoever builds
  Phase 10's AWS deployment, not yet built or tested.
- **The AI Copilot only knows about the Knowledge module.** It retrieves
  and cites uploaded documents (spec §8–9's basic case works end to end),
  but the cross-functional examples in spec §8 (pulling from Compliance,
  Security, Sales, and Support context in one answer) can't work yet —
  that data all exists now but nothing wires any of it into Copilot
  retrieval. There's also no cross-module intent router —
  every question goes through the same single retrieval path over
  Knowledge chunks only. This now also includes **Business AI Memory**
  (spec §89, fixed 2026-08-04, BIZ-04): `app.memory` is a real, structured,
  provenance-tracked store (approved facts/answers, policies, business
  rules, preferences, past decisions, workflow outcomes) with real
  admin correct/delete — but `app.ai.copilot.ask_copilot`'s retrieval
  path was deliberately left unmodified in this pass rather than risk
  destabilizing that already-tested, security-sensitive prompt-
  construction code under time pressure. The storage/provenance/
  correction subsystem spec §89 actually names is complete; grounding
  Copilot answers in it is a disclosed, real next step, not done yet.
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
- **Invitation, email verification, and MFA are implemented** (fixed
  2026-07-30, completeness-audit backlog PLAT-13/14/15): `org.users.manage`
  holders invite an email to a specific role at
  `POST /organizations/current/invitations`; accepting at `/invite/[token]`
  creates (or attaches) the user and an active Membership with
  `invited_by` set. Every signup triggers an email verification token
  (`/verify-email/[token]`, resendable). MFA is real TOTP (RFC 6238, via
  `pyotp`): `/settings/security` enrolls and confirms a secret, login for
  an `mfa_enabled` user creates a session with `mfa_verified=False` that
  `app.dependencies.get_org_context` rejects until a correct code is
  submitted at `/mfa-challenge`. No real email provider is wired up yet
  (same log-only dev adapter as password reset) — WebAuthn/hardware-key
  MFA is not implemented, only TOTP.
- **Onboarding Experience (spec §68) is implemented** (fixed 2026-07-30,
  completeness-audit backlog PLAT-25): a real 9-screen wizard at
  `/onboarding` (spec's steps 1-2, Company and Business profile, are
  combined onto one screen; every other named step maps 1:1), resumable
  via `OnboardingProfile.current_step`. Steps 8-9 ("Connect tools",
  "Upload knowledge") deliberately have no fields of their own — they
  link to the real, already-existing Integrations and Knowledge pages
  rather than duplicating those flows. Step 10's "Business AI Readiness"
  output is computed live from real organization data on every request
  (never stored, never a hardcoded example number) across 5 dimensions
  and a list of named opportunities — see `SPEC_TRACEABILITY_MATRIX.md`
  PLAT-25 for exactly which real query backs each one. Signup now
  redirects new organizations here instead of straight to the dashboard.
- **SSO is real; SAML/SCIM are not** (fixed 2026-07-30, completeness-audit
  backlog PLAT-18): spec §59 lists "SSO" plain but "SAML architecture" and
  "SCIM architecture" — only the latter two carry the spec's own
  deferral qualifier. `/login` has real "Sign in with Google"/"Sign in
  with Microsoft" buttons (shown only when that provider is actually
  configured, via a public `GET /auth/sso/providers` status check) that
  reuse the exact same OAuth adapters Integrations uses for the token
  exchange, with a minimal identity-only scope rather than Integrations'
  broader Calendar/Gmail/Drive/Mail scopes. A first-time SSO login
  auto-provisions a brand-new organization exactly like normal signup
  (new org_admin Membership, default LegalEntity) since there's no
  invitation-only-SSO concept in this build. SAML and SCIM remain
  genuinely unbuilt — that really is Phase 10 per spec's own qualifier
  for those two specifically, not for SSO.
- **Multi-entity (spec §53) is real for its "Support:" tier, not its
  "Future:" tier.** `LegalEntity`/`Team` have full CRUD
  (`/organizations/current/legal-entities`, `/teams`; migration
  `3b81902c0a1d`), RBAC-gated (`org.entities.manage`), audited, with
  archival instead of destructive delete and an enforced exactly-one-
  default-entity invariant — fixed 2026-07-30, completeness-audit backlog
  PLAT-16. What remains genuinely unbuilt, per that same spec section's
  own separate "Future:" marker (PLAT-17): `Organization` has no parent-
  organization FK (no subsidiary hierarchy), and there is no
  agency/consultant multi-client mode (one login managing several client
  organizations) — both are spec-deferred product-roadmap items, not
  gaps in what was attempted.
- **Notification dispatch is real for 2 of spec §66's 4 named channels
  beyond in-app** (fixed 2026-07-30): `app.core.notifications.notify` is
  now the single call site every module uses (replacing 6 places that
  each constructed a `Notification` row directly) and honestly records
  what was requested vs. actually delivered on
  `channels_requested`/`channels_delivered`. **Email**: dispatched through
  the same log-only dev adapter every other transactional email in this
  build uses — no real SMTP/SES provider is configured anywhere. **Webhook**:
  a real `httpx` POST to `Organization.notification_webhook_url` when one
  is configured (settable on `/settings/organization`) — genuinely
  delivered, not simulated. **Slack**/**Teams**: honestly never deliverable
  — the Slack OAuth connector is deliberately scoped `channels:read` only
  (spec §B1) and cannot post; no Teams connector exists at all. A user can
  still store a preference for either channel (their stated intent, real
  `NotificationPreference` rows, migration `f2899856bd0f`), but `notify()`
  never marks Slack/Teams as delivered even when "enabled." Per-user
  channel toggles live on the new `/notifications` page alongside a real
  inbox (list, mark-read) — previously the backend list/read endpoints
  existed with no frontend page (finding A3). Only two of the 6 existing
  notification call sites request a channel beyond in-app (both
  `critical`-severity incident-assignment notifications, Compliance's AI
  incident and Security's incident, request `email`) — the rest remain
  in-app-only, unchanged from before this fix, since retrofitting every
  call site to request every channel wasn't the goal; the dispatch
  infrastructure itself being real and correctly wired was.
- **Billing & entitlements (spec §64) is real for the "entitlement
  service" requirement, not for the section's own "Plans architecture:"
  payment-collection half** (fixed 2026-07-30, PLAT-19): 4 seeded plans
  (Starter/Growth/Business/Enterprise, `app.billing.PLAN_CATALOG`) each
  carry a real entitlements blob (19 spec-named keys); `GET /billing/
  plans`, `GET`/`PUT /billing/current` (org_admin, audited). Which
  numeric/boolean value unlocks at which tier is a disclosed judgment
  call — the spec names the entitlement keys but not their per-tier
  cutoffs. Enforcement is real but deliberately narrow: `max_users` on
  new invitation creation, and `sso_enabled` on SSO login for an
  *existing* user at an *existing* org (a brand-new org auto-provisioned
  by its own first SSO login is exempt, to avoid rejecting the very
  login that creates it). Gating `trust_center_enabled` on the Trust
  Center write endpoint was attempted and reverted before commit: every
  org — including every pre-existing Trust Center test's freshly-signed-
  up org — defaults to Starter, whose catalog has `trust_center_enabled:
  false`, which would have silently broken a feature that predates
  Billing entirely. No other pre-existing feature is retroactively
  gated. There is no Stripe/payment integration anywhere — switching
  plans on `/settings/billing` is an immediate, free, self-service
  change, not a checkout flow; this matches the spec's own "Plans
  architecture:" qualifier on that half of §64.
- **Reporting (spec §65) is real for all 14 named report types and all
  5 export options** (fixed 2026-08-04, PLAT-20), with two disclosed
  scope choices. First, "Secure link" is realized as the same signed-
  URL download mechanism (`app.core.storage.presign_download`) every
  format already uses to be fetched at all, not a distinct 5th file to
  generate — every report is delivered exclusively that way, never
  inlined or emailed, so the mechanism itself satisfies the requirement
  for all 4 real formats. Second, **Automation ROI** reports real run
  volume, success rate, and status breakdown (the same data
  `app.automation.analytics.compute_workflow_analytics` already
  powers) rather than a dollar figure — this build collects no
  per-workflow cost-per-manual-execution basis to compute a real ROI
  dollar amount against, so the report says so explicitly rather than
  inventing one. Every other report type is a live aggregate over this
  org's own rows (verified: generating and downloading real PDF/DOCX/
  XLSX/CSV files, not just checking for a 201 response).

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
- **Trust Center now exists** (`app.trust_center`, ADR-0034) — a
  genuinely public `/trust/[org_slug]` page and public evidence-request
  workflow, outside the progressive trust model above (that model
  governs *outbound* connectors reading third-party data; Trust Center
  is an *inbound*-facing public page, a different concern spec B4
  describes separately).

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
