# Veyntra Design System

The design system for the enterprise modernization (branch `ui/enterprise-modernization`).
Tokens live as CSS custom properties in `apps/web/app/globals.css`, mapped into Tailwind
utilities via `@theme inline` (Tailwind v4's CSS-first config — no `tailwind.config.js`
needed). Every component should reach for a token utility (`bg-surface`, `text-fg-muted`,
`border-default`) before reaching for a raw Tailwind color (`bg-white`, `text-neutral-500`)
so a future palette change is a one-file edit, not a grep-and-replace across 70 pages.

## Design principles

1. **Calm, not loud.** No gradients, no neon, no decorative shadows. Every visual choice
   should read as *confidence*, not *effort*.
2. **Density over whitespace.** This is a tool compliance officers and security analysts
   use for hours a day, not a marketing site. Prefer information-dense, scannable layouts
   over generous padding.
3. **Color carries meaning, never carries it alone.** Every status uses an icon or label
   alongside color (WCAG 1.4.1).
4. **One way to build each pattern.** One table component, one badge system, one form
   layout, one detail-page skeleton — reused everywhere, not re-invented per page.
5. **Light mode is the default and the priority.** Dark mode is supported via the same
   tokens and a real toggle, but never blocks a light-mode-only visual decision.

## Brand identity

The mark is two interlocking arcs — a teal→cyan sweep and a violet→blue
sweep — meeting around a warm amber spark. Those three families are the
whole brand vocabulary, defined once in `app/globals.css` so the mark, the
marketing site, and the app all draw from one source.

| Token | Role |
|---|---|
| `--brand-teal` → `--brand-cyan` | the mark's left arc; `--gradient-arc-teal` |
| `--brand-violet` → `--brand-blue-deep` | the mark's right arc; `--gradient-arc-blue` |
| `--brand-spark` | the center spark — the one warm note, kept rare (AI moments, a single hero accent) so it stays meaningful |
| `--gradient-brand` | the full sweep across both arcs, for **decorative fills only**: rules, hairlines, hover edges |
| `--gradient-brand-text` | the sweep for **gradient text** — see the warning below |
| `--aurora-*` | low-alpha ambient glows echoing the mark's two lobes |

**`--brand-primary` stays indigo.** It is the action color on hundreds of
existing buttons, links, and focus rings; the arc colors are brand
*atmosphere* (the mark, gradients, ambient glows), not an "this is
clickable" signal. Recoloring every control is a separate decision.

### Never paint text with `--gradient-brand`

The decorative stops are not readable: `--brand-cyan` is **1.81:1** on
white and `--brand-violet` **2.98:1**, both under the 3:1 WCAG AA floor for
large text. A headline painted with it looks correct at the ends and
becomes illegible through the middle. Use `--gradient-brand-text` (or the
`.brand-gradient-text` helper), whose stops are all ≥3.68:1 in light and
≥7.9:1 in dark. `components/logo.test.tsx` pins both gradients so the two
cannot be swapped by accident.

### Dark navigation chrome

The marketing header, the app sidebar, and the app top bar are dark in
**both** themes (`--nav-*` tokens). Two reasons: the mark's arcs read as
light against a dark ground, and a persistently dark chrome frames the
working canvas the way enterprise consoles do instead of chrome and content
melting into one white sheet.

These are fixed values, not theme-swapped surface tokens — reaching for
`--bg-surface` inside the chrome would turn it white in light mode and
defeat the point. Contrast against `--nav-bg`: `--nav-fg` 15.8:1,
`--nav-fg-muted` 6.1:1.

Components rendered inside the chrome need chrome-specific colors, not the
content-surface defaults: `<Logo tone="nav">` for the wordmark, and an
explicit `bg`/`text`/`placeholder` on the shared `Input` and `Button`.

### Helpers

- `.brand-gradient-text` — gradient headline text, with a solid-color
  fallback for browsers without `background-clip: text` and a
  `forced-colors` override.
- `.brand-aurora` — the viewport-scale two-lobe wash (marketing heroes).
- `.brand-aurora-panel` — the card-scale variant. The full wash's three
  lobes muddy into a yellow-green band when compressed into a panel, so
  this one drops the warm lobe and pushes the other two to the corners.

Everything carrying an aurora or gradient fill is decorative and must be
`aria-hidden`.

## Color tokens

Neutral scale is a cool slate (matches "neutral or slightly cool background" direction).
Primary is deep indigo — trustworthy, distinct from the destructive-red/success-green
semantic pair, reads as enterprise software rather than a startup landing page. AI
features get their own violet accent so Copilot/AI-generated content is always visually
identifiable at a glance, distinct from the primary brand color used for ordinary actions.

