import { NextResponse, type NextRequest } from "next/server";

import { isSafeRedirectTarget } from "@/lib/auth-redirect";

// Mirrors settings.session_cookie_name's default in apps/api/app/config.py.
const SESSION_COOKIE_NAME = "agora_session";

// Every real public marketing route (docs/PUBLIC_SITE_DESIGN.md §2) —
// viewable regardless of auth state, no redirect either direction.
const PUBLIC_MARKETING_PATHS = new Set([
  "/",
  "/features",
  "/solutions",
  "/trust",
  "/pricing",
  "/about",
  "/contact",
  "/privacy",
  "/terms",
  "/cookies",
]);

// Bounce an already-authenticated visitor straight to their dashboard —
// there's no reason to show them the login/signup form again.
const AUTH_ONLY_PATHS = new Set(["/login", "/signup"]);

// Modules removed from the product. Prefix-matched, so every child route
// goes with the parent.
//
// Exported so tests can assert against the real list rather than a copy
// that drifts: a Copilot citation pointing at any of these renders as a
// working link and lands on a 404, which is precisely how citations went
// on opening `/knowledge/<id>` after that module was withdrawn. Mirrored
// server-side by RETIRED_ROUTE_PREFIXES in app/ai/citations.py, which
// composes the hrefs.
export const RETIRED_MODULE_PREFIXES = [
  "/sales",
  "/support",
  "/automation",
  "/knowledge",
  // /integrations is the compliance monitoring catalog and is part
  // of the product. The old /settings/integrations screen belonged to
  // the withdrawn module and stays gone.
  "/settings/integrations",
  "/recommendations",
  "/briefing",
  "/reports",
];

// Never redirected either direction: a signed-in user may legitimately
// need to reset a different password, verify a second email, accept an
// invitation into another organization, or complete a pending MFA
// challenge while already signed into an existing session.
const AUTH_NEUTRAL_PREFIXES = [
  "/forgot-password",
  "/reset-password",
  "/verify-email",
  "/invite",
  "/mfa-challenge",
];

/** This check is deliberately cookie-*presence*, not validity — an edge
 * round-trip to the database/API on every request would add real latency
 * to every page load. `AuthGuard` (apps/web/components/auth-guard.tsx)
 * remains the client-side check for a cookie that's present but
 * expired/revoked, and the API enforces real authorization on every
 * request regardless (docs/PUBLIC_SITE_DESIGN.md §3, §9) — this
 * middleware only closes the "visible flash before the client-side
 * redirect fires" and "authenticated user can still load /login" gaps
 * documented in docs/AUTH_UX_AUDIT.md §5, it is not the authorization
 * boundary. */
export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has(SESSION_COOKIE_NAME);

  if (PUBLIC_MARKETING_PATHS.has(pathname)) {
    return NextResponse.next();
  }

  if (AUTH_ONLY_PATHS.has(pathname)) {
    if (hasSession) {
      const requestedRedirect = request.nextUrl.searchParams.get("redirect");
      const destination = isSafeRedirectTarget(requestedRedirect) ? requestedRedirect : "/dashboard";
      return NextResponse.redirect(new URL(destination, request.url));
    }
    return NextResponse.next();
  }

  if (AUTH_NEUTRAL_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  // Veyntra ships as a compliance platform. These modules' code is still
  // in the repository — DSAR data discovery reads the sales and support
  // tables, because that is where personal data lives — but they are not
  // part of the product, so their screens must not be reachable. Rewritten
  // to a 404 rather than redirected: a stale bookmark should report that
  // the page does not exist, not silently land somewhere unrelated.
  if (RETIRED_MODULE_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.rewrite(new URL("/not-found", request.url));
  }

  // Everything else is an authenticated app route.
  if (!hasSession) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", pathname + request.nextUrl.search);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    // The trailing `|.*\..*` excludes any path whose last segment contains
    // a dot — every real Next.js *page* route is extensionless, so this
    // catches static files generically (images, fonts, manifests, etc.
    // under /public) without needing to name each one here. It's what
    // caught out the homepage module carousel's images (docs/RELEASE_CHECKLIST.md):
    // /images/modules/*.jpg fell through to "protected route" and 307'd to
    // /login, since nothing in the old list named /images specifically.
    "/((?!_next/static|_next/image|_next/data|favicon.ico|icon|apple-icon|opengraph-image|sitemap.xml|robots.txt|api/|.*\\..*).*)",
  ],
};
