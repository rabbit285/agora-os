# Route & API Inventory

Audit date: 2026-07-30, updated same day after the Platform-foundation auth completion
work (PLAT-13/14/15), the Knowledge-module completeness work (XLSX/HTML extraction,
reranking, Knowledge Graph, Global Search — KNOW-03/06/07/08, PLAT-21), the
Compliance completeness work (Policy publish, Evidence Library, Framework Dashboard,
Compliance-as-Governance-Layer — COMP-05/17/18), the Security-module completeness
work (audited alerts, full incident workspace, Cloud/Identity Security scanning,
Security Overview dashboard, Asset/Alert Detail + Security Policies pages —
SEC-03/05/06/07/08/09), the Sales-module completeness work (ICP scoring, Lead
Finder, Enrichment, Sequences/Campaigns, Sales Inbox, Meeting Assistant, Sales
Intelligence, Lead/Contact/Opportunity detail pages — SALES-04/05/06/07/08), and the
Support-module completeness work (AI-grounded ticket response, Knowledge Base page,
Conversations view, AI Agent configuration, QA scoring + analytics dashboard —
SUPP-03/04/05/06/07), and the Automation-module completeness work (Temporal-durable
execution, all 24 spec-named action types, 11 of 16 trigger types genuinely wired,
WorkflowVersion history, a real @xyflow/react visual builder, Templates gallery,
Connections page, Automation Analytics — AUTO-03/04/05/06/07/08). Frontend routes taken from a fresh
`npm run build` (Next.js 16.2, Turbopack) — not from `docs/ROUTES_AND_SCREENS.md`, which
was found to contain stale entries claiming placeholder pages that did not exist in the
build at audit time (see `REMAINING_PRODUCT_GAPS.md` §A3; the ones that were genuinely
missing at audit time have since been built and are listed below). Backend routes taken
from a fresh `GET /openapi.json` fetch against the running dev API (port 8001, container
`agora-origin-api-1`).

## Frontend routes (66 total, from `npm run build` output, 2026-08-04)

○ = static, ƒ = server-rendered dynamic.

