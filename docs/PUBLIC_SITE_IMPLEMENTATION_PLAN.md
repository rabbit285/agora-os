# Public Site & Auth Modernization — Implementation Plan

Branch: `ui/public-site-and-auth-modernization`. Companion docs:
`docs/PUBLIC_SITE_AUDIT.md` (what exists today), `docs/AUTH_UX_AUDIT.md` (auth-specific
audit), `docs/PUBLIC_SITE_DESIGN.md` (the concrete design this plan builds). Executes in
dependency order, each slice implemented for real, checked, and committed separately — the
same discipline used for `docs/SALES_LEAD_FINDER_IMPLEMENTATION_PLAN.md`.

## Scope and honesty about pacing

This is a large, mostly-frontend build: a new route group, a new middleware layer, ~22 new
reusable components, 7 public pages, a rebuild of 7 existing auth pages, an onboarding
refresh, one new small backend module (demo requests), a design-token fix, and a full
SEO/accessibility/test pass. Given the size, real vertical slices are built and checked in
priority order, matching the brief's own 7-slice commit strategy exactly (its numbering is
used as this plan's phase numbering below, 1:1).

## Phase 1 — Public-site audit, design system foundation, and shared components

Already-committed docs (this phase): the four audit/design docs. Code in this phase: the
`--radius-sm/md/lg` fix and the new `--text-display-1/2`/`--text-3xl` tokens in
`globals.css`; the new `Logo` component (replacing the plain-text wordmark in both
`AppSidebar` and `(auth)/layout.tsx`, plus a generated favicon/OG image derived from it);
`apps/web/lib/pricing-config.ts`; `apps/web/lib/analytics.ts`; all 13 marketing components
and all 10 auth components listed in `docs/PUBLIC_SITE_DESIGN.md` §4, built against
realistic placeholder content so later phases only need to pass real props, not build UI.

**Done when**: every new component renders in isolation with representative props; `tsc`
and ESLint are clean; the radius/type-scale token additions don't visually regress any
existing authenticated page (spot-checked, since these are additive tokens, not
replacements).

## Phase 2 — Enterprise homepage

`apps/web/app/(marketing)/layout.tsx` (PublicHeader + PublicFooter shell) and
`apps/web/app/(marketing)/page.tsx` composing, in order: Hero (with `ProductPreview`),
Problem section, Platform/`ModuleOverview` (6 modules: Compliance, Security, Sales,
Support, Automation, AI Governance), How-it-works (4 steps), AI Copilot section,
Cross-module `WorkflowExample`s, `TrustSection`, `IntegrationGrid` (9 real connectors,
accurately labeled per `docs/PUBLIC_SITE_AUDIT.md` §8), `CustomerTypeSection`,
`PricingPreview`, `FinalCTA`. Also: `/features`, `/solutions`, `/trust`, `/about`,
`/contact` pages (each a focused, non-padded page — no empty placeholders, per the brief's
own instruction). `/contact` and the homepage's "Request a demo" CTA both submit to the new
demo-request endpoint (Phase 2 also includes its backend half —
`apps/api/app/marketing/`, per `docs/PUBLIC_SITE_DESIGN.md` §6 — since the contact page is
not meaningfully done without a real submit path).

**Done when**: all 7 public routes render real content (no lorem ipsum, no fake stats/logos
per the brief's explicit list), `next build` includes them as statically generated where
practical, the demo-request form round-trips against the real backend, and
`docs/PUBLIC_SITE_AUDIT.md`'s pricing/integrations findings are reflected accurately (no
integration shown as more "live" than §8 supports).

## Phase 3 — Sign-in and sign-up modernization

Rebuild `/login` and `/signup` on `AuthLayout`/`AuthCard`/`AuthField`/`PasswordField`/
`OAuthButtons`/`AuthAlert`, preserving every existing field, validation rule, and API call
from `docs/AUTH_UX_AUDIT.md` §1–3 exactly (same endpoints, same request bodies, same SSO
provider-gating logic lifted from the existing `login/page.test.tsx`-covered behavior).
New in this phase: `apps/web/middleware.ts` and `apps/web/lib/auth-redirect.ts`
(`docs/PUBLIC_SITE_DESIGN.md` §3) — redirect-back, auth-away-from-login/signup,
protected-route edge gating; the dashboard relocation from `/` to `/dashboard`
(`docs/PUBLIC_SITE_DESIGN.md` §2 Decision A) and every one of the 6 call-site updates from
`docs/AUTH_UX_AUDIT.md` §5's table; the account-disabled message-parity fix (§9 of the
design doc); marketing-consent as a separate, unchecked-by-default optional field on
signup, distinct from the required Terms/Privacy acceptance (per the brief's explicit
instruction not to bundle the two).

