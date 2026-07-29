# Security Assumptions

What Phase 1's security posture currently relies on, stated explicitly so
future work (and any security review) knows what's assumed vs. verified.

## Trust boundary

- The FastAPI process is the only thing that talks to PostgreSQL directly.
  The Next.js server and browser never hold database credentials.
- The browser is fully untrusted. Every authorization decision (tenant
  membership, RBAC permission) is re-derived server-side on every request
  from the session cookie — a client-supplied `organization_id` is only
  ever used to *select* which of the caller's own memberships to activate,
  never to grant access by itself (see `app/dependencies.py::get_org_context`).
- MinIO/S3 is only reachable from the API/worker containers on the
  internal Docker network in local dev; the browser only ever receives
  short-lived signed URLs, never storage credentials.

## Session model

- A session is valid if and only if its hashed token matches a row in
  `sessions` with `revoked_at IS NULL` and `expires_at` in the future.
  There is no other path to authentication.
- Logging out, resetting a password, and (once built) an admin-initiated
  "sign out everywhere" all work by setting `revoked_at` — there is no
  separate token-denylist to keep in sync.
- Passwords are hashed with Argon2id (`argon2-cffi`) using library
  defaults; no custom parameter tuning has been performed or benchmarked
  for this deployment's expected load.

## What Phase 1 does *not* defend against

Read `docs/KNOWN_LIMITATIONS.md` for the full list. The highest-signal
gaps for a security reviewer: no rate limiting on auth endpoints, no CSRF
token (relies on `SameSite=Lax` + JSON-only request bodies), no DB-level
enforcement of the audit log's append-only property, and no malware
scanning on uploaded files.

## Assumptions inherited from configuration

- `SECRET_KEY` must be a real random value in any non-development
  environment; `app/config.py` refuses to boot with the placeholder value
  when `APP_ENV=production`. Nothing currently enforces this for
  `APP_ENV=staging` — a gap worth closing before staging carries any real
  data.
- `COOKIE_SECURE` must be `true` everywhere the app is served over HTTPS.
  It defaults to `false` for local HTTP-only development and is not
  auto-derived from `APP_ENV`.
- AI provider adapters (`AnthropicAdapter`, `OpenAIAdapter`) send whatever
  string is passed as `GenerateRequest.prompt` to the provider verbatim.
  No prompt-injection defenses exist yet because no Phase 1 code path
  passes untrusted (uploaded/connector) content into the gateway — this
  assumption breaks the moment Phase 2's Knowledge module starts feeding
  retrieved document content into prompts, and spec §F5 must be
  implemented before that ships.
