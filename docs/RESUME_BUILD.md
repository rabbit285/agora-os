# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) is functionally complete and verified.**
See `docs/RELEASE_CHECKLIST.md` for the itemized list. In short: monorepo,
local Docker Compose infra, auth, multi-tenancy, RBAC, audit log, tasks,
approvals, files, notifications, AI gateway + demo adapter, Next.js app
shell, all lint/typecheck/test/build checks passing.

No domain module (Compliance, Security, Sales, Support, Automation) has
been started. No AWS infrastructure exists. See
`docs/IMPLEMENTATION_PLAN.md` for the full phase order and
`docs/KNOWN_LIMITATIONS.md` for exactly what's missing.

## Branch and commit

Branch: `main`. This is the first substantive commit on top of the initial
"Create readme.md" commit — see `git log` for the exact SHA once committed
(this file is written before that commit; check `git log -1` if the exact
hash matters).

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run

```bash
# Infra
cd infra/docker
docker compose up -d postgres redis minio
docker compose build api
docker compose build worker   # if not already built
docker compose up -d temporal temporal-ui api worker

# Migrations
docker compose run --rm api alembic revision --autogenerate -m "initial schema"
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check          # confirms no drift
docker compose run --rm api python -m app.seed      # idempotent demo data

# Backend checks (all green as of this writing)
docker compose run --rm --no-deps api ruff check .
docker compose run --rm --no-deps api ruff format --check .
docker compose run --rm --no-deps api mypy app
docker compose run --rm --no-deps api pytest -q     # 12 passed

# Frontend checks (all green as of this writing)
cd apps/web
npm install
npx eslint .
npx tsc --noEmit
npm run build
```

## Next highest-priority task

**Phase 2 — Knowledge & AI Infrastructure** (see
`docs/IMPLEMENTATION_PLAN.md`). Concretely, in dependency order:

1. Add `documents`, `document_chunks`, `knowledge_bases`,
   `knowledge_sources` models to a new `app/knowledge/` package
   (`apps/api/app/knowledge/models.py`), following the pattern in
   `app/core/models.py`.
2. Alembic migration for the new tables (pgvector extension needs
   `CREATE EXTENSION IF NOT EXISTS vector;` — add as a migration, not
   inside `app/db/base.py`).
3. Document upload flow: reuse `app/core/storage.py` presign helpers;
   add a `document_processing` step (parse → chunk → embed) — likely a
   Temporal workflow in `apps/worker/worker/` rather than inline in the
   request handler, since parsing can be slow (spec §61: don't couple
   workflows to HTTP requests).
4. Extend `app/ai/gateway.py` usage: the `embed()` method already exists
   on `ModelAdapter` — wire it into the chunk-embedding step.
5. `/api/v1/knowledge/documents` router + `packages`/frontend pages
   (`apps/web/app/(app)/knowledge/`), replacing the current
   `/coming-soon?module=documents` stub in `lib/navigation.ts`.
6. Tests: tenant isolation for documents (same pattern as
   `tests/test_tenant_isolation.py`), a fixture that documents can't be
   retrieved cross-org.
7. Update `docs/IMPLEMENTATION_STATUS.md` and this file when done.

## Files to edit next

- `apps/api/app/knowledge/__init__.py` (new)
- `apps/api/app/knowledge/models.py` (new)
- `apps/api/migrations/versions/` (new revision)
- `apps/api/app/routers/knowledge.py` (new)
- `apps/api/app/main.py` (register the new router)
- `apps/web/lib/navigation.ts` (flip `knowledge` to `implemented: true`
  once the route exists)
- `apps/web/app/(app)/knowledge/` (new pages)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green
```
