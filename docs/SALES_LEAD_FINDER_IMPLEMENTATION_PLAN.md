# Sales Lead Finder — Implementation Plan

Branch: `ui/sales-lead-finder-enterprise`. Companion docs:
`docs/SALES_LEAD_FINDER_AUDIT.md` (what exists), `docs/SALES_DATA_PROVIDER_ARCHITECTURE.md`
(concrete design). This plan executes in dependency order, each slice implemented for real,
checked, and committed separately — the same discipline used for
`docs/UI_MODERNIZATION_PLAN.md`.

## Scope and honesty about pacing

This is a large backend-plus-frontend build: ~8 new database tables, a new provider
Protocol with a real Apollo adapter, a new Temporal workflow, a CSV import pipeline,
RBAC/audit/compliance extensions, and an entirely new frontend workspace. Given the size,
this plan makes the same kind of transparent scoping calls as the UI modernization effort:
build real, tested, working vertical slices in priority order; where a sub-feature is
narrowed for this pass, say so explicitly in the relevant commit and in
`docs/SALES_DATA_PROVIDER_ARCHITECTURE.md` §17 rather than silently shipping a thinner
version under the same name.

## Phase 0 — Backend foundation

1. `app/config.py`: add `apollo_api_key`, wire into `_diagnose()`.
2. `app/sales/providers/`: `base.py` (Protocol + dataclasses), `schemas.py` (typed
   request/response models), `status.py` (`SalesProviderStatus` enum), `demo.py`
   (deterministic demo adapter), `apollo.py` (real adapter), `registry.py`
   (`get_provider()`, `list_providers()`, `is_apollo_configured()`).
3. Migration (`down_revision = "04c732fd7697"`): `sales_provider_records`,
   `sales_provider_credit_usage`, `sales_saved_searches`, `sales_lists`,
   `sales_list_items`, `sales_suppression_entries`, `sales_import_jobs`,
   `sales_enrichment_jobs`; partial unique index on `sales_contacts(organization_id,
   lower(email))`.
4. `app/core/rbac.py`: add the 7 new `sales.lead_finder.*` / `sales.suppression.manage`
   keys; extend `ROLE_PERMISSION_GRANTS` per §14 of the architecture doc.

**Done when**: migration applies cleanly on a fresh DB and rolls back cleanly; `apollo.py`
unit-tested against a mocked `httpx` transport (real request shape, real error mapping);
demo adapter unit-tested deterministic; `ruff` + strict `mypy` clean.

## Phase 1 — Search, saved searches, lists (backend)

1. `app/sales/lead_finder_service.py`: `search_companies`/`search_people` (provider
   dispatch + Redis cache per §8 of the architecture doc + dedupe-check composition),
   `find_decision_makers`.
2. `app/sales/saved_search_service.py`, `app/sales/list_service.py`: CRUD, tenant-scoped,
   audited.
3. New router `app/routers/sales_lead_finder.py` mounted at `/api/v1/sales/lead-finder`:
   `POST /companies/search`, `POST /people/search`, `POST /companies/dedupe-check`,
   `POST /people/dedupe-check`, `POST /decision-makers`, `GET/POST/PATCH/DELETE
   /saved-searches`, `POST /saved-searches/{id}/run`, `GET/POST/PATCH/DELETE /lists`,
   `POST /lists/{id}/items`, `DELETE /lists/{id}/items/{item_id}`,
   `GET /providers`, `GET /providers/{key}/usage`.
4. Natural-language filter parsing: `app/sales/nl_filter_parser.py` using the existing
   `ModelGateway.generate_structured()` (same pattern as any other structured AI call in
   this codebase) against a `ParsedFilters` Pydantic schema — returns filters only, never
   records; `POST /api/v1/sales/lead-finder/parse-query` returns the parsed filters plus a
   list of any requested criteria the schema couldn't represent (`unsupported_criteria`),
   for the frontend to show honestly rather than silently drop.

