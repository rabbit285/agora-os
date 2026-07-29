# Known Limitations

Honest accounting of what Phase 1 does **not** do yet, per the spec's
"Definition of Done" (§83) and "No Fake Features" (§82) rules. This is not
a bug list — it's scope not yet built, tracked here so nothing is silently
implied to work.

## Product scope

- **Compliance, Security, Sales, Support, and Automation** (the five
  primary product modules) have zero domain logic — their nav entries
  route to a `/coming-soon` page. See `docs/IMPLEMENTATION_PLAN.md` for
  the phase order.
- **The Knowledge module ingests documents but nothing retrieves them
  yet.** Upload → parse → chunk → embed → store all work end to end, but
  Phase 2 (spec's "Knowledge & AI Infrastructure") isn't finished — there
  is no similarity search, no RAG pipeline, and no AI Copilot yet.
  `/api/v1/ai/copilot/ask` is still a minimal exercise of the gateway
  (prompt in, demo/real text out), not grounded retrieval (spec §8–9).
  Embeddings are stored (JSON, see ADR-0007) but unused until that's built.
- **Document parsing supports text/plain, text/markdown, text/csv, PDF,
  and DOCX only.** XLSX, PPTX, images/OCR are not implemented; uploading
  them marks the document `unsupported_format` honestly rather than
  pretending to extract text (spec §82).
- **No entity/relationship extraction** (spec §11's knowledge graph).
  Chunks are stored flat with no cross-linking to other entities yet.
- **No invitation flow.** New members can only join today via signup
  (which creates a new organization) or direct database insertion (see
  `tests/test_rbac.py` for the pattern). `/invite/[token]` is not built.
- **MFA is schema-only.** `users.mfa_enabled` / `mfa_secret_encrypted`
  columns exist; there is no enrollment or challenge flow yet.
- **No SSO/SAML/SCIM.** Reserved for Phase 10 per the spec.

## Trust and progressive access model (spec §B)

- **No connectors exist yet**, so Stage 1–4 of the progressive trust model
  (read-only → scoped write → approved automation → bounded
  auto-execution) has nothing to apply to. The `Approval` primitive and
  risk-classification fields exist and are wired into the Tasks/Approvals
  UI so the pattern is ready for the first connector (Phase 9).
- **No Trust Center page.** Reserved for the Compliance module (Phase 3).

## Security

- **Audit log append-only-ness is enforced at the application layer only**,
  not the database level yet — see ADR-0004 in `docs/DECISIONS.md`. No
  code path issues `UPDATE`/`DELETE` against `AuditEvent`, but a bug or a
  future contributor could still write one; a DB-level `REVOKE` requires
  the app to connect as a non-owning role, planned for the AWS/RDS phase.
- **No CSRF/CSP/rate limiting/SSRF middleware yet.** These matter once
  there are state-changing browser forms beyond auth and outbound-fetching
  features (connectors) to protect. Auth endpoints rely on the session
  cookie's `SameSite=Lax` plus JSON-only bodies (not form-encoded) as a
  baseline CSRF mitigation, not a complete one.
- **Cross-subdomain cookie sharing is unresolved for production.** Locally,
  the session cookie (host-only, domain=`localhost`) happens to be sent to
  both `localhost:3000` and `localhost:8000` because browsers don't scope
  cookie storage by port. A production deployment with `app.` / `api.`
  subdomains needs an explicit shared `Domain` attribute (e.g.
  `.agora-origin.example`) — not yet configurable via an environment
  variable.
- **No malware scanning on uploaded files.** `files.classification` and
  signed URLs exist; the "malware-scanning workflow" from spec §L3 is not
  implemented.
- **No rate limiting or brute-force protection on login/signup.**

## Email

- **No real transactional email provider.** Password reset logs the reset
  link instead of emailing it (see ADR-0003). Amazon SES integration is
  planned alongside the AWS deployment phase.

## Infrastructure

- **No AWS deployment exists.** Everything in spec §L/§M/§N (Terraform,
  ECS, RDS, CloudFront, WAF, GitHub Actions CI/CD) is documented as a plan
  in `docs/IMPLEMENTATION_PLAN.md` but not implemented. Only a local Docker
  Compose environment runs today.
- **No CI pipeline configured** (no `.github/workflows/*` yet).
- **Local port conflicts**: this development machine has other unrelated
  Docker projects (`compliance-os`, `ai-sales-os`) bound to the default
  ports; Agora Origin's compose stack uses an `infra/docker/.env`
  override (gitignored) for non-standard host ports on this machine only.
  See `docs/ENVIRONMENT_VARIABLES.md`.
- **The web container's Turbopack dev server doesn't reliably detect new
  route files added while it's already running**, on this Windows +
  Docker Desktop bind-mount setup (`next dev` itself warns "Slow
  filesystem detected"). Editing existing files hot-reloads fine; adding
  a brand-new page under `app/` needed `docker compose restart web` to be
  picked up. Not a code bug — a note for whoever's developing against
  this stack locally.
- **npm audit reports 12 high-severity advisories** in Next.js's bundled
  build-time dependencies (postcss, sharp, and eslint's transitive
  minimatch). All are build-tool-only (no runtime/user-facing exposure);
  `npm audit fix --force` would downgrade Next.js to version 9, which is
  actively harmful — not applied. Revisit when Next.js ships a patch.

## Testing

- **No Playwright/E2E tests yet.** Backend has tenant-isolation, RBAC, and
  auth-flow tests (pytest, 12 passing). Frontend has typecheck/lint/build
  verification but no browser-driven tests.
- **No AI evaluation fixtures.** Planned for Phase 2 once RAG exists.
- **The SQLite-backed unit test suite did not catch two real bugs that
  only surfaced during a live Docker smoke test**: (1) the MinIO bucket
  was never created outside the seed script, so the first real upload
  404'd; (2) the worker process crashed on its first real activity
  because it had never imported `app.identity.models`, so SQLAlchemy
  couldn't resolve a foreign key into the `users` table (fixed via
  `app/db/register_all_models.py`, see ADR-0010). Both are now fixed and
  covered by a live smoke test, but neither would have been caught by
  pytest alone — a reminder that fast in-memory tests validate logic, not
  cross-service integration.
- **The full-stack smoke test was API-level (curl), not a real browser
  click-through.** Verified: signup → session cookie → `/me` → create task
  → list tasks → AI gateway demo response, all through the live API
  container; CORS preflight confirmed for the web origin; the login page
  HTML renders with the correct title through the web container. Not
  verified: actually clicking through the React app in a browser (React
  Query fetching, the auth-guard redirect, form validation UX). No browser
  automation tool was available in this environment — this is a gap to
  close with real Playwright E2E tests, not just curl.