```css
:root {
  /* Neutral scale (cool slate) */
  --gray-50:  #f8fafc;
  --gray-100: #f1f5f9;
  --gray-200: #e2e8f0;
  --gray-300: #cbd5e1;
  --gray-400: #94a3b8;
  --gray-500: #64748b;
  --gray-600: #475569;
  --gray-700: #334155;
  --gray-800: #1e293b;
  --gray-900: #0f172a;
  --gray-950: #020617;

  /* Primary — deep indigo */
  --primary-50:  #eef2ff;
  --primary-100: #e0e7ff;
  --primary-200: #c7d2fe;
  --primary-500: #6366f1;
  --primary-600: #4f46e5;
  --primary-700: #4338ca;

  /* Semantic */
  --success-50: #ecfdf5; --success-500: #10b981; --success-600: #059669; --success-700: #047857;
  --warning-50: #fffbeb; --warning-500: #f59e0b; --warning-600: #d97706; --warning-700: #b45309;
  --critical-50: #fef2f2; --critical-500: #ef4444; --critical-600: #dc2626; --critical-700: #b91c1c;
  --info-50: #eff6ff; --info-500: #3b82f6; --info-600: #2563eb; --info-700: #1d4ed8;

  /* AI accent — violet, deliberately distinct from primary indigo */
  --ai-50: #f5f3ff; --ai-500: #8b5cf6; --ai-600: #7c3aed; --ai-700: #6d28d9;

  /* Semantic surface roles (what components actually consume) */
  --bg-app: var(--gray-50);          /* page background */
  --bg-surface: #ffffff;              /* card/panel background */
  --bg-surface-hover: var(--gray-50);
  --bg-sunken: var(--gray-100);       /* table header, code blocks */

  --fg-default: var(--gray-900);
  --fg-muted: var(--gray-600);
  --fg-subtle: var(--gray-400);
  --fg-on-primary: #ffffff;
  --fg-on-dark: var(--gray-50);

  --border-default: var(--gray-200);
  --border-strong: var(--gray-300);
  --border-focus: var(--primary-500);

  --brand-primary: var(--primary-600);
  --brand-primary-hover: var(--primary-700);
  --brand-primary-subtle: var(--primary-50);
}

[data-theme="dark"] {
  --bg-app: var(--gray-950);
  --bg-surface: var(--gray-900);
  --bg-surface-hover: var(--gray-800);
  --bg-sunken: var(--gray-900);
  --fg-default: var(--gray-50);
  --fg-muted: var(--gray-400);
  --fg-subtle: var(--gray-500);
  --border-default: var(--gray-800);
  --border-strong: var(--gray-700);
  --brand-primary-subtle: rgba(99, 102, 241, 0.12);
}
```

### Semantic color usage

| Token | Use for |
|---|---|
| `--brand-primary` | primary buttons, active nav state, links, focus rings, selected-tab underline |
| `--success-*` | Active, Approved, Healthy, Completed, Live, Connected, pass |
| `--warning-*` | Pending, Paused, Degraded, Medium/High severity, In Progress |
| `--critical-*` | Rejected, Failed, Critical severity, Revoked, destructive actions |
| `--info-*` | Draft, informational banners, Not Configured |
| `--ai-*` | Copilot messages, AI-generated content badges, AI recommendation cards, confidence indicators |

## Typography

Geist Sans (already loaded via `next/font/google`, previously overridden by a stray
`font-family: Arial` in `globals.css` — fixed as part of this modernization). Geist Mono
for anything tabular/technical (audit event payloads, API keys, correlation IDs).

The scale sits one step above Tailwind's defaults (`text-sm` = 15px, not
14px; `text-xs` = 13px, not 12px), overridden in `@theme`. The app was
originally drawn at a 12/13/14px operational density that reads as cramped
on a large display and is tiring over a long session. Set via the type
tokens rather than by scaling the root font size, so `rem`-based spacing
everywhere else stays exactly where it was.

> **Applying a size token in Tailwind needs the `length:` hint.**
> `text-[var(--text-display-1)]` is ambiguous — Tailwind resolves it as a
> text *color*, so the font size silently never applies and the color
> resolves to an invalid value that falls back to `inherit`. The marketing
> display scale was written this way and had never actually rendered:
> every hero and section heading was coming out at body size. Always write
> `text-[length:var(--text-display-1)]`.

```css
--font-sans: var(--font-geist-sans), ui-sans-serif, system-ui, sans-serif;
--font-mono: var(--font-geist-mono), ui-monospace, monospace;

--text-xs:   0.75rem;  /* 12px — helper text, badges, table meta */
--text-sm:   0.8125rem; /* 13px — body default, table cells, form inputs */
--text-base: 0.875rem; /* 14px — emphasized body */
--text-lg:   1rem;      /* 16px — section headings, card titles */
--text-xl:   1.25rem;   /* 20px — page titles */
--text-2xl:  1.5rem;    /* 24px — dashboard hero numbers only */

--font-weight-normal: 400;
--font-weight-medium: 500;
--font-weight-semibold: 600;

--line-height-tight: 1.25;
--line-height-normal: 1.5;
```

