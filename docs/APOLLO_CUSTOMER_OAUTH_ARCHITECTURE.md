# Apollo Customer-Connected OAuth — Architecture

The production model: each Agora Origin **customer organization connects its
own Apollo workspace** via OAuth 2.0. Every Apollo search and enrichment
request runs against that customer's Apollo account, permissions, rate
limits, and credits. Agora Origin never supplies Apollo data from one shared
platform key, and never asks a customer to paste an Apollo password or
personal API key.

See [APOLLO_OAUTH_MIGRATION_AUDIT.md](APOLLO_OAUTH_MIGRATION_AUDIT.md) for
what existed before this migration, and
[SALES_DATA_PROVIDER_ARCHITECTURE.md](SALES_DATA_PROVIDER_ARCHITECTURE.md)
for the provider-neutral discovery layer this plugs into.

## 1. Two subsystems, one provider name

`apollo` names two deliberately separate things, in two packages:

| | `app/integrations/` | `app/sales/providers/` |
|---|---|---|
| Protocol | `OAuthConnectorAdapter` | `SalesDataProvider` |
| Apollo class | `ApolloOAuthAdapter` (new) | `ApolloDataProvider` (refactored) |
| Owns | the OAuth token lifecycle: authorize, exchange, refresh, health, disconnect | the capability surface: company/people search, enrichment, decision-makers, credit estimates |
| Stores | `IntegrationConnection` row per organization | nothing — stateless per request |

The Sales adapter **consumes** a token the integrations connection owns. It
never reads `settings.apollo_api_key` in OAuth mode, and never holds a
long-lived credential of its own.

## 2. Connection model

Apollo reuses the existing per-organization `IntegrationConnection`
(`app/integrations/models.py`) with `connector_key="apollo"`, extended with
the fields the brief §6 requires that the generic model didn't already have:

| Field | Status | Purpose |
|---|---|---|
| `id`, `organization_id`, `connector_key`, `status`, `created_at`, `updated_at` | existing | identity + tenancy |
| `created_by` | existing | serves as `connected_by_user_id` |
| `external_account_id` | existing | the Apollo user id that authorized |
| `encrypted_access_token`, `encrypted_refresh_token` | existing | Fernet-encrypted at rest (`app/core/crypto.py`) |
| `token_expires_at`, `scopes` | existing | computed from `expires_in`; granted scopes as returned by Apollo |
| `oauth_state`, `oauth_state_created_at` | existing | single-use CSRF state, 600s TTL |
| `health_status`, `last_health_check_at`, `last_error` | existing | connection health |
| `provider_user_email` | **new** | shown in the connection UI ("Connected Apollo user") |
| `provider_workspace_id`, `provider_workspace_name` | **new** | only populated when Apollo actually returns them — never inferred |
| `token_type` | **new** | as returned by Apollo (`Bearer`) |
| `connected_at`, `refreshed_at`, `last_success_at` | **new** | lifecycle timestamps |
| `last_error_code` | **new** | machine-readable, safe (e.g. `invalid_grant`, `missing_scope`) |
| `reauthorization_required_at`, `disconnected_at`, `revoked_at` | **new** | explicit lifecycle states |
| `version` | **new** | optimistic-concurrency guard for the refresh lock (§10) |

`last_error` is reused as the brief's `last_error_message_safe` — it is
already only ever assigned sanitized, human-readable text, never a raw
provider body.

**One active Apollo connection per organization.** Enforced by a partial
unique index on `(organization_id, connector_key)` where
`connector_key='apollo'` and `disconnected_at IS NULL`. The model keeps a
row per historical connection (disconnect sets `disconnected_at` rather than
deleting), so multi-connection support later is an index change plus a
selection UI, not a destructive redesign. **Documented limitation:** a
second simultaneous Apollo workspace per organization is not supported in
this build.

## 3. OAuth flow

Apollo's real endpoints (per the migration brief §2):

- Authorize: `https://app.apollo.io/#/oauth/authorize`
- Token: `https://app.apollo.io/api/v1/oauth/token`
- API base: `https://api.apollo.io/api/v1`

Authorization request carries `client_id`, `redirect_uri`,
`response_type=code`, `scope`, `state`. Token exchange posts
`grant_type=authorization_code`, `code`, `client_id`, `client_secret`,
`redirect_uri`. Refresh posts `grant_type=refresh_token`, `refresh_token`,
`client_id`, `client_secret`.

Because the authorize URL is a **fragment** route (`#/oauth/authorize`),
query parameters are placed after the fragment (`#/oauth/authorize?...`) —
Apollo's SPA parses them from the fragment. This is why
`ApolloOAuthAdapter.authorization_url()` builds the string explicitly rather
than using `httpx.URL(params=...)` as the other adapters do.

All customer-connected API requests authenticate with
`Authorization: Bearer <customer_access_token>`. **`x-api-key` is never used
for a customer request** — it survives only in the isolated, non-production
legacy mode described in §7.

## 4. Scopes

Requested (least-privilege, matching only what this build implements):

