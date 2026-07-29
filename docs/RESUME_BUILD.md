# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are complete. Phase 3 (Compliance) has its core backbone
built and verified** — Framework/Requirement catalog, Control,
ControlMapping, ControlAssessment, Evidence, Risk, Policy — but not its
larger sub-features (audits, AI governance, privacy workflows, vendor
risk, questionnaires, Trust Center). See `docs/RELEASE_CHECKLIST.md` and
`docs/IMPLEMENTATION_STATUS.md` for the itemized list.

Working and verified end to end: everything from Phase 1/2, plus:
GDPR/EU AI Act/ISO 27001 seeded as catalog data; the demo org has two
controls (one passing, one failing) mapped to GDPR requirements; a failed
assessment automatically creates a remediation `Task` (the cross-module
hook spec §80 requires); evidence links a control to the previously-seeded
GDPR overview document. `/compliance` and `/compliance/controls/[id]`
render this live. All lint/typecheck/test/build checks pass (35 backend
tests, ruff + mypy --strict clean; frontend eslint + tsc + production
build clean).

No other domain module (Security, Sales, Support, Automation) has been
started. No AWS infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md`
for the full phase order and `docs/KNOWN_LIMITATIONS.md` for exactly
what's missing — notably, the Compliance catalog is a small representative
seed (a handful of requirements per framework), not the complete
regulatory text, and the AI Copilot doesn't yet retrieve from Compliance
data (only from Knowledge documents).

## Branch and commit

Branch: `main`. Four substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, Phase 2 completion (RAG + Copilot), and this
Phase 3 Compliance backbone. See `git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session, on top of Phase 1 + Phase 2)

```bash
cd infra/docker
docker compose ps   # confirm the stack from earlier sessions is still up

# Migration for frameworks/requirements/controls/control_mappings/
# control_assessments/evidence/risks/policies
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add compliance module tables"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

docker compose run --rm api python -m app.seed   # ran twice, confirmed idempotent

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 35 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build
```

## Next highest-priority task

**Start Phase 4 — Security** (spec sections 13–19, 4th module in
`docs/IMPLEMENTATION_PLAN.md`). Suggested dependency order, following the
`app/compliance/` pattern:

1. **Data model**: `app/security/models.py` — security_assets,
   security_findings, vulnerabilities, security_alerts,
   security_incidents, identity_findings, cloud_findings (spec §50). Link
   findings/incidents to `core.files` (for evidence) and consider whether
   a critical finding should auto-create a `core.Task` or `core.Approval`
   — same cross-module-hook pattern as Compliance's failed assessment.
2. **The compliance ↔ security connection is explicit in the spec**
   (§19: "Integrate incidents with: GDPR breach process... This
   connection between security and compliance is critical"). Don't build
   Security as an island — when a security incident's severity is
   critical, consider creating a compliance `Risk` or linking to one,
   mirroring how a failed compliance assessment creates a `Task`.
3. **Migration**, then `app/routers/security.py` — asset inventory,
   findings list, incident workspace endpoints. Add
   `security.findings.manage` / `security.incidents.manage` permission
   keys to `app/core/rbac.py`, granted to the `security_manager` system
   role (already seeded, currently has zero permissions — same gap
   `compliance_manager`/`dpo` had before this phase).
4. **Frontend**: replace `/coming-soon?module=security` — security
   dashboard first (asset count, findings by severity), incident detail
   second.
5. Tests: tenant isolation + RBAC denial (same pattern as
   `tests/test_compliance.py`), plus a test for whatever cross-module
   hook you build.
6. Update `docs/DATABASE_MODEL.md`, `docs/DOMAIN_MODEL.md`,
   `docs/IMPLEMENTATION_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`, and
   this file when done.

## Files to edit next

- `apps/api/app/security/` (new package: `models.py`, `schemas.py`, `service.py`)
- `apps/api/app/routers/security.py` (new)
- `apps/api/app/core/rbac.py` (new permission keys, grant to `security_manager`)
- `apps/api/migrations/versions/` (new revision)
- `apps/api/app/seed.py` (seed a few assets/findings/one incident for the demo org)
- `apps/api/tests/test_security.py` (new)
- `apps/web/lib/navigation.ts` (flip `security` to `implemented: true`)
- `apps/web/app/(app)/security/` (new pages)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (35 passed)
```