**Done when**: `test_auth.py`, `test_sso.py`, `login/page.test.tsx` all still pass
unmodified (no backend/API contract changed); `auth.spec.ts` passes with its
`/dashboard`-destination assertions updated to match the relocation; the new
`isSafeRedirectTarget` unit tests pass against known-bad open-redirect payloads; manually
verified that an authenticated user hitting `/login` is bounced to `/dashboard` and an
unauthenticated user hitting `/dashboard` is bounced to `/login?redirect=/dashboard` and
actually lands back on `/dashboard` after logging in.

## Phase 4 — Password, verification, and invitation flows

Rebuild `/forgot-password`, `/reset-password/[token]`, `/verify-email/[token]`,
`/invite/[token]` on the same shared auth components, preserving every backend contract
from `docs/AUTH_UX_AUDIT.md` §3 exactly (silent forgot-password response, 2h reset-token
TTL and force-logout-everywhere behavior, 48h verification-token TTL, 7-day invitation TTL).
New in this phase: the invitation-acceptance "sign in when an account already exists"
branch that today's frontend has no code path for at all (§8 item 5 of the audit) —
`InvitationSummary` now checks whether the invited email already resolves to an account
(a new, minimal, unauthenticated-safe check, or simply branches on the `full_name`/`password`
fields being absent from the invitation's own metadata the backend already returns) and
offers "Sign in to accept" instead of forcing a redundant password field. A minimal MFA
pending-challenge guard for `/mfa-challenge` (§8 item 6 of the audit).

**Done when**: `test_email_verification_invitations_mfa.py` passes unmodified; every state
listed in the brief for each of these four flows (invalid/expired token, already-verified,
revoked invitation, etc.) is reachable and visibly distinct in the UI, verified live against
the real backend (not mocked).

## Phase 5 — Onboarding experience

Restyle the existing 9-screen wizard on `OnboardingStepper` + the shared auth/marketing
visual language, preserving every field, every backend endpoint, and the exact
resume-at-`current_step` mechanic from `docs/AUTH_UX_AUDIT.md` §6 unchanged — this phase is
visual and navigational polish (stepper UI, consistent spacing/typography, "Configure
later" labeling on the two pass-through steps per the brief's explicit wording), not a
rebuild of onboarding's data model or step count.

**Done when**: `onboarding/page.test.tsx` and `onboarding.spec.ts` pass, with the wizard's
final-step navigation assertion updated from `/` to `/dashboard` per the Phase 3 relocation.

## Phase 6 — Accessibility, SEO, and performance

`apps/web/app/sitemap.ts`, `apps/web/app/robots.ts`, per-page `metadata`/`generateMetadata`
exports (including `noindex` on every auth/onboarding route, per
`docs/PUBLIC_SITE_DESIGN.md` §8) across all 7 public pages plus the 7 auth pages plus
onboarding. Skip-to-content link, landmark regions, and focus-visible audit across the new
`(marketing)` and `(auth)` layouts specifically (the authenticated app shell is unchanged
and out of scope). `prefers-reduced-motion` respected by every new transition/animation.
Image optimization (`next/image`) for the generated OG image and any product-preview
imagery. No new animation framework is introduced (the brief's own constraint) — CSS
transitions only, matching what the app already uses.

**Done when**: axe-core scans (new `apps/web/e2e/public-site-accessibility.spec.ts`,
following the exact pattern already established in
`apps/web/e2e/sales-lead-finder-accessibility.spec.ts`) return zero violations on the
homepage, `/login`, `/signup`, and onboarding; Lighthouse-style manual spot-check confirms
no obvious layout shift on the homepage hero; `next build`'s static-generation report shows
every public page prerendered.

## Phase 7 — Tests and documentation

New Playwright spec `apps/web/e2e/public-site-and-auth.spec.ts` covering all 18 journeys
listed in the brief's §22 (homepage → nav → signup → email verification → onboarding →
dashboard → sign out → sign in → forgot/reset password → invitation accept/invalid →
authenticated-user-can't-reach-login → redirect-back → mobile nav → keyboard-only signup),
built on the existing `apps/web/e2e/helpers.ts` `signup()`/`login()`/`logout()`/
`getLatestInvitationUrl()` helpers (extended, not replaced) exactly as
`sales-lead-finder.spec.ts` did. New Vitest coverage for every component/state listed in
the brief's §22 frontend-tests list, plus `isSafeRedirectTarget`'s dedicated security unit
tests. Full check suite (ruff/mypy/pytest for the new marketing backend module; ESLint/tsc/
Vitest/`next build`/Playwright/axe for the frontend; Docker smoke test). Screenshot capture
per the brief's §25 list. Documentation updates: `docs/ROUTES_AND_SCREENS.md`,
`docs/IMPLEMENTATION_STATUS.md`, `docs/IMPLEMENTATION_PLAN.md`,
`docs/RELEASE_CHECKLIST.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/ENVIRONMENT_VARIABLES.md`
(if any new env var is introduced — none is anticipated, since no new third-party
credential is required by anything in this plan), plus closing out any decisions recorded
provisionally in this plan with a new ADR in `docs/DECISIONS.md`.

## Testing (maps to brief §22)

Backend: demo-request creation/validation/rate-limiting/audit-logging, demo-request list
permission-gating, no regressions in any existing auth/onboarding/tenant-isolation test.

Frontend (Vitest): homepage section rendering, mobile menu, CTA links, pricing rendering
from live entitlements, sign-in/sign-up validation and error states, password
visibility/strength, forgot/reset-password states, email-verification states, invitation
states, onboarding step rendering, `isSafeRedirectTarget` open-redirect cases, SEO metadata
presence.

Playwright (18 journeys, brief §22 numbering): see Phase 7 above for the full mapping.

Accessibility: axe-core WCAG 2.1 A/AA scans on homepage, login, signup, onboarding
(`public-site-accessibility.spec.ts`), plus keyboard-only navigation tests for the
homepage's mobile menu and the signup form, following the exact precedent already
established in this codebase for the Sales Lead Finder effort.

## Commit strategy (brief §26, followed literally)

1. Public-site audit and design system (docs + token fixes + shared components).
2. Enterprise homepage (+ `/features`, `/solutions`, `/trust`, `/about`, `/contact`, demo-request backend).
3. Sign-in and sign-up modernization (+ middleware, dashboard relocation, redirect-back).
4. Password, verification, and invitation flows.
5. Onboarding experience.
6. Accessibility, SEO, and performance.
7. Tests and documentation.

Sub-slices within a numbered commit are committed separately when independently testable,
following the same "implement → check → commit" discipline as every prior effort in this
codebase. Push to `origin/ui/public-site-and-auth-modernization` after each phase; do not
merge until the complete verification suite in Phase 7 passes.

## Phase 8 — Homepage product-module carousel (`ui/homepage-module-carousel`, follow-on branch)

A separate branch on top of the merged public site, adding a major visual showcase of
the six modules to the homepage. See `docs/PUBLIC_SITE_DESIGN.md` §11 for the full
design (image handling, layout, autoplay, accessibility, two real bugs found and fixed).

Commit strategy (this branch's own brief, followed literally):

1. Optimized product-module image assets (6 real photos, PNG→JPEG).
2. Responsive homepage module carousel (`embla-carousel-react`, `/features` anchors,
   the `middleware.ts` static-asset matcher fix, the Embla `watchDrag` click fix).
3. Carousel accessibility and interaction tests (18 Vitest, 9 Playwright functional
   journeys, 2 additional axe/keyboard tests).
4. Documentation.

Verification: full frontend `tsc`/ESLint/Vitest/production-build, the full Playwright
suite, and a live Docker smoke test — see `docs/RELEASE_CHECKLIST.md`. Merged to `main`
after the complete verification suite passes, per this branch's own instruction.
