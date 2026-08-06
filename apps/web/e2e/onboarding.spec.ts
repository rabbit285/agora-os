import { expect, test } from "@playwright/test";

import { signup } from "./helpers";

test("a new organization can walk the full 9-screen onboarding wizard end to end", async ({ page }) => {
  await signup(page, "onboarding-full");

  // Screen 1 — Company
  await page.getByLabel("Industry").fill("Software");
  await page.getByRole("button", { name: "Continue" }).click();

  // Screen 2 — Goals (spec §68 step 3)
  await page.getByLabel("Improve compliance").check();
  await page.getByLabel("Automate customer support").check();
  await page.getByRole("button", { name: "Continue" }).click();

  // Screen 3 — Compliance profile (real frameworks fetched from the API)
  const firstFrameworkCheckbox = page.locator('input[type="checkbox"]').first();
  await firstFrameworkCheckbox.check();
  await page.getByRole("button", { name: "Continue" }).click();

  // Screen 4 — Security profile
  await page.getByRole("combobox").selectOption("aws");
  await page.getByRole("button", { name: "Continue" }).click();

  // Screen 5 — Sales profile
  await page.getByPlaceholder("e.g. Enterprise SaaS accounts in Europe").fill("Mid-market fintech");
  await page.getByRole("button", { name: "Continue" }).click();

  // Screen 6 — Support profile
  await page.getByLabel("email").check();
  await page.getByRole("button", { name: "Continue" }).click();

  // Screen 7 — Connect tools (pass-through, skippable)
  await page.getByRole("button", { name: "Configure later" }).click();

  // Screen 8 — Upload knowledge (pass-through, skippable)
  await page.getByRole("button", { name: "Configure later" }).click();

  // Screen 9 — real, live-computed Business AI Readiness (spec §68 step 10)
  await expect(page.getByText("Your Business AI Readiness")).toBeVisible();
  await page.getByRole("button", { name: "Open Business Command Center" }).click();
  await expect(page).toHaveURL("/dashboard");
});

test("onboarding progress survives a reload (resumable, spec §68)", async ({ page }) => {
  await signup(page, "onboarding-resume");
  await page.getByLabel("Industry").fill("Retail");
  await page.getByRole("button", { name: "Continue" }).click();

  await page.reload();

  // Should resume on the Goals screen (step 2), not restart at Company.
  await expect(page.getByLabel("Improve compliance")).toBeVisible();
});
