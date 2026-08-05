# Public Site Audit

Audit date: 2026-08-05, on branch `ui/public-site-and-auth-modernization` (created from
`main`, which includes the full Sales Lead Finder effort — see
`docs/SALES_LEAD_FINDER_AUDIT.md` for that audit's precedent and format, followed here).
This audit inspects the current state of public routes, the homepage, the design system,
and adjacent backend capability (billing, demo-request, analytics), before any code in this
effort is written. Companion doc: `docs/AUTH_UX_AUDIT.md` covers authentication pages,
session handling, and redirects in the same detail.

## 1. There is no public homepage today

`apps/web/app/` has no top-level `page.tsx`. The route for `/` is served by
`apps/web/app/(app)/page.tsx` — a `"use client"` authenticated dashboard ("Command Center")
pulling live task/approval/compliance/security/sales/support/automation data, wrapped in
`AuthGuard` via `apps/web/app/(app)/layout.tsx`. An unauthenticated visitor to `/` today
sees a brief "Loading…" flash, then a client-side `router.replace("/login")` — there is no
server-side/edge redirect and no marketing content at all.

Full route-group structure (2 groups today; no third, public group exists):

```
apps/web/app/
├── layout.tsx                  # root layout: fonts + Providers only, no header/footer/nav
├── globals.css
├── favicon.ico                 # untouched default Next.js icon
├── (app)/                      # authenticated shell — "/", "/tasks", "/sales", "/compliance", etc.
│   ├── layout.tsx                # AuthGuard + SidebarProvider + AppSidebar + TopNavigation
│   ├── page.tsx                  # "/" = dashboard (see above)
│   └── ...23 module directories (approvals, automation, compliance, knowledge,
│         onboarding, sales, security, settings, support, tasks, ...)
├── (auth)/                     # unauthenticated auth flows
│   ├── layout.tsx                # centered Card, plain "Agora Origin" text wordmark
│   └── login/, signup/, forgot-password/, reset-password/[token]/,
│         verify-email/[token]/, invite/[token]/, mfa-challenge/
└── trust/[org_slug]/page.tsx   # a genuinely public route OUTSIDE both groups — a
                                   # per-org, no-auth Trust Center page. The one existing
                                   # precedent in this repo for "public route beside the
                                   # app/auth groups." Nothing exists at the bare `/trust`
                                   # path today (only the dynamic `[org_slug]` segment) —
                                   # relevant below (§6).
```

There is no `apps/web/middleware.ts` anywhere in the repo. Route protection today is
entirely the client-side `AuthGuard` component (full detail in `docs/AUTH_UX_AUDIT.md` §4).

## 2. None of the requested public routes exist

`/features`, `/solutions`, `/pricing`, `/about`, `/contact` do not exist in any form —
greenfield.

**`/security` is not available as a new public route name.** It already resolves to
`apps/web/app/(app)/security/page.tsx` — the real, tested, authenticated Security
Operations module dashboard (assets/findings/alerts/incidents). Next.js route groups do
not disambiguate identical literal paths; a second `page.tsx` resolving to `/security`
would be a build-time conflict. Per this effort's own constraint ("preserve existing route
names when changing them would break links or tests"), the authenticated module keeps
`/security`. See `docs/PUBLIC_SITE_DESIGN.md` §2 for where the public security/trust
content is placed instead.

## 3. Pricing: no dollar amounts exist anywhere in the system

Canonical source: `apps/api/app/billing/service.py`, `PLAN_CATALOG` (lines 59–156), seeded
into Postgres on every boot via `ensure_plan_catalog()` (`main.py:64`). The `Plan` model
(`apps/api/app/billing/models.py:24-33`) has exactly `key`, `name`, `entitlements` (JSON) —
**no price/currency column exists**. Four real plans: `starter` → "Starter", `growth` →
"Growth", `business` → "Business", `enterprise` → "Enterprise", differentiated by 18
entitlement keys (`ENTITLEMENT_KEYS`, service.py:29-51) — numeric limits (`max_users`,
`max_ai_usage_monthly`, `max_documents`, `max_storage_gb`, `max_frameworks`,
`max_ai_systems`, `max_security_connectors`, `max_sales_leads`,
`max_outreach_volume_monthly`, `max_support_conversations_monthly`,
`max_automation_runs_monthly`, `max_integrations`; `None` = unlimited) plus booleans
(`sso_enabled`, `scim_enabled`, `api_enabled`, `custom_frameworks_enabled`,
`trust_center_enabled`, `advanced_reporting_enabled`, `data_residency_enabled`).

`GET /api/v1/billing/plans` (`apps/api/app/routers/billing.py:24-31`) has **no auth
dependency** — genuinely callable by a logged-out visitor, returning
`[{key, name, entitlements}]` for all four plans. This is a legitimate real data source for
a pricing page's feature-comparison rows. Plan switching (`PUT /api/v1/billing/current`) is
immediate and free — **no payment collection exists** (`docs/KNOWN_LIMITATIONS.md:456-475`
discloses this explicitly). The only existing frontend consumer is the authenticated
`apps/web/app/(app)/settings/billing/page.tsx`, which is API-driven (not hardcoded) but not
directly reusable for a public page (it requires auth and has no marketing framing).

**Implication**: a pricing preview can honestly show real plan names and real
entitlement-based feature comparisons, but any € figure is necessarily new, editorial
content this effort must author — not a number pulled from the system. See
`docs/PUBLIC_SITE_DESIGN.md` §5 for the resulting design decision.

## 4. No demo-request / public lead-capture endpoint exists

Every Sales endpoint (`apps/api/app/routers/sales.py`, `sales_lead_finder.py`) requires an
authenticated session tied to an existing organization
(`Depends(require_permission(...))`). There is no unauthenticated "submit an inquiry"
endpoint anywhere in the backend — only `apps/api/app/routers/health.py` is genuinely
public today. The Sales models (`Account`, `Contact`, `Lead`, `Opportunity`,
`OutreachMessage` — `apps/api/app/sales/models.py`) are all `organization_id`-scoped, built
for tracking a tenant's *own* pipeline, not for public-website intake with no organization
yet. A demo-request feature is net-new backend work; see
`docs/PUBLIC_SITE_DESIGN.md` §6.

## 5. No analytics provider exists

Case-insensitive search across `apps/web` and `apps/api` for PostHog, Segment, Plausible,
Google Analytics/gtag, and Mixpanel found no real integration. The closest existing
mechanisms — `apps/api/app/audit/service.py`'s `record_event` (compliance/security audit
trail) and `apps/api/app/core/notifications.py`'s in-app `Notification`s — are both
internal, not product/marketing analytics. Per this effort's own instruction ("do not add
analytics automatically unless an existing privacy-approved analytics provider exists"), no
third-party analytics SDK is introduced by this effort. See
`docs/PUBLIC_SITE_DESIGN.md` §10 for the resulting no-op instrumentation-hook decision.

