# Public Site & Auth UX — Design

Concrete design decisions for `ui/public-site-and-auth-modernization`, building directly on
the findings in `docs/PUBLIC_SITE_AUDIT.md` and `docs/AUTH_UX_AUDIT.md`. Phased build order
lives in `docs/PUBLIC_SITE_IMPLEMENTATION_PLAN.md`.

## 1. Design-token foundation: fix the real radius gap, add a marketing type scale

`--radius-sm/md/lg` are used throughout the app but were never actually defined in
`globals.css` (only documented, plus two components' own inline fallbacks — see
`docs/PUBLIC_SITE_AUDIT.md` §6). This effort defines them for real
(`--radius-sm: 0.25rem; --radius-md: 0.5rem; --radius-lg: 0.75rem;`) in `globals.css` — a
small, low-risk, high-value fix that closes a latent bug rather than propagating it into
new components that would otherwise need their own redundant fallbacks.

The existing type scale tops out at 24px (`--text-2xl`), correctly tuned for dense
operational software. A marketing homepage needs real hero/display sizes. Rather than
inflate the app-wide scale (which would ripple into every authenticated screen), this
effort adds a **public-site-only** display scale, scoped by naming convention
(`--text-display-1: 3.5rem` / 56px, `--text-display-2: 2.75rem` / 44px,
`--text-3xl: 1.875rem` / 30px) defined alongside the existing tokens in `globals.css` but
only ever referenced by components under `apps/web/app/(marketing)/` and
`apps/web/components/marketing/`. All color, spacing, radius, shadow, and border tokens are
reused unchanged — the public site is visually the same design language at a larger scale,
not a different one.

## 2. Route structure: relocate the dashboard, place public "Security" content at `/trust`

Two hard constraints from the audit: `/` currently means "authenticated dashboard" (must
become the public homepage), and `/security` is already the real, tested Security
Operations module (a second `page.tsx` at the same literal path is a build-time collision
regardless of route grouping).

**Decision A — relocate the dashboard from `/` to `/dashboard`.** This is the one
unavoidable existing-route change in this effort, and it is the entire point of the task
(a public marketing page must own `/`). `apps/web/app/(app)/page.tsx` moves to
`apps/web/app/(app)/dashboard/page.tsx`. Every one of the 6 confirmed call sites that
navigates to the literal `"/"` as a post-auth destination (`docs/AUTH_UX_AUDIT.md` §5
table: login, MFA challenge, invitation accept, verify-email's manual link, onboarding
complete, and the app-shell logo/home link) is updated to `"/dashboard"` in the same commit
that performs the move, together with the two e2e tests whose assertions encode the old
`/` destination. No other route under `(app)/` changes name or path.

