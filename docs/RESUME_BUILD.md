# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are complete. All five primary product modules —
Compliance, Security, Sales, Support, and Automation (Phases 3-7) — now
have a real, tested backbone**, but not their larger sub-features. See
`docs/RELEASE_CHECKLIST.md` and `docs/IMPLEMENTATION_STATUS.md` for the
itemized list.

Working and verified end to end, on top of everything from Phase 1-6:
Workflow/WorkflowRun/WorkflowStepRun, with a genuine cross-module hook —
a `human_approval` workflow step creates a real Phase 1 `core.Approval`
and pauses the run at `awaiting_approval` until that Approval is decided
through the existing `/api/v1/approvals/{id}/decide` endpoint (spec §42,
ADR-0021) — the first domain module to actually exercise that primitive
outside its own generic UI. `/automation` and
`/automation/workflows/[id]` render this live: creating a workflow with a
`human_approval` step, publishing it, running it, watching it pause, then
deciding the approval and resuming to completion. Workflow governance is
real but simple — a workflow's steps can only be edited via `PATCH
.../steps` while `status = draft`; publishing to `active` locks them
(spec §41). All lint/typecheck/test/build checks pass (70 backend tests,
ruff + mypy --strict clean; frontend eslint + tsc + production build
clean).

No AWS infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the
full phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's
missing in each module — notably, Automation only executes 3 step types
(`create_task`, `send_notification`, `human_approval`) out of spec §37's
much larger vocabulary, and only the `manual` trigger works (every other
trigger needs external connectors, Phase 9). The AI Copilot still only
retrieves from Knowledge documents — Compliance, Security, Sales,
Support, and Automation data all exist now but none of it is wired into
Copilot retrieval yet.

## Branch and commit

Branch: `main`. Eight substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, Phase 2 completion (RAG + Copilot), Phase 3
Compliance backbone, Phase 4 Security backbone, Phase 5 Sales backbone,
Phase 6 Support backbone, and this Phase 7 Automation backbone. See
`git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session, on top of Phase 1-6)

```bash
cd infra/docker
docker compose ps   # confirm the stack from earlier sessions is still up

# Migration for automation_workflows/automation_workflow_runs/
# automation_workflow_step_runs
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add automation module tables"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

docker compose run --rm --no-deps api python -m app.seed   # ran twice, confirmed idempotent

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 70 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build
```

Still to do before this phase is fully closed out: restart the
`api`/`web` containers to pick up this session's code, run a live
curl-based smoke test proving the `human_approval` hook works against the
real running stack (create a workflow with a `human_approval` step,
publish it, run it, confirm it pauses at `awaiting_approval` with a real
row in `/api/v1/approvals`, decide it, resume, confirm it reaches
`succeeded`), then commit.

## Next highest-priority task

**Start Phase 8 — Cross-Module Intelligence** (spec section 69 lists five
named cross-module scenarios; spec section 43 covers automation
analytics; this phase is explicitly about connecting modules that already
exist rather than building a new one). Recommended approach, following
the discipline established every phase so far — pick ONE real, narrow
vertical rather than all five scenarios at once:

1. **Best first candidate: "Support Upsell Signal"** (spec section 69).
   It only touches two modules that already exist and need no new
   tables of their own — Support and Sales — making it the cheapest
   genuine slice to ship. Concretely: when a support ticket is created
   (or perhaps when N tickets from the same customer share a signal —
   keep the trigger condition simple and honest, e.g. a manual "flag as
   upsell signal" action on a ticket rather than inventing NLP pattern
   detection that doesn't exist), create a `sales.Lead` linked to the
   ticket's customer (via `Customer.sales_account_id` where present) and
   a `core.Notification` to the account owner. This reuses three
   existing primitives (Ticket, Lead, Notification) instead of inventing
   a new `sales_signal` type — same "shared primitives" discipline as
   every ADR so far (spec §80).
2. **Second candidate, larger: "Security Incident" cross-module chain**
   (spec section 69) — Security Incident → Compliance risk (already
   built, ADR-0018) → **new**: incident response Tasks + a notification
   to the responsible team. This extends the existing Phase 4 hook
   rather than building something new; smaller lift than it looks
   because half the chain already exists.
3. Do **not** attempt "Enterprise Sales Security Review" or "New AI Tool
   Adoption" yet — both require modules/data that don't exist (customer
   questionnaires, AI system inventory) and would need real feature work
   in Compliance first, not just a cross-module link.
4. Whichever scenario you pick: add the hook to the *originating*
   module's existing service function (e.g. `app/support/service.py` if
   extending ticket creation), not a new "orchestration" module — spec
   §69's examples are the payoff of modules sharing primitives, not a
   reason to add a workflow-engine-on-top-of-the-workflow-engine.
5. Tests: the hook itself, plus confirming it's visible through the
   *other* module's existing generic endpoint (same verification pattern
   as every previous ADR — e.g. `test_security_category_ticket_creates_linked_alert`
   asserts the alert via `/api/v1/security/alerts`, not by reading the
   ticket alone).
6. Update `docs/DATABASE_MODEL.md` (only if a new column/table is
   needed — the Support Upsell Signal candidate above needs none),
   `docs/DOMAIN_MODEL.md`, `docs/IMPLEMENTATION_STATUS.md`,
   `docs/IMPLEMENTATION_PLAN.md`, `docs/DECISIONS.md` (next ADR,
   0022), and this file when done.

Realistic scope note: spec section 69 also describes an "AI daily
briefing," "business process discovery," an "AI recommendation engine,"
and "organization memory" as part of Phase 8 — these are large,
open-ended AI features with no existing primitive to hang them off of
(unlike the five named scenarios, which mostly reuse Tasks/
Notifications/Approvals/Risks that already exist). Treat them as
separate, later slices once at least one concrete cross-module scenario
is real, rather than starting there.

## Files to edit next (if the Support Upsell Signal candidate is chosen)

- `apps/api/app/support/service.py` (extend, or add a new
  `flag_upsell_signal` function alongside `create_ticket`)
- `apps/api/app/routers/support.py` (new endpoint, e.g.
  `POST /tickets/{id}/flag-upsell`)
- `apps/api/tests/test_support.py` (extend with the new hook's tests)
- `apps/web/app/(app)/support/tickets/[id]/page.tsx` (a button to flag
  the signal, and a banner if the ticket already has one — same pattern
  as the existing "Linked Security Alert" banner)
- `docs/DECISIONS.md` (ADR-0022)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (70 passed)
```
