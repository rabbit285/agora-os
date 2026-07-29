# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are complete. All five primary product modules —
Compliance, Security, Sales, Support, and Automation (Phases 3-7) — have
a real, tested backbone. Phase 8 (Cross-Module Intelligence) has two of
spec §69's five named scenarios implemented.** See
`docs/RELEASE_CHECKLIST.md` and `docs/IMPLEMENTATION_STATUS.md` for the
itemized list.

Working and verified end to end, on top of everything from Phase 1-7:

1. `app/support/service.py::flag_upsell_signal` — flagging a support
   ticket creates a real `sales.Lead` and a `core.Notification` to the
   linked account's owner (spec §69 "Support Upsell Signal", ADR-0022).
2. `app/secops/service.py::create_incident` — a `critical`-severity
   incident (which already auto-created a linked Compliance `Risk` since
   Phase 4, ADR-0018) now *also* creates a response `core.Task` and, if
   the incident has an owner, notifies them via `core.Notification` —
   completing spec §69's "Security Incident" chain by extending the same
   hook rather than adding a new one (ADR-0023). `/security/incidents/[id]`
   renders both the linked Risk and the linked Task.

All lint/typecheck/test/build checks pass (75 backend tests, ruff + mypy
--strict clean; frontend eslint + tsc + production build clean).