**Done when**: full pytest coverage per `docs/SALES_LEAD_FINDER_IMPLEMENTATION_PLAN.md`
§Testing below for this slice; RBAC-denial + cross-org-404 tests for every new route;
cache tenant-isolation test; NL-parser test asserting it returns structured filters, never
fabricated company/person records (a fake `ModelGateway` in tests, no real model call).

## Phase 2 — Selective enrichment, credit tracking, Temporal workflow

1. `app/sales/enrichment_job_service.py`: `create_enrichment_job`/`execute_enrichment_job`
   split per the architecture doc's Temporal section.
2. `apps/worker/worker/workflows.py` + `activities.py` + `main.py`: register
   `SalesBulkEnrichmentWorkflow`.
3. `app/sales/workflow_client.py::start_bulk_enrichment`.
4. Router: `POST /api/v1/sales/lead-finder/enrich` (selective, sync path for ≤5 records),
   `POST /api/v1/sales/lead-finder/enrich/bulk` (Temporal path, returns job id),
   `GET /api/v1/sales/lead-finder/enrichment-jobs/{id}`.
5. `app/sales/provider_models.py::SalesProviderCreditUsage` write path wired into every
   provider call that spends credit.

**Done when**: `execute_enrichment_job` directly callable and tested without a live
Temporal worker (existing pattern); a Docker-stack integration test proves the workflow
actually runs end-to-end through the real worker container; partial-failure test (2 of 5
records fail) asserts job status `partial` with populated `error_records`.

## Phase 3 — Compliance, suppression, deduplication wiring

1. `app/compliance/governance.py::evaluate_outreach_eligibility` per architecture doc §12.
2. `app/sales/suppression_service.py`: add/remove/list suppression entries.
3. Update `app/routers/sales.py`'s sequence-enroll and campaign-create/enroll call sites to
   call `evaluate_outreach_eligibility` and block (not just warn) on `blocked`.
4. `OrganizationSettings.requires_lawful_basis_metadata` column + settings UI toggle
   (Settings → Organization).