## 6. Design system: real, extensive, but tuned for dense operational UI, not a landing page

Full token inventory, `apps/web/app/globals.css` (mirrored in `docs/DESIGN_SYSTEM.md`):

- **Neutral**: `--gray-50` #f8fafc … `--gray-950` #020617 (11 steps).
- **Primary (indigo)**: `--primary-50` #eef2ff … `--primary-700` #4338ca.
- **Semantic**: success/warning/critical/info, each with 50/500/600/700 steps.
- **AI accent (violet, deliberately distinct from primary)**: `--ai-50` … `--ai-700`.
- **Semantic surface roles**: `--bg-app/surface/surface-hover/sunken`,
  `--fg-default/muted/subtle/on-primary/on-dark`, `--border-default/strong/focus`,
  `--brand-primary/-hover/-subtle` — all remapped under `[data-theme="dark"]` and
  `prefers-color-scheme: dark`.
- **Layout**: `--sidebar-width`, `--header-height`, `--content-max-width: 88rem`.
- **Shadow**: only `--shadow-sm` and `--shadow-md` — deliberately restrained, no
  large/dramatic shadow scale exists.
- **Typography**: documented scale tops out at `--text-2xl` (24px, dashboard hero numbers
  only) — the largest text size used anywhere in the authenticated app today. Body text is
  13px. No CSS-var-backed spacing scale exists in `globals.css` (documented in
  `docs/DESIGN_SYSTEM.md` only, not materialized as real tokens).
