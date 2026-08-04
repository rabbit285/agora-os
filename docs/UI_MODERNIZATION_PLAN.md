# UI Modernization Plan

Branch: `ui/enterprise-modernization`. Companion docs: `docs/UI_UX_AUDIT.md` (what's
wrong today), `docs/DESIGN_SYSTEM.md` (the tokens and components this plan builds).

## Scope and honesty about pacing

This is a full visual modernization of ~11,200 lines across 70 real routes. It is
executed the same way the product-completeness backlog was: dependency-ordered slices,
each one implemented for real, tested, and committed separately — not a single pass that
claims completion prematurely. Progress is tracked slice by slice below; each slice's
"done" line is only checked once it's actually shipped, tested, and committed.

No backend behavior, API contract, RBAC rule, or tenant-isolation check changes. Every
slice is presentation-layer only, verified against the real running stack the same way
every prior feature in this codebase has been.

## Phase 0 — Foundation (blocks everything else)

1. **Design tokens**: rewrite `app/globals.css` with the full token set from
   `docs/DESIGN_SYSTEM.md`, fix the Geist-Sans-never-applied bug, add a real `data-theme`
   dark-mode architecture (toggle deferred past this pass per the brief's own priority
   order, but the tokens support it from day one).
2. **New shared dependencies**: add `@radix-ui/react-dialog`, `@radix-ui/react-dropdown-menu`,
   `@radix-ui/react-tabs`, `@radix-ui/react-tooltip`, `@radix-ui/react-popover` — the
   minimum Radix primitives needed for accessible dialogs/menus/tabs. No other new
   dependencies.
3. **Restyle existing primitives** (`Button`, `Badge`, `Card`, `Input`, `Select`,
   `Textarea`) onto the new tokens — same props, same call sites, new look.
4. **Build the new shared primitives** listed in `DESIGN_SYSTEM.md`'s component
   inventory: `EmptyState`, `ErrorState`, `LoadingSkeleton`, `PermissionDenied`,
   `StatusBadge`/`SeverityBadge`/`ConfidenceBadge` (extended), `MetricCard`,
   `InsightCard`, `DataTable`, `FilterBar`, `Breadcrumbs`, `HealthIndicator`,
   `ActivityTimeline`, `DetailHeader`, `EntityTabs`, `FormSection`, `ApprovalPanel`,
   `SourceCitation`, `AIActionPreview`, `IntegrationCard`, `CommandPalette`.

**Done when**: tokens compile, primitives render in isolation (component tests), `tsc
--noEmit` clean, no page has been touched yet — this phase produces the toolkit, not the
rollout.

## Phase 1 — Application shell

`AppSidebar` (grouped per the brief's suggested taxonomy, collapsible, icon-led,
permission-aware via the existing `useCurrentPermissions()` hook — hide a group only when
the current role holds none of that group's permissions, never hide an item a role can
actually use), `TopNavigation` (add notification bell with unread count, approvals badge
with pending count, user avatar + dropdown menu replacing the bare logout button,
`CommandPalette` wired to ⌘K), root `(app)/layout.tsx` updated to the new shell.

**Done when**: every one of the 70 routes renders inside the new shell automatically
(layout-level change), `AuthGuard`'s loading state uses `LoadingSkeleton`, full Vitest +
Playwright suite still green, manual check of sidebar collapse/expand and permission
filtering against 2 different seeded roles.

## Phase 2 — Command Center

Dashboard (`/`) rebuilt as a real command center: AI Daily Briefing summary, priority
actions, compliance/security/sales/support/automation posture tiles using `MetricCard`,
pending approvals list, recent activity, AI recommendations feed — all from data this
dashboard's existing queries and the Briefing/Recommendations APIs already provide, no
new backend calls invented. `/copilot` rebuilt around `CopilotPanel` with the
Facts/Analysis/Recommendations/Proposed-Actions/Sources separation the brief requires.
`/tasks`, `/tasks/[id]`, `/approvals`, `/reports`, `/recommendations`, `/briefing`,
`/notifications` restyled onto `DataTable`/`DetailHeader` patterns.

**Done when**: manual walkthrough of dashboard + Copilot + tasks + approvals against the
seeded demo org, Playwright suite green, no fabricated metrics (every tile traces to a
real query already in the codebase).

## Phase 3 — Governance (Compliance + Security)

The largest single-file target (`compliance/page.tsx`, 1,519 lines) split into its
existing logical sections, each restyled onto `DataTable`, with the
Requirement→Control→Evidence→Assessment→Risk→Task relationship made visually explicit.
9 Compliance detail routes + Security overview + 3 Security detail routes get
`DetailHeader`/`EntityTabs`/`ActivityTimeline`.

**Done when**: manual walkthrough of AI System detail, DPIA, DSAR, Security incident
detail; Playwright's Compliance/Security specs green.

## Phase 4 — Growth (Sales) & Customer Operations (Support)

Sales list/pipeline/detail pages onto `DataTable` + a compact pipeline view; Support
ticket workspace redesigned so an agent can see customer context, AI summary, and
suggested response without leaving the ticket page.

**Done when**: manual walkthrough of Lead Finder, Account detail, Opportunity pipeline,
Support inbox, Ticket detail; Playwright's Sales/Support specs green.

## Phase 5 — Operations (Automation) & Integrations/Trust

Workflow builder canvas gets visual polish (node styling, panel chrome) without touching
`@xyflow/react` wiring or the Temporal execution model. Integrations page rebuilt around
`IntegrationCard` with the exact status vocabulary the brief specifies (Not configured /
Ready to connect / Connected / Syncing / Degraded / Failed / Disabled / Revoked / Demo) —
mock adapters stay honestly labeled, never dressed up as live.

**Done when**: manual walkthrough of Workflow builder + a run detail + Integrations page;
Playwright's Automation/Integrations specs green.

## Phase 6 — Administration, Knowledge, Auth, Trust Center

Settings pages (`organization`, `users`, `roles`, `billing`, `security`, `ai-providers`,
`memory`, `business-rules`, `data-management`), Knowledge module, all auth pages
(`login`/`signup`/`onboarding`/etc.), and the public `/trust/[org_slug]` page (its own
lighter-weight treatment — it's unauthenticated marketing-adjacent surface, not the
authenticated app shell).

**Done when**: manual walkthrough of Users/Roles, Billing, Onboarding wizard, Trust
Center public page; full Playwright suite green.

## Phase 7 — Cross-cutting verification

Responsive check at 4 breakpoints (desktop-xl, laptop, tablet, mobile) for every phase's
pages; accessibility pass (keyboard nav, focus rings, `aria-label`s, contrast, reduced
motion) across the shell and every new shared primitive; full check suite (ESLint, `tsc
--noEmit`, Vitest, production `next build`, full Playwright run, relevant backend tests);
screenshots of the 23 key pages listed in the task brief captured via Playwright for
visual review; `docs/ROUTES_AND_SCREENS.md`/`docs/ROUTE_API_INVENTORY.md` updated to
reflect the modernized state.

## Commit discipline

Every phase (and large sub-slices within Phase 3+) gets its own commit, following this
session's established convention: implement, run the relevant checks, commit with a
message explaining what changed and why — never a single mega-commit at the end.
