# Agora Origin — Product Completeness Audit

**Audit date**: 2026-07-30
**Commit audited**: `e5fa62d` ("Add Data Transfers, completing Privacy and the full
Compliance/Trust program")
**Auditor constraint honored**: no product code was modified during this audit. `git
status` is clean at the time of writing; only the 5 documents listed below were added,
in a separate commit from all prior feature work.

This is an audit, not a status report. Every VERIFIED claim in the companion
`SPEC_TRACEABILITY_MATRIX.md` is backed by at least one of: a file:line code citation, a
fresh live HTTP/DB proof gathered in this session, or a named passing test in the fresh
206-test pytest run recorded below — never by a commit message, a doc checkbox, or a
route/model's mere existence.

---

## 1. Methodology

1. **Spec mapping**: extracted the full section-header line-map of the 8325-line
   `docs/AGORA_ORIGIN_MASTER_SPEC.md`, separating the AWS/infrastructure sections (A-N,
   largely excluded per this audit's scope) from the numbered product spec (§1-101,
   starting at line 2565).
2. **Parallel module audits**: dispatched 9 independent, isolated, read-only Explore
   agents (Platform Foundation, Knowledge/AI/Copilot, Compliance, Security, Sales,
   Support, Automation, Integrations, Enterprise/Routes), each given exact spec line
   ranges, exact backend/frontend directories, and a strict evidence-citation format. All
   9 completed and reported file:line evidence or explicit "NOT FOUND."
3. **Clean-environment verification** (a genuinely fresh, isolated database, not the
   existing seeded dev database — see §2 below).
4. **Fresh live smoke testing** against the running dev stack, using a disposable
   second organization created via real signup and fully cleaned up afterward — never
   touching or destroying the pre-existing "Acme AI Technologies" seeded dev data.
5. **Repo-wide code-smell sweep** for TODO/FIXME/NotImplementedError/mock/fake/stub
   outside the 9 subagents' clusters (`apps/worker`, root-level config), and a
   cross-check of every `mock`/`fake`-flagged file to confirm each was an honest,
   documented fallback rather than a hidden stub.
6. **Cross-reference check**: compared `docs/KNOWN_LIMITATIONS.md`'s own completeness
   claims and `docs/ROUTES_AND_SCREENS.md`'s route table against direct code/build
   evidence, rather than trusting them (both were found to contain inaccuracies — see
   `REMAINING_PRODUCT_GAPS.md` §A2, §A3).

## 2. Clean-environment verification results

All 20 checklist items were run against a genuinely empty, isolated throwaway database
(`audit_clean_test`, created and dropped inside the same running Postgres container via
`DATABASE_URL` override — the actual seeded dev database was never touched) or, where a
running stack was required, against the pre-existing dev containers without modifying
their data.

| # | Check | Result |
|---|---|---|
| 1 | Stack builds from clean checkout | ✅ 7 services running from `infra/docker/docker-compose.yml`, `docker-compose.yml` config inspected, all 3 Dockerfiles present |
| 2 | Docker services start | ✅ all 8 containers `Up`/`healthy` |
| 3 | Migrations apply from empty DB | ✅ all 21 migrations applied cleanly, in sequence, to `audit_clean_test` |
| 4 | Alembic has one valid head | ✅ `alembic heads` → single head `a121c274b0ab`; `alembic check` → no drift |
| 5 | Seed data loads, idempotent | ✅ `python -m app.seed` run twice against the fresh DB; second run made zero duplicate rows |
| 6 | Backend lint passes | ✅ `ruff check .` → "All checks passed!" |
| 6b | Backend format check | ✅ `ruff format --check .` → 131 files already formatted |
| 7 | Strict backend type checking | ✅ `mypy app` → "Success: no issues found in 94 source files" |
| 8 | All backend tests pass | ✅ fresh run, this audit: **206 passed, 0 failed**, 4 deprecation warnings only, 386.69s |
| 9 | Frontend lint passes | ✅ `npx eslint .` → clean, zero output |
| 10 | Frontend type checking | ✅ `npx tsc --noEmit` → clean, zero output |
| 11 | Frontend unit tests | ✅ `npx vitest run` → 2 test files, 23 tests, all passed |
| 12 | Production frontend build | ✅ `npm run build` → compiled successfully, 33 routes generated, 0 errors |
| 13 | Critical E2E (Playwright-equivalent) tests | 🔴 **none exist** — repo-wide search found no Playwright, Cypress, or equivalent E2E suite anywhere |
| 14 | No secrets committed | ✅ `.gitignore` covers `.env`/`.env.local`/`.env.*.local`; only `.env.example`/`.env.test.example` tracked; repo-wide grep for API-key/private-key/password patterns in tracked files found nothing; `infra/docker/.env` (port overrides only, no secrets) confirmed untracked and gitignored |
| 15 | System operates without third-party credentials | ✅ live Copilot ask returned a clearly labeled `"provider":"demo"` response rather than failing or fabricating a real-looking answer |
| 16 | Unconfigured providers marked "Not configured" | ✅ confirmed in Integrations settings UI copy and code (`apps/web/.../settings/integrations/page.tsx:434`) |
| 17 | Tenant isolation, ≥2 orgs | ✅ fresh live proof, 3 techniques (list-scoping, direct-ID-guess 404, header-spoof 403) — see `ACCEPTANCE_TEST_EVIDENCE.md` #21 |
| 18 | RBAC denial, restricted user | ✅ fresh live proof — `read_only` role: 403 on write, 200 on read — see `ACCEPTANCE_TEST_EVIDENCE.md` #22 |
| 19 | Audit events for critical actions | 🟡 **partially proven** — events ARE emitted for the actions tested, but a real, previously-undetected bug was found live: `object_id` is stored as the literal string `"None"` for ~8 of ~17 "created" event types (missing `db.flush()` before capturing the new row's ID) — see `REMAINING_PRODUCT_GAPS.md` §A1 |
| 20 | Duplicate/idempotency protection | ✅ fresh live proof — `close_opportunity_won` called twice on the same opportunity produced byte-identical responses and exactly one `Customer` row, not two |

**Item 13 and item 19 are the two checklist items that did not fully pass.** Item 13 is a
straightforward MISSING (no E2E suite exists at all). Item 19 is PARTIAL: the audit
mechanism is real and does write tenant-scoped, append-only rows for the correct action
names — the defect is narrower (broken resource-ID linkage on a known subset of actions)
but real and reproducible.

## 3. Requirement counts

Full requirement-by-requirement detail is in `SPEC_TRACEABILITY_MATRIX.md` (110 rows
across Platform Foundation, Knowledge & RAG, AI Gateway & Copilot, Compliance/GDPR/AI
governance, Security, Sales, Support, Automation, Integrations, the 5 named cross-module
scenarios, the Business Intelligence layer, and AWS-excluded items).

| Status | Count |
|---|---|
| **VERIFIED** | 43 |
| **IMPLEMENTED_NOT_LIVE_VERIFIED** | 1 |
| **PARTIAL** | 20 |
| **MISSING** | 42 |
| **AWS_EXCLUDED** | 4 |
| **Total** | 110 |

Of the 106 non-AWS-excluded requirements, 62 (20 PARTIAL + 42 MISSING) are not fully
verified — 58% of in-scope requirements.

Of the 25 required end-to-end scenarios (`ACCEPTANCE_TEST_EVIDENCE.md`): **14 VERIFIED,
8 PARTIAL, 2 MISSING** (data export/deletion execution; global search).

## 4. Blocking gaps (the items that most concretely block a "product complete" claim)

In rough priority order — see `REMAINING_PRODUCT_GAPS.md` for the full list and exact
missing work per item:

1. **Audit-event `object_id="None"` bug** — undermines the audit trail's core promise
   (link an event to the resource it concerns) for ~8 action types; small, mechanical fix
   (`await db.flush()` before capturing `.id`) but currently live in the running system.
2. **No E2E test suite** — zero Playwright/Cypress coverage; all UI-level correctness
   evidence in this audit came from manual live smoke-testing plus the backend test
   suite, not automated browser tests.
3. **`docs/KNOWN_LIMITATIONS.md` overstates 3 of 5 named cross-module scenarios** as
   "fully implemented" when only 2-3 of each scenario's 4-9 spec'd steps exist — the
   subset that exists is real and tested, but the completeness claim itself is inaccurate.
4. **Business Intelligence layer (spec §86-90)** — Business Process Discovery, AI
   Recommendation Engine, AI Daily Briefing, Business AI Memory, Business Rules Engine —
   entirely unbuilt, 5 of 5 requirements MISSING.
5. **Sales module beyond core CRUD** — ICP scoring, Lead Finder, Sequences, Sales Inbox,
   Meeting Assistant, Sales Intelligence all MISSING (5 of 9 Sales requirements).
6. **Security module depth** — Cloud Security, Identity Security entirely MISSING;
   Incident workspace has only a status enum, none of the spec'd
   Timeline/Evidence/Communication/Root-Cause structure.
7. **Automation architecture mismatch** — executes synchronously in-request with zero
   Temporal usage, contradicting spec §61 explicitly; only 3 of ~24 action types and 2 of
   ~16 trigger types are executable.
8. **Integrations connector coverage** — only 6 of the many spec'd §48 connector
   categories have any code; several major categories (Email, Marketing, Cloud, Identity
   beyond the 6, Engineering, Documents, Accounting) have zero connectors.
9. **Enterprise platform gaps** — no invitation flow, no email verification, no MFA
   beyond schema, no Billing/Entitlements, no Reporting module, no Global Search, no
   Global Create — all MISSING (SSO/SAML/SCIM, multi-entity, and agency-mode are
   consistent with the spec's own explicit Phase-10/"Future" deferral, and are treated
   as such rather than as broken attempts).
10. **Data export/deletion execution** — the DSAR *tracking* workflow is real and tested,
    but no endpoint actually executes a data export or erasure.

## 5. Final Verdict

Per the audit's own rule — verdict A requires **zero** PARTIAL and **zero** MISSING
requirements outside AWS-excluded scope — and given 20 PARTIAL + 42 MISSING non-AWS
requirements documented above with concrete evidence:

# B. PRODUCT NOT YET COMPLETE

This verdict is not a comment on the quality of what has been built: the 43 VERIFIED
requirements include a genuinely real AI gateway with honest demo fallback, a real
evidence-grounded RAG pipeline, a large and genuinely tested Compliance/Trust program (14
of 18 requirements VERIFIED), real tenant isolation and RBAC enforcement (proven live in
this audit against a freshly created second organization and a freshly created
restricted-role user), and several real, tested cross-module hooks. The codebase was also
found, independently and repeatedly, to be honest about most of its own limitations —
`docs/KNOWN_LIMITATIONS.md`, `docs/DECISIONS.md`'s ADRs, and the "Not configured" /
coming-soon UI states all reflect a "no fake features" discipline that this audit's
methodology (verify, don't trust) was specifically designed to catch violations of, and
found only a small number of (the audit-event bug, the 3 overstated cross-module
scenarios, and the stale `ROUTES_AND_SCREENS.md` entries — all now documented precisely
in `REMAINING_PRODUCT_GAPS.md`).

The verdict is B because the spec is large (101 numbered product sections plus the
Business Intelligence layer and full enterprise feature set) and substantial named
portions of it — an entire Business Intelligence layer, most of Sales and Security beyond
core CRUD, most of Automation's spec'd action/trigger surface, most of the Integrations
connector catalog, and most enterprise platform features (billing, reporting, global
search, invitations, email verification, MFA) — have no implementation at all yet. This
is independent of, and in addition to, the correctly-excluded AWS infrastructure/live
deployment items.

## 6. Recommendation

Prioritize, in this order: (1) the audit-event `object_id` fix (small, mechanical, fixes
a real defect in a completed feature — highest value-per-effort); (2) correcting
`docs/KNOWN_LIMITATIONS.md`'s scenario-completeness claim so the codebase's documentation
matches its own honesty discipline everywhere; (3) standing up even a minimal Playwright
suite covering the 25 acceptance scenarios in `ACCEPTANCE_TEST_EVIDENCE.md`, since none
exists today; then (4) work through `REMAINING_PRODUCT_GAPS.md` module-by-module,
treating the Business Intelligence layer and the non-CRUD halves of Sales/Security/
Automation/Integrations as the largest remaining bodies of net-new work, separate from
the Phase-10 enterprise items the spec itself already defers.
