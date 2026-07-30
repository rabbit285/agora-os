# Route & API Inventory

Audit date: 2026-07-30, updated same day after the Platform-foundation auth completion
work (PLAT-13/14/15), the Knowledge-module completeness work (XLSX/HTML extraction,
reranking, Knowledge Graph, Global Search — KNOW-03/06/07/08, PLAT-21), and the
Compliance completeness work (Policy publish, Evidence Library, Framework Dashboard,
Compliance-as-Governance-Layer — COMP-05/17/18). Frontend routes taken from a fresh
`npm run build` (Next.js 16.2, Turbopack) — not from `docs/ROUTES_AND_SCREENS.md`, which
was found to contain stale entries claiming placeholder pages that did not exist in the
build at audit time (see `REMAINING_PRODUCT_GAPS.md` §A3; the ones that were genuinely
missing at audit time have since been built and are listed below). Backend routes taken
from a fresh `GET /openapi.json` fetch against the running dev API (port 8001, container
`agora-origin-api-1`).

## Frontend routes (40 total, from `npm run build` output)

○ = static, ƒ = server-rendered dynamic.

| Route | Type | Notes |
|---|---|---|
| `/` | ○ | Unified Dashboard — 2 of 4 metric tiles real, 2 honest "Not available yet" |
| `/_not-found` | ○ | — |
| `/login` | ○ | Redirects to `/mfa-challenge` when the account has TOTP enabled |
| `/signup` | ○ | — |
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
| `/security` | ○ | Assets + findings + alerts + incidents — 4 flat lists, not a dashboard |
| `/security/incidents/[id]` | ƒ | — |
| `/sales` | ○ | Accounts + pipeline overview |
| `/sales/accounts/[id]` | ƒ | Contacts, outreach, opportunities, deal-blocker link |
| `/support` | ○ | Customers + tickets |
| `/support/tickets/[id]` | ƒ | — |
| `/automation` | ○ | Workflow list + step-form create |
| `/automation/workflows/[id]` | ƒ | — |
| `/settings/organization` | ○ | — |
| `/settings/users` | ○ | Member list + invite-a-member form + pending-invitations list with revoke |
| `/settings/security` | ○ | Email verification status/resend, TOTP MFA enroll/confirm/disable |
| `/settings/integrations` | ○ | Provider catalog, OAuth connections, webhooks |
| `/coming-soon` | ƒ | Honest not-yet-built landing for unimplemented modules |

### Documented-but-nonexistent routes (drift, see gaps §A3)

`/onboarding/company`, `/onboarding/goals`, `/notifications`, `/settings/roles`,
`/settings/ai-providers` — listed in `docs/ROUTES_AND_SCREENS.md` as `[~]`/`[ ]` but
produce no route in the build. (`/invite/[token]`, `/verify-email/[token]`, and the MFA
challenge were also in this list at first-audit time; all 3 are now built — see above.)

## Backend API surface (133 paths, from live `/openapi.json`)

| Prefix | Paths | Notes |
|---|---|---|
| `/auth` | 13 | signup, login, logout, me, forgot/reset-password, verify-email, resend-verification-email, mfa/{enroll,confirm,disable,verify}, accept-invitation |
| `/organizations` | 4 | current (GET/PATCH), current/members (GET), current/invitations (GET/POST) + revoke |
| `/tasks`, `/approvals` | 4 | core primitives |
| `/notifications` | 2 | list, mark-read — no dispatch-channel config endpoint |
| `/files` | 2 | upload-url, get |
| `/ai/copilot` | 1 | `/ask` (real reranking now runs between retrieval and generation) |
| `/knowledge` | 6 | documents (list/create/get/chunks) incl. real XLSX/HTML extraction, knowledge-bases, graph (entity-types, entity traversal) |
| `/search` | 1 | tenant-scoped substring search across 16 entity types |
| `/compliance` | 53 | by far the largest surface — controls, risks, evidence, policies (incl. publish status), frameworks (incl. per-framework dashboard), vendors, questionnaires, audits, ai-systems, ai-incidents, processing-activities, dpias, dsars, data-transfers, security-reviews |
| `/security` | 8 | assets, findings, alerts, incidents |
| `/sales` | 11 | accounts, contacts, leads, opportunities, outreach |
| `/support` | 8 | customers, tickets, messages, knowledge-articles, csat, flag-upsell |
| `/automation` | 6 | workflows, runs, resume |
| `/integrations` | 10 | providers, connections, oauth start/callback, refresh/disconnect/health/sync, sync-runs, webhooks/receive |
| `/trust-center` | 5 | items, evidence-requests, public (unauthenticated) |
| `/health` | 2 | health, health/ready |

**Cross-check against frontend**: every backend route group above has at least
list/detail frontend usage EXCEPT Support Knowledge Articles (full CRUD API, zero FE
page). (`Policy` and the Compliance frameworks/requirements endpoints previously had no
standalone frontend usage — both fixed 2026-07-30: Policy via the Evidence-Library-style
section on `/compliance`, frameworks via the new `/compliance/frameworks/[id]`
dashboard.)

**API-level gaps** (apply across the whole surface, not one module): no pagination
parameters on any list endpoint observed in the schema; no `Idempotency-Key` header
support; no visible rate-limiting; no bulk/batch endpoints.

## Docker / infra configuration (inspected this audit)

- `infra/docker/docker-compose.yml` — 7 services (postgres, redis, minio, temporal,
  temporal-ui, api, worker, web); host ports overridden via a gitignored, untracked
  `infra/docker/.env` (confirmed not committed, contains only port numbers, no secrets).
- `infra/docker/api.Dockerfile`, `worker.Dockerfile`, `web.Dockerfile` — all present.
- No `.github/` directory — no CI workflow configuration exists in-repo (separate from
  live AWS deployment, which is correctly out of this audit's scope).
