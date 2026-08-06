import { execSync } from "node:child_process";

import { expect, type Page } from "@playwright/test";

// The FastAPI backend, not the Next.js dev server `page.request` inherits
// its baseURL from — a request to a *relative* /api/v1/... path would hit
// the web container's own (nonexistent) route and get its HTML 404 page
// back instead of JSON. Same host-mapped port apps/web/lib/api.ts's
// NEXT_PUBLIC_API_URL points the browser's own fetch calls at.
export const API_BASE_URL = process.env.PLAYWRIGHT_API_BASE_URL ?? "http://localhost:8001";

export type SignedUpOrg = {
  email: string;
  password: string;
  fullName: string;
  organizationName: string;
};

/** Real signup through the actual UI form against the real running API —
 * every E2E spec gets its own fresh, disposable organization so tests
 * never interfere with each other or with seeded demo data. */
export async function signup(page: Page, label: string): Promise<SignedUpOrg> {
  const unique = `${label}-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
  const org: SignedUpOrg = {
    email: `${unique}@example.com`,
    password: "CorrectHorseBattery9!",
    fullName: `${label} Tester`,
    organizationName: `${label} Org ${unique}`,
  };

  await page.goto("/signup");
  await page.getByLabel("Full name").fill(org.fullName);
  await page.getByLabel("Work email").fill(org.email);
  await page.getByLabel("Organization name").fill(org.organizationName);
  await page.getByLabel("Password", { exact: true }).fill(org.password);
  await page.getByLabel("Confirm password").fill(org.password);
  await page.getByRole("checkbox", { name: /Terms of Service/ }).check();
  await page.getByRole("button", { name: "Start free" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  return org;
}

export async function login(page: Page, org: Pick<SignedUpOrg, "email" | "password">): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(org.email);
  await page.getByLabel("Password", { exact: true }).fill(org.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/dashboard");
}

/** Log out is a menu item inside the top-nav user menu, not a standalone
 * button — open the menu first. */
export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "User menu" }).click();
  await page.getByRole("menuitem", { name: "Log out" }).click();
}

/** No real email provider is configured in this environment (spec —
 * see docs/KNOWN_LIMITATIONS.md), so every transactional link
 * (invitation, email verification, password reset) is logged rather
 * than emailed — the same real docker-compose stack the whole E2E suite
 * already runs against (project name "agora-origin",
 * infra/docker/docker-compose.yml) is where that log line actually
 * lands, both locally and in CI. This reads it back rather than mocking
 * the email step. Shared by getLatestInvitationUrl/VerificationUrl/
 * PasswordResetUrl below. */
async function getLatestLoggedUrl(
  logMarker: string,
  urlPathPrefix: string,
  identifyingText: string,
): Promise<string> {
  // The container's log driver can lag a moment behind the HTTP response
  // that triggered it — poll briefly rather than assuming the line is
  // already flushed the instant the request resolves.
  for (let attempt = 0; attempt < 20; attempt++) {
    // uvicorn/Python's logging module writes to stderr, not stdout —
    // execSync only captures stdout by default, so merge streams at the
    // shell level or the log line (and everything else) is silently
    // invisible to this process despite `docker logs` showing it fine in
    // an interactive terminal (which displays both).
    const logs = execSync("docker logs agora-origin-api-1 --tail 3000 2>&1", { encoding: "utf-8" });
    const matchingLines = logs
      .split("\n")
      .filter((line) => line.includes(logMarker) && line.includes(identifyingText));
    const lastLine = matchingLines[matchingLines.length - 1];
    if (lastLine) {
      const match = lastLine.match(new RegExp(`(https?://\\S+${urlPathPrefix}\\S+)`));
      if (!match) {
        throw new Error(`Could not parse a ${urlPathPrefix} URL out of log line: ${lastLine}`);
      }
      return match[1];
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`No "${logMarker}" log line found for ${identifyingText} in the api container's logs`);
}

export async function getLatestInvitationUrl(email: string): Promise<string> {
  return getLatestLoggedUrl("Invitation to join", "/invite/", email);
}

export async function getLatestVerificationUrl(email: string): Promise<string> {
  return getLatestLoggedUrl("Email verification requested for", "/verify-email/", email);
}

export async function getLatestPasswordResetUrl(email: string): Promise<string> {
  return getLatestLoggedUrl("Password reset requested for", "/reset-password/", email);
}
