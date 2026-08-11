# Apollo Customer OAuth — Implementation Plan

Execution plan for the migration described in
[APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md](APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md),
against the findings in
[APOLLO_OAUTH_MIGRATION_AUDIT.md](APOLLO_OAUTH_MIGRATION_AUDIT.md).

Branch: `integrations/apollo-customer-oauth`.

## Phase 1 — Connection model + configuration

- Extend `IntegrationConnection` with the customer-connection fields
  (architecture §2): `provider_user_email`, `provider_workspace_id`,
  `provider_workspace_name`, `token_type`, `connected_at`, `refreshed_at`,
  `last_success_at`, `last_error_code`, `reauthorization_required_at`,
  `disconnected_at`, `revoked_at`, `version`.
- Alembic migration, additive and nullable only; partial unique index for
  one active Apollo connection per organization.
- `Settings`: `apollo_oauth_client_id`, `apollo_oauth_client_secret`,
  `apollo_oauth_redirect_uri`, `apollo_oauth_authorize_url`,
  `apollo_oauth_token_url`, `apollo_api_base_url`, `apollo_auth_mode`.
- Startup guard: refuse to boot when `apollo_auth_mode="api_key"` and
  `APP_ENV=production`.

## Phase 2 — Apollo OAuth adapter + flow wiring

- `app/integrations/adapters/apollo.py` — `ApolloOAuthAdapter` implementing
  `OAuthConnectorAdapter`. Fragment-aware `authorization_url`; real token
  exchange/refresh; `test_connection` fetching the Apollo user profile;
  no-op `sync`/`revoke` (documented, not faked).
- Register in `_provider_specs()`; add to `PROVIDER_CATALOG`.
- Per-connector RBAC: new `integrations.apollo.manage` permission, granted
  to `org_admin` + `sales_manager`; the four mutating OAuth endpoints
  resolve the required permission per connector at request time.
- Callback: persist granted scopes, Apollo user identity, `connected_at`;
  handle denial/insufficient-permission with clear, safe messaging.

## Phase 3 — Refresh lifecycle

- Version-guarded refresh (architecture §10) preventing concurrent refresh.
- Refresh-on-401 once, then `reauthorization_required`.
- `invalid_grant` → reauthorization required, no further retries.
- Audit events for refreshed / refresh failed / reauthorization required.

## Phase 4 — Tenant-scoped Sales provider

- `ApolloCredential` + `OrganizationApolloCredentialResolver`.
- `ApolloDataProvider(credential_resolver=...)`; Bearer auth; scope checks
  before each operation; `last_success_at` on success.
- `registry.get_provider()` → async, `(db, organization_id, provider_key)`;
  returns demo provider when unconnected; `apollo_status()` derives from the
  org's connection.
- Update all call sites: `lead_finder_service` (3), `enrichment_job_service`
  (3, widening `estimate_enrichment_credits` with `organization_id`),
  `routers/sales_lead_finder` (`/providers`), and the Temporal activity's
  resolution point.

## Phase 5 — Frontend

- Apollo card on `/settings/integrations` with permission-preview dialog
  before redirect; connected user, workspace, granted scopes, connected
  date, last success, customer-credit notice, reconnect/disconnect.
- Lead Finder: not-connected / connected / missing-scope /
  reauthorization-required states; Connect action for authorized users,
  "contact your administrator" otherwise; demo mode stays explicitly labeled.
- Credit confirmation shows the connected workspace being charged.

## Phase 6 — Credit attribution

- `SalesProviderCreditUsage.connection_id` (nullable FK) + migration.
- Record it at the usage write site; surface connection/connected-user in
  the usage dashboard.

## Phase 7 — Tests

Backend: authorization URL + exact redirect URI + requested scopes; state
generation/expiry/mismatch/replay; invalid callback; user denial; Apollo 403
authorization-permission; token exchange success/failure; encrypted storage
and no plaintext token persisted; profile retrieval; expiry; refresh success;
rotating refresh token; concurrent-refresh locking; refresh failure;
401-refresh-and-retry; missing scope; rate limiting; disconnect; reconnect;
RBAC; cross-tenant denial; Temporal credential resolution; usage attribution;
secret redaction; production global-key prohibition.

Frontend: not-connected, connect, permission preview, redirect initiation,
callback success/failure, insufficient Apollo permission, connected state,
connected-user info, granted scopes, missing scope, reauthorization required,
disconnect confirmation, Lead Finder provider status, credit notice,
permission denial.

Playwright: the brief's 16 journeys, driven against the mock adapter — no
real Apollo credits are ever consumed in automated tests.

## Phase 8 — Documentation

`ENVIRONMENT_VARIABLES.md`, `INTEGRATIONS.md`,
`SALES_DATA_PROVIDER_ARCHITECTURE.md`, `SALES_LEAD_FINDER_AUDIT.md`,
`IMPLEMENTATION_STATUS.md`, `KNOWN_LIMITATIONS.md`, `ROUTES_AND_SCREENS.md`,
`RELEASE_CHECKLIST.md`, the three Apollo OAuth docs, `.env.example`,
`.env.test.example`, Render deployment notes, and a new ADR for
customer-owned Apollo connections.

## External prerequisites (blocked on the account owner)

Implementation proceeds against the mock adapter; the following require real
action in Apollo before live verification is possible:

1. Register Agora Origin as an OAuth integration in Apollo (Settings →
   Integrations → API/OAuth registration).
2. Upload the approved Agora Origin logo.
3. Register the exact HTTPS callback URL(s) — separate ones for
   development, staging, and production where supported. Apollo requires
   HTTPS; local development needs an HTTPS tunnel rather than weakened
   callback validation.
4. Request only the six scopes in architecture §4.
5. Securely provide `APOLLO_OAUTH_CLIENT_ID` / `APOLLO_OAUTH_CLIENT_SECRET`.

Until Apollo approves the registration, this integration is **not** claimed
to be approved anywhere in the product or docs.
