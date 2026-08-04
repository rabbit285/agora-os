# UI/UX Audit — Agora Origin Frontend

Audit date: 2026-08-04, on branch `ui/enterprise-modernization`. This audit inspects the
frontend as it exists today — 70 real routes, ~11,200 lines of `page.tsx` code, backed by
a fully real, tested API (see `docs/SPEC_TRACEABILITY_MATRIX.md`; 101 of 112 requirements
VERIFIED). **The product is functionally complete. This audit is about how it looks and
feels, not what it does.**

---

## 1. Current state of the design foundation

There is effectively no design system today — every page is built directly against raw
Tailwind utility classes with the framework's default neutral/red/amber/emerald palette,
no custom tokens, and a 7-component primitive library.

- **`app/globals.css` is the untouched `create-next-app` scaffold.** `--background`/
  `--foreground` are the only two custom properties in the entire app. `body` is hardcoded
  to `font-family: Arial, Helvetica, sans-serif` — this silently overrides the Geist Sans/
  Geist Mono fonts that `app/layout.tsx` already loads via `next/font/google` and exposes
  as `--font-geist-sans`/`--font-geist-mono`. The app has been rendering in the browser's
  default Arial fallback the entire time, not the font it actually ships.
- **No design tokens** for spacing, radius, shadow, typography scale, or semantic color
  beyond Tailwind's own defaults used ad hoc (`text-neutral-900`, `border-neutral-200`,
  `bg-neutral-50` typed out individually on every page).
- **`components/ui/` has 7 primitives**: `Button`, `Badge`, `Card`, `Input`, `Label`,
  `Select` (a bare native `<select>`, not a Radix listbox), `Textarea`. That's the entire
  shared library. No `Table`, `Dialog`, `DropdownMenu`, `Tabs`, `Sheet`/`Drawer`, `Toast`,
  `Skeleton`, `Tooltip`, `Popover`, or `Command` palette exist — every table, modal-like
  interaction, and tab strip across all 70 routes is hand-rolled per page.
- **Dark mode is a single hardcoded `prefers-color-scheme` media query** with two literal
  hex values (`#0a0a0a`/`#ededed`) — no toggle, no `data-theme` attribute, no tokens that
  would make extending it straightforward.
- **Dependencies are lean and modern**: Next.js 16.2 (Turbopack), React 19.2, Tailwind 4,
  `@radix-ui/react-label` + `@radix-ui/react-slot` only (no other Radix primitives
  installed yet), `class-variance-authority` + `tailwind-merge` (the `cn()` pattern is
  already in place in `lib/utils.ts`), `lucide-react` (installed, barely used — most pages
  have zero icons), `react-hook-form` + `zod` (installed, unused — every form in the app
  is uncontrolled `useState` + manual submit, not react-hook-form), `@xyflow/react`
  (already powers the real workflow builder canvas at `/automation/workflows/[id]`).

## 2. Application shell

- **`AppSidebar`** (`components/app-sidebar.tsx`): fixed `w-60`, no collapse, no icons, no
  section grouping beyond a flat label, no permission-based filtering (every item renders
  for every role regardless of what that role can actually do — the API enforces access
  regardless, but the UI doesn't reflect it). Driven by `lib/navigation.ts`'s `NAVIGATION`
  tree, which is flatter than the real route surface — sub-resource pages
  (`/compliance/controls/[id]`, `/sales/accounts/[id]`, `/security/incidents/[id]`, etc.)
  aren't nav items at all, reached only by click-through from a list, which is fine but
  means the sidebar undersells how much is actually in each module. The tree also still
  says "Notifications" as a standalone Overview item but doesn't include `/recommendations`
  or `/briefing` under a coherent label (they're listed, just not organized).
- **`TopNavigation`**: has `ModuleSwitcher`, `GlobalCreateButton`, a search input that
  navigates to `/search`, org name as plain text, user name as plain text, and a bare
  "Log out" button. No notification bell (route exists, unlinked from the header), no
  approvals badge/count, no user avatar or dropdown menu, no organization switcher (this
  app's data model is single-org-per-session via `Membership`, so a switcher isn't
  currently meaningful without more backend support — noted, not fixed here), no
  breadcrumbs anywhere in the app.
- **`ModuleSwitcher`**: a flat list of 6 top-level links, no active-state indicator, no
  icons.
- **`PageHeader`**: minimal — title, optional description, optional actions slot. Used
  fairly consistently across pages, which is good; it just doesn't do much (no
  breadcrumbs, no status/health summary, no tabs).
- **`AuthGuard`**: sound logic (server is the real enforcement point, this only prevents
  flash-of-unauthenticated-content), loading state is a bare centered text string.

## 3. Component-level findings

- **Badges** (`StatusBadge`, `SeverityBadge`, `RiskBadge`): a genuinely good foundation —
  one shared `STATUS_VARIANTS` lookup already covers ~90 real status strings across every
  module, which is exactly the "one semantic status system" the modernization should keep
  and extend, not replace. Gaps: no icons (color is the only signal, which is an
  accessibility problem being explicitly called out to fix), several of the specifically
  required states aren't in the map yet (`not_configured`, `live`, `demo`, `revoked`,
  `completed`), and the visual style (a plain rounded-full color chip) reads as generic
  admin-dashboard rather than enterprise SaaS.
