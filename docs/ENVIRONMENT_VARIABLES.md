# Environment Variables

Copy [`.env.example`](../.env.example) to `.env` at the repo root. Docker
Compose (`infra/docker/docker-compose.yml`) reads it via variable
substitution for the values a developer might override (currently
`AI_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`); every other value has
a working in-compose default so `docker compose up` succeeds with an empty
`.env`.

**Host port conflicts**: every published port (Postgres 5432, Redis 6379,
MinIO 9000/9001, Temporal 7233, Temporal UI 8088, API 8000, web 3000) is
overridable via `POSTGRES_HOST_PORT` / `REDIS_HOST_PORT` /
`MINIO_API_HOST_PORT` / `MINIO_CONSOLE_HOST_PORT` / `TEMPORAL_HOST_PORT` /
`TEMPORAL_UI_HOST_PORT` / `API_HOST_PORT` / `WEB_HOST_PORT` in an
`infra/docker/.env` file (gitignored — compose reads `.env` from the compose
file's own directory, not the repo root). Only needed if something else on
your machine already holds one of the default ports; container-to-container
traffic always uses the fixed internal ports regardless.

Validation happens in `apps/api/app/config.py` (`Settings`, a
`pydantic-settings` model). At startup it logs which **optional** variables
are unset, by name only — never their values — and refuses to start in
`APP_ENV=production` if `SECRET_KEY` is still the insecure default.

## Core

| Variable | Required | Default (local) | Notes |
|---|---|---|---|
| `APP_ENV` | no | `development` | `development` \| `staging` \| `production` \| `test` |
| `APP_URL` | no | `http://localhost:3000` | frontend origin; used for CORS and email links |
| `API_URL` | no | `http://localhost:8000` | |
| `SECRET_KEY` | **yes in production** | dev placeholder | app refuses to boot in production without a real value |
| `DATABASE_URL` | no | local Postgres | `postgresql+psycopg://...`; converted to `+asyncpg` at runtime |
| `REDIS_URL` | no | local Redis | |
| `TEMPORAL_ADDRESS` / `TEMPORAL_NAMESPACE` / `TEMPORAL_DEPLOYMENT_MODE` | no | local Temporal | `TEMPORAL_DEPLOYMENT_MODE` is `local` \| `self_hosted` \| `cloud` |
| `S3_ENDPOINT_URL` / `S3_BUCKET` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` / `S3_REGION` | no | local MinIO | swap for real AWS S3 credentials/endpoint in staging/production |

## Sessions

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SESSION_COOKIE_NAME` | no | `agora_session` | |
| `SESSION_TTL_HOURS` | no | `336` (14 days) | |
| `COOKIE_SECURE` | no | `false` | **must** be `true` outside local HTTP dev |

## AI providers — optional

| Variable | Required | Behavior when unset |
|---|---|---|
| `AI_PROVIDER` | no | `demo` \| `anthropic` \| `openai`; defaults to `demo` |
| `ANTHROPIC_API_KEY` | no | falls back to the deterministic `DemoAdapter` — see `docs/AI_ARCHITECTURE.md` |
| `OPENAI_API_KEY` | no | same fallback |

No AI feature crashes or blocks signup/login when these are unset — Copilot
responses are just clearly labeled demo output until a key is added.

## Email — optional

| Variable | Behavior when unset |
|---|---|
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` | password-reset links are logged at INFO level instead of emailed (see `app/identity/service.py::_dispatch_password_reset_email`) — see `docs/KNOWN_LIMITATIONS.md` |
| `SES_REGION` | reserved for the AWS SES adapter added with the AWS deployment phase; not yet implemented |

## Billing — optional

| Variable | Behavior when unset |
|---|---|
| `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET` | billing module not yet implemented (Phase 10); reserved now so the shape doesn't change later |

## Frontend

Only variables prefixed `NEXT_PUBLIC_` are ever bundled into browser
JavaScript by Next.js — this is a hard boundary the build enforces, not a
convention to remember. `NEXT_PUBLIC_API_URL` is the only one Phase 1 needs.
