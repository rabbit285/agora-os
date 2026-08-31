import { expect, test } from "@playwright/test";

import { signup } from "./helpers";

/**
 * The controls list has to stay a list.
 *
 * It was a stack of cards positioning "EVIDENCE COVERAGE" and "STATUS"
 * wherever each row's content happened to end, with the captions repeated
 * on every one. Nothing lined up, the labels were louder than the values,
 * and a reader scanning twenty controls for the two that needed them had
 * to read every card.
 *
 * These run against the real dev stack — real signup, real API, real
 * layout — because alignment is exactly the kind of thing a jsdom test
 * cannot see. `boundingBox()` is the assertion: columns either share an
 * x-coordinate or they do not.
 */
const VIEWPORTS = [
  { name: "1440px", width: 1440, height: 900 },
  { name: "1280px", width: 1280, height: 800 },
  { name: "1024px", width: 1024, height: 768 },
  { name: "768px", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
];

test.describe("controls list layout", () => {
  test("aligns its columns and never overflows horizontally", async ({ page }) => {
    await signup(page, "controls-layout");

    // Adopt a framework so there are controls to lay out. Done through
    // the API the app itself uses, not by clicking through onboarding.
    await page.goto("/compliance/frameworks");
    const frameworks = await page.evaluate(async () => {
      const response = await fetch("http://localhost:8001/api/v1/compliance/frameworks", {
        credentials: "include",
      });
      return (await response.json()) as { id: string; key: string }[];
    });
    const gdpr = frameworks.find((framework) => framework.key === "gdpr");
    expect(gdpr).toBeTruthy();
    await page.evaluate(async (id) => {
      await fetch(
        `http://localhost:8001/api/v1/compliance/frameworks/${id}/activation`,
        {
          method: "PUT",
          credentials: "include",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ active: true }),
        }
      );
    }, gdpr!.id);

    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto("/compliance/controls");

      const rows = page.locator("ul > li > a");
      await expect(rows.first()).toBeVisible({ timeout: 30_000 });
      const count = await rows.count();
      expect(count, `${viewport.name}: no control rows rendered`).toBeGreaterThan(3);

      // Nothing may push the page sideways.
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      );
      expect(overflow, `${viewport.name}: horizontal overflow`).toBeLessThanOrEqual(1);

      const isDesktop = viewport.width >= 768;

      // Status badges share a left edge on desktop, because the grid
      // gives the column a fixed width rather than letting each badge's
      // own width decide where it starts.
      const badgeXs: number[] = [];
      const barWidths: number[] = [];
      for (let index = 0; index < Math.min(count, 8); index++) {
        const row = rows.nth(index);

        const badge = row.locator("span").filter({ hasText: /^\S/ }).last();
        const bar = row.getByRole("progressbar").first();

        if (await bar.isVisible()) {
          const box = await bar.boundingBox();
          if (box) barWidths.push(Math.round(box.width));
        }

        const box = await badge.boundingBox();
        if (box) badgeXs.push(Math.round(box.x));
      }

      if (isDesktop && badgeXs.length > 2) {
        const spread = Math.max(...badgeXs) - Math.min(...badgeXs);
        expect(spread, `${viewport.name}: status column not aligned`).toBeLessThanOrEqual(2);
      }

      // Progress bars are one consistent width, not sized by content.
      if (barWidths.length > 1) {
        const spread = Math.max(...barWidths) - Math.min(...barWidths);
        expect(spread, `${viewport.name}: coverage bars inconsistent`).toBeLessThanOrEqual(2);
        expect(
          Math.max(...barWidths),
          `${viewport.name}: coverage bar too small to read`
        ).toBeGreaterThanOrEqual(80);
      }
    }
  });

  test("puts the controls that need action first", async ({ page }) => {
    await signup(page, "controls-order");

    await page.goto("/compliance/frameworks");
    const frameworks = await page.evaluate(async () => {
      const response = await fetch("http://localhost:8001/api/v1/compliance/frameworks", {
        credentials: "include",
      });
      return (await response.json()) as { id: string; key: string }[];
    });
    await page.evaluate(async (id) => {
      await fetch(
        `http://localhost:8001/api/v1/compliance/frameworks/${id}/activation`,
        {
          method: "PUT",
          credentials: "include",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ active: true }),
        }
      );
    }, frameworks.find((framework) => framework.key === "gdpr")!.id);

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/compliance/controls");
    await expect(page.locator("ul > li > a").first()).toBeVisible({ timeout: 30_000 });

    // A page that opens on "Not applicable" makes the reader hunt for
    // the problems.
    const statuses = await page.locator("ul > li > a").allInnerTexts();
    const firstNotApplicable = statuses.findIndex((text) =>
      text.includes("Not applicable")
    );
    const lastNeedsWork = statuses.reduce(
      (last, text, index) =>
        /No evidence|Evidence insufficient|Partially evidenced/.test(text) ? index : last,
      -1
    );
    if (firstNotApplicable >= 0 && lastNeedsWork >= 0) {
      expect(
        lastNeedsWork,
        "controls needing action must sort above not-applicable ones"
      ).toBeLessThan(firstNotApplicable);
    }
  });
});
