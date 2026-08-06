/** The single gate every `?redirect=` value must pass before it's ever
 * used for navigation — by both middleware.ts (bouncing an unauthenticated
 * visitor back after login) and the login/MFA-challenge pages that read
 * the query param back out. This is the one piece of new logic in this
 * whole effort with a real open-redirect consequence if it's wrong
 * (docs/PUBLIC_SITE_DESIGN.md §3), so it lives in one place with its own
 * dedicated tests rather than being inlined per call site. */
export function isSafeRedirectTarget(target: string | null | undefined): target is string {
  if (!target) return false;
  // Must be a same-origin, absolute path.
  if (!target.startsWith("/")) return false;
  // "//evil.com" is protocol-relative — the browser treats it as an
  // absolute URL to a different origin, not a path.
  if (target.startsWith("//")) return false;
  // "/\evil.com" — some browsers normalize a leading backslash to a
  // forward slash, turning this into the same protocol-relative case.
  if (target.startsWith("/\\")) return false;
  // Rejects an absolute URL smuggled in after the leading slash, e.g.
  // "/https://evil.com" being naively concatenated onto this origin
  // downstream, or a "javascript:" URI.
  if (target.includes("://")) return false;
  return true;
}
