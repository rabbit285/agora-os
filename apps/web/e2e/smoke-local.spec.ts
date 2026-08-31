import { expect, test } from "@playwright/test";

import { signup } from "./helpers";

/** Does the product actually work when you open it?
 *
 * Not a feature test — a walk through the screens a new customer meets
 * in their first minute, with a screenshot of each. Its job is to catch
 * the failures that never reach a unit test: a page that renders blank,
 * a nav link into a 404, a dashboard that throws on an organization with
 * no data yet.
 */

const SHOTS = "test-results/local-smoke";

test("a new organization can walk the product", async ({ page }) => {
  test.slow();

  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`${error.name}: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });

  await signup(page, "smoke");
  await expect(page).toHaveURL(/\/onboarding/);
  await page.screenshot({ path: `${SHOTS}/01-onboarding.png`, fullPage: true });

  // The screens a customer reaches from the sidebar. Each has to render
  // something for an organization that has just been created and has no
  // data at all — the state every trial account is in.
  // The sidebar label, not the page heading — a screen is free to call
  // itself something better than its nav entry ("Dashboard" opens
  // "Compliance Overview"), and pinning the heading text here would be
  // asserting my guess about the copy rather than that the page works.
  const screens: Array<[string, string]> = [
    ["dashboard", "/dashboard"],
    ["review-center", "/review"],
    ["copilot", "/copilot"],
    ["documents", "/documents"],
    ["policies", "/compliance/policies"],
    ["ai-systems", "/ai-systems"],
    ["frameworks", "/compliance/frameworks"],
    ["controls", "/compliance/controls"],
    ["audit-logs", "/settings/audit-logs"],
  ];

  for (const [name, path] of screens) {
    await page.goto(path);

    // Content of its own, not just a 200: a blank page and a rendered
    // page are the same status code, and the shell renders either way.
    const main = page.locator("#main-content, main").first();
    await expect(main, `${path} should render`).toBeVisible({ timeout: 20_000 });
    await expect(
      main.getByRole("heading").first(),
      `${path} should have a heading of its own`,
    ).toBeVisible({ timeout: 20_000 });

    // Not the withdrawn-module 404, and not an error boundary.
    await expect(page.getByText(/isn't part of Veyntra/i)).toHaveCount(0);
    await expect(page.getByText(/something went wrong|unhandled|500/i)).toHaveCount(0);

    // Still where we asked to be — no silent redirect to /login or /not-found.
    expect(new URL(page.url()).pathname, `${path} should not redirect`).toBe(path);

    await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
  }

  // Uncaught exceptions anywhere in that walk are a failure even when
  // every assertion above passed — a page can render and still be broken.
  const real = errors.filter(
    (message) =>
      !/favicon|ResizeObserver|Download the React DevTools|hydrat/i.test(message),
  );
  expect(real, `console/page errors:\n${real.join("\n")}`).toEqual([]);
});