| Route | Type | Notes |
|---|---|---|
| `/` | ○ | Unified Dashboard — all 4 metric tiles real (Open Tasks, Pending Approvals, Compliance Health, Security Posture) |
| `/_not-found` | ○ | — |
| `/login` | ○ | Redirects to `/mfa-challenge` when the account has TOTP enabled |
| `/signup` | ○ | Redirects to `/onboarding` on success (spec §68) |
| `/onboarding` | ○ | Real 9-screen guided setup wizard + live-computed Business AI Readiness — PLAT-25 |
| `/forgot-password` | ○ | — |
| `/reset-password/[token]` | ƒ | — |
| `/verify-email/[token]` | ƒ | Consumes an email-verification token |
| `/invite/[token]` | ƒ | Accepts an org invitation, creating or attaching the user |
| `/mfa-challenge` | ○ | TOTP code entry, unlocks `get_org_context`-gated endpoints |
| `/tasks` | ○ | — |
| `/approvals` | ○ | — |
| `/copilot` | ○ | Retrieval-grounded Q&A with citations |
| `/knowledge` | ○ | List + upload — PDF/DOCX/TXT/MD/CSV/XLSX/HTML all real extractors |
| `/knowledge/[id]` | ƒ | Detail with chunk viewer |
| `/knowledge/graph` | ƒ | Organization Knowledge Graph explorer, click-through traversal |
| `/search` | ƒ | Global Search results, reachable from an always-visible top-nav box |
| `/compliance` | ○ | All Compliance sub-features on one page (controls, risks, vendors, questionnaires, audits, Trust Center mgmt, security reviews, AI systems, AI incidents, RoPA/DPIA/DSAR, data transfers) |
| `/compliance/controls/[id]` | ƒ | — |
| `/compliance/vendors/[id]` | ƒ | — |
| `/compliance/questionnaires/[id]` | ƒ | — |
| `/compliance/audits/[id]` | ƒ | — |
| `/compliance/security-reviews/[id]` | ƒ | — |
| `/compliance/ai-systems/[id]` | ƒ | — |
| `/compliance/ai-incidents/[id]` | ƒ | — |
| `/compliance/dpias/[id]` | ƒ | — |
| `/compliance/dsars/[id]` | ƒ | — |
| `/compliance/frameworks/[id]` | ƒ | Per-framework compliance dashboard — requirements, mapped controls, coverage % |
| `/trust/[org_slug]` | ƒ | Genuinely public, no auth dependency |
| `/security` | ○ | Security Overview dashboard (9 live metrics, "Run cloud scan" button) + assets + findings + alerts + incidents |
| `/security/assets/[id]` | ƒ | Findings on this asset, incidents referencing this asset |
| `/security/alerts/[id]` | ƒ | Status workflow, related finding |
| `/security/incidents/[id]` | ƒ | Full incident workspace: status workflow, timeline/communication log, affected-assets linker, root-cause/lessons-learned editor, linked compliance risk, linked response task |
| `/security/policies` | ○ | Reuses `GET /compliance/policies` read-only |
| `/sales` | ○ | Sales Intelligence dashboard + accounts + leads + pipeline overview, Lead Finder button |
| `/sales/accounts/[id]` | ƒ | Contacts, outreach, opportunities, deal-blocker link, ICP score badge, Enrich button |
| `/sales/icp` | ○ | ICP Builder — saving rescans every Account |
| `/sales/sequences` | ○ | Sequence list + "process due steps" trigger |
| `/sales/sequences/[id]` | ƒ | Sequence Builder — steps, enrollments, enroll-a-contact form |
| `/sales/campaigns` | ○ | Campaign list + create (sequence + contacts) |
| `/sales/campaigns/[id]` | ƒ | Real campaign stats (enrolled/sent/blocked/completed) |
| `/sales/inbox` | ○ | Sales Inbox — outbound outreach status only |
| `/sales/meetings` | ○ | Meeting CRUD + AI Copilot prep-notes generation |
| `/sales/leads/[id]` | ƒ | Detail: linked account/contact, status workflow |
| `/sales/contacts/[id]` | ƒ | Detail: linked account, outreach history, suppression toggle |
| `/sales/opportunities/[id]` | ƒ | Detail: linked account, stage workflow, onboarding indicator |
| `/support` | ○ | Analytics tiles + customers + tickets, sub-page nav |
| `/support/tickets/[id]` | ƒ | AI draft-reply + approval, QA review section |
| `/support/knowledge` | ○ | Knowledge Base article CRUD + publish toggle |
| `/support/ai-agent` | ○ | AI Agent enable/auto-send config |
| `/support/conversations` | ○ | Thread-first view over Tickets, filtered to email/chat channels |
| `/automation` | ○ | Analytics dashboard tiles + workflow list/create |
| `/automation/workflows/[id]` | ƒ | Visual @xyflow/react drag-and-drop Step Builder (draft only), version history, polling run history |
| `/automation/templates` | ○ | Workflow Templates gallery, clone-to-draft |
| `/automation/connections` | ○ | Reuses `GET /integrations/connections` |
| `/settings/organization` | ○ | Profile, Legal Entities/Teams (PLAT-16), notification webhook URL |
| `/settings/users` | ○ | Member list + invite-a-member form + pending-invitations list with revoke |
| `/settings/roles` | ○ | All 16 system roles + real granted permissions (reference view, not an editor) |
| `/settings/security` | ○ | Email verification status/resend, TOTP MFA enroll/confirm/disable |
| `/settings/integrations` | ○ | Provider catalog, OAuth connections, webhooks |
| `/settings/ai-providers` | ○ | Real-time status per spec §57 provider (has-adapter/configured/active) |
| `/settings/billing` | ○ | 4 plans, current plan + user count, per-entitlement comparison grid, self-service plan switch (no payment collection — PLAT-19) |
| `/notifications` | ○ | Inbox (list, mark-read) + per-channel preference toggles |
| `/reports` | ○ | 14 spec §65 report types × 4 export formats, generate + past-reports list + secure download link (PLAT-20) |
| `/recommendations` | ○ | 5 real generators (compliance/security/sales/automation/support), dismiss/act, each citing its exact source rows (spec §87, BIZ-02) |
| `/briefing` | ○ | Real daily briefing — 5 spec §88 sections + an AI suggestion reused from Recommendations, one per org per day (BIZ-03) |
| `/coming-soon` | ƒ | Honest not-yet-built landing for unimplemented modules |

### Documented-but-nonexistent routes (drift, see gaps §A3)

`/onboarding/company`, `/onboarding/goals` — listed in `docs/ROUTES_AND_SCREENS.md` as
`[ ]`, still produce no route in the build. (`/invite/[token]`, `/verify-email/[token]`,
the MFA challenge, `/notifications`, `/settings/roles`, and `/settings/ai-providers` were
also in this list at earlier audit points; all 6 are now built — see above.)

## Backend API surface (195 paths, from live `/openapi.json`, 2026-08-04)

