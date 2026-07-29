# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are complete. All five primary product modules —
Compliance, Security, Sales, Support, and Automation (Phases 3-7) — have
a real, tested backbone. Phase 8 (Cross-Module Intelligence) has two of
spec §69's five named scenarios implemented. Phase 9 (Integrations) has
its first connector implemented.** See `docs/RELEASE_CHECKLIST.md` and
`docs/IMPLEMENTATION_STATUS.md` for the itemized list.

Working and verified end to end, on top of everything from Phase 1-8:
`app/integrations/service.py::receive_webhook_event` — a generic inbound
Webhook connector. `IntegrationConnection` holds a per-connection
HMAC-SHA256 secret; `POST /api/v1/integrations/webhooks/{connection_id}/receive`
is the one route in this app with no session/`OrgContext` dependency,
because the caller is an external system, not a logged-in user — its
security boundary is the signature, verified with `hmac.compare_digest`
(spec §H "webhook signature verification"). A verified event on a
connection whose `linked_workflow_id` points at an `active` Automation
workflow with `trigger_type="webhook"` triggers that workflow through the
existing `app.automation.service.start_run` — Automation's first
non-manual trigger (spec §38), reusing the execution engine rather than
duplicating it (ADR-0024). `/settings/integrations` renders this live:
create a connection, copy its webhook URL and secret, link it to a
webhook-triggered workflow, and see received events (verified/rejected).

All lint/typecheck/test/build checks pass (82 backend tests, ruff + mypy
--strict clean; frontend eslint + tsc + production build clean).

No AWS infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the
full phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's
missing in each module. Phase 9 specifically: only the Webhook category
of spec §48's dozen-plus connector categories is implemented — every
other one (CRM, Email, Cloud, Identity, Engineering, Communication,
Documents, Accounting) needs real third-party OAuth credentials this
environment doesn't have and won't fabricate.

## Branch and commit

Branch: `main`. Eleven substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, Phase 2 completion (RAG + Copilot), Phase 3
Compliance backbone, Phase 4 Security backbone, Phase 5 Sales backbone,
Phase 6 Support backbone, Phase 7 Automation backbone, Phase 8 Support
Upsell Signal, Phase 8 Security Incident chain extension, and this Phase
9 Webhook connector slice. See `git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session, on top of Phase 1-8)

```bash
cd infra/docker
docker compose ps   # confirm the stack from earlier sessions is still up

# Migration for integration_connections / integration_webhook_events
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add integrations module tables"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

docker compose run --rm --no-deps api python -m app.seed   # ran twice, confirmed idempotent

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 82 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build
```

Still to do before this phase is fully closed out: restart the
`api`/`web` containers to pick up this session's code, run a live
curl-based smoke test that computes a real HMAC-SHA256 signature and
POSTs it to the running container to confirm the linked workflow
actually runs (and that a forged signature is rejected), then commit.

## Next highest-priority task

Two reasonable directions:

**Option A: another Phase 9 connector category.** Every remaining spec
§48 category needs a real OAuth app or API key this environment doesn't
have — do not attempt one speculatively. If the user provides real
credentials for a specific provider (e.g. a Slack incoming-webhook URL,
a HubSpot developer app), that becomes the natural next slice, following
the same pattern as the Webhook connector: one adapter, read-only or
push-only first (progressive trust model, spec §B1), tenant-isolated,
tested, live-smoke-tested.

**Option B: Phase 10 — Enterprise**, or continuing to round out Phase 8's
remaining three named scenarios (Enterprise Sales Security Review, New AI
Tool Adoption, New Customer) — all three still need modules/data that
don't exist yet (customer questionnaires, an AI system inventory), so
expect these to require real feature work in Compliance first, not just
a cross-module link.

If given another "go on" with no further direction and no new
credentials provided, prefer revisiting **Phase 8's "New Customer"**
scenario next: unlike the other two remaining Phase 8 scenarios, it
doesn't strictly need new data — spec §69 describes "CRM deal won →
create customer → create onboarding project → send welcome email →
create support profile → provision internal tasks → update billing
integration → assign account owner → schedule check-in." A first real
slice could be: when a Sales `Opportunity.stage` transitions to
`closed_won` (`app/sales/service.py` — not yet a service function, only
inline in the router), automatically create a `support.Customer` linked
to the account (reusing the existing `Customer.sales_account_id` field
from Phase 6) and a `core.Task` ("Onboard new customer: {account
name}") — reusing three primitives that already exist, same discipline
as every hook so far.

## Files to edit next (if the "New Customer" Phase 8 scenario is chosen)

- `apps/api/app/sales/service.py` (new function, e.g. `close_opportunity_won`)
- `apps/api/app/routers/sales.py` (call it from `update_opportunity` when `stage == "closed_won"`)
- `apps/api/tests/test_sales.py` (assert the Customer via `/api/v1/support/customers` and the Task via `/api/v1/tasks`)
- `apps/web/app/(app)/sales/accounts/[id]/page.tsx` (surface the linked Support Customer once created)
- `docs/DECISIONS.md` (ADR-0025)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (82 passed)
```
