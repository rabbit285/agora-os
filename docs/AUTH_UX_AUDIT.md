# Auth UX Audit

Audit date: 2026-08-05, on branch `ui/public-site-and-auth-modernization`. This audit
inspects every authentication page, its exact API contract, session/redirect mechanics,
onboarding, and existing test coverage as they exist today, before any code in this effort
is written. Companion doc: `docs/PUBLIC_SITE_AUDIT.md` (public routes, homepage, design
system). Concrete design decisions building on these findings live in
`docs/PUBLIC_SITE_DESIGN.md`.

## 1. Existing auth pages, field-by-field

All live under `apps/web/app/(auth)/` (route group, no auth required) plus
`apps/web/app/(app)/onboarding/` (requires auth). `(auth)/layout.tsx` centers a `Card`
with a static "Veyntra" text wordmark — no other logic.

| Route | Fields | States handled | Calls | On success |
|---|---|---|---|---|
| `/login` | email, password | submitting, serverError, SSO-provider loading, SSO error banner from `?error=` query | `GET /auth/sso/providers`, `apiFetch(/auth/sso/{provider}/start)`, `POST /auth/login` | `router.push(mfa_required ? "/mfa-challenge" : "/")` |
| `/signup` | full_name, organization_name, email, password (≥12 chars) | submitting, serverError | `POST /auth/signup` | `router.push("/onboarding")` |
| `/forgot-password` | email | submitting, `submitted` (swaps to "check your email" — **no error state**, by design) | `POST /auth/forgot-password` | stays on page |
| `/reset-password/[token]` | new_password (≥12) | submitting, serverError | `POST /auth/reset-password` `{token, new_password}` | `router.push("/login")` |
| `/verify-email/[token]` | none — fires in `useEffect` on mount | `"verifying" \| "success" \| "error"` | `POST /auth/verify-email` `{token}` | no auto-nav; "Go to dashboard" button (`href="/"`) shown in every terminal state |
| `/invite/[token]` | full_name, password (≥12) — **always required by the UI**, even though the backend allows omitting both when the invited email already has an account | submitting, serverError | `POST /auth/accept-invitation` `{token, full_name, password}` | `router.push("/")` |
| `/mfa-challenge` | code (6–8 chars) | submitting, serverError (defaults "Invalid code") | `POST /auth/mfa/verify` `{code}` — relies on the pending session cookie already being set by `/login`; **no check that a challenge is actually pending before rendering** | `router.push("/")` |

## 2. Auth API client

No shared `lib/auth.ts` exists — every page calls `apiFetch` (`apps/web/lib/api.ts`)
directly with a hardcoded path. `apiFetch<T>(path, {method, body, organizationId})` always
sends `credentials: "include"`, sets `Content-Type: application/json`, and unwraps the
backend's `{error:{message, request_id}}` envelope into a typed `ApiError`.

`apps/web/lib/session.ts` is the closest thing to an auth lib: `useCurrentUser()` (→
`GET /auth/me`, React Query, `retry:false`), `useCurrentOrganization()`,
`useCurrentPermissions()`.

Every auth endpoint the frontend calls today:

| Endpoint | Method | Caller |
|---|---|---|
| `/auth/signup` | POST | signup/page.tsx |
| `/auth/login` | POST | login/page.tsx |
| `/auth/sso/providers` | GET | login/page.tsx |
| `/auth/sso/{provider}/start` | GET | login/page.tsx (redirects via `window.location.href`) |
| `/auth/forgot-password` | POST | forgot-password/page.tsx |
| `/auth/reset-password` | POST | reset-password-form.tsx |
| `/auth/verify-email` | POST | verify-email-status.tsx |
| `/auth/accept-invitation` | POST | accept-invitation-form.tsx |
| `/auth/mfa/verify` | POST | mfa-challenge/page.tsx |
| `/auth/me` | GET | lib/session.ts |
| `/auth/logout` | POST | top-navigation user menu (not a standalone page) |

Not called from any page examined (presumably reachable from `/settings/security`):
`/auth/resend-verification-email`, `/auth/mfa/enroll`, `/auth/mfa/confirm`,
`/auth/mfa/disable`.

## 3. Backend auth endpoints — full contract

Router `apps/api/app/identity/router.py` (prefix `/api/v1/auth`), service
`apps/api/app/identity/service.py`, SSO `apps/api/app/identity/sso.py`, invitations
`apps/api/app/core/invitations.py`.

