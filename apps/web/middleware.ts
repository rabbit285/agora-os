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
    "/((?!_next/static|_next/image|_next/data|favicon.ico|icon|apple-icon|opengraph-image|sitemap.xml|robots.txt|api/).*)",
  ],
};
