# UI Modernization Plan

Branch: `ui/enterprise-modernization`. Companion docs: `docs/UI_UX_AUDIT.md` (what was
wrong before this branch), `docs/DESIGN_SYSTEM.md` (the tokens and components this plan
builds and uses).

## Status: shipped, with specific deferrals called out honestly below

Every route in the app now renders on the shared design tokens (verified by an app-wide
grep sweep — zero raw Tailwind neutral/red/gray color classes remain in `app/` or
`components/`), the application shell is rebuilt and mobile-responsive, and the Command
Center, Governance, Growth, Customer Operations, Operations, Knowledge, Administration,
and Auth/Onboarding areas have all been touched. Within that, two different depths of
work were applied depending on whether a page had its own protected test suite:

- **Pages with no dedicated test file** (Dashboard, Copilot, Tasks, Approvals, Reports,
  Security, Sales, Support, Automation, Knowledge hub) got the full treatment: rebuilt
  onto `MetricCard`/`DataTable`/`InsightCard`/`CopilotPanel` with real loading/error/empty
  states, not just a color pass.
- **Pages with an existing test suite or E2E coverage exercising their exact DOM structure**
  (Compliance's 1,519-line hub, Integrations, most of Settings) were deliberately
  retokenized onto the design system — colors, spacing, the hand-rolled `<select>`
  styling — **without** restructuring their markup, because Radix `Tabs` unmounts inactive
  content by default and a DataTable conversion would have required rewriting each
  protected test to interact with a different DOM shape. That structural conversion is
  real, scoped follow-up work, not something silently skipped — it's listed under
  "Deferred" below so it isn't lost.

No backend behavior, API contract, RBAC rule, or tenant-isolation check changed anywhere
in this branch. Every commit is presentation-layer only.

## What shipped, phase by phase

**Phase 0 — Foundation.** Design tokens (`app/globals.css` rewritten: full color/type/
spacing/radius/shadow/layout scale, the Geist-font bug fixed, `data-theme` dark-mode
architecture in place though the toggle UI is deferred), 5 new Radix dependencies
(dialog/dropdown-menu/tabs/tooltip/popover), the 7 existing primitives restyled, and 21
new shared components built (`EmptyState`, `ErrorState`, `LoadingSkeleton`,
`PermissionDenied`, `MetricCard`, `InsightCard`, `DataTable`, `FilterBar`, `Breadcrumbs`,
`HealthIndicator`, `ActivityTimeline`, `DetailHeader`, `EntityTabs`, `FormSection`,
`ApprovalPanel`, `SourceCitation`, `AIActionPreview`, `IntegrationCard`, `CommandPalette`,
`CopilotPanel`, plus Radix wrappers for Dialog/DropdownMenu/Tabs/Tooltip).

**Phase 1 — Application shell.** `AppSidebar` rebuilt: grouped per the brief's taxonomy,
collapsible on desktop, permission-filtered via `useCurrentPermissions()`, nested nav for
Sales/Support/Automation. `TopNavigation` rebuilt: notification bell with real unread
count, approvals badge with real pending count, a user-menu dropdown replacing the bare
logout button, `CommandPalette` on ⌘K. Verified against the live stack (collapse/expand,
nested-group expand/collapse, command palette, user menu, navigation to 6 modules) before
committing.

**Phase 2 — Command Center.** Dashboard rebuilt as a real command center: `MetricCard`
tiles for tasks/approvals/compliance/security/sales/support/automation posture (every
tile traces to a query the app already had — no new backend calls), today's AI briefing
suggestion, a pending-approvals list, a recent-activity timeline assembled from real
task/approval data, an AI recommendations feed. `CopilotPanel` built as a real
conversation UI (message history, suggested prompts, grounded/ungrounded badges, inline
citations) — it does **not** implement the brief's Facts/Analysis/Recommendations/
Proposed-Actions/Sources section split, because `/ai/copilot/ask` returns one grounded
text answer, not that structure; building the split would mean fabricating structure the
model didn't produce. Tasks and Approvals moved onto `DataTable`/`ApprovalPanel`; Reports,
Recommendations, Briefing, and Notifications retokenized with proper empty/error states.
Caught and fixed 3 real E2E regressions this shell/table change caused (logout moved into
a menu, a sidebar nav label collided with a page heading, a row action moved into an
overflow menu) rather than leaving them broken.

**Phase 3 — Governance.** Security (small enough, no tests) got the full `MetricCard` +
`DataTable` treatment. Compliance's 16-section, 1,519-line hub kept its existing
Card-list-per-section structure (protected by an 18-test suite exercising every section
in one render) but was retokenized and its sections were grouped under labeled headings
(Controls & Risk, Assessments, AI Governance, Privacy, Vendors & Trust, Frameworks) so the
Requirement→Control→Evidence→Risk relationship reads as one structure. All 9 Compliance
detail routes and Security's 3 detail routes were retokenized; they do not yet use
`DetailHeader`/`EntityTabs`/`ActivityTimeline` (deferred, see below).

**Phase 4 — Growth & Customer Operations.** Sales and Support hub pages rebuilt onto
`MetricCard` + `DataTable`. The 16 remaining Sales routes (ICP, sequences, campaigns,
inbox, meetings, and 5 detail pages) and 4 remaining Support routes retokenized.

**Phase 5 — Operations & Integrations/Trust.** Automation hub rebuilt onto `MetricCard` +
`DataTable`; the workflow builder's chrome (borders, controls panel, empty-state box)
retokenized without touching `@xyflow/react` wiring — verified visually that the canvas,
zoom controls, and minimap still render correctly. Integrations (500 lines, its own test
suite, real per-connection expand/health-check/sync/disconnect interactions) and the
public Trust Center page were retokenized only — the `IntegrationCard`/
`deriveIntegrationStatus` component built in Phase 0 exists and is ready, but wiring the
Integrations page onto it is deferred (see below) rather than risking that page's test
coverage in this pass.

**Phase 6 — Administration, Knowledge, Auth.** All 9 Settings pages retokenized (with
semantic color mapping, not blind find-replace — e.g. the billing page's "current plan"
border now uses `--brand-primary`, the data-management danger zone uses the critical
token scale). Knowledge's document list moved onto `DataTable`; its detail page and graph
explorer retokenized. All Auth pages and the 9-screen Onboarding wizard retokenized.

**Phase 7 — Cross-cutting verification.** App-wide grep sweep confirmed zero remaining raw
color classes anywhere in `app/` or `components/`. Responsive verification at mobile
(390px) and tablet (834px) viewports **found a real bug**: `AppSidebar` had no responsive
behavior at all and permanently occupied ~150px of a 390px screen, making every page
unusable on a phone. Fixed with a proper off-canvas drawer (new `SidebarContext`
coordinating `AppSidebar` and `TopNavigation`'s new hamburger button, backdrop, auto-close
on nav) — verified visually that it works before committing. Accessibility spot-check
confirmed keyboard-only command-palette open/close, tab order, and user-menu open/close
via Enter/Escape all work (not a full WCAG audit — see below). Full check suite run
repeatedly through every phase and once more at the end: `tsc --noEmit` clean, `eslint`
clean, Vitest 67/67, Playwright E2E 18/18, and a production `next build` succeeds across
all 70 routes with no build-time errors.

## Deferred — real, scoped follow-up work (not silently dropped)

- **Compliance hub DataTable conversion**: convert the 16 sections' Card-lists to
  `DataTable` and the hub to `EntityTabs`. Needs the 18-test suite rewritten alongside it
  (each test would need to open the relevant tab before asserting, since Radix `Tabs`
  unmounts inactive content by default) — a coordinated change, not a drive-by edit.
- **Integrations page → `IntegrationCard`/`deriveIntegrationStatus`**: the component is
  built and exports the exact status vocabulary the brief specifies (Not configured /
  Ready to connect / Connected / Syncing / Degraded / Failed / Disabled / Revoked / Demo).
  Wiring the real page onto it means preserving per-connection health-check/refresh/sync/
  disconnect actions and the webhook event-history expand panel, which its own test suite
  exercises directly.
- **`DetailHeader`/`EntityTabs`/`ActivityTimeline` on detail routes**: the 9 Compliance
  detail pages, Security's 3 detail pages, and the Sales/Support detail pages are
  retokenized but still use their original ad hoc layout rather than the standardized
  detail-page structure the brief describes.
- **Full WCAG 2.1 AA audit**: this pass verified keyboard reachability and focus
  management for the shell's interactive surfaces (sidebar, command palette, user menu)
  but did not run an automated contrast/semantic-markup audit (e.g. axe-core) across all
  70 routes.
- **`docs/ROUTES_AND_SCREENS.md` / `docs/ROUTE_API_INVENTORY.md`**: not yet updated to
  describe the modernized shell/component usage.

## Commit discipline

Every phase (and sub-slice within larger phases) got its own commit: implement, run
`tsc --noEmit` + `eslint` + the full Vitest suite, restart the dev stack and verify
visually and/or via the relevant Playwright spec, then commit with a message explaining
what changed and, where relevant, what was deliberately left unchanged and why.
