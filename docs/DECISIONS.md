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