**Done when**: existing `test_sales_sequences_and_campaigns.py` and `test_sales.py`
suppression tests still pass unmodified (the extended function is a superset of the old
one's behavior); new tests for suppression-list-only (no Contact yet) blocking, requires-
review staleness, and the lawful-basis toggle.

## Phase 4 — CSV import and manual entry

1. `app/sales/csv_import.py` per architecture doc §13; `SalesImportJob` model + router
   routes (`POST /api/v1/sales/lead-finder/import/preview`,
   `POST /api/v1/sales/lead-finder/import/commit`, `GET .../import-jobs/{id}`).
2. Manual entry: `POST /api/v1/sales/lead-finder/companies/manual`,
   `.../people/manual` — thin wrappers that create a `SalesProviderRecord` with
   `provider="manual"`, `verification_status="user_entered"`, then delegate to the same
   save-as-Account/Contact path search results use.

**Done when**: import of a 500-row fixture CSV completes via the Temporal path with a
correct error report for intentionally-malformed rows; manual entry never marks a record
verified; audit events fire for both paths.

## Phase 5 — Frontend: shell, filter sidebar, provider status

1. `apps/web/app/(app)/sales/lead-finder/{page.tsx,companies/page.tsx,people/page.tsx,
   saved-searches/page.tsx}`, `apps/web/app/(app)/sales/lists/page.tsx`. Update
   `lib/navigation.ts` to add Lead Finder + Lists under the Growth group.
2. `components/sales/lead-finder-filter-sidebar.tsx` (collapsible, grouped filters per the
   brief's §8 — Lists / Company / Signals / Qualification / People groups, active-filter
   chip row, explicit "Run search" rather than per-keystroke re-fetch).
3. `components/sales/sales-provider-status.tsx` (new — the `SalesProviderStatus` vocabulary
   from the architecture doc; visually consistent with, but not the same component as,
   `IntegrationCard`).
4. Reuse `DataTable`, `FilterBar`, `EmptyState`/`ErrorState`/`LoadingSkeleton`,
   `StatusBadge`/`SeverityBadge` from the existing design system — no new table primitive.

**Done when**: filter sidebar renders all groups with real backend-sourced option lists
where applicable (e.g. industries), active-filter chips reflect current state and are
individually removable, provider-not-configured state shows Apollo as `Not configured`
with the exact env-var name.

## Phase 6 — Frontend: Companies and People workspaces

1. Companies table: default columns per the brief's §9, sorting, pagination, column
   visibility, density, row selection (page + all-eligible-with-confirmation), row overflow
   menu, all required states.
2. People table: mirrors Companies per §10.
3. Contextual bulk-selection toolbar (§11): selected/eligible/duplicate/already-saved
   counts, credit estimate preview before enrichment, confirmation.
4. Natural-language search bar wired to `parse-query`, editable-filters review step before
   running the real search (§12).

**Done when**: Playwright journeys 2, 5, 10, 11, 12, 13 (see `docs/
SALES_LEAD_FINDER_IMPLEMENTATION_PLAN.md` §Testing) pass against the live dev stack with
Apollo unconfigured (demo-labeled results) — a real live-Apollo run is only exercised when
real credentials are supplied, per the brief's §37.

## Phase 7 — Frontend: Company detail, person drawer

1. `apps/web/app/(app)/sales/companies/[id]/page.tsx` — tabs per the brief's §13, reusing
   `EntityTabs`/`DetailHeader`/`ActivityTimeline` from the design system (the first Sales
   detail page to adopt them — the earlier UI modernization pass deferred this for existing
   Sales detail pages; this is new code, so it starts on the standardized pattern directly).
2. Person detail drawer (`components/sales/person-detail-drawer.tsx`, built on the existing
   Radix `Dialog` primitive per the design system's drawer convention) per §14.
3. Outreach eligibility panel component (`components/sales/outreach-eligibility-panel.tsx`)
   shared between the person drawer and the bulk-action confirmation flow.

**Done when**: Playwright journeys 3, 4, 6, 16 pass; eligibility panel shows all 4 states
(Eligible/Requires Review/Blocked/Unknown) against fixture data in a Vitest component test.

## Phase 8 — Cross-cutting verification

Full check suite (§37 of the brief): Ruff, strict mypy, full pytest, migration up/down
check, tenant-isolation + RBAC tests; ESLint, strict TypeScript, Vitest, `next build`,
Playwright, accessibility spot-check; Docker smoke test; provider-not-configured test;
demo-mode test. Screenshots per §36. Documentation updates per §38.

## Testing (maps to brief §35)

Backend: filter normalization, NL parsing, capability handling, not-configured, pagination/
sorting/caching (+ tenant isolation), selective + bulk enrichment, deduplication, saved
searches/lists, CSV import, manual entry, rate-limit/retry, provenance, credit estimate vs.
actual, RBAC, suppression, eligibility, campaign gating, audit object-ids, partial failure.

Frontend (Vitest): filter groups, chips, saved searches, pagination/sorting/columns/
density, selection, bulk actions, enrichment preview, not-configured state, demo labeling,
duplicate state, compliance gating, detail views, loading/error states.

Playwright journeys (19, matching the brief's §35 list numbering exactly):
1 open Lead Finder · 2 manual company search · 3 open company · 4 find decision-makers ·
5 people search · 6 open person drawer · 7 save company as Account · 8 save person as
Contact · 9 create Lead · 10 save+rerun search · 11 add to list · 12 start selective
enrichment · 13 credit preview · 14 not-configured state · 15 demo labeling · 16 duplicate
detection · 17 campaign compliance block · 18 restricted-role denial · 19 cross-tenant
denial.

## Commit strategy (brief §39, followed literally)

1. Audit + architecture docs (this commit).
2. Provider-neutral backend foundation.
3. Saved searches, lists, deduplication.
4. Apollo adapter and configuration states.
5. Companies workspace.
6. People workspace.
7. Company and person details.
8. Selective enrichment and Temporal workflows.
9. Compliance and outreach gating.
10. Playwright, accessibility, and documentation.

Sub-slices within a numbered commit (e.g. migration vs. service vs. router within commit 2)
are committed separately when a slice is independently testable, following the same
"implement → check → commit" discipline as every prior effort in this codebase.
