# Sales Lead Finder — Audit

Audit date: 2026-08-05, on branch `ui/sales-lead-finder-enterprise` (created from `main`,
which already includes the full enterprise UI modernization — see
`docs/UI_MODERNIZATION_PLAN.md`). This audit inspects the Sales module and Lead Finder as
they exist today, before any code in this effort is written.

## 1. What "Lead Finder" means today

`apps/api/app/sales/lead_finder.py` (62 lines) is **not** an external prospecting
integration. Its own docstring says so directly: it finds the organization's own existing
`Account` rows that fit the org's ICP but have no open `Lead` tracking them yet, and
creates one. It never makes an external HTTP call and never sees a company or person that
isn't already in this organization's own database.

Concretely (`find_and_create_leads`):
1. Load the org's single `ICPProfile` row (industries + employee-count range).
2. Query all `Account` rows for the org; if a profile exists, keep only those with
   `icp_score >= 60.0`.
3. Exclude accounts that already have an open `Lead` (`status in new|qualified|contacted`).
4. Create a `Lead(source="lead_finder", status="new", score=account.icp_score)` for each
   remaining candidate.

The frontend's "Run Lead Finder" button (`apps/web/app/(app)/sales/page.tsx`) posts to
`POST /api/v1/sales/leads/find` and shows "considered N account(s), created M new lead(s)."
This is honest, real, tested code — just a fundamentally different capability from "search
5 million companies and their decision-makers," which does not exist anywhere in this
codebase today.

**Decision**: keep this endpoint and its semantics exactly as-is (it has real value and
real test coverage — surfacing accounts already in the CRM that are falling through the
cracks) rather than repurposing its name. The new external-discovery capability gets its
own route namespace, `/api/v1/sales/lead-finder/*`, so nothing about the existing endpoint,
its tests, or its frontend caller changes.

## 2. Sales domain model today

| Model | Table | Notes |
|---|---|---|
| `Account` | `sales_accounts` | The company record — no separate `Company` model exists. `icp_score` (Numeric 5,2), `status` (prospect/customer/churned). |
| `Contact` | `sales_contacts` | `do_not_contact` boolean already gates outreach sending (see §5). |
| `Lead` | `sales_leads` | Loosely linked to Account/Contact (both nullable). |
| `Opportunity` | `sales_opportunities` | Pipeline stage, value, cross-links to Support `Customer` on `closed_won`. |
| `OutreachMessage` | `sales_outreach_messages` | `status` includes `blocked` with a `blocked_reason` — real compliance gating already exists (see §5). |
| `ICPProfile` | `sales_icp_profiles` | One per org; industries + employee-count range only — no scoring dimensions beyond that. |
| `Sequence` / `SequenceStep` / `SequenceEnrollment` | `sales_sequences` etc. | Multi-step cadences; every automated send re-runs the same compliance check as a manual send. |
| `Campaign` | `sales_campaigns` | Named bulk-enrollment into one Sequence. |
| `Meeting` | `sales_meetings` | AI Copilot-grounded prep notes. |

No model exists today for: a saved search, a list/collection of prospected (not-yet-saved)
records, a provider search result, an enrichment job, provenance metadata, or a suppression
list independent of the `Contact.do_not_contact` flag. All of this is genuinely new.

## 3. What already exists that this effort must reuse, not duplicate

- **Provider-neutral adapter pattern** — `app/integrations/adapters/base.py`'s
  `OAuthConnectorAdapter` Protocol (+ dataclass results) and `app/ai/gateway.py`'s
  `ModelGateway` Protocol are the two existing "Protocol + real adapters + a Mock/Demo
  adapter that's never presented as live" abstractions in this codebase. The new
  `SalesDataProvider` Protocol (see `docs/SALES_DATA_PROVIDER_ARCHITECTURE.md`) follows the
  identical shape — it is a **new, sibling** Protocol, not a reuse of
  `OAuthConnectorAdapter`, because the capability surface is different (search/enrich, not
  OAuth-token-lifecycle + CRM-object sync).
- **HubSpot and Pipedrive already exist** as OAuth2 CRM-sync connectors in the Integrations
  module (`app/integrations/adapters/hubspot.py`, `pipedrive.py`) — real `httpx` calls
  against each provider's documented API, gated on `{PROVIDER}_CLIENT_ID`/`_SECRET`, never
  exercised end-to-end without real credentials. Per the brief, these "may supply CRM
  records and existing contacts" — this effort reads their already-synced data (via the
  existing `IntegrationConnection`/contact-sync tables) for existing-record cross-
  referencing, but does **not** duplicate them as new `SalesDataProvider` adapters, since
  neither exposes a company/people *search* capability today (both `capabilities()` will
  report `search_companies=False, search_people=False`).
- **Credential-gated honesty pattern** — every optional external credential in
  `app/config.py` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `CLEARBIT_API_KEY`, the six
  OAuth-provider triples, `AWS_SECURITY_SCAN_*`) follows the identical shape: absence never
  crashes the app, the feature just reports `configured=False`, and the key name (never its
  value) is logged at startup via `_diagnose()`. `APOLLO_API_KEY` slots into this exact
  pattern.
- **Existing Clearbit company enrichment** (`app/sales/enrichment.py`,
  `POST /accounts/{id}/enrich`) stays exactly as-is — a narrower, already-working
  firmographic-lookup path independent of the new Apollo-backed `enrich_company()`
  capability. Not merged, not removed; documented as intentionally coexisting in
  `SALES_DATA_PROVIDER_ARCHITECTURE.md`.
