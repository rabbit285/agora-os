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
that now has two of its steps. Phase 9 (Integrations) has two connector
shapes complete: a generic inbound Webhook connector, and a
provider-neutral OAuth2 framework with six real (credential-gated)
adapters — HubSpot, Google, Microsoft, GitHub, Slack, Salesforce.
Compliance also has an AI System Inventory (EU AI Act risk tiers) and,
as of this slice, Privacy sub-features (RoPA/DPIA/DSAR).** See
`docs/RELEASE_CHECKLIST.md` and `docs/IMPLEMENTATION_STATUS.md` for the
itemized list.

Most recent slice: **Privacy workflows** (`ProcessingActivity`, `DPIA`,
`DSAR` — spec §2/§12's Privacy sub-features of the AI Compliance module,
not a separate module; confirmed against the spec text before building,
since the numbered spec sections don't have a standalone "Privacy"
heading). All in `apps/api/app/compliance/`:

- **ProcessingActivity** — the organization's own RoPA entry (GDPR
  Article 30): name, purpose, legal basis (GDPR Article 6's six lawful
  bases), data categories, data subjects, retention period. Tenant-scoped
  like Control, unlike Framework/Requirement's global catalog data.
- **DPIA** (GDPR Article 35) — may link to a `ProcessingActivity`, an
  `AISystem`, both, or neither. A DPIA created directly with
  `risk_level="high"` gets its own real `core.Approval`, gating
  `approved` exactly like `AISystem` does (ADR-0027's pattern reused a
  third time — this build's fourth use of Approval outside its own
  generic UI).
- **The AI System hook extended a second time** (ADR-0029):
  `register_ai_system` now also creates a linked draft `DPIA` for
  high/unacceptable-risk systems — completing another step of spec §69's
  "New AI Tool Adoption" chain ("... -> Security assessment -> **Privacy
  assessment** -> ..."). No second Approval is created for this
  auto-linked DPIA — it shares the AI system's existing one, since a
  second sign-off gate for the same registration would be governance
  fatigue, not additional safety. This mirrors exactly how the Security
  Incident chain (Phase 8) extended its own hook twice (ADR-0018, then
  ADR-0023) rather than inventing a second mechanism each time.
- **DSAR** (GDPR Articles 15-20) — `due_at = created_at + 30 days` (GDPR
  Article 12(3)'s one-month response window), a
  received→in_progress→fulfilled/rejected lifecycle, `fulfilled_at` set
  automatically on completion.
- **RBAC**: new `compliance.privacy.manage` permission, granted to `dpo`
  (extending its existing Compliance + AI Governance grant) and `legal`
  — a system role seeded since Phase 1 with zero permissions, activated
  for the first time here (mirroring how `ai_governance_manager` was
  activated by the AI System Inventory slice).
- **Frontend**: RoPA/DPIA/DSAR sections added to `/compliance` (create
  forms + lists), plus `/compliance/dpias/[id]` (status workflow, a
  linked-Approval banner shown only when `approval_id` is set, findings,
  a link to any linked AI system) and `/compliance/dsars/[id]` (status
  workflow, due date with an overdue indicator, fulfilled date, notes).
- **Seed data**: 1 processing activity, 1 medium-risk standalone DPIA
  linked to it, 1 fulfilled DSAR, 1 still-open DSAR — the high-risk AI
  system already seeded by the prior slice now also produces its own
  linked DPIA for free, via the extended hook.

All lint/typecheck/test/build checks pass: **149 backend tests** (was
137), ruff + mypy --strict clean; frontend eslint + tsc + production build
clean; **8 frontend tests** (was 5; 3 new for the Privacy sections), all
passing.

No AWS infrastructure exists. See `docs/IMPLEMENTATION_PLAN.md` for the
full phase order and `docs/KNOWN_LIMITATIONS.md` for exactly what's
missing in each module. Not modeled yet in Privacy: data transfers (the
remaining spec sub-feature) — a substantial feature (cross-border
transfer mechanisms, adequacy decisions, SCCs) with no existing primitive
to hang it off of, deliberately deferred rather than half-built.

## Branch and commit

Branch: `main`. Sixteen substantive commits: Phase 1 platform foundation,
Phase 2 Knowledge ingestion, Phase 2 completion (RAG + Copilot), Phase 3
Compliance backbone, Phase 4 Security backbone, Phase 5 Sales backbone,
Phase 6 Support backbone, Phase 7 Automation backbone, Phase 8 Support
Upsell Signal, Phase 8 Security Incident chain extension, Phase 9 Webhook
connector, Phase 8 New Customer, Phase 9 OAuth2 framework + HubSpot, the
AI System Inventory slice, the OAuth framework completion slice, and this
Privacy (RoPA/DPIA/DSAR) slice. See `git log` for exact SHAs.

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
testing against. This bit the OAuth framework completion slice (the
worker's image predated `cryptography` being added, so its first real
Temporal activity call failed with `ModuleNotFoundError` until rebuilt).

## Exact commands already run (this session)

```bash
# Migration for the Privacy tables
docker compose run --rm --no-deps api alembic revision --autogenerate -m "add privacy processing activities dpias dsars"
docker compose run --rm --no-deps api ruff format migrations/
docker compose run --rm api alembic upgrade head
docker compose run --rm api alembic check   # confirms no drift

# Backend checks (all green)
docker compose run --rm --no-deps api sh -c "ruff check . && ruff format --check . && mypy app && pytest -q"
# -> 149 passed

# Seed script re-run (idempotent, confirmed on a second run)
docker compose run --rm --no-deps api python -m app.seed

# Frontend checks (all green)
cd apps/web
npx tsc --noEmit
npx eslint .
npx vitest run   # -> 8 passed
npm run build
```

Still to do before this slice is fully closed out: restart the `api`/
`web` containers, run a live smoke test against the running stack
(register a high-risk AI system and confirm a linked DPIA appears via
`GET /api/v1/compliance/dpias`; create a standalone high-risk DPIA,
confirm its own Approval gates `approved` via a 422 then a 200 after
deciding it; create a DSAR and confirm `due_at` is ~30 days out; check
`audit_events` for the new `compliance.dpia.*`/`compliance.dsar.*`
actions), then commit.

## Next highest-priority task

Per the user's explicit instruction, continue with **AI Incidents** next
— the second of the two credential-free slices named, and the piece that
completes AI Governance's near-term scope now that the Inventory (from
the prior slice) exists to link against.

1. **AI Incidents**: an incident log for AI systems, likely
   `AIIncident` mirroring `SecurityIncident`'s shape (severity, status,
   linked `AISystem`, `app/compliance/models.py`) — check spec §12/§19
   for what an AI-specific incident should capture that a generic
   SecurityIncident doesn't (e.g., "model produced a harmful/biased
   output" isn't quite a security incident). Look for a genuine
   cross-module hook before inventing one: does a `critical`-severity
   AIIncident plausibly warrant the same Risk-linking + Task +
   Notification chain `SecurityIncident` already has (ADR-0018,
   ADR-0023)? If the reasoning holds, reuse that exact pattern rather
   than a new mechanism — that would be this build's third reuse of that
   specific chain shape.
