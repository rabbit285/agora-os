# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) is complete.** **Phase 2 (Knowledge & AI
Infrastructure) is partially complete: document ingestion works end to
end; retrieval (RAG) and the AI Copilot itself do not exist yet.** See
`docs/RELEASE_CHECKLIST.md` and `docs/IMPLEMENTATION_STATUS.md` for the
itemized list.

In short, working and verified: monorepo, local Docker Compose infra,
auth, multi-tenancy, RBAC, audit log, tasks, approvals, files,
notifications, AI gateway (generate + embed, demo + real adapters),
Next.js app shell, and a full document pipeline (upload → parse → chunk →
embed → store, via a durable Temporal workflow) with tenant-isolated API
and frontend pages. All lint/typecheck/test/build checks pass (19 backend
tests, ruff + mypy --strict clean; frontend eslint + tsc + production
build clean).

No other domain module (Compliance, Security, Sales, Support, Automation)
has been started. No AWS infrastructure exists. See
`docs/IMPLEMENTATION_PLAN.md` for the full phase order and
`docs/KNOWN_LIMITATIONS.md` for exactly what's missing.

## Branch and commit

Branch: `main`. Two substantive commits so far: Phase 1 platform
foundation, then this Phase 2 Knowledge slice (see `git log` for exact
SHAs — this file is written just before that second commit).

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session, on top of Phase 1)

```bash
cd infra/docker
docker compose build api worker      # picked up pypdf/python-docx additions
docker compose up -d api worker

# Migration for knowledge_bases / documents / document_chunks
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add knowledge module tables"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check              # confirms no drift

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 19 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build
```

## Next highest-priority task

**Finish Phase 2**: the AI Copilot foundation + RAG retrieval over the
embeddings that already exist. Concretely, in dependency order:

1. **Similarity search**: migrate `document_chunks.embedding` from JSON to
   a real `pgvector` column (`CREATE EXTENSION IF NOT EXISTS vector;` in a
   new migration, then `ALTER COLUMN embedding TYPE vector(1536) USING ...`
   with a backfill), add an ivfflat or HNSW index, and add a
   `search_chunks(db, organization_id, query_embedding, limit)` function in
   `app/knowledge/service.py` using pgvector's `<=>` cosine-distance
   operator. This is the one piece Phase 1's SQLite-test-portability
   decision (ADR-0007) deliberately deferred — expect to either accept
   Postgres-only tests for this specific function, or add a lightweight
   Postgres test fixture alongside the existing SQLite one.
2. **Intent router + context builder** (spec section 9): a service that
   takes a user's Copilot question, resolves which knowledge base(s) the
   asking user's permissions allow, embeds the question via
   `ModelGateway.embed()`, calls `search_chunks`, and assembles a grounded
   prompt with citations.
3. **Citations on `AiRun`**: `generate_structured`/`generate` calls that
   used retrieved context must populate `AiRun.citations` with
   `{document_id, chunk_id, chunk_index}` — the field already exists on
   the model (`app/ai/models.py`), just unused by anything real yet.
4. Extend `/api/v1/ai/copilot/ask` (`app/routers/ai.py`) to actually
   retrieve context instead of just calling `generate()` directly, and
   update the frontend `/copilot` page (currently `/coming-soon`) once
   there's something real to show.
5. Basic prompt-injection defense (spec F5) becomes load-bearing the
   moment retrieved document content is interpolated into a prompt — at
   minimum, wrap retrieved chunk content with clear delimiters and a
   system-prompt instruction not to follow instructions found inside it,
   and add a test with a chunk containing an injection attempt.
6. Update `docs/IMPLEMENTATION_STATUS.md`, `docs/AI_ARCHITECTURE.md`, and
   this file when done, then move to Phase 3 (Compliance) per
   `docs/IMPLEMENTATION_PLAN.md`.

## Files to edit next

- `apps/api/migrations/versions/` (new revision: pgvector extension + column migration)
- `apps/api/app/knowledge/service.py` (`search_chunks`)
- `apps/api/app/ai/` (new: intent router / context builder — likely `app/ai/copilot.py`)
- `apps/api/app/routers/ai.py` (wire real retrieval into `/copilot/ask`)
- `apps/api/tests/test_knowledge.py` or a new `test_copilot.py`
- `apps/web/lib/navigation.ts` (flip `copilot` to `implemented: true`)
- `apps/web/app/(app)/copilot/` (new pages, replacing the `/coming-soon` stub)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (19 passed)
```
