# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are complete. Phases 3-5 (Compliance, Security, Sales)
each have their core backbones built and verified**, but not their larger
sub-features. See `docs/RELEASE_CHECKLIST.md` and
`docs/IMPLEMENTATION_STATUS.md` for the itemized list.

Working and verified end to end: everything from Phase 1-4, plus:
Account/Contact/Lead/Opportunity/OutreachMessage with a genuine
compliance-gated send — a contact marked `do_not_contact` cannot receive
outreach (the message is marked `blocked`, not silently dropped or faked
as sent). `/sales` and `/sales/accounts/[id]` render this live, including
a working suppression toggle and compose-and-send flow. All
lint/typecheck/test/build checks pass (51 backend tests, ruff + mypy
--strict clean; frontend eslint + tsc + production build clean).

No other domain module (Support, Automation) has been started. No AWS
infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the full
phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's missing —
notably, Sales has no real email/LinkedIn sending (status transitions
only), no sequences/campaigns, and no lead-finding/enrichment (all need
external connectors from Phase 9). The AI Copilot still only retrieves
from Knowledge documents — Compliance, Security, and Sales data all exist
now but none of it is wired into Copilot retrieval yet.

## Branch and commit

Branch: `main`. Six substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, Phase 2 completion (RAG + Copilot), Phase 3
Compliance backbone, Phase 4 Security backbone, and this Phase 5 Sales
backbone. See `git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

## Exact commands already run (this session, on top of Phase 1-4)

```bash
cd infra/docker
docker compose ps   # confirm the stack from earlier sessions is still up

# Migration for sales_accounts/sales_contacts/sales_leads/
# sales_opportunities/sales_outreach_messages
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add sales module tables"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

docker compose run --rm api python -m app.seed   # ran twice, confirmed idempotent

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 51 passed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npm run build
```

## Next highest-priority task

**Start Phase 6 — Customer Support** (spec sections 30–35, 6th module in
`docs/IMPLEMENTATION_PLAN.md`). Suggested dependency order, following the
`app/compliance/` / `app/secops/` / `app/sales/` pattern:

1. **Data model**: `app/support/models.py` — customers, tickets,
   ticket_messages, support_intents (or a category field, mirroring
   `SecurityFinding.category` — ADR-0017's consolidation pattern likely
   applies here too), knowledge_articles, csat_responses (spec §50). A
   `Customer` here is distinct from Sales' `Account`/`Contact` — consider
   whether to link them (a converted Sales Account becoming a Support
   Customer is one of the spec's cross-module use cases, §69 "New
   Customer") rather than modeling two disconnected concepts.
2. **Cross-module hook candidates** (pick one, don't try all): spec §35
   explicitly calls out "Ticket mentions security breach → mark urgent →
   notify Security → create incident → notify Compliance → preserve
   evidence." A simpler, still-real version: a ticket tagged/categorized
   as a security concern creates a `SecurityAlert` (mirrors the
   Security→Compliance and Compliance→Task hooks already built). Or: an
   AI-drafted support response above a configured confidence threshold
   auto-resolves the ticket, otherwise it requires human approval — this
   would be the first real use of the `core.Approval` primitive by a
   domain module, which nothing has exercised yet despite it existing
   since Phase 1.
3. **Migration**, then `app/routers/support.py` — customers, tickets
   (create, detail, status transitions), knowledge articles. Add
   `support.tickets.manage` / `support.knowledge.manage` permission keys,
   granted to `support_manager` and `support_agent` (both seeded with
   zero permissions).
4. **Frontend**: replace `/coming-soon?module=support` — inbox/ticket
   list first, ticket detail second.
5. Tests: tenant isolation + RBAC denial (same pattern as prior phases),
   plus whichever cross-module hook you build.
6. Update `docs/DATABASE_MODEL.md`, `docs/DOMAIN_MODEL.md`,
   `docs/IMPLEMENTATION_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`, and
   this file when done.

Realistic scope note, same shape as the last three phases: real AI
ticket-drafting grounded in the knowledge base is possible right now
(the Copilot/retrieval infrastructure already exists — `app/ai/copilot.py`
could be reused or adapted for support-specific grounding), but real
multi-channel ticket ingestion (email, chat widgets) depends on
connectors that don't exist yet.

## Files to edit next

- `apps/api/app/support/` (new package: `models.py`, `schemas.py`, `service.py`)
- `apps/api/app/routers/support.py` (new)
- `apps/api/app/core/rbac.py` (new permission keys, grant to `support_manager`/`support_agent`)
- `apps/api/migrations/versions/` (new revision)
- `apps/api/app/seed.py` (seed a customer, a couple tickets, one knowledge article for the demo org)
- `apps/api/tests/test_support.py` (new)
- `apps/web/lib/navigation.ts` (flip `support` to `implemented: true`)
- `apps/web/app/(app)/support/` (new pages)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (51 passed)
```