| Scope | Enables |
|---|---|
| `read_user_profile` | identifying the connected Apollo user (required for the callback's profile fetch) |
| `mixed_companies_search` | company search |
| `mixed_people_api_search` | people search, decision-makers |
| `organizations_enrich` | company enrichment |
| `people_match` | person enrichment |
| `api_usage_stats_read` | provider usage dashboard |

No write scopes are requested — this build never creates Apollo sequences,
contacts, accounts, or tasks. Optional signal scopes
(`organizations_job_posting`, `organizations_news_articles`,
`webhook_result_read`) are **not** requested, because no implemented
capability consumes them.

Apollo's **granted** scopes (from the token response) are stored on the
connection and drive capability gating: before any operation, the required
scope is checked against `connection.scopes`. A missing scope disables only
that capability, names it in the UI, and offers reconnection — it never
falls back to a shared credential.

## 5. Credential resolution

`ApolloDataProvider` is constructed with a **credential resolver**, not a key:

```python
ApolloDataProvider(credential_resolver=OrganizationApolloCredentialResolver(db, organization_id))
```

The resolver, on each request: loads the org's active Apollo connection →
verifies status → refreshes the token if it is within the expiry window →
decrypts → returns an `ApolloCredential(access_token, connection_id, scopes)`.
The decrypted token exists only for the duration of the outbound HTTP call.

`registry.get_provider()` becomes async and organization-aware:

```python
await get_provider(db, organization_id=..., provider_key="apollo")
```

It returns the demo provider when the organization has no active connection
— never a shared-key provider.

## 6. Request lifecycle

1. Router resolves `OrgContext` (organization from session + membership,
   never from client input) and checks the operation's RBAC permission.
2. Service resolves the org's Apollo connection through the registry.
3. Required scope for the operation is verified against the granted scopes.
4. Credential resolver returns a fresh access token (refreshing first if needed).
5. Adapter calls Apollo with `Authorization: Bearer <token>`.
6. On `401`, exactly one refresh-and-retry is attempted; a second failure
   marks the connection `reauthorization_required`.
7. Usage is recorded against `(organization_id, connection_id)`.
8. Normalized, provider-neutral records are returned; provenance records the
   provider and connection.

## 7. Auth modes

`APOLLO_AUTH_MODE` (default `oauth`):

- **`oauth`** — the only mode permitted in production. Customer-connected
  Bearer tokens only.
- **`api_key`** — legacy/local-development only. Uses the deployment-wide
  `APOLLO_API_KEY` with `x-api-key`. **A startup guard exits the process** if
  this is set while `APP_ENV=production` — a shared key must never serve
  multi-tenant production traffic.

Demo mode is unchanged and remains explicitly labeled: an organization with
no Apollo connection gets the deterministic demo provider, never fabricated
"live" results.

## 8. Tenant isolation

- `organization_id` is always resolved server-side (`OrgContext`).
- Connection lookups are scoped by `organization_id`; a cross-org
  connection id returns 404.
- Search caches were already keyed by `organization_id`
  (`app/sales/providers/cache.py`) — a per-org credential cannot cause a
  cross-tenant cache hit.
- No global/shared Apollo client object holds a mutable customer token; the
  provider is constructed per request with a resolver bound to one org.
- Temporal activities receive only `job_id`; the activity loads the job row,
  reads its `organization_id`, and resolves that org's connection inside the
  worker. **No token ever enters a workflow argument or workflow history.**

## 9. Credit ownership

All Apollo credit consumption belongs to the connected customer's Apollo
workspace. Agora Origin maintains no credit pool and never deducts one.
`SalesProviderCreditUsage` gains a nullable `connection_id` so usage is
attributable to a specific connection (and therefore to a specific connected
Apollo user), alongside the existing organization, initiating Agora user,
operation, estimated/actual credits, record count, and success flag.

Estimates remain explicitly labeled estimates: Apollo determines final cost
from the data actually returned, so the confirmation dialog shows the
estimate, the connected workspace that will be charged, and — when a real
number cannot be computed honestly — "Estimate unavailable" rather than a
fabricated figure. Confirmation before credit-spending operations stays
mandatory.

## 10. Token refresh and concurrency

Refresh happens (a) proactively when the token is within 5 minutes of
expiry, and (b) reactively, exactly once, on an eligible `401`.

Concurrent refreshes for one connection are prevented by an
**optimistic-concurrency version check**: a refresh reads `version`, and its
`UPDATE` is conditioned on that same value. The loser of a race sees zero
rows updated, discards its own token result, and re-reads the row — which by
then holds the winner's fresh token. This is portable across SQLite (tests)
and Postgres (production), unlike `SELECT ... FOR UPDATE`, and avoids
introducing a distributed-lock dependency for a single-row invariant.

Permanent refresh failure (`invalid_grant`) sets
`reauthorization_required_at` and status `reauthorization_required`; no
further Apollo calls are attempted and the UI prompts reconnection. Refresh
is never retried indefinitely.

## 11. Connection states

`not_connected`, `connecting`, `connected`, `healthy`, `refreshing`,
`degraded`, `rate_limited`, `missing_scope`, `reauthorization_required`,
`failed`, `disabled`, `disconnected`.

Provider-failure mapping: `401` → one refresh + retry, else
reauthorization required; `403` → distinguish missing scope from plan
restriction from Apollo permission, no repeated retries; `429` → respect
`Retry-After`, show rate-limited, controlled backoff; `invalid_grant` →
reconnection required. Raw provider responses are never surfaced.

## 12. Disconnect

Disconnect requires `integrations.apollo.manage` and explicit confirmation.
It clears both encrypted tokens, sets `disconnected_at` and status
`disconnected`, stops new Apollo operations, and writes an audit event.
It **preserves** historical provenance, usage records, saved Accounts and
Contacts, lists, and saved searches — disconnecting a data provider never
deletes customer-created Sales records.

Apollo publishes no token-revocation endpoint, so `revoke()` is an honest
no-op that clears local tokens only; this is disclosed rather than faked.

## 13. Secrets

`APOLLO_OAUTH_CLIENT_SECRET` exists only on the backend, is never a
`NEXT_PUBLIC_*` variable, is never logged, never returned to the frontend,
and never committed. Tokens are Fernet-encrypted at rest and absent from
every API response schema, all audit metadata, all Temporal input, and all
logs. Authorization codes are consumed server-side and stripped from the
final browser URL by the callback's redirect.
