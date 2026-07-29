# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are both complete.** See `docs/RELEASE_CHECKLIST.md` and
`docs/IMPLEMENTATION_STATUS.md` for the itemized list.

Working and verified end to end: monorepo, local Docker Compose infra,
auth, multi-tenancy, RBAC, audit log, tasks, approvals, files,
notifications, a full document pipeline (upload → parse → chunk → embed →
store, via a durable Temporal workflow), similarity search over
embeddings, and a retrieval-grounded AI Copilot (`/copilot`) that answers
questions using only uploaded documents and cites exactly which chunks it
used. All lint/typecheck/test/build checks pass (26 backend tests, ruff +
mypy --strict clean; frontend eslint + tsc + production build clean).

No other domain module (Compliance, Security, Sales, Support, Automation)
has been started. No AWS infrastructure exists. See
`docs/IMPLEMENTATION_PLAN.md` for the full phase order and
`docs/KNOWN_LIMITATIONS.md` for exactly what's missing — notably,
similarity search is a Python-side linear scan (fine now, not at scale —
ADR-0012), and the Copilot only knows about the Knowledge module (no
cross-module intent router since no other module exists yet to route to).

## Branch and commit

Branch: `main`. Three substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, and this Phase 2 completion (RAG + Copilot).
See `git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session, on top of Phase 1 + Knowledge ingestion)

```bash
cd infra/docker
docker compose ps   # confirm the stack from earlier sessions is still up

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 26 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build
```

No new migration was needed this round — retrieval and the Copilot only
add Python modules (`app/knowledge/retrieval.py`, `app/ai/copilot.py`,
`app/ai/schemas.py`), no new tables.

## Next highest-priority task

**Start Phase 3 — Compliance** (spec sections 12, 3rd module in
`docs/IMPLEMENTATION_PLAN.md`). This is the first of the five primary
product modules and the largest single phase in the spec. Suggested
dependency order, following the pattern established in `app/knowledge/`:

1. **Data model first**: `app/compliance/models.py` — frameworks,
   framework_versions, requirements, controls, control_mappings,
   control_assessments, evidence, evidence_versions, risks, policies,
   audits, regulatory_updates (spec §50). Link evidence to `core.files`
   and (once it exists) `knowledge.documents`, not a duplicate storage
   path.
2. **Seed one framework concretely** rather than all seven abstractly:
   GDPR is explicitly named throughout the spec and the seeded sample
   document (`docs/RESUME_BUILD.md`'s predecessor already seeded a "GDPR
   Compliance Overview" document) — start there, add EU AI Act/ISO 27001
   as the pattern repeats cleanly.
3. **Migration**, then `app/routers/compliance.py` — framework overview,
   control detail, evidence library endpoints, tenant-isolated and
   RBAC-gated behind `compliance.controls.*` / `compliance.evidence.*`
   permission keys (extend `app/core/rbac.py`'s `PERMISSIONS` dict and
   grant them to `compliance_manager`/`dpo` system roles, not just
   `org_admin`).
4. **Frontend**: replace the `/coming-soon?module=compliance` stub —
   framework overview page first, control detail second.
5. **Cross-module hook**: since compliance is meant to *govern* other
   modules (spec §91), at minimum wire one real example now — e.g. the
   AI Copilot's Compliance-aware answers, or a `compliance.controls.view`
   permission check somewhere real — rather than only building it as an
   island, per spec §80 ("do not build disconnected modules").
6. Tests: tenant isolation + RBAC denial for the new endpoints (same
   pattern as `tests/test_tenant_isolation.py` / `tests/test_rbac.py`).
7. Update `docs/DATABASE_MODEL.md`, `docs/DOMAIN_MODEL.md`,
   `docs/IMPLEMENTATION_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`, and
   this file when done.

## Files to edit next

- `apps/api/app/compliance/` (new package: `models.py`, `schemas.py`, `service.py`)
- `apps/api/app/routers/compliance.py` (new)
- `apps/api/app/core/rbac.py` (new permission keys)
- `apps/api/migrations/versions/` (new revision)
- `apps/api/app/seed.py` (seed a GDPR framework + a few controls/evidence for the demo org)
- `apps/api/tests/test_compliance.py` (new)
- `apps/web/lib/navigation.ts` (flip `compliance` to `implemented: true`)
- `apps/web/app/(app)/compliance/` (new pages)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (26 passed)
```
