# Apollo OAuth Migration — Audit

Inspection performed before any implementation, per the migration brief. This
document reports exactly where the current build depends on a single,
deployment-wide Apollo credential, and what already exists in the codebase
that the OAuth migration can reuse rather than reinvent.

## 1. Where the global API key is used today

| Concern | Location |
|---|---|
| The credential itself | `apps/api/app/config.py` — `Settings.apollo_api_key`, env var `APOLLO_API_KEY`, one value for the whole deployment. |
| Auth header | `apps/api/app/sales/providers/apollo.py` — `ApolloDataProvider._headers()` sends `x-api-key: <APOLLO_API_KEY>` on every request. |
| Credential injection | `apps/api/app/sales/providers/registry.py` — `get_provider()` constructs `ApolloDataProvider(api_key=settings.apollo_api_key)` fresh on every call. No `organization_id` parameter exists anywhere in this function's signature. |
| Configured/status check | `registry.is_apollo_configured()` / `registry.apollo_status()` — both read `settings.apollo_api_key` directly; "connected" today means only "a key is present in this deployment's environment," never "this organization has authorized anything." |
| Every call site | `apps/api/app/sales/lead_finder_service.py:70,120,163` (`search_companies`, `search_people`, `find_decision_makers`), `apps/api/app/sales/enrichment_job_service.py:70,101,151` (credit estimate, per-record enrichment), `apps/api/app/routers/sales_lead_finder.py:222,231,232,237,239` (`/providers` listing). All seven call `get_provider()`/`is_apollo_configured()`/`apollo_status()` with zero org context — the same key answers every organization's request. |
| Provider status enum | `apps/api/app/sales/providers/status.py` — already carries `READY_TO_CONNECT`, `DISABLED`, `REVOKED` values explicitly commented `"Reserved for a future per-organization credential model — not reachable with today's single deployment-wide APOLLO_API_KEY."` This migration is what makes them reachable. |
| Provider status UI | `apps/web/app/(app)/sales/lead-finder/provider-status-card.tsx` — docstring: *"Deliberately not the OAuth IntegrationCard — Apollo is a single deployment-wide API key, not a per-organization connection, so there's no Connect/Disconnect/Revoke action here, just an honest read-only status."* No connect/disconnect UI exists for Apollo anywhere today. |
| Temporal boundary | `apps/api/app/sales/workflow_client.py` + `apps/worker/worker/activities.py` — bulk enrichment/import workflows pass only `job_id`; the activity re-derives provider access by calling the same global `get_provider()` inside the worker process. No credential crosses the Temporal boundary today (good — nothing to unwind here), but the activity's re-derivation point is exactly where per-org resolution must be added. |
| Cache keys | `apps/api/app/sales/providers/cache.py` — `build_cache_key()` already includes `organization_id` as the first key segment, with an explicit docstring calling this out as the tenant-isolation mechanism. **No change needed** — search-result caching was already organization-scoped even though the credential wasn't. |
| Naming collision | `apps/api/app/integrations/` already has an unrelated `Apollo`-free set of OAuth connectors (HubSpot, Google, Microsoft, GitHub, Slack, Salesforce, Zendesk, Pipedrive, Intercom). This migration adds `connector_key="apollo"` as a tenth entry in that same generic framework — it is a different subsystem from `app.sales.providers.apollo`, which continues to exist as the actual search/enrich adapter, now credential-resolved through the new connection instead of `settings.apollo_api_key`. |

## 2. What already exists and will be reused, not rebuilt

The repo already runs a real, working, provider-neutral **OAuth2
authorization-code framework** for nine other connectors
(`apps/api/app/integrations/`). It already implements almost everything
sections 6–11 and 20–22 of the migration brief ask for:

- **Connection model** — `IntegrationConnection`
  (`apps/api/app/integrations/models.py`): per-organization row,
  `encrypted_access_token`/`encrypted_refresh_token` (Fernet, `app/core/crypto.py`),
  `token_expires_at`, `scopes` (JSON), `external_account_id`, single-use
  `oauth_state`/`oauth_state_created_at` (10-minute TTL), `health_status`,
  `last_health_check_at`, `last_error`, `created_by`. This is extended
  (not replaced) for Apollo — see the architecture doc §2.
- **State protection** — cryptographically random (`secrets.token_urlsafe(32)`),
  stored on the connection row itself (not a cookie — the callback has no
  session), one-time (cleared on use), 600-second expiry, checked before any
  token exchange.
- **Connect/callback endpoints** —
  `POST /api/v1/integrations/connections/oauth/{provider}/start` and
  `GET /api/v1/integrations/connections/oauth/{provider}/callback`
  (`apps/api/app/routers/integrations.py`) already do everything the brief's
  §7/§8 ask for: server-side org/membership resolution via `OrgContext`,
  state generation/validation/expiry/one-time-use, server-to-server code
  exchange, token encryption, upsert, audit event, redirect to an
  allow-listed `settings.app_url` page with the sensitive code/state
  stripped from the final URL.
- **Adapter protocol** — `OAuthConnectorAdapter`
  (`apps/api/app/integrations/adapters/base.py`): `authorization_url`,
  `exchange_code_for_tokens`, `refresh_access_token`, `test_connection`,
  `sync`, `revoke`. Apollo's real OAuth endpoints (brief §2) map cleanly
  onto the first four; `sync` has no Apollo equivalent (Apollo is
  search/enrich, not object sync) and is implemented as an honest no-op;
  `revoke` is also a no-op, since Apollo's documentation does not publish a
  token-revocation endpoint — inventing one is explicitly prohibited by the
  brief (§18).
