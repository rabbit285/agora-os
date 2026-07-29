# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are complete. All five primary product modules —
Compliance, Security, Sales, Support, and Automation (Phases 3-7) — have
a real, tested backbone. Phase 8 (Cross-Module Intelligence) has three of
spec §69's five named scenarios fully implemented, plus a partial fourth.
Phase 9 (Integrations) now has two connector shapes complete: a generic
inbound Webhook connector, and a provider-neutral OAuth2 framework with
six real (credential-gated) adapters — HubSpot, Google, Microsoft, GitHub,
Slack, Salesforce. Compliance also has an AI System Inventory (EU AI Act
risk tiers).** See `docs/RELEASE_CHECKLIST.md` and
`docs/IMPLEMENTATION_STATUS.md` for the itemized list.

Most recent slice: **completing the OAuth integration framework**
(explicitly requested — the user confirmed real credentials will be
supplied later via environment variables, and asked for everything
credential-free to be finished now). What changed, all in
`apps/api/app/integrations/` and `apps/worker/`:

- **Five new real adapters** alongside HubSpot —
  `adapters/{google,microsoft,github,slack,salesforce}.py` — each a
  genuine implementation against that provider's documented OAuth/API
  endpoints (real HTTP calls, never a stub), none exercised end to end
  here (no real developer app for any of them, same as HubSpot). Adapter
  selection moved from HubSpot-only `if` branches into one registry table
  (`adapters/__init__.py::_provider_specs`) — adding a seventh provider is
  one adapter module + one table entry + three env vars, not a structural
  change (ADR-0028).
- **Permission preview**: every adapter carries a `SCOPES` class
  attribute; the provider catalog (`GET /api/v1/integrations/providers`)
  exposes it per provider, and the frontend shows the exact scopes a
  Connect click will request *before* the user clicks "Authorize" — even
  for unconfigured providers.
- **Sync now runs as a durable Temporal workflow**
  (`IntegrationSyncWorkflow` + `execute_integration_sync_activity`,
  `apps/worker/`), not inline in the request — closing the gap
  ADR-0026/`KNOWN_LIMITATIONS.md` flagged. `create_sync_run` (writes the
  `running` row) and `execute_sync_run` (the actual provider call) are
  split the same way Knowledge's `ingest_document` is split from
  `DocumentIngestionWorkflow`, so tests exercise the real logic without a
  live Temporal connection.