- **Known, real gap**: `--radius-sm/md/lg` are documented in `docs/DESIGN_SYSTEM.md:145-147`
  as real tokens but are **not actually defined** in `globals.css`. Two components
  (`badge.tsx`, `card.tsx`) reference them with inline fallbacks; every other consumer
  (`app-sidebar.tsx`, `top-navigation.tsx`, `dialog.tsx`, `dropdown-menu.tsx`,
  `data-table.tsx`, ...) has no fallback and would silently resolve to `unset` if that
  never-defined variable is ever the only source. This is a latent, real bug independent of
  this effort — worth fixing for real (defining the three vars) rather than propagating it
  into new components, since the new public-site components will want to reference the same
  radius vocabulary. See `docs/PUBLIC_SITE_DESIGN.md` §1.

**No logo exists.** The "logo" everywhere in the app today is the plain text string
`"Agora Origin"` (`apps/web/components/app-sidebar.tsx:49-51`,
`apps/web/app/(auth)/layout.tsx:5-7`) — no SVG mark, no icon, no favicon beyond the
untouched Next.js default. `apps/web/public/` contains only stock `create-next-app`
scaffold SVGs (`file.svg`, `globe.svg`, `next.svg`, `vercel.svg`, `window.svg`) — zero real
product screenshots, brand assets, or OG images exist anywhere in the repo.

**Fonts**: `next/font/google` Geist Sans + Geist Mono (`apps/web/app/layout.tsx`), no local
font files — reused as-is for the public site (no reason to diverge).

**Reusable UI primitives** (`apps/web/components/ui/`): `Button` (variants
default/outline/ghost/destructive/ai; sizes default/sm/lg/icon), `Badge` (8 variants),
`Card`/`CardHeader`/`CardTitle`/`CardDescription`/`CardContent`/`CardFooter`, `Input`,
`Label`, `Textarea`, `Select` (native `<select>`, not Radix), `Tabs`, `Dialog`,
`DropdownMenu`, `Tooltip` — all Tailwind + `cva`, several wrapping Radix primitives. These
are directly reusable by the public site. **No** `PublicHeader`, `PublicFooter`,
`LandingPage`, or `Marketing*`-named component exists anywhere in the repo — the entire
public-site UI (nav bar, footer, hero, pricing table, feature grid, module overview) is new
work; only tokens and the generic `ui/` primitives carry over.

## 7. App shell (for contrast with what a public shell needs)

`apps/web/app/(app)/layout.tsx` composes `AuthGuard` → `SidebarProvider` → a fixed left
`AppSidebar` (driven by `apps/web/lib/navigation.ts`'s permission-gated `NAVIGATION` tree)
+ `TopNavigation` (search, notifications, user menu) + a `<main>` capped at
`--content-max-width`. None of this is reusable for a public page — no sidebar, no
`AuthGuard`, no `SidebarProvider` should wrap public routes. The root `apps/web/app/layout.tsx`
is minimal (fonts + `Providers` only, no header/footer of its own), which is good: a new
public route group's own `layout.tsx` can supply public-only chrome exactly the way
`(auth)/layout.tsx` already supplies its own distinct (if minimal) chrome, without touching
the root layout or the authenticated shell.

## 8. Integrations: real, complete adapters, honestly "not exercised end-to-end," not fake

All integration adapters (`apps/api/app/integrations/adapters/`) — GitHub, Google
(Calendar+Gmail+Drive), HubSpot, Microsoft (Calendar+Outlook), Pipedrive, Slack, Intercom,
Zendesk — are real, complete OAuth + REST implementations against each provider's
documented API, gated on that provider's client credentials being configured. None are
stubs; the honest caveat is "not exercised against a live provider account in this
deployment," never "fake" or merely "planned." Apollo (`apps/api/app/sales/providers/apollo.py`)
follows the identical pattern as a single deployment-wide-key sales-data provider, separate
from the OAuth integrations system. A homepage integrations section can honestly list all
nine as supported connectors without claiming production-proven reliability it can't back.

## 9. Conclusion

This is close to a greenfield build on the frontend (no existing public/marketing surface
to extend) sitting on top of a real, extensive design-token system and a real (if
price-less) billing/entitlements API. The one hard structural constraint this effort must
resolve is that `/` currently means "authenticated dashboard" and `/security` is already
taken — both addressed as explicit design decisions in `docs/PUBLIC_SITE_DESIGN.md`. See
`docs/AUTH_UX_AUDIT.md` for the parallel audit of every authentication page, API contract,
and redirect behavior this effort must preserve while rebuilding the UI around it.
