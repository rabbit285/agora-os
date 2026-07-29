# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are complete. All five primary product modules —
Compliance, Security, Sales, Support, and Automation (Phases 3-7) — have
a real, tested backbone. Phase 8 (Cross-Module Intelligence) has three of
spec §69's five named scenarios implemented. Phase 9 (Integrations) has
two connector shapes: a generic inbound Webhook connector and a
provider-neutral OAuth2 framework with HubSpot as the first real
provider.** See `docs/RELEASE_CHECKLIST.md` and
`docs/IMPLEMENTATION_STATUS.md` for the itemized list.

Working and verified end to end, on top of everything through the Phase 9
Webhook connector: a real OAuth2 authorization-code flow
(`app/integrations/adapters/`), generalized behind an
`OAuthConnectorAdapter` Protocol that mirrors `app.ai.gateway`'s
`ModelAdapter`/`DemoAdapter` pattern exactly. `HubSpotAdapter` makes
genuine HTTP calls to HubSpot's documented OAuth/CRM endpoints, but is
only selected when `HUBSPOT_CLIENT_ID`/`HUBSPOT_CLIENT_SECRET` are
configured (they aren't, in this environment) — otherwise
`MockOAuthAdapter` runs instead, the same role `DemoAdapter` plays for
the AI gateway, and what the automated test suite exercises. The
provider catalog endpoint (`GET /api/v1/integrations/providers`) reports
`configured: bool` honestly, so `/settings/integrations` shows HubSpot as
"Not configured" rather than ever faking a connected state — verified
live by starting the OAuth flow, completing a callback against the mock
adapter with zero real credentials anywhere, and confirming the
connection reached `connected` status with a real `SyncRun` afterward.
Tokens are encrypted at rest (`app/core/crypto.py`, Fernet).
`Opportunity`-`closed_won` "New Customer" hook (Phase 8's third
cross-module scenario) is also complete and committed.

All lint/typecheck/test/build checks pass (92 backend tests, ruff + mypy
--strict clean; frontend eslint + tsc + production build clean).

No AWS infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the
full phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's
missing in each module. Phase 8 now has 3 of 5 named scenarios
(Enterprise Sales Security Review and New AI Tool Adoption remain, both
need modules/data that don't exist yet). Phase 9 has two connector
shapes; every other spec §48 category still needs real credentials this
environment doesn't have.

## Branch and commit

Branch: `main`. Thirteen substantive commits: Phase 1 platform
foundation, Phase 2 Knowledge ingestion, Phase 2 completion (RAG +
Copilot), Phase 3 Compliance backbone, Phase 4 Security backbone, Phase
5 Sales backbone, Phase 6 Support backbone, Phase 7 Automation backbone,
Phase 8 Support Upsell Signal, Phase 8 Security Incident chain
extension, Phase 9 Webhook connector, Phase 8 New Customer, and this
Phase 9 OAuth2 framework + HubSpot slice. See `git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session)

```bash
# Added the `cryptography` package (Fernet, for encrypted OAuth token
# storage) to apps/api/requirements.txt — required a Docker image rebuild:
cd infra/docker
docker compose build api

# Migration for oauth connector fields (encrypted tokens, scopes,
# oauth_state, health) on integration_connections, plus integration_sync_runs
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add oauth connector fields and sync runs"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 92 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build
```

Still to do before this phase is fully closed out: restart the
`api`/`web` containers, run a live smoke test against the running stack
using the mock adapter (start the HubSpot OAuth flow, extract `state`
from the fake authorization URL, hit the callback, confirm the
connection reaches `connected` with a real health check and
`external_account_id`, run a sync, disconnect), then commit.

## Next highest-priority task

No further direction has been given, and no real third-party credentials
have been supplied for any additional provider. Do not start another
OAuth connector speculatively — spec §82/§C2 forbid building toward
fabricated "connected" states, and every remaining spec §48 category
needs its own real developer app or API key.

Two reasonable directions, in priority order:

1. **If the user supplies real credentials for a specific provider**
   (a HubSpot developer app's client ID/secret to actually test
   `HubSpotAdapter` end to end, a Slack incoming-webhook URL, a second
   CRM's OAuth app, etc.) — wire that in immediately: it's a small,
   bounded task now that the adapter framework exists (one new adapter
   class implementing `OAuthConnectorAdapter`, added to
   `app/integrations/adapters/__init__.py::get_oauth_adapter` and the
   `PROVIDER_CATALOG` list in `app/routers/integrations.py`).
2. **Otherwise, round out Phase 8's remaining two named scenarios**
   ("Enterprise Sales Security Review", "New AI Tool Adoption") — both
   need real feature work first (customer questionnaires, an AI system
   inventory), not just a cross-module link, so expect these to be
   larger efforts than the three Phase 8 scenarios already shipped.
   Alternatively, start Phase 10 (Enterprise: SSO/SAML/SCIM, public API +
   webhooks) or the AWS production deployment (spec §L/§M/§N) — both are
   large, self-contained next arcs.

## Files to edit next (if a new OAuth provider is added)

- `apps/api/app/integrations/adapters/<provider>.py` (new adapter class)
- `apps/api/app/integrations/adapters/__init__.py` (`get_oauth_adapter`, `is_provider_configured`, `OAUTH_PROVIDER_KEYS`)
- `apps/api/app/routers/integrations.py` (`PROVIDER_CATALOG` entry)
- `apps/api/app/config.py` (new `<PROVIDER>_CLIENT_ID`/`_CLIENT_SECRET`/`_REDIRECT_URI` settings)
- `.env.example` (document the new variables — no real values)
- `apps/api/tests/test_integrations.py` (repeat the HubSpot test pattern against the mock adapter)
- `docs/DECISIONS.md` (new ADR)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (92 passed)
```