- **Audit logging for the full lifecycle**: refresh (success + failure),
  sync (started/succeeded/failed), disconnect (including whether the
  provider's own revoke call succeeded) — previously only connect/
  disconnect were logged. Every adapter failure is caught and normalized
  to a 422, never an unhandled 500.
- **`.env.local` support** (`Settings` reads `.env` then `.env.local`,
  later wins) and a new repo-root `.dockerignore` so neither file can ever
  land in a Docker build context. `docs/ENVIRONMENT_VARIABLES.md` commits
  to a specific (not yet built) AWS production shape: Secrets Manager +
  ECS `secrets` injection + least-privilege IAM task roles for credentials,
  SSM Parameter Store for non-secret config — a design contract for
  whoever builds Phase 10/AWS, not implemented infrastructure.
- **Frontend test infrastructure added from scratch**: Vitest + React
  Testing Library (`apps/web/vitest.config.mts`, `npm test`) — nothing
  existed before this slice. 5 tests cover the provider catalog, the
  permission-preview disclosure gating the real OAuth-start call, the
  connected-connection controls, in-flight-sync button disabling, and
  disconnect.

All lint/typecheck/test/build checks pass: **137 backend tests** (was
101), ruff + mypy --strict clean; frontend eslint + tsc + production build
clean; **5 new frontend tests**, all passing.

No AWS infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the
full phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's
missing in each module. Phase 8 still has 3 full + 1 partial of 5 named
scenarios (Enterprise Sales Security Review remains, needs customer
questionnaires that don't exist). Phase 9's OAuth framework now covers six
providers; every other spec §48 category still needs real credentials
this environment doesn't have.

## Branch and commit

Branch: `main`. Fifteen substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, Phase 2 completion (RAG + Copilot), Phase 3
Compliance backbone, Phase 4 Security backbone, Phase 5 Sales backbone,
Phase 6 Support backbone, Phase 7 Automation backbone, Phase 8 Support
Upsell Signal, Phase 8 Security Incident chain extension, Phase 9 Webhook
connector, Phase 8 New Customer, Phase 9 OAuth2 framework + HubSpot, the
AI System Inventory slice, and this OAuth framework completion slice. See
`git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

Docker Desktop on this machine has intermittently stopped mid-session more
than once. If `docker compose` commands start failing with `failed to
connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`,
launch it directly (`"/c/Program Files/Docker/Docker/Docker Desktop.exe"`)
and poll `docker info` every few seconds until it responds (~10-30s);
containers restart automatically once the daemon is back.

## Exact commands already run (this session)

```bash
# No new Alembic migration needed this slice — the six-provider registry,
# Temporal sync split, and audit logging are all code-level changes; the
# existing IntegrationConnection/SyncRun schema already had every column
# needed.

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 137 passed

# Frontend checks (all green)
cd apps/web
npm install -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/dom @testing-library/jest-dom @testing-library/user-event
npx tsc --noEmit
npx eslint .
npx vitest run   # -> 5 passed
npm run build
```

Live smoke test completed against the running stack: started a **Slack**
OAuth flow (not HubSpot, to prove the framework is genuinely
provider-neutral), completed the mock callback, triggered "sync now",
confirmed it ran through `IntegrationSyncWorkflow` on the real worker
(`docker compose logs worker` showed the activity completing), refreshed
the token, disconnected, and confirmed `audit_events` has the full
`integrations.oauth.started/connected/refreshed/disconnected` and
`integrations.sync.started/succeeded` trail.

This surfaced one real bug, now fixed: the **worker's Docker image had
never been rebuilt** since `cryptography` was added to
`requirements.txt` earlier this session (for Fernet token encryption) —
the worker never needed that import before `execute_integration_sync_activity`
existed, so the gap was latent and harmless until this slice. First sync
attempt failed with `ModuleNotFoundError: No module named 'cryptography'`,
retrying indefinitely (Temporal's default unlimited-retry behavior, same
as the pre-existing `DocumentIngestionWorkflow` activities — no retry
policy override exists for either, consistent with established
precedent). Fixed with `docker compose build worker`; the orphaned
in-flight retry then self-healed on its own next attempt once the image
was current (and correctly finalized as `failed` with "Connection has no
stored access token", since the connection had been disconnected in the
meantime — the honest-failure path working exactly as designed). **If a
future slice adds a new worker activity with a new third-party
dependency, remember to rebuild the worker image, not just the api
image** — they share `requirements.txt` but are built and cached
separately.

## Next highest-priority task

The user has explicitly asked to continue automatically into the
remaining credential-free product work after the OAuth foundation:
**Privacy workflows, then AI Incidents**, in that order — both
self-contained, credential-free slices extending existing backbones
(Compliance), not inventing a new module.

1. **Privacy workflows** (spec §13's RoPA / DPIA / DSAR): a Record of
   Processing Activities register (`ProcessingActivity` — organization's
   own data-processing catalog, tenant-scoped, unlike Compliance's global
   Framework/Requirement catalog), Data Protection Impact Assessments
   (`DPIA`, likely linked to a `ProcessingActivity` and gated similarly to
   the AI System Inventory's Approval gate — a high-risk processing
   activity plausibly should require sign-off the same way a high-risk AI
   system does, ADR-0027's pattern reused a third time), and Data Subject
   Access Requests (`DSAR` — an intake + fulfillment-status workflow,
   spec's DSAR portal). Look for a real cross-module hook rather than
   inventing one speculatively (e.g., does a DSAR plausibly relate to
   Support tickets or Sales contacts holding the data subject's PII?) —
   only wire one if it's genuine, per spec §80/§82.
2. **AI Incidents**: an incident log for the AI systems the Inventory
   already tracks (`AIIncident`, likely mirroring `SecurityIncident`'s
   shape: severity, status, linked `AISystem`) — completes AI Governance's
   near-term scope now that the Inventory (Phase 3 extension) exists to
   link against.
3. **Enterprise Sales Security Review** (spec §69's last named
   cross-module scenario) needs customer questionnaires built first — a
   larger, self-contained feature, not just a cross-module link.
4. **If the user supplies real credentials** for a specific provider (any
   of the six adapters, or SSO/IdP metadata for Phase 10) — wire that in
   immediately; these are now small, bounded tasks given the existing
   adapter framework / RBAC groundwork.
5. Phase 10 (Enterprise: SSO/SAML/SCIM, public API + webhooks) or the AWS
   production deployment (spec §L/§M/§N) — both are large, self-contained
   next arcs, but SSO needs a real IdP and AWS deployment needs real cloud
   spend, so treat starting either as a business decision to confirm
   first, not something to infer from a bare "go on."

## Files to edit next (Privacy workflows)

- `apps/api/app/compliance/models.py` (new `ProcessingActivity`, `DPIA`,
  `DSAR` models — or a new `apps/api/app/privacy/` module if the scope
  justifies a standalone module rather than extending `compliance/`;
  decide based on how spec §13 frames it relative to §12)
- `apps/api/app/compliance/service.py` (or `privacy/service.py`) — creation,
  any real cross-module hook, DPIA approval gating if warranted
- schemas + router + migration + tests, following the AI System
  Inventory's exact pattern (ADR-0027) as the template
- `apps/web/lib/types.ts`, new `apps/web/app/(app)/compliance/...` (or
  `.../privacy/...`) pages
- `docs/DECISIONS.md` (new ADR)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (137 passed)
cd ../../apps/web && npx vitest run   # confirm still green (5 passed)
```