- **`POST /signup`** — `{email, password (12-200 chars), full_name, organization_name}`.
  Creates User + Organization + default LegalEntity + `org_admin` Membership, fires
  email-verification request, sets session cookie. Duplicate email → generic
  `400 "Unable to create account"` (no enumeration).
- **`POST /login`** — `{email, password}`. Wrong password *or* inactive user both return
  the identical `401 "Invalid email or password"` — no enumeration, no disabled-account
  leak on this path (contrast with SSO below). Sets cookie with
  `mfa_verified = !mfa_enabled`. Returns `{user, mfa_required}`.
- **`GET /sso/providers`** — public; `[{provider, configured}]` for `google`/`microsoft`.
- **`GET /sso/{provider}/start`** — public; 400 if not configured; creates a
  `SsoLoginAttempt` (state CSRF token, 10 min TTL), returns the real authorization URL.
- **`GET /sso/{provider}/callback`** — public, top-level redirect target. Validates
  `state`, exchanges code, provisions or reuses a user, sets the cookie on the
  `RedirectResponse` itself, redirects to `/mfa-challenge`, `/onboarding` (new user), or
  `/` (existing user); any error redirects to `/login?error=<message>` (read by the login
  page's SSO error banner).
- **`POST /logout`** — auth required; revokes session, deletes cookie.
- **`GET /me`** — auth required; `UserOut`.
- **`POST /forgot-password`** — `{email}`; **always** returns `{ok:true}`, silent whether
  or not the email exists.
- **`POST /reset-password`** — `{token, new_password}`.
- **`POST /resend-verification-email`** — auth required.
- **`POST /verify-email`** — `{token}`.
- **`POST /mfa/enroll` / `/mfa/confirm` / `/mfa/disable` / `/mfa/verify`** — auth required
  (verify uses the *pending*, `mfa_verified=False` session set by `/login`).
- **`POST /accept-invitation`** — `{token, full_name?, password?}` — both genuinely
  optional server-side, required only if the invited email has no existing `User` yet.
  Sets session cookie.

**Rate limiting**: a global, Redis-backed, IP-keyed, 60-second fixed-window
`RateLimitMiddleware` (`apps/api/app/core/rate_limit.py`) wraps every request — not
auth-specific, not per-account. Fails open on Redis outage. Returns `429` +
`Retry-After: 60`. **No per-account/per-email lockout exists** — failed logins are
audit-logged (`auth.login.failed`) but never separately throttled.

**Passwords**: 12–200 chars, no complexity rules, Argon2id hashing
(`apps/api/app/security.py`).

**Email-verification tokens**: opaque `secrets.token_urlsafe(32)`, only the SHA-256 hash is
stored, 48h TTL, single-use. No real email — a dev/local adapter logs the URL
(`_dispatch_email_verification_email`).

**Password-reset tokens**: same opaque/hash pattern, 2h TTL, single-use. **On successful
reset, every existing session for that user is revoked** — force-logout-everywhere. Never
reveals whether the email exists.

**Invitation tokens**: opaque/hash pattern, 7-day TTL, single-use, revocable. Enforces
`max_users` entitlement at creation time. Accepting fires a `new_employee` automation
trigger. No real email.

**Real SSO login exists and must not be dropped**: `apps/api/app/identity/sso.py`
implements genuine Sign-in-with-Google/Microsoft (module docstring explicitly distinguishes
this from the Integrations module's per-connection OAuth for HubSpot/Calendar/etc. — same
underlying adapter helpers, minimal identity-only scopes:
`openid email` / `openid email profile User.Read`). CSRF state stored server-side
(`SsoLoginAttempt`, 10 min TTL, single-use), not in a cookie. First-time SSO login
auto-provisions a new org exactly like `/signup` (random unusable password). Existing-user
SSO login is gated by the org's `sso_enabled` billing entitlement (`402` if the plan
doesn't include it) — new-org SSO signups are exempt. SAML/SCIM enterprise-directory SSO is
explicitly **not built** (disclosed in `docs/KNOWN_LIMITATIONS.md`).

**"Remember me"**: does not exist anywhere, frontend or backend.

**Account-disabled handling is inconsistent between the two login paths** — a real,
pre-existing bug worth fixing in this effort: `/login` folds an inactive user into the
generic "Invalid email or password" (matches the no-enumeration intent), while the SSO
callback raises a distinct `401 "Account disabled"` (a real information leak relative to
the password-login path's own stated goal). `User.is_active` exists but nothing in the
codebase currently sets it false (no admin "disable user" endpoint found).

## 4. Session handling

Cookie (`apps/api/app/identity/router.py:38-47`): name `agora_session`
(`settings.session_cookie_name`), `httponly=True`,
`secure=settings.cookie_secure` (env `COOKIE_SECURE`, default `False`), `samesite="lax"`,
`max_age` = 14 days (`settings.session_ttl_hours`, default 336h), `path="/"`. Value is a
raw opaque token; only its SHA-256 hash is stored server-side (`Session.session_token_hash`)
— sessions are DB rows, not JWTs, so logout/reset revocation is a single `revoked_at`
write.

Frontend "am I logged in" check is **entirely client-side**: `useCurrentUser()` → `GET
/auth/me` via React Query, gated by `AuthGuard` (`apps/web/components/auth-guard.tsx`,
wraps the whole `(app)` route group). `AuthGuard` shows a full-screen "Loading…" while the
query resolves, then `router.replace("/login")` on error/no-user. Its own code comment is
explicit that this is a UX convenience gate, not the real authorization boundary — the API
enforces auth/authz server-side on every request regardless
(`apps/api/app/dependencies.py`'s `get_current_user`/`get_org_context`, which additionally
requires `session.mfa_verified` and an active `Membership` in the resolved organization).

## 5. Redirect behavior — the biggest gap this effort must close

**No `apps/web/middleware.ts` exists at all.** Route protection today is 100% the
client-side `AuthGuard` described above — there is no edge/SSR-level redirect, and
consequently:

- **No "return to the page you were trying to reach" mechanism exists anywhere** —
  `AuthGuard` calls `router.replace("/login")` without capturing the current path in a
  query param, cookie, or storage. Every post-login `router.push` target found in the
  codebase is a **fixed** destination (see table below) — none is derived from where the
  user was headed. This is genuinely new work, not a refactor of existing logic.
- **No "redirect an already-authenticated user away from `/login`/`/signup`" logic exists**
  — an authenticated user can freely load either page today; submitting just creates a
  fresh session with no special-casing.

Every fixed post-action destination in the codebase today (all become `/dashboard` after
this effort's required relocation of the dashboard off `/` — see
`docs/PUBLIC_SITE_DESIGN.md` §2 — with call sites confirmed via a full-repo grep for
`router.push("/")` / `router.replace("/")` / `href="/"`):

| Event | Current destination | File |
|---|---|---|
| Login success, no MFA | `/` | `(auth)/login/page.tsx:89` |
| Login success, MFA required | `/mfa-challenge` | same |
| MFA challenge success | `/` | `(auth)/mfa-challenge/page.tsx:33` |
| Signup success | `/onboarding` | `(auth)/signup/page.tsx:40` |
| Reset-password success | `/login` | `(auth)/reset-password/[token]/reset-password-form.tsx:35` |
| Accept-invitation success | `/` | `(auth)/invite/[token]/accept-invitation-form.tsx:38` |
| Verify-email (any terminal state) | `/` (manual button) | `(auth)/verify-email/[token]/verify-email-status.tsx:49` |
| SSO callback (backend redirect) | `/mfa-challenge`, `/onboarding` (new user), or `/` | `identity/router.py:134-139` |
| SSO callback error | `/login?error=<msg>` | same |
| Onboarding complete | `/` | `(app)/onboarding/page.tsx:359` |
| App shell logo/home link | `/` | `components/app-sidebar.tsx:49` |

An unauthenticated user hitting a protected route today renders the page shell, shows
"Loading…" while `/auth/me` resolves, then client-redirects — a visible flash, and a window
where any child component not itself waiting on the guard could fire an unauthorized
request. This is the concrete problem a real `middleware.ts` (introduced by this effort,
see `docs/PUBLIC_SITE_DESIGN.md` §3) solves.

## 6. Onboarding flow

`apps/web/app/(app)/onboarding/page.tsx` — inside the authenticated `(app)` layout, every
backend call requires `org.settings.manage` (`apps/api/app/routers/onboarding.py`, all 9
endpoints). Resumable: `GET /onboarding/status` returns `current_step`; the page derives
`resumedScreen = min(current_step - 1, 8)`. Each screen's `PUT`/`POST` only ever advances
`current_step` forward.

9 screens: **1. Company** (industry required, employee range) · **2. Goals** (multi-select,
≥1 required) · **3. Compliance profile** (multi-select frameworks, fetched live from
`GET /compliance/frameworks`, skippable) · **4. Security profile** (cloud provider,
defaults `none`, effectively skippable) · **5. Sales profile** (free text, required) ·
**6. Support profile** (multi-select channels, skippable) · **7. Connect tools**
(pass-through link to `/settings/integrations`, fully skippable) · **8. Upload knowledge**
(pass-through link to `/knowledge`, fully skippable) · **9. Readiness** (read-only,
live-computed 5-dimension score via `GET /onboarding/readiness`; "Open Business Command
Center" calls `POST /onboarding/complete` then navigates to `/`).

No "skip the whole wizard" button exists; nothing blocks direct URL navigation to `/`
before completion, but there's no in-UI shortcut either.

## 7. Existing tests that must keep passing (or be deliberately, visibly updated)

**`apps/web/e2e/auth.spec.ts`** (3 tests): signup lands on `/onboarding`; logout then login
works and shows the org name in the user menu; a wrong password shows "Invalid email or
password" and stays on `/login`.

**`apps/web/e2e/onboarding.spec.ts`** (2 tests): the full 9-screen wizard end to end,
asserting the final URL is exactly `/`; onboarding resumes correctly after a page reload.

**`apps/web/e2e/helpers.ts`**: `signup()`, `login()`, `logout()` (drives the real UI, not a
shortcut), `getLatestInvitationUrl()` (reads the invite link out of the API container's
docker logs, since no real email provider exists).

**`apps/web/app/(auth)/login/page.test.tsx`** (Vitest, 3 tests): SSO buttons hidden when
unconfigured; shown only for the configured provider and navigate correctly; error banner
sourced from `?error=` query param.

**`apps/web/app/(app)/onboarding/page.test.tsx`** (Vitest, 6 tests): resume-at-correct-step
behavior, step submission/advancement, readiness rendering, completion navigation.

**Backend** (`apps/api/tests/test_auth.py`, 8 tests; `test_email_verification_invitations_mfa.py`,
14 tests; `test_sso.py`, 6 tests) — full coverage of signup/login/logout/me,
forgot/reset-password, email verification, invitations (create/accept/revoke/duplicate),
MFA enroll/confirm/verify/disable, and SSO providers/start/callback/state-reuse-rejection.
**None of this backend surface changes in this effort** — the rebuild is a frontend UI/UX
and routing effort on top of an unchanged, already-real API contract; every test in this
list is expected to keep passing unmodified, since no request/response shape here is being
altered. Any e2e test whose *assertion* encodes the old fixed-destination-`/` behavior
(e.g. onboarding's "final URL is exactly `/`") will need a small, deliberate, documented
update to assert `/dashboard` instead, per the relocation decision in
`docs/PUBLIC_SITE_DESIGN.md` §2 — never a silent behavior change without a matching test
update.

## 8. Gaps and small real bugs this effort should fix (not just redesign around)

1. **No redirect-back-to-intended-page mechanism** — net-new (`docs/PUBLIC_SITE_DESIGN.md` §3).
2. **No middleware/edge route protection** — net-new, same section.
3. **No "redirect an authenticated user away from `/login`/`/signup`"** — net-new, same section.
4. **Account-disabled messaging is inconsistent** between `/login` (generic, no leak) and
   SSO callback (explicit "Account disabled", a real leak) — fixed in the auth-flows slice
   by matching SSO's message to the generic one.
5. **`/invite/[token]`'s frontend form always demands full_name+password**, even though the
   backend supports an invite being accepted by a user whose account already exists (no
   name/password needed then) — the current UI has no code path for that branch at all.
   Fixed in the invitation-flow slice per the brief's own required "sign in when an account
   already exists" state.
6. **`/mfa-challenge` doesn't verify a challenge is actually pending** before rendering —
   low-severity (submitting without a pending challenge just 401s), but worth a guard for a
   cleaner error state rather than a confusing generic failure.

None of items 1–3 are bugs in the strict sense — they're real, disclosed absences this
effort is scoped to build. Items 4–6 are genuine, narrow defects fixed alongside the
redesign, each called out in its own commit rather than silently folded in.