- **Compliance gating already exists**: `app/compliance/governance.py::check_contact_permission`
  already blocks outreach send/enrollment when `Contact.do_not_contact` is set, returning a
  `GovernanceDecision(allowed, reason)`. The new outreach-eligibility panel (§23 of the
  brief) extends this function's decision model (richer status enum, more reasons) rather
  than replacing it — every existing call site keeps working unchanged.
- **Temporal wiring pattern**: `apps/worker/worker/{workflows,activities,main}.py` +
  `app/integrations/workflow_client.py`'s `create_*_run` (sync row write) /
  `execute_*_run` (idempotent activity body, directly callable in tests) / `start_*`
  (Temporal `start_workflow` by string name) three-way split is the exact shape the new
  bulk-enrichment workflow follows.
- **RBAC**: `require_permission("key")` FastAPI dependency + `app/core/rbac.py`'s flat
  `PERMISSIONS` registry + `SALES_PERMISSIONS` list + `ROLE_PERMISSION_GRANTS`. New
  `sales.lead_finder.*` keys are added there, not a new mechanism.
- **Audit**: `app/audit/service.py::record_event()`, including its literal guard against
  `object_id == "None"` (i.e. always `db.flush()` before turning a freshly created row's id
  into a string for the audit call) — every new mutating action in this effort follows it.
- **Tenant scoping**: hand-declared `organization_id: Mapped[uuid.UUID] = mapped_column(...,
  ForeignKey("organizations.id"), nullable=False, index=True)` on every new table — there is
  deliberately no mixin for this in the codebase (SQLAlchemy declarative-mapping
  constraint), enforced by `tests/test_tenant_isolation.py`-style tests instead.

## 4. Gaps this effort fills

- No external company/people search of any kind.
- No provider-neutral sales-data abstraction (Apollo doesn't exist anywhere in this repo —
  confirmed via a case-insensitive repo-wide search returning zero matches).
- No saved searches, no saved lists, no provenance tracking, no deduplication beyond
  incidental `Account`/`Contact` uniqueness, no credit tracking, no structured CSV import
  (the only existing CSV code path treats CSV as unstructured document text for the
  Knowledge module's embedding pipeline — not a tabular import pipeline; not reusable here).
- No natural-language-to-filter AI assist anywhere in Sales.
- No decision-maker-finding capability.
- No selective/bulk enrichment workflow (Temporal or otherwise) for external data.
- ICP scoring is two dimensions only (industry, employee count) — no confidence, no
  per-criterion match/no-match breakdown, no evidence/source per signal.
- Outreach eligibility is a single boolean (`do_not_contact`) with one reason — no
  suppression list independent of a saved `Contact`, no staleness/verification-based
  "Requires Review" tier, no lawful-basis metadata.

## 5. UI inconsistencies inherited from before this effort

The Sales module's frontend (`apps/web/app/(app)/sales/`) already went through the earlier
enterprise UI modernization pass (`ui/enterprise-modernization`, merged to `main`) — the hub
page and Support/Security-style list pages use the shared `DataTable`/`MetricCard`/token
design system. The ICP Builder, Campaigns, Sequences, and detail pages are retokenized but
still hand-rolled forms/lists (documented as deferred structural work in
`docs/UI_MODERNIZATION_PLAN.md`). None of them have a filter sidebar, saved search/list
concept, or bulk-action toolbar — this effort is the first to need those patterns in Sales,
though the shared `DataTable`, `FilterBar`, `EmptyState`/`ErrorState`/`LoadingSkeleton`,
`StatusBadge`/`SeverityBadge`, `Card`, dropdown/dialog primitives, and design tokens already
exist and are reused directly (see `docs/DESIGN_SYSTEM.md`).

## 6. Provider limitations to design around, not paper over

- **Apollo's actual API** exposes organization search, people search, and enrichment
  endpoints, each metered separately with its own credit cost that Apollo's response
  headers/bodies report per-call — not a flat, predictable rate. The credit-tracking design
  (`docs/SALES_DATA_PROVIDER_ARCHITECTURE.md` §Credit tracking) treats "actual credits" as
  authoritative when Apollo returns it and clearly labels an estimate as an estimate
  otherwise, per the brief's explicit "never fabricate credit values" instruction.
- **LinkedIn**: no scraping, no automated login, no bot, no unofficial messaging. The
  richest LinkedIn field this build can ever honestly show is a **URL** a licensed provider
  (Apollo) returns as part of a person record, opened manually by the user, plus a "draft a
  message" helper that composes text the user copies — never an automated send.
- **HubSpot/Pipedrive as sales-data sources**: real, but read-only and CRM-object-shaped,
  not discovery-shaped — this effort's `capabilities()` for those two adapters honestly
  reports no search support rather than faking one against sync-cache data.

## 7. Conclusion

This is a greenfield build on top of a real, working, already-tested Sales module and an
established set of architectural conventions (adapter Protocols, credential-gated honesty,
Temporal sync-run pattern, RBAC/audit/tenant-isolation discipline) that this effort follows
rather than reinvents. See `docs/SALES_DATA_PROVIDER_ARCHITECTURE.md` for the concrete
design and `docs/SALES_LEAD_FINDER_IMPLEMENTATION_PLAN.md` for the phased build-out.