**Decision B — public marketing "Security" content lives at `/trust`, not `/security`.**
`/trust` (the bare path, as opposed to `/trust/[org_slug]`) resolves to nothing today — no
collision. It is also the closest existing conceptual sibling: `/trust/[org_slug]` is
already this codebase's own name for "a public page about how we handle your data,"
per-organization; `/trust` is that same idea at the product level. The public nav/footer
label this link "Security" (matching the brief's requested IA) while the route itself is
`/trust` — a normal, common pattern (nav label and URL slug are not required to be
identical) that avoids inventing an awkward path like `/security-and-trust` or, worse,
touching the real authenticated module.

**Decision C — `/features`, `/solutions`, `/pricing`, `/about`, `/contact` are created as
literally named, top-level public routes** — none collide with anything that exists today.

**Route group**: all seven public pages (`/`, `/features`, `/solutions`, `/trust`,
`/pricing`, `/about`, `/contact`) live under a new `apps/web/app/(marketing)/` route group,
with its own `layout.tsx` supplying `PublicHeader` + `PublicFooter` — no `AuthGuard`, no
`SidebarProvider`, no app-shell chrome, exactly parallel to how `(auth)/layout.tsx` already
supplies its own distinct, minimal chrome without touching the root layout. `(marketing)`,
`(app)`, and `(auth)` are siblings under `apps/web/app/`.

## 3. Middleware: real edge-level route protection, redirect-back, and auth-away-from-login

`apps/web/middleware.ts` is new (none exists today). It runs on every request and does
exactly three things, each independently justified by a gap in `docs/AUTH_UX_AUDIT.md` §5:

1. **Protected routes** (`/dashboard`, and everything else currently under `(app)/`): if
   the session cookie (`agora_session`) is absent, redirect to
   `/login?redirect=<original-path>` — a real, SSR-level redirect, replacing the visible
   "Loading… then flash-redirect" behavior of the client-only `AuthGuard`. `AuthGuard`
   itself is **not removed** — it stays as the belt-and-suspenders check for a cookie that
   is present but invalid/expired/revoked (middleware only checks *presence*, never
   validity, since edge middleware doing a DB/API round-trip on every request would add
   real latency to every page load; this mirrors the existing, already-documented
   philosophy in `auth-guard.tsx`'s own comment that client-side checks are a UX
   convenience, with the API remaining the real authorization boundary on every request
   regardless).
2. **`/login` and `/signup`**: if the session cookie is present, redirect to `/dashboard`
   (or to a pending `?redirect=` target if one was carried through) — closes the
   "authenticated user can freely reload the login page" gap the brief explicitly asks to
   fix. Every other `(auth)` route (`/forgot-password`, `/reset-password/[token]`,
   `/verify-email/[token]`, `/invite/[token]`, `/mfa-challenge`) is deliberately **not**
   included in this redirect — a logged-in user legitimately needs to reset a password,
   verify a second email, or accept an invitation into a different organization while
   already signed into another.
3. **Public marketing routes**: no redirect either direction — viewable regardless of auth
   state. (An authenticated visitor might still want to check `/pricing`.) The public
   header's own CTA area — not the middleware — is what adapts copy from "Sign in / Start
   free" to "Go to dashboard" based on `useCurrentUser()`, exactly the same client-side
   pattern the rest of the app already uses for permission-gated UI.

**Redirect-back mechanism, concretely**: `login/page.tsx` reads `useSearchParams().get("redirect")`.
On successful login (no MFA), it navigates to that value **only if it passes a strict
same-origin relative-path check** — starts with a single `/`, does not start with `//` (a
protocol-relative URL, the classic open-redirect vector), and does not contain a `:` before
the first `/` (rules out `javascript:`/`http:` disguised as a path) — otherwise it falls
back to the fixed `/dashboard` default. This exact validation function
(`isSafeRedirectTarget`, `apps/web/lib/auth-redirect.ts`) is unit-tested directly (Vitest)
against known-bad inputs (`//evil.com`, `https://evil.com`, `javascript:alert(1)`) per this
effort's own required "open-redirect prevention" test coverage — this is the single piece
of new logic in the whole effort with a real security consequence if it's wrong, so it gets
isolated, dedicated tests rather than being inlined and only indirectly exercised.

When MFA is required, the `redirect` value is carried forward as `/mfa-challenge?redirect=...`
so it survives the second hop.

## 4. Public design-system components

New, reusable, all under `apps/web/components/marketing/` (except the four `Auth*`
components, under `apps/web/components/auth/`, since they're shared between the `(auth)`
route group's pages, not marketing-specific):

`PublicHeader`, `PublicFooter`, `HeroSection`, `SectionHeader`, `ProductPreview`,
`ModuleOverview`, `FeatureGrid`, `WorkflowExample`, `TrustSection`, `IntegrationGrid`,
`PricingPreview`, `CustomerTypeSection`, `FinalCTA` — one file each, composed by the
`(marketing)` pages; `AuthLayout`, `AuthCard`, `AuthField`, `PasswordField`,
`PasswordStrength`, `OAuthButtons`, `AuthAlert`, `VerificationState`, `InvitationSummary`,
`OnboardingStepper` — shared by every page under `(auth)` and the onboarding wizard.

All of them consume the existing `ui/` primitives (`Button`, `Card`, `Badge`, `Input`,
`Label`) and existing CSS variables — none defines its own color, spacing, or radius. This
is the literal meaning of "reuse the enterprise design system" from the brief: the
marketing site is a new *layout and copy* layer over the same tokens, not a parallel visual
language.

`Logo` (`apps/web/components/logo.tsx`) is new and shared by literally everything —
`PublicHeader`, `AuthLayout`, and the existing `AppSidebar`/`(auth)/layout.tsx` (which today
each independently render the plain text string "Agora Origin" — both are updated to use
the same component, so the brand mark is consistent everywhere for the first time). It's a
small SVG wordmark: a minimal geometric mark (a rounded square containing a stylized
concentric-node motif in `--brand-primary`, evoking "a governed center" — deliberately
restrained, not a literal shield/lock cliché) plus the "Agora Origin" text set in the
existing Geist Sans, with a `size` prop (`sm`/`md`/`lg`) and a `markOnly` prop for the
favicon/collapsed-sidebar case. The generated favicon and OG image are both derived from
this same mark for visual consistency (previously: an untouched default Next.js favicon,
no OG image at all).

## 5. Pricing preview: real entitlements, honest pricing framing

The pricing page and homepage pricing-preview section both call the real, already-public
`GET /api/v1/billing/plans` for the four real plan names and their entitlement values — the
feature-comparison rows are never hardcoded. Display copy (plan taglines, which
entitlements to surface as headline bullets, and the price label) lives in exactly one
place, `apps/web/lib/pricing-config.ts` — a small config object keyed by the same four plan
keys the backend uses (`starter`/`growth`/`business`/`enterprise`), imported by both the
homepage preview and the full `/pricing` page so there is never a second copy to drift.

Since no plan has a real € figure anywhere in the system (`docs/PUBLIC_SITE_AUDIT.md` §3),
this effort does **not** invent precise numbers. Starter is labeled **"Free"** — literally
true today (org creation has no payment step at all, and it matches the brief's own hero
CTA, "Start free") — and Growth/Business/Enterprise are labeled **"Contact sales"**,
exactly the fallback the brief itself specifies for unfinalized pricing. This is more
honest than authoring plausible-looking numbers with no backing, and requires no future
"we made up a price" cleanup once real pricing exists — only `pricing-config.ts` would need
one line changed per plan at that point.

## 6. Demo-request: new, minimal, real backend capability

No public lead-capture path exists today (`docs/PUBLIC_SITE_AUDIT.md` §4). This effort adds
a genuinely new, minimal, real backend surface rather than a form that silently discards
input:

- `apps/api/app/marketing/models.py` — new `DemoRequest` (a new small module, not folded
  into `app.sales`, since it deliberately has **no** `organization_id` — a demo requester
  has no organization yet, unlike every existing Sales model which is tenant-scoped by
  design; folding it into `app.sales` would be the wrong shape, not a convenience).
  Columns: `id`, `full_name`, `work_email`, `company_name`, `company_size` (enum matching
  the brief's own bracket suggestion), `country`, `primary_interest`, `message` (nullable),
  `created_at`, `status` (`new`/`contacted`/`closed`, default `new`, for whoever follows up
  manually).
- `POST /api/v1/marketing/demo-requests` — genuinely public (no auth dependency, exactly
  like `GET /billing/plans` already is), protected by the existing global
  `RateLimitMiddleware` (already IP-keyed and applied to every route, including this one, at
  no extra cost). Validates and normalizes email, writes the row, fires a `record_event`
  audit entry (`marketing.demo_request.created`, no `organization_id` — the audit service
  already supports a nullable org per `docs/AUTH_UX_AUDIT.md`'s note on platform-level
  events) so the submission is durably, auditably recorded even with no real email provider
  to notify anyone (`docs/PUBLIC_SITE_AUDIT.md` §4's email-sending finding). Returns
  `{ok: true}`.
- `GET /api/v1/marketing/demo-requests` — `org_admin`-only (reuses the existing permission
  rather than minting a new key, matching the RBAC-reuse discipline already established for
  this codebase — see `docs/SALES_DATA_PROVIDER_ARCHITECTURE.md` §14 for the precedent),
  lets a real person at Agora actually see and follow up on submissions without needing a
  working email provider. A minimal list view only — no dedicated UI page in this pass
  (documented as a follow-up in `docs/KNOWN_LIMITATIONS.md`, not silently dropped).

The contact form and the "Request a demo" CTA share this same endpoint — there is no
separate, second "contact us" backend path, since the brief's own field lists for both are
effectively identical (name, work email, company, message).

## 7. Analytics: documented event hooks, zero third-party data egress

No privacy-approved analytics provider exists (`docs/PUBLIC_SITE_AUDIT.md` §5), and the
brief explicitly forbids adding one automatically. This effort adds
`apps/web/lib/analytics.ts` — a single `track(event: MarketingEvent, props?)` function whose
body, today, only `console.debug`s in development and is a genuine no-op in production (no
network call, no third-party SDK, nothing leaves the browser). The six events the brief
names (`homepage_cta_clicked`, `pricing_viewed`, `signup_started`, `signup_completed`,
`login_completed`, `demo_request_submitted`) are wired at their real call sites now, so the
instrumentation points exist and are documented — the moment a real, privacy-approved
provider is chosen, only `analytics.ts`'s internal implementation needs to change, not
every call site. No event payload ever includes an email address or other personal data,
enforced by convention in the one function every call site goes through.

## 8. SEO and metadata

Every `(marketing)` page exports real Next.js `metadata` (title, description, canonical,
Open Graph, Twitter card) via each page's own `metadata` export or `generateMetadata`.
`apps/web/app/sitemap.ts` and `apps/web/app/robots.ts` are new, generated (not static
files), listing exactly the seven public routes. `robots.ts` additionally disallows
`/login`, `/signup`, `/forgot-password`, `/reset-password`, `/verify-email`, `/invite`,
`/mfa-challenge`, `/onboarding`, and everything under the authenticated app — belt-and-
suspenders alongside each of those pages' own `metadata = { robots: { index: false } }`
export (the actual mechanism search engines respect; `robots.txt` is the crawl-budget
hint). The root `layout.tsx`'s existing static metadata becomes the shared fallback/default
that per-page metadata overrides, not something removed.

## 9. Security considerations specific to this effort

- **Open-redirect prevention** — §3 above; the one piece of new logic with real attacker
  value if wrong, given its own unit tests.
- **No new session/cookie behavior** — the backend contract (`docs/AUTH_UX_AUDIT.md` §3–4)
  is completely unchanged; this effort is a UI/routing layer on top of it.
- **Account-disabled message parity** — SSO callback's distinct "Account disabled" `401` is
  changed to match `/login`'s generic "Invalid email or password" framing (fixed as part of
  the sign-in/sign-up slice, called out on its own in that commit).
- **Demo-request endpoint** is genuinely public by necessity (like `GET /billing/plans`
  already is) — relies on the existing global rate limiter for abuse resistance, exactly as
  every other newly-added public endpoint in this codebase's history has (no CSRF token is
  meaningful here since an unauthenticated form has no session to forge against).
- **`redirect` query param** is never trusted as-is — validated by `isSafeRedirectTarget`
  before use, never rendered as raw HTML, never used to construct a redirect outside the
  app's own origin.
- **Middleware cookie check is presence-only, not validity** — documented, not hidden; the
  API remains the real authorization boundary on every request, unchanged from today.

## 10. What this design deliberately does not attempt

- **No payment collection** — pricing stays "Free" / "Contact sales," matching the
  pre-existing, disclosed absence of billing/checkout in this codebase
  (`docs/KNOWN_LIMITATIONS.md`).
- **No third-party analytics provider** — instrumentation hooks only, per §7.
- **No SAML/SCIM enterprise SSO** — real Google/Microsoft SSO already exists and is
  preserved as-is; SAML remains a disclosed, pre-existing limitation, not something this
  effort promises.
- **No admin UI for demo-request follow-up** — the list endpoint exists (§6); a dedicated
  page is out of scope for this pass and named as a follow-up in
  `docs/KNOWN_LIMITATIONS.md`, not silently dropped.
- **No custom illustration/photography** — the hero's "real product preview" is a
  controlled, code-built `ProductPreview` component using the actual application's own
  design language (real `Card`/`Badge`/`MetricCard`-style pieces, clearly labeled demo
  values), not a commissioned illustration or a stock photo, per the brief's own explicit
  list of things to avoid.
