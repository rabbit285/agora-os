# Veyntra

AI-powered business operating system for SMEs — a multi-tenant
B2B SaaS platform unifying Compliance, Security, Sales, Customer Support,
and Business Process Automation around one company knowledge layer, one
AI infrastructure, and one governance/audit model.

**Current status**: Phase 1 (platform foundation) only — see
[`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) for exactly
what exists, [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)
for what's next, and [`docs/RESUME_BUILD.md`](docs/RESUME_BUILD.md) if
you're picking this up mid-build.

The full product specification is
[`docs/AGORA_ORIGIN_MASTER_SPEC.md`](docs/AGORA_ORIGIN_MASTER_SPEC.md).

## Quick start (local development)

Requires Docker Desktop. No local Python or Node installation is required —
everything runs in containers.

```bash
cp .env.example .env
cd infra/docker
docker compose up -d
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.seed
```

Then open:

- Web app: http://localhost:3000 (or `$WEB_HOST_PORT` if overridden — see below)
- API docs: http://localhost:8000/docs
- Temporal UI: http://localhost:8088

Demo login (from the seed script): `admin@acme-ai.example` / `ChangeMe123456!`

### Port conflicts

If something else on your machine already uses 5432/6379/9000/9001/7233/8088/8000/3000,
create `infra/docker/.env` with overrides — see
[`docs/ENVIRONMENT_VARIABLES.md`](docs/ENVIRONMENT_VARIABLES.md).

## Running checks

Backend (inside the `api` container):

```bash
cd infra/docker
docker compose run --rm --no-deps api ruff check .
docker compose run --rm --no-deps api ruff format --check .
docker compose run --rm --no-deps api mypy app
docker compose run --rm --no-deps api pytest -q
```

Frontend (`apps/web`, runs on host with Node ≥ 20):

```bash
cd apps/web
npm install
npm run lint
npx tsc --noEmit
npm run build
```

## Repository layout

```text
apps/
  web/      Next.js 16 (App Router), TypeScript strict
  api/      FastAPI, SQLAlchemy 2, Alembic
  worker/   Temporal Python worker
infra/
  docker/   docker-compose.yml + Dockerfiles (local dev)
  terraform/  AWS IaC — not started yet
docs/       Architecture, decisions, status, and the full product spec
```

See [`docs/PLATFORM_ARCHITECTURE.md`](docs/PLATFORM_ARCHITECTURE.md) for
the full architecture.

## Documentation index

| Doc | Purpose |
|---|---|
| [PRODUCT_VISION.md](docs/PRODUCT_VISION.md) | What this product is and why |
| [PLATFORM_ARCHITECTURE.md](docs/PLATFORM_ARCHITECTURE.md) | Monorepo, domain boundaries, tenant isolation |
| [DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md) | Shared entities and their relationships |
| [DATABASE_MODEL.md](docs/DATABASE_MODEL.md) | Phase 1 table-level schema |
| [AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md) | Model Gateway, governance, demo adapter |
| [SECURITY_ARCHITECTURE.md](docs/SECURITY_ARCHITECTURE.md) | Auth, RBAC, tenant resolution |
| [ROUTES_AND_SCREENS.md](docs/ROUTES_AND_SCREENS.md) | Frontend route map and build status |
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Phased delivery order |
| [IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md) | What's built right now |
| [RESUME_BUILD.md](docs/RESUME_BUILD.md) | Exact state + next steps for continuing the build |
| [DECISIONS.md](docs/DECISIONS.md) | ADRs for autonomous engineering decisions |
| [KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) | What's explicitly not done yet |
| [SECURITY_ASSUMPTIONS.md](docs/SECURITY_ASSUMPTIONS.md) | What the current security posture relies on |
| [RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) | Honest completion status |
| [ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md) | Full env var reference |
