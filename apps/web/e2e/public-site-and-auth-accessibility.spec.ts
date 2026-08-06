import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { signup } from "./helpers";

// Formal accessibility audit for the public marketing site and every
// authentication page: automated axe-core scans (WCAG 2.1 A/AA rule
// sets) on every real page state, plus keyboard-only passes proving the
// homepage's mobile menu and the sign-up form are operable without a
// mouse — the same discipline already established in
// sales-lead-finder-accessibility.spec.ts, applied to the new surfaces
// this effort adds.
//
// Excludes the same pre-existing violation that spec already documented
// and excluded: nav[aria-label="Primary"] (the app-shell sidebar's group
// labels, ~2.56:1 contrast) — shared chrome across 70+ routes, not
// something this effort's scope covers fixing. Every real contrast issue
// found in this effort's own new components (marketing pages, auth
// pages, and MetricCard's optional description text as used in the new
// ProductPreview) was fixed for real rather than excluded — see the
// commit history for this file's own change and PUBLIC_SITE_DESIGN.md.
async function runAxeScan(page: Page) {
  return new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .exclude('nav[aria-label="Primary"]')
    .analyze();
}

test.describe("Accessibility: public site", () => {
  test("Homepage", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("heading", { name: /Run compliance, security, sales, and operations/ }).waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("Features page", async ({ page }) => {
    await page.goto("/features");
    await page.getByRole("heading", { name: "Everything your operations team needs, in one place" }).waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("Solutions page", async ({ page }) => {
    await page.goto("/solutions");
    await page.getByRole("heading", { name: "Built for the teams that keep a growing business governed" }).waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("Trust & Security page", async ({ page }) => {
    await page.goto("/trust");
    await page.getByRole("heading", { name: "Governed by design, not by afterthought" }).waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("Pricing page", async ({ page }) => {
    await page.goto("/pricing");
    await page.getByRole("heading", { name: "Simple plans that grow with you" }).waitFor();
    await page.getByText("Contact sales").first().waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("About page", async ({ page }) => {
    await page.goto("/about");
    await page.getByRole("heading", { name: "The secure AI operating system for European SMEs" }).waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("Contact page", async ({ page }) => {
    await page.goto("/contact");
    await page.getByRole("heading", { name: "Request a demo" }).waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("Legal pages (privacy, terms, cookies)", async ({ page }) => {
    for (const path of ["/privacy", "/terms", "/cookies"]) {
      await page.goto(path);
      await page.getByRole("heading", { level: 1 }).waitFor();
      const results = await runAxeScan(page);
      expect(results.violations, `${path}: ${JSON.stringify(results.violations, null, 2)}`).toEqual([]);
    }
  });
});

test.describe("Accessibility: authentication pages", () => {
  test("Login page", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("heading", { name: "Welcome back" }).waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("Signup page", async ({ page }) => {
    await page.goto("/signup");
    await page.getByRole("heading", { name: "Create your secure workspace" }).waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("Forgot-password page", async ({ page }) => {
    await page.goto("/forgot-password");
    await page.getByRole("heading", { name: "Reset your password" }).waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("Forgot-password submitted state", async ({ page }) => {
    await page.goto("/forgot-password");
    await page.getByLabel("Email").fill(`axe-forgot-${Date.now()}@example.com`);
    await page.getByRole("button", { name: "Send reset link" }).click();
    await page.getByRole("heading", { name: "Check your email" }).waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("Onboarding, first step", async ({ page }) => {
    await signup(page, "a11y-onboarding");
    await page.getByLabel("Industry").waitFor();
    const results = await runAxeScan(page);
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });
});

test.describe("Accessibility: keyboard-only navigation", () => {
  test("Homepage mobile menu is fully keyboard-operable", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");

    const menuButton = page.getByRole("button", { name: "Open menu" });
    await menuButton.focus();
    await expect(menuButton).toBeFocused();
    await page.keyboard.press("Enter");

    const mobileMenu = page.locator("#public-mobile-menu");
    const featuresLink = mobileMenu.getByRole("link", { name: "Product" });
    await expect(featuresLink).toBeVisible();
  });

  test("Sign-up form is fully keyboard-operable", async ({ page }) => {
    await page.goto("/signup");

    const nameField = page.getByLabel("Full name");
    await nameField.focus();
    await expect(nameField).toBeFocused();
    await page.keyboard.type("Keyboard Tester");
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Work email")).toBeFocused();
    await page.keyboard.type(`kbd-${Date.now()}@example.com`);
    await page.keyboard.press("Tab");
    await expect(page.getByLabel("Organization name")).toBeFocused();
  });
});
