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

**Local override file**: `Settings` reads `.env` first, then `.env.local`
(both gitignored, both excluded from every Docker build context by the
repo-root `.dockerignore`) — anything in `.env.local` wins, so a developer
can keep personal/experimental values (e.g. their own HubSpot developer
app credentials) out of the shared `.env` without editing it. Neither file
is ever deployed to AWS; see "AWS production secrets" below.

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
| `S3_PUBLIC_ENDPOINT_URL` | no | falls back to `S3_ENDPOINT_URL` | the host used when **signing** presigned upload/download URLs handed to the browser. In Docker Compose, `S3_ENDPOINT_URL` is the internal hostname `http://minio:9000`, which the browser can't resolve — this variable points signed URLs at the host-mapped port instead (`http://localhost:9002` by default; see the port-override note below). Not needed outside Docker, where both are already the same reachable host. |

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

## Integrations — optional

Every OAuth provider follows the identical three-variable shape
(`<PROVIDER>_CLIENT_ID` / `<PROVIDER>_CLIENT_SECRET` /
`<PROVIDER>_REDIRECT_URI`) and the identical fallback behavior: unset means
`GET /api/v1/integrations/providers` reports that connector's
`configured: false` and the frontend disables "Connect" (showing "Not
configured" instead); a mock adapter still lets that provider's OAuth flow
be exercised end to end for tests/demo, but it's never presented as a live
connection (spec §82). Filling in the three variables for a provider
activates its real adapter automatically — no code or structural change —
see `docs/DECISIONS.md` ADR-0026/ADR-0028.

| Variable | Behavior when unset |
|---|---|
| `HUBSPOT_CLIENT_ID` / `HUBSPOT_CLIENT_SECRET` / `HUBSPOT_REDIRECT_URI` | HubSpot connector reports `configured: false`; redirect URI derived from `API_URL` when unset |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI` | Google connector reports `configured: false`; redirect URI derived from `API_URL` when unset |
| `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET` / `MICROSOFT_REDIRECT_URI` | Microsoft connector reports `configured: false`; redirect URI derived from `API_URL` when unset |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` / `GITHUB_REDIRECT_URI` | GitHub connector reports `configured: false`; redirect URI derived from `API_URL` when unset |
| `SLACK_CLIENT_ID` / `SLACK_CLIENT_SECRET` / `SLACK_REDIRECT_URI` | Slack connector reports `configured: false`; redirect URI derived from `API_URL` when unset |
| `SALESFORCE_CLIENT_ID` / `SALESFORCE_CLIENT_SECRET` / `SALESFORCE_REDIRECT_URI` | Salesforce connector reports `configured: false`; redirect URI derived from `API_URL` when unset |
| `TOKEN_ENCRYPTION_KEY` | falls back to a key derived from `SECRET_KEY` (fine for dev/test only — see `docs/KNOWN_LIMITATIONS.md`); a real deployment must set its own so rotating `SECRET_KEY` doesn't also break every stored OAuth token |

Where to register each provider's OAuth app/client (redirect URI must
match the `<PROVIDER>_REDIRECT_URI` value exactly):

| Provider | Register at |
|---|---|
| HubSpot | https://developers.hubspot.com/ |
| Google | https://console.cloud.google.com/apis/credentials |
| Microsoft | https://portal.azure.com/ (Azure AD App registrations) |
| GitHub | https://github.com/settings/developers |
| Slack | https://api.slack.com/apps |
| Salesforce | Setup -> App Manager -> New Connected App |

## Frontend

Only variables prefixed `NEXT_PUBLIC_` are ever bundled into browser
JavaScript by Next.js — this is a hard boundary the build enforces, not a
convention to remember. `NEXT_PUBLIC_API_URL` is the only one Phase 1 needs.
No OAuth client secret is ever read by, or reachable from, frontend code —
every token exchange happens server-side in `apps/api`.

## AWS production secrets

No AWS infrastructure exists yet (see `docs/IMPLEMENTATION_STATUS.md`), but
the config layer is already shaped for it: `Settings` reads every value
from the process environment regardless of *how* it got there, so a real
deployment's job is populating that environment, not changing
`app/config.py`. The intended (not yet built — this is a design commitment
for whoever builds the Terraform/ECS layer) production wiring is:

- **Secrets** (OAuth client secrets, `SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`,
  database/Redis credentials, SMTP/Stripe keys) live in **AWS Secrets
  Manager**, one secret per logical credential (or a JSON blob per
  provider), never in a deployed `.env` file, a Terraform output, a task
  definition's plaintext `environment` block, or CloudWatch logs.
- **ECS task definitions** reference those secrets via the `secrets` field
  (`valueFrom: <secret ARN>`), which injects them as environment variables
  at container start through the ECS agent — the running container's
  environment looks identical to local dev (same variable names), but the
  values never touch Terraform state or version control.
- **IAM task roles** are scoped per-service and least-privilege: the API
  task role gets `secretsmanager:GetSecretValue` only for the specific
  secret ARNs it needs, not a wildcard; the worker task role gets the same
  narrow grant, not broader access "just in case."
- **Non-secret configuration** (`APP_ENV`, `APP_URL`, `TEMPORAL_ADDRESS`,
  feature flags) belongs in **AWS Systems Manager Parameter Store**
  (standard, unencrypted-at-rest tier is fine for non-sensitive values) —
  cheaper and simpler to read/audit than Secrets Manager for values that
  aren't credentials.
- Terraform should reference secret ARNs (a `data "aws_secretsmanager_secret"` lookup or a
  write-only resource with `lifecycle { ignore_changes = [secret_string] }`
  for values rotated outside Terraform), never inline a real secret value
  as a Terraform variable/output — `terraform plan`/`show`/state files must
  never contain plaintext credentials.

None of this is implemented yet — Phase 10/AWS deployment hasn't started
(see `docs/RESUME_BUILD.md`) — but every provider variable already follows
the flat `<PROVIDER>_CLIENT_ID`/`_CLIENT_SECRET`/`_REDIRECT_URI` shape
Secrets Manager + ECS `secrets` injection expects, so wiring this up later
is infrastructure work, not an application-code change.
