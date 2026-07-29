# Release Checklist

Honest status against the spec's "Definition of Full Completion" (§J) and
"Definition of Done" (§83). This is a **Phase 1 / local-only** checkpoint,
not a production release — most items below are correctly unchecked.

## Phase 1 (platform foundation) — this checkpoint

- [x] Monorepo bootstrapped (`apps/api`, `apps/web`, `apps/worker`)
- [x] Local Docker Compose environment (Postgres+pgvector, Redis, MinIO, Temporal)
- [x] Clean-database migration works (`alembic upgrade head` from empty DB)
- [x] `alembic check` reports no model/migration drift
- [x] Seed script loads successfully and is idempotent
- [x] Auth: signup, login, logout, forgot/reset password
- [x] Tenant-context middleware + RBAC dependency enforced server-side
- [x] Audit log writes on every state-changing auth/task/approval/org action
- [x] Tasks, Approvals, Files, Notifications (shared primitives) — API + UI
- [x] AI Model Gateway + Demo adapter + real Anthropic/OpenAI adapter shells
- [x] Next.js app shell (sidebar, top nav, module switcher), auth pages, dashboard
- [x] Backend: ruff check, ruff format, mypy strict — all clean
- [x] Backend tests: 12 passing (auth flow, tenant isolation, RBAC denial)
- [x] Frontend: eslint, tsc --noEmit, production build — all clean
- [x] `.env.example` / `.env.test.example` / `docs/ENVIRONMENT_VARIABLES.md`
- [x] Missing AI/email credentials degrade gracefully (demo mode / logged email)
- [ ] Frontend automated tests (Playwright/unit) — not yet written
- [ ] Invitation flow, MFA enforcement — schema only, no flow

## Not started (tracked in docs/IMPLEMENTATION_PLAN.md)

- [ ] Phase 2 — Knowledge & AI Infrastructure (RAG, Copilot)
- [ ] Phase 3 — Compliance
- [ ] Phase 4 — Security module
- [ ] Phase 5 — Sales
- [ ] Phase 6 — Customer Support
- [ ] Phase 7 — Business Automation (workflow builder)
- [ ] Phase 8 — Cross-module intelligence
- [ ] Phase 9 — Integrations / connectors
- [ ] Phase 10 — Enterprise (SSO/SAML/SCIM)
- [ ] AWS Terraform, ECS, RDS, CloudFront, WAF, GitHub Actions CI/CD (spec §L/§M/§N)
- [ ] Trust Center
- [ ] Security release baseline (spec §H): CSRF, CSP, rate limiting, SSRF
      controls, malware scanning, brute-force protection

## Gate for calling *any* future milestone "production ready"

Before this checklist can claim more than Phase 1:

1. All items in `docs/KNOWN_LIMITATIONS.md` under "Security" resolved or
   explicitly risk-accepted with a named owner.
2. AWS deployment evidence recorded in `docs/DEPLOYMENT_EVIDENCE.md` and
   `docs/RECOVERY_TEST_RESULTS.md` (not yet created — see spec §N10).
3. Every domain module claims completion only per its own
   `docs/IMPLEMENTATION_STATUS.md` entry — no module is "done" because a
   route exists; it needs DB + service + API + RBAC + audit + UI + tests
   (spec §83).
