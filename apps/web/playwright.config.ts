import { defineConfig, devices } from "@playwright/test";

// Real E2E suite against the actual running dev stack (docker-compose)
// — no mocked API, no fixture server. PLAYWRIGHT_BASE_URL lets CI point
// this at a different host/port than local dev's 3001 without editing
// this file.
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3001";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // each spec signs up its own org, but shares no state that requires isolation beyond that
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Always serial: the target is a single `next dev` process, not a
  // production build. Concurrent workers race page compilation/hydration
  // against each other — under load a click can fire before React attaches
  // its handlers, so the browser falls through to a native form submit
  // (observed as signup landing on "/signup?field=value&..." instead of
  // "/onboarding"). Not a real app bug, just dev-server contention.
  workers: 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  // The dev stack's web container runs `next dev`, which JIT-compiles
  // each route on its first visit — a cold first hit to a heavy page
  // (e.g. /onboarding) can take longer than a typical E2E timeout.
  // Generous here rather than flaky; a production `next build` target
  // wouldn't need this.
  timeout: 60_000,
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
