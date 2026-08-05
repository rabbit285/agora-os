/** Documented instrumentation hooks, not a third-party analytics
 * integration — no privacy-approved analytics provider exists in this
 * codebase today (docs/PUBLIC_SITE_AUDIT.md §5), and this effort doesn't
 * add one on its own initiative (per its own brief). track() is a real
 * no-op in production: no network call, nothing leaves the browser. Every
 * call site funnels through this one function so that wiring a real,
 * chosen provider later is a one-file change, and so no event payload can
 * ever accidentally carry an email address or other personal data — keep
 * props to plan keys, page names, and booleans, never raw form values. */

export type MarketingEvent =
  | "homepage_cta_clicked"
  | "pricing_viewed"
  | "signup_started"
  | "signup_completed"
  | "login_completed"
  | "demo_request_submitted";

export function track(event: MarketingEvent, props?: Record<string, string | number | boolean>): void {
  if (process.env.NODE_ENV !== "production") {
    console.debug("[analytics]", event, props ?? {});
  }
}
