# Sales Data Provider Architecture

Companion to `docs/SALES_LEAD_FINDER_AUDIT.md` (what exists today) and
`docs/SALES_LEAD_FINDER_IMPLEMENTATION_PLAN.md` (build order). This is the concrete design
for the provider-neutral company/people discovery and enrichment layer behind the Lead
Finder.

## 1. Why a new Protocol, not a reuse of `OAuthConnectorAdapter`

`app/integrations/adapters/base.py`'s `OAuthConnectorAdapter` Protocol models an OAuth2
token lifecycle plus one generic `sync()` call that pulls CRM objects into
`IntegrationConnection`/`SyncRun`. Apollo doesn't use OAuth (API-key auth) and doesn't
"sync" anything — a caller asks it a search or enrichment question and gets an answer back.
HubSpot/Pipedrive's *existing* adapters stay exactly what they are. This effort adds a
sibling Protocol, `SalesDataProvider`, in `app/sales/providers/base.py`, modeled on the same
"Protocol + real adapters + a Demo adapter never presented as live" shape used by both
`ModelGateway` (`app/ai/gateway.py`) and `OAuthConnectorAdapter`.

```python
class SalesDataProvider(Protocol):
    provider_key: str  # "apollo" | "hubspot" | "pipedrive" | "csv" | "manual" | "demo"

    def capabilities(self) -> ProviderCapabilities: ...
    async def health(self) -> ProviderHealth: ...

    async def search_companies(self, request: CompanySearchRequest) -> CompanySearchResponse: ...
    async def search_people(self, request: PersonSearchRequest) -> PersonSearchResponse: ...
    async def enrich_company(self, request: CompanyEnrichRequest) -> CompanyEnrichResponse: ...
    async def enrich_person(self, request: PersonEnrichRequest) -> PersonEnrichResponse: ...
    async def find_decision_makers(self, request: DecisionMakerRequest) -> PersonSearchResponse: ...
    async def estimate_credit_usage(self, request: CreditEstimateRequest) -> CreditEstimate: ...

    def normalize_company(self, raw: dict[str, Any]) -> NormalizedCompany: ...
    def normalize_person(self, raw: dict[str, Any]) -> NormalizedPerson: ...
```

