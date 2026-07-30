# Route & API Inventory

Audit date: 2026-07-30. Frontend routes taken from a fresh `npm run build` (Next.js 16.2,
Turbopack) run in this audit — not from `docs/ROUTES_AND_SCREENS.md`, which was found to
contain 8 stale entries claiming placeholder pages that do not exist in the actual build
(see `REMAINING_PRODUCT_GAPS.md` §A3). Backend routes taken from a fresh
`GET /openapi.json` fetch against the running dev API (port 8001, container
`agora-origin-api-1`).

## Frontend routes (33 total, from `npm run build` output)

○ = static, ƒ = server-rendered dynamic.

| Route | Type | Notes |
|---|---|---|
| `/` | ○ | Unified Dashboard — 2 of 4 metric tiles real, 2 honest "Not available yet" |
| `/_not-found` | ○ | — |
| `/login` | ○ | — |
| `/signup` | ○ | — |
| `/forgot-password` | ○ | — |
| `/reset-password/[token]` | ƒ | — |
| `/tasks` | ○ | — |
| `/approvals` | ○ | — |
| `/copilot` | ○ | Retrieval-grounded Q&A with citations |
| `/knowledge` | ○ | List + upload |
| `/knowledge/[id]` | ƒ | Detail with chunk viewer |
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
| `/settings/users` | ○ | — |
| `/settings/integrations` | ○ | Provider catalog, OAuth connections, webhooks |
| `/coming-soon` | ƒ | Honest not-yet-built landing for unimplemented modules |

### Documented-but-nonexistent routes (drift, see gaps §A3)

`/onboarding/company`, `/onboarding/goals`, `/notifications`, `/settings/roles`,
`/settings/ai-providers`, `/invite/[token]`, `/verify-email/[token]`, MFA challenge — all
listed in `docs/ROUTES_AND_SCREENS.md` as `[~]`/`[ ]` but produced no route in the build.

## Backend API surface (119 paths, from live `/openapi.json`)

| Prefix | Paths | Notes |
|---|---|---|
| `/auth` | 6 | signup, login, logout, me, forgot-password, reset-password. No verify-email, no invite-accept. |
| `/organizations` | 3 | current (GET/PATCH), current/members (GET only — no invite/add-member POST) |
| `/tasks`, `/approvals` | 4 | core primitives |
| `/notifications` | 2 | list, mark-read — no dispatch-channel config endpoint |
| `/files` | 2 | upload-url, get |
| `/ai/copilot` | 1 | `/ask` |
| `/knowledge` | 4 | documents (list/create/get/chunks), knowledge-bases |
| `/compliance` | 51 | by far the largest surface — controls, risks, evidence, policies, frameworks, vendors, questionnaires, audits, ai-systems, ai-incidents, processing-activities, dpias, dsars, data-transfers, security-reviews |
| `/security` | 8 | assets, findings, alerts, incidents |
| `/sales` | 11 | accounts, contacts, leads, opportunities, outreach |
| `/support` | 8 | customers, tickets, messages, knowledge-articles, csat, flag-upsell |
| `/automation` | 6 | workflows, runs, resume |
| `/integrations` | 10 | providers, connections, oauth start/callback, refresh/disconnect/health/sync, sync-runs, webhooks/receive |
| `/trust-center` | 5 | items, evidence-requests, public (unauthenticated) |
| `/health` | 2 | health, health/ready |

**Cross-check against frontend**: every backend route group above has at least
list/detail frontend usage EXCEPT: `Policy` (full CRUD API, zero FE), Support
Knowledge Articles (full CRUD API, zero FE page), and the Compliance frameworks/
requirements endpoints (used only internally to populate dropdowns, no standalone
browse page).

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