| Prefix | Paths | Notes |
|---|---|---|
| `/auth` | 16 | signup, login, logout, me, forgot/reset-password, verify-email, resend-verification-email, mfa/{enroll,confirm,disable,verify}, accept-invitation, sso/providers, sso/{provider}/start, sso/{provider}/callback (spec §59) |
| `/billing` | 2 | plans (GET), current (GET/PUT, org_admin, audited) — 4 seeded plans, real entitlement enforcement on max_users/sso_enabled (spec §64, PLAT-19) |
| `/reports` | 4 | types (catalog of 14 spec §65 report types), list/create (GET/POST), detail (GET), download (GET, mints a fresh signed link) — real PDF/DOCX/XLSX/CSV generation from live organization data (spec §65, PLAT-20) |
| `/recommendations` | 3 | list (recomputes then returns active), dismiss, action — 5 real generators over Compliance/Security/Sales/Automation/Support (spec §87, BIZ-02) |
| `/briefing` | 1 | get-or-create-for-today — 5 real sections + an AI suggestion reused from Recommendations (spec §88, BIZ-03) |
| `/organizations` | 12 | current (GET/PATCH incl. notification_webhook_url), current/members (GET), current/invitations (GET/POST) + revoke, current/my-permissions (GET), current/roles (GET), current/legal-entities (GET/POST/PATCH/DELETE), current/teams (GET/POST/PATCH/DELETE) |
| `/onboarding` | 10 | status, company, goals, compliance-profile, security-profile, sales-profile, support-profile, advance, readiness, complete — spec §68 |
| `/tasks`, `/approvals` | 4 | core primitives |
| `/notifications` | 4 | list, mark-read, preferences (GET/PUT) — real multi-channel dispatch (email/webhook real, Slack/Teams honestly non-deliverable) |
| `/files` | 2 | upload-url, get |
| `/ai` | 2 | `/copilot/ask` (real reranking now runs between retrieval and generation), `/providers` (real-time status per spec §57 provider) |
| `/knowledge` | 6 | documents (list/create/get/chunks) incl. real XLSX/HTML extraction, knowledge-bases, graph (entity-types, entity traversal) |
| `/search` | 1 | tenant-scoped substring search across 16 entity types |
| `/compliance` | 53 | by far the largest surface — controls, risks, evidence, policies (incl. publish status), frameworks (incl. per-framework dashboard), vendors, questionnaires, audits, ai-systems, ai-incidents, processing-activities, dpias, dsars, data-transfers, security-reviews |
| `/security` | 13 | overview dashboard, assets (+detail), findings, alerts (+detail), incidents (+detail, timeline, affected-assets, postmortem), cloud-scan |
| `/sales` | 25 | accounts (+detail+enrich), contacts (+detail), leads (+detail+find), opportunities (+detail), outreach, icp-profile, sequences (+detail+steps+enroll+process-due-steps), campaigns (+detail), meetings (+prep-notes), inbox, intelligence |
| `/support` | 14 | customers, tickets (+detail+flag-upsell), messages (+draft-reply+send), knowledge-articles, csat, ai-agent-config, qa-score(s), analytics |
| `/automation` | 12 | workflows (+detail+steps+status+run+versions), runs (+detail+resume), templates (+use), analytics |
| `/integrations` | 10 | providers, connections, oauth start/callback, refresh/disconnect/health/sync, sync-runs, webhooks/receive |
| `/trust-center` | 5 | items, evidence-requests, public (unauthenticated) |
| `/health` | 2 | health, health/ready |

**Cross-check against frontend**: every backend route group above has at least
list/detail frontend usage EXCEPT Support Knowledge Articles (full CRUD API, zero FE
page). (`Policy` and the Compliance frameworks/requirements endpoints previously had no
standalone frontend usage — both fixed 2026-07-30: Policy via the Evidence-Library-style
section on `/compliance`, frameworks via the new `/compliance/frameworks/[id]`
dashboard.)

**API-level, fixed 2026-08-04** (spec §E7, apply across the whole surface, not one
module): real Redis-backed rate limiting (per-IP, global middleware) and real
`Idempotency-Key` support (global middleware, opt-in) now cover every endpoint; real
`limit`/`offset` pagination with an `X-Total-Count` header now covers 18 of the highest-
cardinality list endpoints (see `REMAINING_PRODUCT_GAPS.md` for the exact list and the
disclosed reasoning for which ~42 catalog/child-collection endpoints were left
unpaginated). **Still genuinely missing**: no bulk/batch endpoints.

## Docker / infra configuration (inspected this audit)

- `infra/docker/docker-compose.yml` — 7 services (postgres, redis, minio, temporal,
  temporal-ui, api, worker, web); host ports overridden via a gitignored, untracked
  `infra/docker/.env` (confirmed not committed, contains only port numbers, no secrets).
- `infra/docker/api.Dockerfile`, `worker.Dockerfile`, `web.Dockerfile` — all present.
- No `.github/` directory — no CI workflow configuration exists in-repo (separate from
  live AWS deployment, which is correctly out of this audit's scope).
