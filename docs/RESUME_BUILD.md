# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are complete. Phase 3 (Compliance) and Phase 4 (Security)
both have their core backbones built and verified**, but not their larger
sub-features. See `docs/RELEASE_CHECKLIST.md` and
`docs/IMPLEMENTATION_STATUS.md` for the itemized list.

Working and verified end to end: everything from Phase 1/2/3, plus:
SecurityAsset/SecurityFinding/SecurityAlert/SecurityIncident with a status
workflow; a critical-severity incident automatically creates a linked
Compliance Risk (spec §19's explicit security↔compliance connection,
implemented as a cross-module hook — the same shared-primitives pattern
Compliance's failed-assessment→Task hook used, just in the other
direction). `/security` and `/security/incidents/[id]` render this live.
All lint/typecheck/test/build checks pass (43 backend tests, ruff + mypy
--strict clean; frontend eslint + tsc + production build clean).

No other domain module (Sales, Support, Automation) has been started. No
AWS infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the full
phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's missing —
notably, Security has no cloud/identity provider connectors yet (those
need the connector SDK from Phase 9 to do properly, not one-off
per-provider code), and the AI Copilot still only retrieves from Knowledge
documents, not Compliance or Security data.

## Branch and commit

Branch: `main`. Five substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, Phase 2 completion (RAG + Copilot), Phase 3
Compliance backbone, and this Phase 4 Security backbone. See `git log` for
exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session, on top of Phase 1-3)

```bash
cd infra/docker
docker compose ps   # confirm the stack from earlier sessions is still up

# Migration for security_assets/security_findings/security_alerts/security_incidents
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add security module tables"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

docker compose run --rm api python -m app.seed   # ran twice, confirmed idempotent

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 43 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build
```

## Next highest-priority task

**Start Phase 5 — Sales** (spec sections 20–29, 5th module in
`docs/IMPLEMENTATION_PLAN.md`). Suggested dependency order, following the
`app/compliance/` and `app/secops/` pattern:

1. **Data model**: `app/sales/models.py` — accounts, contacts, leads,
   sequences, sequence_steps, outreach_messages, opportunities (spec
   §50). Note: `app/security.py` (password/session helpers) already
   exists — `secops` was used for the Security domain package for the
   same reason; check for naming collisions before naming this one too
   (a plain `app/sales/` should be fine, nothing else uses that name).
2. **Compliance governs Sales explicitly** (spec §91: "Sales AI asks: Can
   we contact this prospect? Compliance checks: jurisdiction, data
   source, marketing basis, opt-out, suppression, organization policy").
   Don't build outreach as an island — at minimum, model a suppression/
   opt-out flag on Contact and check it before any "send" action, even
   before real email sending exists. This is Phase 5's natural
   cross-module hook, mirroring Compliance→Task and Security→Risk.
3. **Migration**, then `app/routers/sales.py` — accounts, leads,
   opportunities, pipeline endpoints. Add `sales.leads.manage` /
   `sales.accounts.manage` / `sales.opportunities.manage` permission
   keys, granted to `sales_manager` and `sales_representative` (both
   already seeded with zero permissions).
4. **Frontend**: replace `/coming-soon?module=sales` — pipeline/accounts
   overview first, account detail second.
5. Tests: tenant isolation + RBAC denial (same pattern as
   `tests/test_compliance.py` / `tests/test_security.py`), plus the
   suppression-check cross-module test.
6. Update `docs/DATABASE_MODEL.md`, `docs/DOMAIN_MODEL.md`,
   `docs/IMPLEMENTATION_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`, and
   this file when done.

Note: real lead-finding, enrichment, and outreach sending all depend on
external data sources / email providers that don't exist yet in this
build (spec's progressive trust model — Stage 1 read-only connectors
first). Phase 5's realistic scope here is the **data model and pipeline
management** (accounts/contacts/leads/opportunities, manually entered or
seeded), not real prospecting — same "backbone now, connectors later"
shape as Compliance and Security.

## Files to edit next

- `apps/api/app/sales/` (new package: `models.py`, `schemas.py`, `service.py`)
- `apps/api/app/routers/sales.py` (new)
- `apps/api/app/core/rbac.py` (new permission keys, grant to `sales_manager`/`sales_representative`)
- `apps/api/migrations/versions/` (new revision)
- `apps/api/app/seed.py` (seed a few accounts/contacts/leads/one opportunity for the demo org)
- `apps/api/tests/test_sales.py` (new)
- `apps/web/lib/navigation.ts` (flip `sales` to `implemented: true`)
- `apps/web/app/(app)/sales/` (new pages)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (43 passed)
```
