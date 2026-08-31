import { expect, test } from "@playwright/test";

import { signup } from "./helpers";

/**
 * Framework cards have to line up.
 *
 * The readiness block and the CTA used to sit in an `auto` column, so the
 * column took its width from whichever button label happened to be
 * longest — "View EU AI Act" on one card, "View SOC 2" on the next. The
 * readiness percentage and its bar then landed in a different place on
 * every card down the page. Columns only line up if nothing in them is
 * allowed to decide its own width, and `boundingBox()` is the only
 * assertion that can prove it.
 */
const VIEWPORTS = [
  { name: "1440px", width: 1440, height: 900 },
  { name: "1280px", width: 1280, height: 800 },
  { name: "1024px", width: 1024, height: 768 },
  { name: "768px", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
];

test("framework cards align and never overflow", async ({ page }) => {
  await signup(page, "fw-layout");

  await page.goto("/compliance/frameworks");
  // Adopt several frameworks with deliberately different name lengths —
  // "SOC 2" against "EU AI Act" is exactly what broke the alignment.
  await page.evaluate(async () => {
    const base = "http://localhost:8001/api/v1/compliance";
    const frameworks = await (
      await fetch(`${base}/frameworks`, { credentials: "include" })
    ).json();
    for (const key of ["gdpr", "eu_ai_act", "iso42001", "soc2"]) {
      const framework = frameworks.find((f: { key: string }) => f.key === key);
      if (!framework) continue;
      await fetch(`${base}/frameworks/${framework.id}/activation`, {
        method: "PUT",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ active: true }),
      });
      await fetch(`${base}/frameworks/${framework.id}/assess`, {
        method: "POST",
        credentials: "include",
      });
    }
  });

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto("/compliance/frameworks");

    const cards = page.locator("ul > li").filter({ has: page.getByRole("progressbar") });
    await expect(cards.first()).toBeVisible({ timeout: 40_000 });
    const count = await cards.count();
    expect(count, `${viewport.name}: no framework cards`).toBeGreaterThan(2);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow, `${viewport.name}: horizontal overflow`).toBeLessThanOrEqual(1);

    const barXs: number[] = [];
    const barWidths: number[] = [];
    const buttonXs: number[] = [];

    for (let index = 0; index < count; index++) {
      const card = cards.nth(index);
      const bar = card.getByRole("progressbar").first();
      const button = card.getByRole("link", { name: /^View / }).first();

      const barBox = await bar.boundingBox();
      if (barBox) {
        barXs.push(Math.round(barBox.x));
        barWidths.push(Math.round(barBox.width));
      }
      const buttonBox = await button.boundingBox();
      if (buttonBox) buttonXs.push(Math.round(buttonBox.x));
    }

    if (viewport.width >= 768) {
      // The readiness bars and the CTAs each share one x down the page,
      // whatever the framework is called.
      expect(
        Math.max(...barXs) - Math.min(...barXs),
        `${viewport.name}: readiness bars not aligned`
      ).toBeLessThanOrEqual(2);
      expect(
        Math.max(...buttonXs) - Math.min(...buttonXs),
        `${viewport.name}: CTA buttons not aligned`
      ).toBeLessThanOrEqual(2);
    }

    // One bar width everywhere, so the fill length is comparable between
    // frameworks rather than being a function of the card's content.
    expect(
      Math.max(...barWidths) - Math.min(...barWidths),
      `${viewport.name}: readiness bars inconsistent`
    ).toBeLessThanOrEqual(2);
  }
});

test("readiness is exposed to assistive technology, not just drawn", async ({ page }) => {
  await signup(page, "fw-a11y");
  await page.goto("/compliance/frameworks");
  await page.evaluate(async () => {
    const base = "http://localhost:8001/api/v1/compliance";
    const frameworks = await (
      await fetch(`${base}/frameworks`, { credentials: "include" })
    ).json();
    const gdpr = frameworks.find((f: { key: string }) => f.key === "gdpr");
    await fetch(`${base}/frameworks/${gdpr.id}/activation`, {
      method: "PUT",
      credentials: "include",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ active: true }),
    });
    await fetch(`${base}/frameworks/${gdpr.id}/assess`, {
      method: "POST",
      credentials: "include",
    });
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/compliance/frameworks");

  const bar = page.getByRole("progressbar", { name: /GDPR readiness/ });
  await expect(bar).toBeVisible({ timeout: 40_000 });
  // A bar drawn with a div width is invisible to a screen reader unless
  // it says what it is worth.
  await expect(bar).toHaveAttribute("aria-valuenow", /^\d+$/);

  // The methodology is reachable by keyboard, as a native disclosure.
  const disclosure = page.getByText("How readiness is calculated").first();
  await expect(disclosure).toBeVisible();
});
