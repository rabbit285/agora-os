# Resume Build

Read this first if you're picking up this build in a new session. It is
kept current at the end of every work session per the execution contract's
"leave an exact, executable continuation record" rule.

## Where things stand

**Phase 1 (platform foundation) and Phase 2 (Knowledge & AI
Infrastructure) are complete. All five primary product modules —
Compliance, Security, Sales, Support, and Automation (Phases 3-7) — have
a real, tested backbone. Phase 8 (Cross-Module Intelligence) has three of
spec §69's five named scenarios fully implemented, plus a partial fourth
with two of its steps done. Phase 9 (Integrations) has two connector
shapes complete: a generic inbound Webhook connector, and a
provider-neutral OAuth2 framework with six real (credential-gated)
adapters — HubSpot, Google, Microsoft, GitHub, Slack, Salesforce.
Compliance now also has AI Governance (AI System Inventory + AI
Incidents) and Privacy (RoPA/DPIA/DSAR) sub-features.** See
`docs/RELEASE_CHECKLIST.md` and `docs/IMPLEMENTATION_STATUS.md` for the
itemized list.

Most recent slice: **AI Incidents** (`AIIncident`,
`app/compliance/models.py` — spec §50's "AI GOVERNANCE" `ai_incidents`
table). Always tied to a specific `AISystem` (`ai_system_id`
non-nullable, unlike `DPIA`'s optional links), with severity
(low/medium/high/critical) and a deliberately simple
open→investigating→resolved→closed lifecycle — not `SecurityIncident`'s
eight-stage IR vocabulary, which is security-response-specific and
doesn't map naturally onto "a model gave biased decisions."

**Cross-module hook (ADR-0030)**: `create_ai_incident` reuses
`app.secops.service.create_incident`'s exact `critical`-severity chain
for a **third** time (after Security's own use, ADR-0018, and its Phase 8
extension, ADR-0023): a critical AI incident creates a linked Compliance
`Risk` (`category="ai_governance"`), a response `core.Task`
(`module="compliance"`, `priority="urgent"`), and — if owned — a
`core.Notification`. This wasn't copied reflexively: a critical AI
incident and a critical security incident represent the same underlying
obligation (assess and respond to a serious incident affecting people —
EU AI Act Article 73's "serious incident" reporting duty plays the same
role GDPR's breach-notification duty plays for `SecurityIncident`), so
reusing the identical chain is the correct call, not just a
pattern-match. RBAC reuses the existing `compliance.ai_systems.manage`
permission rather than minting a new one — AI incidents are managed by
whoever already manages the AI System Inventory.

**Frontend**: an AI Incidents section on `/compliance` (log form with an
AI-system picker, severity select, list) and
`/compliance/ai-incidents/[id]` detail — mirrors
`/security/incidents/[id]`'s exact layout (status workflow, linked-Risk
banner, linked-Task banner), reusing the existing `SeverityBadge`
component.

**Seed data**: 1 critical AI incident logged against the demo org's
already-seeded high-risk "Applicant Resume Screening Assistant" AI
system, producing a real linked Risk and response Task.

All lint/typecheck/test/build checks pass: **157 backend tests** (was
149), ruff + mypy --strict clean; frontend eslint + tsc + production build
clean; **10 frontend tests** (was 8; 2 new for AI Incidents), all
passing.

No AWS infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the
full phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's
missing in each module. Compliance's AI Governance sub-feature is now
essentially complete for this build's near-term scope (Inventory +
Assessments + Incidents); Privacy still lacks data transfers (the one
remaining spec sub-feature, deliberately deferred — cross-border transfer
mechanisms/adequacy decisions/SCCs are a substantial feature with no
existing primitive to hang off of).

## Branch and commit

Branch: `main`. Seventeen substantive commits: Phase 1 platform
foundation, Phase 2 Knowledge ingestion, Phase 2 completion (RAG +
Copilot), Phase 3 Compliance backbone, Phase 4 Security backbone, Phase
5 Sales backbone, Phase 6 Support backbone, Phase 7 Automation backbone,
Phase 8 Support Upsell Signal, Phase 8 Security Incident chain
extension, Phase 9 Webhook connector, Phase 8 New Customer, Phase 9
OAuth2 framework + HubSpot, the AI System Inventory slice, the OAuth
framework completion slice, the Privacy (RoPA/DPIA/DSAR) slice, and this
AI Incidents slice. See `git log` for exact SHAs.