- **Tables**: every table in the app is a hand-rolled `<div>` of `Card`-wrapped rows (see
  `compliance/page.tsx`'s dozen-plus `*Section()` components) rather than an actual
  `<table>` element in most places — meaning no real column semantics, no keyboard
  navigation between cells, and a repeated "row rendered as a flex-justified Card" pattern
  copy-pasted with small variations across ~20+ list views. No sorting, filtering, column
  visibility, density control, bulk actions, or saved views exist anywhere. Pagination
  exists at the API level (`limit`/`offset` + `X-Total-Count`, spec-verified) but almost no
  frontend page actually uses it — most pages fetch the full unpaginated list and render
  it all.
- **Forms**: every form is `useState` per field + a manual `onClick`/`mutate()` call, not
  `react-hook-form` despite it being a dependency. No consistent field grouping, no
  required-field indicator convention, validation errors surface only as a raw
  `ApiError.message` string in a red paragraph after a failed submit (never inline
  per-field). Destructive actions (delete, revoke, org deletion) use real browser-native
  patterns inconsistently — org deletion has a genuine two-step name-confirmation flow
  (excellent, keep it); most other deletes are a bare button with no confirmation at all.
- **Detail pages**: no standardized structure. Some (Compliance controls, Vendors, AI
  Systems, Security incidents) follow a reasonable "header + sections" shape organically;
  none share a common `DetailHeader`/`EntityTabs`/`ActivityTimeline` component, so each
  reinvents its own layout, spacing, and section-heading style.
- **Loading/empty/error/permission states**: present in spirit almost everywhere (this
  codebase's own backend-honesty discipline carries into the frontend — pages do show
  "Loading…", "No X yet", and raw error text rather than blank screens), but every
  instance is a one-off inline `{isLoading && <p>Loading…</p>}` with no shared visual
  language, no skeleton loading (everything is a text string), and no distinct
  permission-denied state (a 403 just renders as whatever the raw `ApiError.message` says,
  inline, styled identically to a validation error).

## 4. Route inventory and modernization surface

70 real frontend routes (see `docs/ROUTE_API_INVENTORY.md` for the authoritative list).
Every one of them needs the shell/token change to land automatically (shared layout +
shared primitives), but the pages listed below have module-specific patterns —
tables, forms, detail layouts — that need direct modernization work beyond the shell:

- **Command Center**: `/` (dashboard — currently 4 bare metric tiles, no briefing feed, no
  recommendations, no activity), `/copilot`, `/tasks` + `/tasks/[id]`, `/approvals`,
  `/reports`, `/recommendations`, `/briefing`, `/notifications`.
- **Governance (Compliance)**: `/compliance` (1,519 lines, ~15 inline list sections in one
  file — the single largest modernization target in the app) + 8 detail routes
  (`ai-systems`, `ai-incidents`, `audits`, `controls`, `dpias`, `dsars`, `frameworks`,
  `questionnaires`, `security-reviews`, `vendors`).
- **Governance (Security)**: `/security` + 3 detail routes (`alerts`, `assets`,
  `incidents`), `/security/policies`.
- **Growth (Sales)**: `/sales` + 6 detail routes (`accounts`, `campaigns`, `contacts`,
  `leads`, `opportunities`, `sequences`) + 3 standalone tool pages (`icp`, `inbox`,
  `meetings`).
- **Customer Operations (Support)**: `/support` + `/support/tickets/[id]`,
  `/support/conversations`, `/support/knowledge`, `/support/ai-agent`.
- **Operations (Automation)**: `/automation` + `/automation/workflows/[id]` (the real
  `@xyflow/react` canvas — needs visual polish, not a rewrite), `/automation/connections`,
  `/automation/templates`.
- **Knowledge**: `/knowledge` + `/knowledge/[id]`, `/knowledge/graph`.
- **Administration**: `/settings/{organization,users,roles,billing,security,integrations,
  ai-providers,memory,business-rules,data-management}`.
- **Trust**: `/trust/[org_slug]` (the genuinely public, unauthenticated Trust Center page
  — different design context from the authenticated app entirely, needs its own treatment).
- **Auth**: `/login`, `/signup`, `/forgot-password`, `/reset-password/[token]`,
  `/verify-email/[token]`, `/invite/[token]`, `/mfa-challenge`, `/onboarding` (a real
  9-screen wizard, already fairly well-built — needs visual polish more than restructuring).
- **Utility**: `/search`, `/coming-soon`.

## 5. What must not change

- Every API contract, every TanStack Query key, every permission check, every
  server-enforced tenant boundary — the backend is correct and fully tested; this is a
  presentation-layer pass only.
- The E2E suite's real selectors (`getByPlaceholder`, `getByRole("button", {name:...})`,
  exact button/placeholder text) are load-bearing — see `apps/web/e2e/*.spec.ts`. Any
  visual restructuring must preserve the accessible name and role of every element those
  tests target, even as the surrounding markup/classes change.
- The 16 existing Vitest page-test files assert on real rendered text and interaction
  outcomes, not snapshots — they should keep passing without modification unless a test
  itself was asserting on now-deliberately-changed copy.

## 6. Summary

The product underneath is genuinely enterprise-grade — real tenant isolation, real RBAC,
real audit trails, a large and correct feature surface. The presentation layer looks like
what it visibly is: a fast, correct MVP built by hand without a design system, using
Tailwind's raw defaults everywhere. Every one of the specific complaints in the
"Avoid" list (generic admin-dashboard appearance, inconsistent spacing, crowded screens)
is an accurate description of the current state, not a hypothetical risk. The good news is
the underlying architecture (Tailwind + CVA + a `cn()` helper + TanStack Query +
consistent `PageHeader`/`StatusBadge` usage) is exactly the right foundation to build a
real design system on top of without a rewrite.