Deliberately smaller than a marketing site's scale (no `text-4xl` headings inside the
app) — this is dense operational software, not a landing page. Page titles (`PageHeader`)
use `--text-xl`/semibold; metric values use `--text-2xl`/semibold and nothing larger.

## Spacing, radius, shadow

```css
--space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem; --space-4: 1rem;
--space-5: 1.25rem; --space-6: 1.5rem; --space-8: 2rem; --space-10: 2.5rem;

--radius-sm: 0.25rem;  /* badges, small controls */
--radius-md: 0.5rem;   /* buttons, inputs, cards */
--radius-lg: 0.75rem;  /* panels, modals */
/* No radius above lg anywhere — avoids the "excessive rounded corners" pitfall */

--shadow-sm: 0 1px 2px 0 rgb(15 23 42 / 0.04);
--shadow-md: 0 4px 12px -2px rgb(15 23 42 / 0.08), 0 2px 4px -2px rgb(15 23 42 / 0.04);
/* Two shadow levels only. No shadow-lg/xl/2xl — flat, restrained surfaces. */

--transition-fast: 120ms ease-out;
--transition-base: 180ms ease-out;
```

## Layout dimensions

```css
--sidebar-width: 15.5rem;      /* 248px, expanded */
--sidebar-width-collapsed: 3.5rem; /* 56px, icon-only */
--header-height: 3.25rem;      /* 52px */
--content-max-width: 88rem;    /* 1408px — dashboard/detail pages cap width on large monitors */
```

## Density

Two density levels, both real Tailwind class sets (not a runtime toggle in this pass —
`DataTable` and `FormSection` accept a `density` prop for future extension, defaulting to
`comfortable`):

- **`comfortable`** (default): table rows `h-11` (44px), form fields `h-9` (36px) with
  `gap-4` between fields.
- **`compact`**: table rows `h-9` (36px), form fields `h-8` (32px) with `gap-3` — used in
  drawers and dense operational views (e.g. workflow run step logs) where more rows should
  fit without scrolling.

## Component inventory

Shared primitives introduced by this modernization, all under `apps/web/components/`:

| Component | Purpose |
|---|---|
| `AppSidebar` | grouped, collapsible, icon-led, permission-aware, active-route highlighted |
| `TopNavigation` | search, global create, notifications, approvals badge, user menu |
| `Breadcrumbs` | route-derived, used on detail pages |
| `PageHeader` | title, description, status/health slot, actions, optional breadcrumbs |
| `MetricCard` | value, trend, status, comparison period, click-through |
| `InsightCard` | AI-recommendation-shaped card (reason, sources, suggested action) |
| `StatusBadge` / `SeverityBadge` / `ConfidenceBadge` | the one semantic status system, extended with icons |
| `DataTable` | sort, filter, pagination, density, row actions, empty/loading/error states |
| `FilterBar` | search + facet filters above a `DataTable` |
| `EmptyState` / `ErrorState` / `LoadingSkeleton` / `PermissionDenied` | the 4 required non-happy-path states, one implementation each |
| `ActivityTimeline` | chronological event list (reused across every detail page) |
| `DetailHeader` / `EntityTabs` | the shared detail-page skeleton |
| `FormSection` | grouped fields with a heading, used inside dialogs/drawers/pages |
| `ApprovalPanel` | risk/requester/decide UI, reused wherever an Approval is inline |
| `SourceCitation` | Copilot/Recommendation source reference chip |
| `AIActionPreview` | proposed-action-before-approval card for Copilot |
| `CopilotPanel` | the redesigned Copilot conversation surface |
| `IntegrationCard` | provider status, permissions, data accessed, connect/reconnect/revoke |
| `HealthIndicator` | small dot+label posture indicator (security/compliance/support) |
| `CommandPalette` | ⌘K global navigation/search |

Existing primitives (`Button`, `Badge`, `Card`, `Input`, `Label`, `Select`, `Textarea`)
are restyled onto the new tokens in place, not replaced — their APIs don't change.

## Icons

`lucide-react` (already a dependency) for every icon in the app — one icon per nav item,
one icon per status badge, one icon per module. No mixing icon sets.

## Accessibility baseline

- All interactive elements keyboard-reachable with a visible `--border-focus` ring.
- Every icon-only control has an `aria-label`.
- Every status badge pairs color with an icon + text label — never color alone.
- Modals/drawers trap focus and restore it on close (Radix `Dialog`/`DropdownMenu`, added
  as new dependencies in this modernization — the only new runtime dependencies this
  effort introduces, both from the Radix primitives family already partially in use).
- `prefers-reduced-motion` disables all non-essential transitions.