2. **Enterprise Sales Security Review** (spec §69's last named
   cross-module scenario) needs customer questionnaires built first — a
   larger, self-contained feature, not just a cross-module link.
3. **If the user supplies real credentials** for a specific OAuth
   provider (any of the six adapters) or SSO/IdP metadata for Phase 10 —
   wire that in immediately; these are now small, bounded tasks given the
   existing adapter framework / RBAC groundwork.
4. Phase 10 (Enterprise: SSO/SAML/SCIM, public API + webhooks) or the AWS
   production deployment (spec §L/§M/§N) — both are large, self-contained
   next arcs, but SSO needs a real IdP and AWS deployment needs real cloud
   spend, so treat starting either as a business decision to confirm
   first, not something to infer from a bare "go on."

## Files to edit next (AI Incidents)

- `apps/api/app/compliance/models.py` (new `AIIncident` model)
- `apps/api/app/compliance/service.py` — creation + cross-module hook if
  one is genuinely warranted (see reasoning above)
- schemas + router endpoints on the existing `/api/v1/compliance` router
  (same "extend Compliance, don't create a new module" reasoning ADR-0029
  used for Privacy) + migration + tests
- `apps/web/lib/types.ts`, a new section on `/compliance` + likely
  `/compliance/ai-incidents/[id]` detail
- `docs/DECISIONS.md` (new ADR)

## Command to resume

```bash
cd d:/agora-os
git status   # confirm clean tree before starting
cd infra/docker
docker compose up -d
docker compose run --rm --no-deps api pytest -q   # confirm still green (149 passed)
cd ../../apps/web && npx vitest run   # confirm still green (8 passed)
```