- **Refresh-before-expiry** — `ensure_fresh_access_token()`
  (`apps/api/app/integrations/service.py`) already refreshes 5 minutes
  before `token_expires_at`, before every use. No refresh-on-401 exists yet
  for any provider; this migration adds it for Apollo specifically (brief
  §10/§11), since Apollo is the first provider this build actually drives
  live traffic through.
- **No concurrent-refresh lock** — confirmed absent (no `SELECT ... FOR
  UPDATE`, `asyncio.Lock`, or advisory lock anywhere in `app/integrations`).
  This is a real gap the brief explicitly calls out (§10); the migration
  adds one for Apollo via an optimistic-concurrency `version` column (see
  architecture doc §2 and §10).
- **Audit trail** — `app/audit/service.py::record_event`, already called
  for `integrations.oauth.started/connected/refreshed/refresh_failed/disconnected`
  with hand-curated, secret-free `after_state` dicts (never a token, never
  a raw provider payload). Apollo reuses the exact same action strings.
- **Tenant isolation** — `OrgContext`/`require_permission`
  (`apps/api/app/dependencies.py`) resolve `organization_id` from the
  session + `Membership` table server-side; a spoofed `X-Organization-Id`
  for an org the caller isn't a member of 403s before any handler code
  runs. `_get_org_connection()` in the integrations router additionally
  404s any connection-id lookup that resolves to a different org's row.
  Both patterns are reused verbatim for Apollo.
- **Existing tests to model new ones on** —
  `apps/api/tests/test_integrations.py` already has a generic-provider proof
  test (`test_generic_oauth_flow_works_for_a_non_hubspot_provider`, run
  against `google` purely by changing the `connector_key` string), state
  validation tests, refresh/health/sync/disconnect lifecycle tests, RBAC
  denial tests, audit-event tests, and a cross-tenant-connection-404 test —
  every one of these is cloned for `apollo` rather than invented fresh.

## 3. What genuinely does not exist yet and must be built

1. **A real Apollo OAuth adapter** (`ApolloOAuthAdapter`) — no code
   anywhere calls `https://app.apollo.io/#/oauth/authorize` or
   `https://app.apollo.io/api/v1/oauth/token` today. Apollo's existing
   in-repo integration (`app/sales/providers/apollo.py`) is a **different**
   API-key-based adapter for a **different** Protocol (`SalesDataProvider`,
   search/enrich — not `OAuthConnectorAdapter`, sync).
2. **Per-organization credential resolution inside the Sales provider
   registry.** `registry.get_provider()` must become async, take
   `db`/`organization_id`, look up the org's `apollo` `IntegrationConnection`,
   and hand `ApolloDataProvider` a credential resolver instead of a static
   key. This is the seam `SalesProviderStatus.READY_TO_CONNECT`/`DISABLED`
   were already reserved for.
3. **`ApolloDataProvider` must accept a credential resolver, not a raw
   key** — today's `__init__(self, *, api_key: str)` bakes in exactly one
   auth mode. The brief's required shape
   (`ApolloProvider(credential_resolver=...)`) replaces this.
4. **Widening `estimate_enrichment_credits`** to receive `organization_id`
   — the one call site in `enrichment_job_service.py` that doesn't already
   have it in scope from its caller.
5. **A `integrations.apollo.manage` RBAC permission** distinct from the
   generic `integrations.connections.manage` (which is Ops/Automation-owned
   per `ROLE_PERMISSION_GRANTS` and is *not* granted to `sales_manager`) —
   needed because Apollo is a Sales-owned data connection, and the existing
   generic OAuth router endpoints check one fixed permission string per
   route via `Depends(require_permission(...))`, evaluated at route-registration
   time, not per-provider at request time. A small per-connector permission
   lookup is added to the four mutating endpoints (`start`, `refresh`,
   `disconnect`, `health`) so Apollo can be gated separately.
6. **Apollo connection card in the frontend Integrations page** — the
   generic `OAuthConnectionCard` component already renders status/scopes/
   external-account-id/disconnect for every other provider; Apollo is added
   to `PROVIDER_CATALOG` and gets a permission-preview dialog before the
   OAuth redirect (brief §14), which no existing provider has yet.
7. **Lead Finder UI states** for not-connected / connected / missing-scope
   / reauthorization-required, replacing today's single read-only
   `ProviderStatusCard`.
8. **Credit-usage attribution to a specific connection** — today
   `SalesProviderCreditUsage` records `organization_id` but not which
   connection (or which connected Apollo user) spent the credits; a
   nullable `connection_id` FK is added.
9. **A guarded legacy mode** (`APOLLO_AUTH_MODE=oauth|api_key`, default
   `oauth`) with a startup check that refuses to boot with `api_key` mode
   enabled while `APP_ENV=production` — today there is no mode flag at all;
   the single key is unconditionally the only path.

## 4. Explicit non-goal confirmed by this audit

Apollo's search-result **cache** (`app/sales/providers/cache.py`) and
**Temporal workflow arguments**
(`app/sales/workflow_client.py`/`apps/worker/worker/activities.py`) were
already organization-scoped/credential-free before this migration — both
are called out here specifically so the implementation does not spend time
"fixing" something that was already correct.