`ProviderCapabilities` is a dataclass of booleans (`company_search`, `people_search`,
`company_enrichment`, `person_enrichment`, `decision_makers`, `credit_estimation`) so the
registry and UI can honestly disable actions a given provider doesn't support instead of
calling a method that would raise `NotImplementedError`. HubSpot/Pipedrive adapters (added
in a later slice, not this pass's Apollo-focused first cut — see the implementation plan)
report every search/enrich capability `False` and exist only so the provider-selector UI can
show them as connected-but-non-discovery sources; today's implementation only registers
`apollo` and `demo`.

## 2. Typed request/response schemas

All in `app/sales/providers/schemas.py`, versioned via a `schema_version: Literal[1]` field
on every top-level request/response so a future breaking provider-schema change doesn't
silently corrupt cached or stored data.

```python
@dataclass
class CompanySearchRequest:
    schema_version: Literal[1]
    organization_id: uuid.UUID
    filters: CompanyFilters       # name, domain, locations, employee_range, industries,
                                   # keywords, revenue_range, funding_stage, technologies, ...
    page: int
    page_size: int
    sort: SortSpec | None

@dataclass
class NormalizedCompany:
    provider: str
    provider_record_id: str
    name: str
    domain: str | None
    website: str | None
    industry: str | None
    locations: list[str]
    employee_count: int | None
    employee_range: str | None
    revenue_range: str | None
    funding_stage: str | None
    total_funding_usd: int | None
    technologies: list[str]
    linkedin_url: str | None
    source_url: str | None
    retrieved_at: datetime
    raw: dict[str, Any]           # bounded, provider-namespaced — see §7 retention

@dataclass
class CompanySearchResponse:
    schema_version: Literal[1]
    provider: str
    companies: list[NormalizedCompany]
    total_available: int | None   # provider's own total-match count when it reports one
    page: int
    page_size: int
    credits_used: int | None      # only when the provider actually reports it (§6)
```

`NormalizedPerson` mirrors this for people: `full_name`, `title`, `seniority`, `department`,
`company_domain`, `location`, `email` (nullable), `email_status`
(`verified|unverified|catch_all|unavailable`), `phone` (nullable), `phone_status`,
`linkedin_url`, `provider`, `provider_record_id`, `retrieved_at`. **`normalize_*` never
invents a field** — a field the provider didn't return is `None`/empty, never guessed.

## 3. Apollo adapter (`app/sales/providers/apollo.py`)

Real `httpx` calls against Apollo's documented REST API, gated by `settings.apollo_api_key`
(`APOLLO_API_KEY`, added to `app/config.py` next to `clearbit_api_key` following the
identical `Field(default=None, alias=...)` shape — see §5). Endpoint mapping:

| Protocol method | Apollo endpoint |
|---|---|
| `search_companies` | `POST https://api.apollo.io/v1/mixed_companies/search` |
| `search_people` | `POST https://api.apollo.io/v1/mixed_people/search` |
| `enrich_company` | `POST https://api.apollo.io/v1/organizations/enrich` |
| `enrich_person` | `POST https://api.apollo.io/v1/people/match` |
| `find_decision_makers` | `search_people` with a seniority filter (`owner`, `founder`, `c_suite`, `vp`, `director`) scoped to the target company's domain — Apollo has no separate "decision makers" endpoint, so this is a documented, honest composition of `search_people`, not a fabricated capability |
| `health` | a zero-cost `GET /v1/auth/health`-equivalent (Apollo has no dedicated health endpoint; this build uses a minimal `search_people` call with `page_size=1` against the calling org's own domain and treats a non-5xx/non-401 response as healthy, documented in the adapter's docstring since it does consume a trivial amount of credit — no free alternative exists) |

`estimate_credit_usage` returns an **estimate**, not a guarantee — Apollo's own credit cost
varies per record type/enrichment depth and is only authoritative in Apollo's own response.
The adapter's estimate is a documented, conservative per-record constant
(`APOLLO_ESTIMATED_CREDITS_PER_COMPANY = 1`, `_PER_PERSON = 1`, `_PER_ENRICHMENT = 1`) shown
to the user labeled "Estimated" everywhere in the UI; the *actual* credits Apollo reports
in a response (when present) are what gets recorded to `SalesProviderCreditUsage` (§6).

Error handling: Apollo's `429` maps to `ProviderRateLimited` (honors `Retry-After` when
present, else exponential backoff starting at 2s, factor 2, max 3 attempts — mirrors
`IntegrationSyncWorkflow`'s existing `RetryPolicy` shape); `401`/`403` maps to
`ProviderAuthError` (surfaced as `Failed` with "credentials rejected," never silently
falling back to demo data — an authored, once-working key that's since been revoked must
never look identical to "never configured"); `5xx` maps to `ProviderUnavailable` (surfaced
as `Degraded`); a connection/timeout error also maps to `ProviderUnavailable`.

## 4. Demo adapter (`app/sales/providers/demo.py`)

Deterministic, seeded from a hash of the request filters (same pattern as `DemoAdapter` in
`app/ai/gateway.py` — stable across repeated calls in tests) — a small fixed catalog of
clearly-fictional companies/people (`"Northwind Robotics (Demo)"`, `demo@example.invalid`
style emails, no real company/person names or domains). Every record's `provider = "demo"`.
This is what runs whenever `APOLLO_API_KEY` is unset — **automatic fallback, not a
per-organization toggle**: this matches the AI Gateway's own established behavior
(`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` unset → `DemoAdapter`, no separate "demo mode" setting
exists anywhere else in this codebase) rather than inventing a new organization-level
concept the brief didn't ask for and nothing else in the app has. The frontend renders a
"Demo data" badge identically to how the Copilot already does this for `provider == "demo"`.

## 5. Configuration

`app/config.py` gains, next to `clearbit_api_key`:

```python
apollo_api_key: str | None = Field(default=None, alias="APOLLO_API_KEY")
```

Added to `_diagnose()`'s `optional_flags` (name-only logging, never the value). Documented
in `.env.example`, `.env.test.example` (unset — tests exercise the Demo adapter path plus
a mocked-`httpx` real-adapter unit test), and `docs/ENVIRONMENT_VARIABLES.md`'s existing
"optional" table format. `TOKEN_ENCRYPTION_KEY`/Fernet (`app/core/crypto.py`) is **not**
needed for Apollo in this build — it's a single deployment-wide key read from process
environment, identical in shape to `ANTHROPIC_API_KEY`, not a per-organization OAuth secret
stored in the database. AWS Secrets Manager / Render secret env vars work automatically
since both inject values as regular process environment variables, which
`pydantic-settings` already reads — no additional code needed, documented as a deployment
note only.

## 6. Credit tracking

New table `sales_provider_credit_usage` (`app/sales/provider_models.py`):

```
id, organization_id, provider, operation
  (search_companies|search_people|enrich_company|enrich_person|find_decision_makers),
estimated_credits, actual_credits (nullable — Unknown until the provider reports it),
requested_by_user_id (nullable), requested_by_workflow_id (nullable),
source_record_ids (JSON list, bounded),
succeeded (bool), created_at
```

`GET /api/v1/sales/providers/{key}/usage` aggregates this per organization for a "monthly
usage" view; the UI shows `estimated_credits` before an action, `actual_credits` (or
"Unknown" when the provider response didn't report it) after. No arithmetic ever fabricates
a value the provider itself didn't supply — the honesty rule from the brief applies
literally to this field.

## 7. Provenance and retention

New table `sales_provider_records` — the single provenance source of truth for **both**
company and person records, whether or not they've been saved as an `Account`/`Contact`:

```
id, organization_id, provider, record_type (company|person),
provider_record_id, normalized_domain (nullable), normalized_email (nullable),
source_url (nullable), retrieved_at, last_verified_at,
verification_status (verified|provider_supplied|unverified|unavailable|stale|user_entered|demo),
enrichment_status (none|partial|complete|failed),
confidence (nullable float, only when the provider reports one),
raw_payload (JSON — provider's normalized response only, not their entire raw HTTP body;
             capped and redacted of anything resembling a credential),
linked_account_id (nullable FK -> sales_accounts),
linked_contact_id (nullable FK -> sales_contacts),
imported_by_user_id (nullable), imported_by_workflow_id (nullable),
credit_usage_id (nullable FK -> sales_provider_credit_usage),
created_at
```

A `SalesProviderRecord` is created the moment a search result is returned to the UI *only
if the user takes an action on it* (save, enrich, add to list) — raw search-result pages
themselves are never persisted (see §8 caching for why), so browsing 5 million rows never
writes 5 million provenance rows. `linked_account_id`/`linked_contact_id` are populated when
"Save as Account"/"Save as Contact" runs, so a `Account`/`Contact` detail page can look up
its full provenance chain (there can be more than one `SalesProviderRecord` per Account over
time — e.g. an initial Apollo find plus a later Apollo re-enrichment — the most recent by
`retrieved_at` is authoritative for "last verified").

## 8. Caching and rate limits

Search results are cached for a short TTL (5 minutes, `SALES_SEARCH_CACHE_TTL_SECONDS`) in
Redis (already provisioned — see `infra/docker/docker-compose.yml`), keyed by
`sales:search:{organization_id}:{provider}:{record_type}:{sha256(normalized_filters)}:{page}:{sort}`.
Tenant isolation is structural (the key includes `organization_id`; a cross-tenant read is
a different key, not an access-control check that could be bypassed) — covered by a test
asserting two organizations issuing byte-identical filter queries get independent cache
entries. "Refresh" in the UI bypasses the cache read (still writes a fresh entry). No
person-level PII (email/phone) is cached beyond this same short TTL and the same
tenant-scoped key — this is the same trust boundary as any other per-request Redis usage
already in the app, not a new one.

Rate-limit and circuit-breaker behavior live in the Apollo adapter itself (§3) rather than a
generic cross-provider layer, since Apollo's limits (429 + `Retry-After`) are
provider-specific; the `SalesDataProvider.health()` result (`healthy|degraded|rate_limited|
failed`) is what the UI's provider-status chip reads, refreshed on a short poll (30s) while
the Lead Finder is open, not on every keystroke.

## 9. Provider state vocabulary (Sales-specific, distinct from `IntegrationStatus`)

`app/sales/providers/status.py` defines:

```python
class SalesProviderStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    READY_TO_CONNECT = "ready_to_connect"   # reserved: a future per-org key model
    CONNECTED = "connected"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    DISABLED = "disabled"
    REVOKED = "revoked"
    DEMO = "demo"
```

For Apollo today: `NOT_CONFIGURED` (no key) → `DEMO` is what actually serves requests;
`CONNECTED`/`HEALTHY` (key present, last health check ok); `DEGRADED` (key present, last
call succeeded but slow/partial); `RATE_LIMITED` (last call 429'd, shown with a
retry-after countdown when Apollo supplies one); `FAILED` (key present but rejected, or
provider unreachable). `DISABLED`/`REVOKED` are reserved for the future per-organization
key model (§13) — not reachable in this build's single deployment-wide-key configuration,
included in the enum now so the frontend `Badge` mapping and any later per-org credential
UI don't need a breaking vocabulary change.

`GET /api/v1/sales/providers` returns each registered provider's `capabilities()` +
`SalesProviderStatus` + (for Apollo) the last `health()` result — the same shape
`GET /api/v1/integrations/providers` already uses for the OAuth catalog, so the frontend's
`IntegrationCard`-derived component can render both with one visual language without being
the same component (different capability sets, deliberately not force-unified — see
`docs/SALES_LEAD_FINDER_IMPLEMENTATION_PLAN.md` for the specific new `SalesProviderCard`).

## 10. Deduplication

- **Companies**: match against existing `Account` rows by (in priority order) exact
  `SalesProviderRecord.provider_record_id`, then normalized domain
  (`_domain_from_website`-equivalent, already exists in `app/sales/enrichment.py` — reused,
  not reimplemented), then case-insensitive exact name match flagged as "possible duplicate"
  (never auto-merged — name matching alone is too weak to be authoritative).
- **People**: match by provider record id, then normalized email (lowercased, exact), then
  (current company domain + normalized full name) as a lower-confidence "possible duplicate"
  signal.
- `GET /api/v1/sales/lead-finder/companies/dedupe-check` and the people equivalent accept a
  batch of provider record references and return, per record,
  `{status: "new"|"existing"|"possible_duplicate", existing_account_id | existing_contact_id}`
  — called once when a page of search results renders (not per-row) so the UI can show the
  "Existing Record" column without N+1 requests. No new unique DB constraint is added for
  company name (too weak); a real unique constraint **is** added on
  `(organization_id, lower(email))` for `sales_contacts` where `email` is not null, since an
  exact-email duplicate contact is never legitimate — this is enforced at the DB layer
  (partial unique index), not just application code, with a migration data-cleanup step
  documented in the implementation plan for any pre-existing violators.

## 11. Saved searches and lists

```
sales_saved_searches: id, organization_id, owner_user_id, name, search_type (company|person),
  filters (JSON, the exact CompanyFilters/PersonFilters the search used),
  provider, columns (JSON), sort (JSON), density, is_shared (bool),
  created_at, updated_at, last_executed_at (nullable), last_result_count (nullable)

sales_lists: id, organization_id, owner_user_id, name, list_type (company|person),
  description (nullable), tags (JSON list), is_shared (bool), created_at, updated_at

sales_list_items: id, list_id, account_id (nullable FK), contact_id (nullable FK),
  added_by_user_id, added_at
  -- unique (list_id, account_id) and unique (list_id, contact_id) prevent silent dupes
```

A list item always points at a real, already-saved `Account`/`Contact` — "add to list" from
a raw search result implicitly runs "save as Account/Contact" first if the record isn't
saved yet (surfaced to the user as a single action, one API call, documented as such — never
a silent double-write the user didn't ask for).

## 12. Suppression and outreach eligibility

New table `sales_suppression_entries` (`organization_id, email (nullable, normalized),
domain (nullable), contact_id (nullable FK), reason, created_by_user_id, created_at`) —
deliberately independent of `Contact.do_not_contact` so a person can be suppressed **before**
they're ever saved as a Contact (e.g. a search result the user recognizes and never wants
contacted). `Contact.do_not_contact` stays exactly as-is for backward compatibility; a
contact is treated as suppressed if *either* its own flag is set *or* its email matches a
`sales_suppression_entries` row for the org.

`app/compliance/governance.py::check_contact_permission` is **extended**, not replaced —
it gains an optional richer result path used only by the new eligibility panel:

```python
async def evaluate_outreach_eligibility(
    db: AsyncSession, *, organization_id: uuid.UUID, contact: Contact | None,
    provider_record: SalesProviderRecord | None = None,
) -> OutreachEligibility:
    """status: eligible | requires_review | blocked | unknown, reasons: list[str]."""
```

It calls `check_contact_permission` first (existing suppression check, unchanged) and layers
on: suppression-list match (§ above) → `blocked`; verification status
`unverified`/`unavailable`/`stale` → `requires_review`; missing lawful-basis metadata when
`ORG_REQUIRES_LAWFUL_BASIS` policy is set (a new, off-by-default per-org
`OrganizationSettings` boolean, since no jurisdiction/consent-tracking concept exists yet in
this build and inventing one wholesale is out of scope — documented as a real limitation,
not silently skipped) → `requires_review`; nothing triggered → `eligible`; provider record
with no linked Contact and no email at all → `unknown` (nothing to evaluate yet). Every
campaign-enrollment and sequence-enrollment call site is updated to call this instead of the
narrower function directly, and to **block** enrollment outright (not just warn) on
`blocked`, matching the existing "sending is blocked automatically" behavior already
documented on the Account detail page.

## 13. CSV import

New module `app/sales/csv_import.py` — genuinely new, no existing generic pipeline to build
on (confirmed in the audit). Pipeline: upload (reuses the existing
`/api/v1/files/upload-url` presigned-upload flow already used by Knowledge/Evidence
uploads) → column-mapping preview (first 20 rows parsed with stdlib `csv`, column headers
matched against a fixed target-field list with a simple case-insensitive/fuzzy heuristic,
always user-confirmable/overridable, never auto-committed) → validation (required fields
per record type, email format, duplicate check via §10's dedupe logic) → background import
via a Temporal activity for files over a row-count threshold (200 rows), synchronous for
smaller files → a `SalesImportJob` row (`status`, `total_rows`, `imported_rows`,
`skipped_rows`, `error_rows` with a downloadable per-row error report) → every imported
record gets a `SalesProviderRecord` with `provider="csv"`,
`verification_status="user_entered"`.

## 14. RBAC additions

Added to `app/core/rbac.py`'s `PERMISSIONS` / `SALES_PERMISSIONS`:

```
sales.lead_finder.view            — view the Lead Finder workspace and run searches
sales.lead_finder.enrich          — trigger selective/bulk enrichment (spends credits)
sales.lead_finder.saved_searches.manage
sales.lead_finder.lists.manage
sales.lead_finder.import          — CSV import / manual entry
sales.lead_finder.providers.manage — configure/view provider status and credit usage
sales.suppression.manage          — add/remove suppression entries
```

`sales.lead_finder.view` is granted to both `sales_manager` and `sales_representative`
(read/search access for the whole team, matching the existing undifferentiated grant
pattern for other Sales permissions). `sales.lead_finder.providers.manage`,
`sales.suppression.manage`, and `sales.lead_finder.import` are granted to `sales_manager`
only — the first real manager/rep permission split in this module, called out explicitly
in the implementation plan since it's a behavior change from today's "identical grants for
both roles."

## 15. Audit events

`sales.lead_finder.search_executed`, `sales.lead_finder.saved_search.created/updated/deleted`,
`sales.lead_finder.company.saved`, `sales.lead_finder.person.saved`,
`sales.lead_finder.enrichment.started/completed/failed`, `sales.lead_finder.list.created/updated`,
`sales.lead_finder.list.item_added/removed`, `sales.lead_finder.import.started/completed`,
`sales.lead_finder.duplicate.detected`, `sales.suppression.added/removed`,
`sales.lead_finder.eligibility.blocked` (fired whenever `evaluate_outreach_eligibility`
returns `blocked` for a bulk-enrollment attempt, `policy_decision="denied"` — mirrors the
existing `sales.outreach.send_attempted` pattern), `sales.lead_finder.provider.status_changed`.
All follow the existing `record_event()` flush-before-id discipline.

## 16. Temporal workflow

`SalesBulkEnrichmentWorkflow` (`apps/worker/worker/workflows.py`, imports restricted to
`temporalio`/stdlib per the existing sandboxing discipline) — `run(job_id: str)`, single
activity `execute_sales_enrichment_activity` (`apps/worker/worker/activities.py`, lazy
app-imports inside the function body) with a `RetryPolicy` matching
`IntegrationSyncWorkflow`'s (5s initial, ×2 backoff, 1min max interval, 3 max attempts) plus
a per-record partial-failure loop **inside** the activity so one bad record doesn't fail the
whole batch — `SalesEnrichmentJob.status` becomes `partial` (not `failed`) when some records
succeed and some don't, with `error_records` (JSON list of `{record_id, error}`) populated.
`app/sales/workflow_client.py::start_bulk_enrichment` mirrors
`integrations/workflow_client.py::start_sync` exactly (lazy Temporal client construction,
`start_workflow` by string name, task queue `"agora-default"`). The synchronous
`create_enrichment_job()` / directly-callable `execute_enrichment_job()` split (usable in
tests without a live Temporal worker) mirrors `create_sync_run`/`execute_sync_run`.

## 17. What this design deliberately does not attempt in this pass

- Per-organization Apollo API keys (only a single deployment-wide key, matching the AI
  provider pattern) — `SalesProviderStatus.READY_TO_CONNECT`/`DISABLED`/`REVOKED` are
  reserved states for this future extension, not dead code without a reason.
- Full jurisdiction/lawful-basis/consent tracking — a single coarse
  `OrganizationSettings.requires_lawful_basis_metadata` boolean stands in for what a real
  compliance system would model as structured per-contact consent records; documented as a
  known limitation, not hidden.
- HubSpot/Pipedrive as real search-capable `SalesDataProvider` adapters — registered with
  `capabilities()` all `False` so the provider list is honest about what each can do, with
  full search/enrich support left as documented future work once (or if) either exposes it.
