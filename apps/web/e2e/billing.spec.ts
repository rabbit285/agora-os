import { expect, test } from "@playwright/test";

import { signup } from "./helpers";

/** Billing, driven through the real UI against the real API.
 *
 * The property worth guarding at this level is the one a unit test cannot
 * see: that a paid plan is never granted by anything the browser does. The
 * upgrade button must leave for Stripe, and the plan must not move.
 */
test.describe("Billing", () => {
  test("a new organization lands on a 14-day trial with no card", async ({ page }) => {
    await signup(page, "billing-trial");

    await page.goto("/settings/billing");

    await expect(page.getByText(/days left in your free trial/)).toBeVisible();
    await expect(page.getByText(/No card is on file/)).toBeVisible();
    await expect(page.getByText("Current plan:")).toContainText("Starter");
  });

  test("says so, rather than offering a dead end, when payments are not configured", async ({
    page,
  }) => {
    // This deployment has no STRIPE_SECRET_KEY. The interesting property
    // is that the UI admits it instead of presenting a button that would
    // fail — and that no paid plan becomes reachable as a result.
    await signup(page, "billing-upgrade");
    await page.goto("/settings/billing");

    await expect(page.getByText(/Online payment is not configured/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Upgrade to Growth" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Upgrade to Business" })).toBeDisabled();
    await expect(page.getByText("Current plan:")).toContainText("Starter");

    // Enterprise is never a button at all — it goes to sales.
    await expect(page.getByRole("link", { name: "Contact sales" })).toBeVisible();
  });

  // The lapsed-trial lock is not exercised here: expiring a trial needs a
  // 14-day wait or a direct database write, and inventing a test-only
  // endpoint to force it would add an unauthenticated plan-mutating route
  // to the API — exactly the kind of thing this feature exists to remove.
  // It is covered instead where the clock can be controlled honestly:
  // tests/test_billing.py (API) and settings/billing/page.test.tsx (UI).
});