No AWS infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the
full phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's
missing in each module. Phase 8 specifically: 2 of spec §69's 5 named
scenarios are done (Enterprise Sales Security Review, New AI Tool
Adoption, and New Customer remain, and all three need modules/data that
don't exist yet — customer questionnaires, an AI system inventory). The
AI Copilot still only retrieves from Knowledge documents.

## Branch and commit

Branch: `main`. Ten substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, Phase 2 completion (RAG + Copilot), Phase 3
Compliance backbone, Phase 4 Security backbone, Phase 5 Sales backbone,
Phase 6 Support backbone, Phase 7 Automation backbone, Phase 8 Support
Upsell Signal, and this Phase 8 Security Incident chain extension. See
`git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session, on top of Phase 1-8 slice 1)

```bash
cd infra/docker
docker compose ps   # confirm the stack from earlier sessions is still up

# Migration adding security_incidents.related_task_id
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add security incident related_task_id"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 75 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build

# Live smoke test against the running Docker stack: create a critical
# incident with an owner, confirm both related_risk_id and
# related_task_id are set, confirm the Task is visible via /api/v1/tasks
# and the Notification via /api/v1/notifications, confirm the
# audit_events row directly in Postgres.
```

## Next highest-priority task: Phase 9 — Integrations (first slice)

Per the master spec, Phase 9 builds the Connector SDK (spec §48/§49) for
categories like CRM, Email, Cloud, Identity, Engineering, Communication,
Documents, Accounting. Building real OAuth connectors for HubSpot/Gmail/
Salesforce/etc. all at once would violate the "no fake features" rule
(spec §82) and the secrets contract (spec §C2: never ask for secrets in
chat, app must boot without paid API keys) — none of those providers'
credentials exist in this environment, and stubbing "connected" states
for them would be exactly the fabricated success state the spec forbids.

**First real, honest slice: a generic inbound Webhook connector.** Spec
§48 lists "Webhook" and "REST API" as their own integration category —
this is the one category buildable with zero external API keys or OAuth
apps, and it closes two gaps already flagged in earlier phases'
`KNOWN_LIMITATIONS.md` entries: Automation's non-manual triggers (spec
§38 lists "Webhook" as a trigger type; only `manual` exists today) and
the Security Release Baseline's explicit "webhook signature verification"
requirement (spec §H).

Design:
1. **Data model**: `app/integrations/models.py` — `IntegrationConnection`
   (`organization_id`, `connector_key` — only `"webhook"` supported for
   now, `name`, `status` [active|disabled], `webhook_secret` — a
   generated per-connection HMAC secret, `linked_workflow_id` nullable FK
   to `automation_workflows`, `last_synced_at`, `last_error`,
   `created_by`) and `WebhookEvent` (`connection_id`, `verified: bool`,
   `payload: JSON`, `triggered_run_id` nullable FK to
   `automation_workflow_runs`, `received_at`) — an audit trail of every
   inbound call, verified or not.
2. **Cross-module hook**: a verified webhook event whose connection has
   a `linked_workflow_id` pointing at an `active` workflow triggers that
   workflow via the existing `app.automation.service.start_run` —
   reusing Phase 7's execution engine rather than building a second one.
   This also means `Workflow.trigger_type` needs a `"webhook"` value
   alongside `"manual"` (schema/validation change only, no new engine).
3. **The receiver endpoint is architecturally different from every other
   route in this app**: `POST /api/v1/integrations/webhooks/{connection_id}/receive`
   has no session/OrgContext dependency, because the caller is an
   external system, not a logged-in user. Its security boundary is HMAC-
   SHA256 verification against `IntegrationConnection.webhook_secret`
   (`hmac.compare_digest`, constant-time), not RBAC — this is the
   connector's own auth model (spec §H: "webhook signature verification").
   Return 404 for an unknown/disabled connection without distinguishing
   "doesn't exist" from "wrong org" (same non-leaking pattern used
   everywhere else, just without a cookie to key off of).
4. **Admin-facing endpoints** (normal session auth): create/list/get a
   connection (secret shown — this backbone doesn't have a secrets vault
   yet, note it in `docs/KNOWN_LIMITATIONS.md`), PATCH to link/unlink a
   workflow or toggle status, list received events for visibility.
5. **RBAC**: new `integrations.connections.manage` permission, granted to
   `org_admin` (already gets everything) and `automation_manager` (the
   role that also owns workflow triggers).
6. **Frontend**: a `/settings/integrations` page (fits the existing
   Settings nav group) — create a connection, copy the webhook URL +
   secret, link it to a workflow, see recent received events with
   verified/unverified status.
7. **Tests**: valid signature triggers the linked workflow (assert via
   `/api/v1/automation/runs`, not just the event's own view — same
   verification pattern as every ADR so far); invalid signature is
   rejected and does not trigger anything; tenant isolation (a
   connection from another org's ID returns 404); disabled connections
   reject events.
8. **Live smoke test**: compute a real HMAC-SHA256 signature with curl/
   openssl against a real webhook secret, POST it to the running
   container, confirm the linked workflow actually ran.
9. Update `docs/DATABASE_MODEL.md`, `docs/DOMAIN_MODEL.md`,
   `docs/IMPLEMENTATION_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`,
   `docs/DECISIONS.md` (ADR-0024), `docs/KNOWN_LIMITATIONS.md`,
   `docs/ROUTES_AND_SCREENS.md`, `docs/RELEASE_CHECKLIST.md`, and this
   file when done.

Realistic scope note: every *other* Phase 9 category (CRM, Email, Cloud,
Identity, Engineering, Communication, Documents, Accounting) needs a real
third-party OAuth app or API key this environment doesn't have and
shouldn't fabricate — those stay explicitly not-started, tracked in
`docs/KNOWN_LIMITATIONS.md`, until real credentials and a concrete
consuming feature justify building one (same "don't build ahead of
demand" principle used since Phase 2).

## Files to edit next

- `apps/api/app/integrations/` (new package: `models.py`, `schemas.py`, `service.py`)
- `apps/api/app/routers/integrations.py` (new — includes the unauthenticated receiver route)
- `apps/api/app/core/rbac.py` (new `integrations.connections.manage` permission)
- `apps/api/app/automation/schemas.py` / `models.py` (allow `trigger_type = "webhook"`)
- `apps/api/migrations/versions/` (new revision)
- `apps/api/app/seed.py` (seed one webhook connection, optionally linked to a demo workflow)
- `apps/api/tests/test_integrations.py` (new)
- `apps/web/lib/navigation.ts` (add Settings → Integrations)
- `apps/web/app/(app)/settings/integrations/page.tsx` (new)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (75 passed)
```
