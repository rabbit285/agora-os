# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are complete. Phases 3-6 (Compliance, Security, Sales,
Support) each have their core backbones built and verified**, but not
their larger sub-features. See `docs/RELEASE_CHECKLIST.md` and
`docs/IMPLEMENTATION_STATUS.md` for the itemized list.

Working and verified end to end, on top of everything from Phase 1-5:
Customer/Ticket/TicketMessage/KnowledgeArticle/CSATResponse, with a
genuine cross-module hook — a ticket categorized `security` automatically
creates a linked `SecurityAlert` in the Security module's triage inbox and
escalates the ticket to `urgent` priority (spec §35, ADR-0020). `/support`
and `/support/tickets/[id]` render this live: creating a security-tagged
ticket, then following its "Linked Security Alert" banner to confirm the
alert is real and visible through `/api/v1/security/alerts`. All
lint/typecheck/test/build checks pass (61 backend tests, ruff + mypy
--strict clean; frontend eslint + tsc + production build clean).

No other domain module (Automation) has been started. No AWS
infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the full
phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's missing —
notably, Support has no real channel connectors (email/chat), no SLA
policies, no QA scoring, and no AI-drafted replies (the Copilot/retrieval
infrastructure from Phase 2 could support this but nothing wires Support
into it yet). The AI Copilot still only retrieves from Knowledge
documents — Compliance, Security, Sales, and Support data all exist now
but none of it is wired into Copilot retrieval yet.

## Branch and commit

Branch: `main`. Seven substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, Phase 2 completion (RAG + Copilot), Phase 3
Compliance backbone, Phase 4 Security backbone, Phase 5 Sales backbone,
and this Phase 6 Support backbone. See `git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session, on top of Phase 1-5)

```bash
cd infra/docker
docker compose ps   # confirm the stack from earlier sessions is still up

# Migration for support_customers/support_tickets/support_ticket_messages/
# support_knowledge_articles/support_csat_responses
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add support module tables"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

docker compose run --rm --no-deps api python -m app.seed   # ran twice, confirmed idempotent

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 61 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build

# Live smoke test against the running Docker stack (see below)
docker compose restart api web
```

## Next highest-priority task

**Start Phase 7 — Business Automation** (spec sections 36-43, the last of
the five primary product modules; spec calls it "a major platform
capability" — expect this to be the largest single phase so far).
Suggested dependency order, following the `app/compliance/` /
`app/secops/` / `app/sales/` / `app/support/` pattern:

1. **Data model**: `app/automation/models.py` — `Workflow` (name,
   trigger_type, trigger_config JSON, steps JSON — an ordered list of
   typed step definitions, status: draft|active|paused|archived — spec
   §37/§42 versioning), `WorkflowRun` (workflow_id, status:
   running|succeeded|failed|awaiting_approval, trigger_payload JSON,
   started_at, completed_at), `WorkflowStepRun` (run_id, step_index,
   step_type, status, input/output JSON) so a run's execution is
   inspectable after the fact, not just a pass/fail.
2. **Scope discipline warning**: spec §37 lists a huge step vocabulary
   (Trigger/Action/Condition/AI Step/Human Approval/Delay/Loop/Data
   Transform/Webhook/Notification/Subworkflow). Do not try to build a
   general visual workflow engine in one slice — per the established
   pattern (spec §80: ship one real vertical, not a stub of everything),
   implement a small, fixed set of step *types* that actually execute
   (e.g. `create_task`, `send_notification`, `human_approval`) rather
   than a generic interpreter. A real React Flow visual builder (spec
   §37's "visual workflow concepts") is a substantial frontend investment
   on its own — consider shipping the backbone with a JSON-defined
   workflow (created via a simple form: name + trigger + ordered step
   list) before the drag-and-drop builder, the same way Sales shipped
   real CRUD before a lead-finder UI.
3. **Cross-module hook candidate**: a `human_approval` step type is the
   natural fit — it should create a real `core.Approval` row and pause
   the `WorkflowRun` at `awaiting_approval` until a decision is recorded,
   then resume. This would be the first domain module to actually
   exercise the `core.Approval` primitive beyond Phase 1's own generic
   UI (noted as unused by any domain module as of Phase 5's resume
   notes) — a genuinely disciplined choice reusing spec §80's shared
   primitives. Alternatively/additionally: spec §38 lists `Control
   failed` and `Security alert` as trigger types — a workflow could
   subscribe to Compliance/Security events already emitted via
   `record_event`, closing the loop the other direction (a domain event
   triggers automation, rather than automation creating a domain
   object). Pick one, not both, for this slice.
4. **Migration**, then `app/routers/automation.py` — workflows (create,
   list, detail, publish/pause/archive status transitions), runs (list,
   detail with step log), a manual "run now" trigger endpoint for the
   demo (`Manual` is explicitly listed as a trigger type in spec §38, so
   this is not a shortcut — it's a real supported trigger). Add
   `automation.workflows.manage` / `automation.runs.manage` permission
   keys, granted to `automation_manager` (seeded with zero permissions).
5. **Frontend**: replace `/coming-soon?module=automation` — workflow
   list + create form first, workflow detail (steps + run history)
   second. A visual drag-and-drop builder is out of scope for this
   slice; a structured list-based step editor is enough to be genuine.
6. Tests: tenant isolation + RBAC denial (same pattern as prior phases),
   a full run executing all seeded step types end to end, and whichever
   cross-module hook you build.
7. Update `docs/DATABASE_MODEL.md`, `docs/DOMAIN_MODEL.md`,
   `docs/IMPLEMENTATION_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`, and
   this file when done.

Realistic scope note, same shape as the last four phases: workflow
*triggers* like "new email," "new CRM lead," "form submission," and
"webhook" all depend on external connectors or public-facing endpoints
that don't exist yet (progressive trust model, spec §B1) — the Manual
trigger and the "subscribe to an internal domain event" pattern above are
the only triggers that can be real today.

## Files to edit next

- `apps/api/app/automation/` (new package: `models.py`, `schemas.py`, `service.py`)
- `apps/api/app/routers/automation.py` (new)
- `apps/api/app/core/rbac.py` (new permission keys, grant to `automation_manager`)
- `apps/api/migrations/versions/` (new revision)
- `apps/api/app/seed.py` (seed one workflow with 2-3 steps and one completed run for the demo org)
- `apps/api/tests/test_automation.py` (new)
- `apps/web/lib/navigation.ts` (flip `automation` to `implemented: true`)
- `apps/web/app/(app)/automation/` (new pages)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (61 passed)
```
