# Architecture Decision Records

Lightweight ADR log for decisions made autonomously during the build,
per the execution contract's "document the decision and continue" rule.
Individual longer ADRs can move to `docs/adrs/NNNN-title.md` if they need
more than a paragraph; short ones live here.

## ADR-0001 — Opaque, server-revocable session tokens instead of JWTs

**Decision**: Sessions are a random token whose SHA-256 hash is stored in
a `sessions` table; the session row can be revoked (logout, password
reset) with a single `UPDATE`.

**Why**: The spec requires session revocation (§E4). A self-contained JWT
can't be revoked without an additional denylist store, which duplicates
exactly what a sessions table already is — so a JWT would add complexity
without removing the sessions table.

## ADR-0002 — `packages/ui`, `packages/sdk`, etc. deferred until needed

**Decision**: The spec's monorepo layout (§52) lists `packages/ui`,
`packages/sdk`, `packages/ai-core`, `packages/automation-core`,
`packages/compliance-models`, `packages/integration-sdk`. Phase 1 does not
create these as empty npm/Python workspaces.

**Why**: `apps/web` is the only frontend consumer today; a shared `ui`
package only earns its keep once a second consumer exists (e.g. a
marketing site or a second app). Creating it now would mean workspace
tooling (npm workspaces / Turborepo config) with nothing genuinely shared.
Introduce each package the first time two apps need it.

## ADR-0003 — Email is a log-only dev adapter until Phase 2/AWS

**Decision**: Password reset (and future transactional email) logs the
link at INFO level instead of sending real email in Phase 1.

**Why**: Spec §C2 requires the app to boot and function without paid
provider keys. SES is the documented production adapter (spec §L3) but
implementing it now, before there's an AWS account/domain to verify,
would be dead code. The interface boundary (`_dispatch_password_reset_email`)
is already isolated so swapping in SES later doesn't touch callers.

## ADR-0004 — Single Postgres role for local dev; DB-level audit-log
protection deferred to the AWS phase

**Decision**: Local Docker Compose Postgres uses one `agora` role for
migrations and the application. `audit_events` append-only-ness is
enforced by code review and tests only, not a DB-level `REVOKE`.

**Why**: Postgres table owners bypass `GRANT`/`REVOKE` on their own
tables, so a `REVOKE` only means something once migrations and the app
connect as different roles — which the spec places in the AWS/RDS phase
(§L3: "separate database roles for application, migrations, and read-only
operational access"). Adding a second local role now would be scaffolding
for infrastructure Phase 1 doesn't otherwise have.

## ADR-0005 — npm instead of pnpm for the frontend

**Decision**: `apps/web` uses npm, not pnpm.

**Why**: The spec's CI section defaults to `pnpm`, but this machine had
npm available and pnpm was not installed. Both are workspace-capable
package managers; switching to pnpm later is a mechanical change
(`package-lock.json` → `pnpm-lock.yaml`) if a monorepo-wide workspace is
introduced (see ADR-0002).

## ADR-0006 — Hand-built shadcn-style primitives instead of the shadcn CLI

**Decision**: `components/ui/*` (button, input, label, card, badge) are
hand-written using the same libraries shadcn/ui generates from
(class-variance-authority, Radix primitives, tailwind-merge) rather than
scaffolded via `npx shadcn init`.

**Why**: The installed shadcn CLI version requires interactive prompts
(component-library and preset selection) with no working non-interactive
flag combination found in this environment. The resulting components are
structurally identical to what the CLI would generate; running the CLI
later to add more components (table, dialog, etc.) remains an option.

## ADR-0007 — Embeddings stored as JSON, not a native pgvector column

**Decision**: `document_chunks.embedding` is a JSON float array
(`list[float]`, length 1536), not `pgvector`'s `Vector` SQLAlchemy type.

**Why**: A native `Vector` column needs the `pgvector` Postgres extension,
which SQLite (used for fast in-memory unit tests) has no equivalent for —
introducing it now would either break test portability or require a
custom dual-dialect type. Nothing in Phase 2 queries by similarity yet
(that's the AI Copilot's RAG pipeline, not yet built); JSON storage is
sufficient until a real cosine-distance query is needed, at which point
this column migrates to `vector(1536)` with an ivfflat/HNSW index.

## ADR-0008 — One AiRun per embedding batch, not one per chunk

**Decision**: `ModelGateway.embed()` writes a single `AiRun` row per call,
covering however many texts were embedded in that batch (`output.chunk_count`),
not one row per text.

**Why**: A single document can produce dozens of chunks; logging one
`AiRun` per chunk would make `ai_runs` grow much faster than any other
table for no analytical benefit — the batch-level record already answers
"what was embedded, by what provider, how long did it take."

## ADR-0009 — Workflow-defining modules never import application code

**Decision**: `apps/worker/worker/workflows.py` imports only `temporalio`
and the stdlib. Activities (which do need `app.config`, the database, and
object storage) live in a separate `activities.py`, referenced from
workflows by string name (`workflow.execute_activity("name", ...)`), and
imported into `main.py` (never into `workflows.py`).

**Why**: Temporal's Python SDK sandboxes and statically validates the
entire import graph of any module that defines a `@workflow.defn` class,
rejecting non-deterministic operations (file/env access) anywhere in that
graph. The Phase 1 health-check workflow crashed the worker at startup
because it lived in the same module as `from app.config import settings`
(which reads a `.env` file) — moving that import to a sibling module the
workflow never imports fixed it permanently, not just for that one case.

## ADR-0010 — A shared `register_all_models` import module

**Decision**: `app/db/register_all_models.py` imports every domain
model module purely for its side effects (registering each model's table
in `Base.metadata`). Alembic's `migrations/env.py`, the test suite's
`conftest.py`, and any Temporal activity that touches the database import
this one module instead of hand-picking which specific model classes they
need.

**Why**: The worker's document-ingestion activity crashed with
`NoReferencedTableError: ... could not find table 'users'` the first time
it ran for real — it imported `app.core.models` and `app.knowledge.models`
directly but never `app.identity.models`, so SQLAlchemy had never seen the
`users` table in that process and couldn't resolve
`documents.created_by -> users.id` on flush. The bug wasn't in the FK
definition, it was that Python module imports are what register a table
with SQLAlchemy, and each process (API, worker, migrations, tests) only
imports what it directly references. A single shared "import everything"
module removes the need to remember this in every new entrypoint.

## ADR-0011 — Presigned URLs signed against a separate "public" S3 endpoint

**Decision**: `app/core/storage.py` has two boto3 clients: `_client()`
(internal Docker hostname, e.g. `http://minio:9000`, used for server-side
downloads/uploads) and `_public_client()` (browser-reachable host, e.g.
`http://localhost:9002`, used only to sign upload/download URLs).

**Why**: A presigned URL's signature is valid only for the host it was
signed against. Signing with the internal Docker hostname would hand the
browser a URL it can't resolve at all; signing with the public host
(`S3_PUBLIC_ENDPOINT_URL`) produces a URL the browser can actually reach,
while the API/worker keep using the internal hostname for their own
direct calls.