## Machine-specific note

This dev machine already runs two unrelated Docker projects
(`compliance-os` at `D:\AI SaaS`, ports 5432/6379/9000-9001/8000, and
`ai-sales-os`, ports 5433/6380) that predate this repository and are not
part of it. Agora Origin's compose stack was given alternate host ports via
a gitignored `infra/docker/.env` (see `docs/ENVIRONMENT_VARIABLES.md`) so
it doesn't collide with them. On a clean machine, delete or ignore that
override file to get the standard ports.

Docker Desktop on this machine has intermittently stopped mid-session more
than once. If `docker compose` commands start failing with `failed to
connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`,
launch it directly (`"/c/Program Files/Docker/Docker/Docker Desktop.exe"`)
and poll `docker info` every few seconds until it responds (~10-30s);
containers restart automatically once the daemon is back.

The **api and worker containers share `requirements.txt` but are built as
separate Docker images** — adding a Python dependency requires rebuilding
both (`docker compose build api worker`), not just the one you're actively
testing against (this bit the OAuth framework completion slice).

## Exact commands already run (this session)

```bash
# Migration for the ai_incidents table
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add ai incidents table"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 157 passed

# Seed script re-run (idempotent, confirmed on a second run)
docker compose run --rm --no-deps api python -m app.seed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npx vitest run   # -> 10 passed
npm run build
```

Still to do before this slice is fully closed out: restart the `api`/
`web` containers, run a live smoke test against the running stack (log a
critical AI incident against a real AI system and confirm the linked
Risk/Task appear via the real `/api/v1/compliance/risks` and
`/api/v1/tasks` endpoints, confirm a non-critical incident does *not*
create either, check `audit_events` for `compliance.ai_incident.*`
rows), then commit.

## Next highest-priority task

Both slices the user explicitly named ("Privacy workflows, then AI
Incidents") are now complete. No further direction has been given.
Reasonable directions, in priority order — none of these should be
started without confirming, since each is either a business decision or
a large, open-ended feature:

1. **If the user supplies real credentials** for a specific OAuth
   provider (any of the six adapters) or SSO/IdP metadata for Phase 10 —
   wire that in immediately; these are now small, bounded tasks given the
   existing adapter framework / RBAC groundwork.
2. **Enterprise Sales Security Review** (spec §69's last named
   cross-module scenario) needs customer questionnaires built first — a
   larger, self-contained feature, not just a cross-module link. This is
   the last of spec §69's five named scenarios still fully unstarted.
3. **Data transfers** (Privacy's remaining sub-feature) — cross-border
   transfer mechanisms, adequacy decisions, SCCs. A real, bounded,
   credential-free feature if the user wants Compliance rounded out
   further, but substantial enough to treat as its own slice rather than
   folding into a "continue" instruction silently.
4. **Vendor risk / questionnaires / audits (auditor portal) / Trust
   Center / regulatory intelligence feed** — spec §12's remaining
   Compliance sub-features, each a substantial standalone feature.
5. Phase 10 (Enterprise: SSO/SAML/SCIM, public API + webhooks) or the AWS
   production deployment (spec §L/§M/§N) — both are large, self-contained
   next arcs, but SSO needs a real IdP and AWS deployment needs real cloud
   spend, so treat starting either as a business decision to confirm
   first, not something to infer from a bare "go on."

Given no further explicit instruction exists at the time of writing, the
right move on a bare continuation signal is to ask which of the above the
user wants, rather than guessing at a multi-day feature — unlike the
Privacy/AI Incidents slices, which were explicitly named.

## Files to edit next (if data transfers are added)

- `apps/api/app/compliance/models.py` (new `DataTransfer` model — likely:
  processing_activity_id or organization-level, destination
  country/region, transfer mechanism (SCCs/adequacy decision/BCRs/
  derogation), safeguards description)
- `apps/api/app/compliance/service.py`, `schemas.py`,
  `app/routers/compliance.py` — following the RoPA/DPIA/DSAR pattern
  (ADR-0029) as the template
- migration + tests + `apps/web/lib/types.ts` + a new section on
  `/compliance`
- `docs/DECISIONS.md` (new ADR)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (157 passed)
cd ../../apps/web && npx vitest run   # confirm still green (10 passed)
```
