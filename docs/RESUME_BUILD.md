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
its first connector implemented.** See `docs/RELEASE_CHECKLIST.md` and
`docs/IMPLEMENTATION_STATUS.md` for the itemized list.

Working and verified end to end, on top of everything from Phase 1-9's
webhook connector: `app/sales/service.py::close_opportunity_won` — the
"New Customer" cross-module scenario (spec §69). The first time a Sales
`Opportunity` transitions to `closed_won`, it creates a real Support
`Customer` (using the account's earliest Contact for the required email)
and a `core.Task` due in 7 days — spec's nine-step chain collapsed into
two existing primitives (ADR-0025). `Opportunity.onboarding_customer_id`
is both the link and the idempotency guard: reopening and re-winning the
same opportunity never creates a second customer. If the account has no
Contact, the stage change still succeeds but onboarding is honestly
skipped rather than fabricating a customer with no real email.
`/sales/accounts/[id]` shows an "Onboarded as a Support customer" link on
any opportunity once this fires.

All lint/typecheck/test/build checks pass (85 backend tests, ruff + mypy
--strict clean; frontend eslint + tsc + production build clean).

No AWS infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the
full phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's
missing in each module. Phase 8 now has 3 of 5 named scenarios
(Enterprise Sales Security Review and New AI Tool Adoption remain, both
need modules/data that don't exist yet). Phase 9 still has only the
Webhook connector — every other spec §48 category needs real third-party
OAuth credentials this environment doesn't have.

## Branch and commit

Branch: `main`. Twelve substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, Phase 2 completion (RAG + Copilot), Phase 3
Compliance backbone, Phase 4 Security backbone, Phase 5 Sales backbone,
Phase 6 Support backbone, Phase 7 Automation backbone, Phase 8 Support
Upsell Signal, Phase 8 Security Incident chain extension, Phase 9 Webhook
connector, and this Phase 8 "New Customer" slice. See `git log` for exact
SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session, on top of Phase 9's webhook connector)

```bash
cd infra/docker
docker compose ps   # confirm the stack from earlier sessions is still up

# Migration for sales_opportunities.onboarding_customer_id
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add opportunity onboarding_customer_id"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 85 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build
```

Still to do before this slice is fully closed out: restart the
`api`/`web` containers, run a live curl-based smoke test proving the
hook works against the real running stack (create an account + contact +
opportunity, transition it to `closed_won`, confirm the Support Customer
and onboarding Task both appear through their own real endpoints), then
commit — after which this session continues immediately into Phase 9's
OAuth connector framework (see below), per explicit instruction to not
stop between the two tasks.

## Next highest-priority task: Phase 9 — provider-neutral OAuth connector framework

Building now, in the same session: a real OAuth2 authorization-code flow
connector framework (spec §49's Connector Contract), generalized beyond
the Phase 9 Webhook connector, with **HubSpot** as the first real
provider. Concretely:

1. **Encrypted token storage**: a small `app/core/crypto.py` (Fernet)
   encrypts `access_token`/`refresh_token` at rest on
   `IntegrationConnection`. Key comes from a new `TOKEN_ENCRYPTION_KEY`
   setting; if unset, dev/test derive a key from the existing
   `SECRET_KEY` so the app still boots without a paid/external key
   (spec §C2), but production must set a dedicated key (documented in
   `.env.example` and `docs/KNOWN_LIMITATIONS.md`).
2. **Adapter interface** (`app/integrations/adapters/base.py`): an
   `OAuthConnectorAdapter` Protocol — `authorization_url()`,
   `exchange_code_for_tokens()`, `refresh_access_token()`,
   `test_connection()` (health), `sync()`, `revoke()` — mirroring the
   existing `ModelGateway`/`ModelAdapter` pattern (Demo vs real
   providers) already used for the AI gateway.
3. **HubSpot adapter**: real HTTP calls (`httpx`) to HubSpot's OAuth
   endpoints, gated behind `HUBSPOT_CLIENT_ID`/`HUBSPOT_CLIENT_SECRET`.
4. **Mock adapter**: used whenever HubSpot isn't configured (this
   environment has no real HubSpot app) — same role as the AI gateway's
   DemoAdapter, and also what tests exercise via dependency override, not
   real network calls.
5. **Provider catalog endpoint**: `GET /api/v1/integrations/providers`
   reports `configured: bool` per provider (mirrors `/settings/ai-providers`'s
   existing configured/not-configured pattern) so the frontend can
   honestly show HubSpot as "Not configured" until real credentials are
   supplied — never a fake "connected" state.
6. **Routes**: OAuth start (session-authed, generates CSRF `state`),
   callback (no session — the redirect comes from HubSpot, not the
   logged-in browser tab necessarily; state alone identifies the pending
   connection, same "capability token" pattern as the webhook receiver),
   refresh, health check, disconnect/revoke, and a synchronous "sync now"
   endpoint that logs a `SyncRun` row (a genuine but simplified sync —
   not a durable Temporal job in this slice, documented as a known
   limitation).
7. Frontend: extend `/settings/integrations` with a HubSpot card showing
   configured/not-configured, Connect/Disconnect, health status, and
   sync history.
8. Tests against the mock adapter (dependency-overridden, same pattern
   as `get_ingestion_starter` in `tests/conftest.py`): full OAuth
   start→callback→connected flow, refresh, disconnect, tenant isolation.
9. `.env.example`: add `HUBSPOT_CLIENT_ID`, `HUBSPOT_CLIENT_SECRET`,
   `HUBSPOT_REDIRECT_URI`, `TOKEN_ENCRYPTION_KEY` — no real values, no
   secrets requested in chat.
10. Live smoke test against the running stack using the mock adapter
    (no real HubSpot credentials exist in this environment) — start the
    flow, "callback" with a fabricated code, confirm the connection
    reaches `connected` status, confirm disconnect clears tokens.
11. Update `docs/DATABASE_MODEL.md`, `docs/DOMAIN_MODEL.md`,
    `docs/IMPLEMENTATION_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`,
    `docs/DECISIONS.md` (ADR-0026), `docs/KNOWN_LIMITATIONS.md`,
    `docs/ENVIRONMENT_VARIABLES.md`, `docs/ROUTES_AND_SCREENS.md`,
    `docs/RELEASE_CHECKLIST.md`, and this file when done.

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (85 passed)
```
