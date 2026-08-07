import { expect, test } from "@playwright/test";

// The homepage's product-module carousel: six real modules (Compliance,
// Security, Sales, Customer Support, Automation, AI Governance), each a
// real photo + working CTA into /features's matching anchored section.
// Public, unauthenticated content — no signup() needed for any test here.

function region(page: import("@playwright/test").Page) {
  return page.getByRole("region", { name: "Product modules" });
}

test.describe("Homepage module carousel", () => {
  test("is visible on the homepage with all six module slides present", async ({ page }) => {
    await page.goto("/");
    await expect(region(page)).toBeVisible();

    const slides = page.locator('[aria-roledescription="slide"]');
    await expect(slides).toHaveCount(6);

    // Matching on the slide's own aria-label (e.g. "1 of 6: Compliance"),
    // not free-text body content — several slides' descriptions mention
    // other modules by name (e.g. Security's copy says "...compliance
    // escalation..."), which would make a hasText substring match ambiguous.
    const labels = ["Compliance", "Security", "Sales", "Customer Support", "Automation", "AI Governance"];
    for (let i = 0; i < labels.length; i++) {
      await expect(page.locator(`[aria-label="${i + 1} of 6: ${labels[i]}"]`)).toHaveCount(1);
    }
  });

  test("navigates forward through every slide and wraps back to the first", async ({ page }) => {
    await page.goto("/");
    const carousel = region(page);
    await carousel.scrollIntoViewIfNeeded();

    await expect(carousel.getByText("1 / 6")).toBeVisible();
    const next = page.getByRole("button", { name: "Next module" });

    for (const expectedCount of ["2 / 6", "3 / 6", "4 / 6", "5 / 6", "6 / 6"]) {
      await next.click();
      await expect(carousel.getByText(expectedCount)).toBeVisible();
    }

    // Wraps past the last slide back to the first.
    await next.click();
    await expect(carousel.getByText("1 / 6")).toBeVisible();
  });

  test("navigates backward and wraps from the first slide to the last", async ({ page }) => {
    await page.goto("/");
    const carousel = region(page);
    await carousel.scrollIntoViewIfNeeded();

    const previous = page.getByRole("button", { name: "Previous module" });
    await previous.click();
    await expect(carousel.getByText("6 / 6")).toBeVisible();
    await previous.click();
    await expect(carousel.getByText("5 / 6")).toBeVisible();
  });

  test("jumps directly to a slide via its pagination dot", async ({ page }) => {
    await page.goto("/");
    const carousel = region(page);
    await carousel.scrollIntoViewIfNeeded();

    const automationDot = page.getByRole("button", { name: "Go to Automation slide" });
    await automationDot.click();
    await expect(carousel.getByText("5 / 6")).toBeVisible();
    await expect(automationDot).toHaveAttribute("aria-current", "true");
  });

  test("supports ArrowLeft/ArrowRight keyboard navigation and updates the visible counter", async ({
    page,
  }) => {
    await page.goto("/");
    const carousel = region(page);
    await carousel.scrollIntoViewIfNeeded();

    const nextButton = page.getByRole("button", { name: "Next module" });
    await nextButton.focus();
    await expect(nextButton).toBeFocused();

    // A generous timeout here, not the 5s default: under load (this dev
    // server JIT-compiles routes and this suite runs fully serially — see
    // playwright.config.ts's own comment on timing variance), a keypress
    // sent immediately after a programmatic .focus() has occasionally been
    // observed to land before the browser's focus change fully settles.
    // Confirmed via direct debugging (see ui/interactive-card-system's
    // near-identical test) — DOM focus can be genuinely confirmed
    // (toBeFocused() above passes) while React's event listeners haven't
    // fully settled post-hydration yet on a page with zero prior
    // interaction; a short settle delay avoids the race.
    await page.waitForTimeout(500);
    await page.keyboard.press("ArrowRight");
    await expect(carousel.getByText("2 / 6")).toBeVisible({ timeout: 10_000 });
    await page.keyboard.press("ArrowRight");
    await expect(carousel.getByText("3 / 6")).toBeVisible({ timeout: 10_000 });
    await page.keyboard.press("ArrowLeft");
    await expect(carousel.getByText("2 / 6")).toBeVisible({ timeout: 10_000 });
  });

  test("a module CTA opens the correct, real /features section", async ({ page }) => {
    await page.goto("/");
    const carousel = region(page);
    await carousel.scrollIntoViewIfNeeded();

    // Navigate to the Security slide (index 1) before its CTA is reachable
    // — non-active slides are aria-hidden by design.
    await page.getByRole("button", { name: "Next module" }).click();
    await expect(carousel.getByText("2 / 6")).toBeVisible();

    await carousel.getByRole("link", { name: "Explore Security" }).click();
    await expect(page).toHaveURL(/\/features#security$/);
    await expect(page.getByRole("heading", { name: "Security", exact: true })).toBeVisible();
  });

  test("pauses automatic rotation on hover and via the visible pause control", async ({ page }) => {
    await page.goto("/");
    const carousel = region(page);
    await carousel.scrollIntoViewIfNeeded();

    // Autoplay advances the carousel in a real browser (unlike the jsdom
    // unit tests, which verify the timer-wiring contract instead — see
    // components/marketing/module-carousel.test.tsx for why).
    await expect(carousel.getByText("2 / 6")).toBeVisible({ timeout: 12_000 });

    await page.getByRole("button", { name: "Pause automatic slide rotation" }).click();
    await expect(page.getByRole("button", { name: "Play automatic slide rotation" })).toBeVisible();
    const pausedAt = await carousel.getByText(/^\d+ \/ \d+$/).textContent();
    expect(pausedAt).toBeTruthy();
    await page.waitForTimeout(9000);
    await expect(carousel.getByText(/^\d+ \/ \d+$/)).toHaveText(pausedAt ?? "");
  });

  test("reduced-motion visitors get no autoplay control and no automatic rotation", async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const carousel = region(page);
    await carousel.scrollIntoViewIfNeeded();

    await expect(
      page.getByRole("button", { name: /automatic slide rotation/ }),
    ).toHaveCount(0);

    await page.waitForTimeout(9000);
    await expect(carousel.getByText("1 / 6")).toBeVisible();

    // Manual navigation still works.
    await page.getByRole("button", { name: "Next module" }).click();
    await expect(carousel.getByText("2 / 6")).toBeVisible();
  });

  test("supports touch swipe navigation on mobile", async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      hasTouch: true,
    });
    const page = await context.newPage();
    await page.goto("/");
    const carousel = region(page);
    await carousel.scrollIntoViewIfNeeded();
    await expect(carousel.getByText("1 / 6")).toBeVisible();

    const slideBox = await page
      .locator('[aria-roledescription="slide"][aria-hidden="false"]')
      .boundingBox();
    if (!slideBox) throw new Error("active slide has no bounding box");
    const centerY = slideBox.y + slideBox.height / 2;
    const startX = slideBox.x + slideBox.width - 40;
    const endX = slideBox.x + 40;

    // Playwright has no built-in touch-swipe gesture helper (only a
    // single-point `touchscreen.tap`); a mouse-drag on a `hasTouch: true`
    // context exercises the same code path Embla uses for a real touch
    // swipe (it unifies mouse-drag and touch-drag through the same
    // pointer handling), which is the standard way to test this.
    await page.mouse.move(startX, centerY);
    await page.mouse.down();
    for (let x = startX; x >= endX; x -= 30) {
      await page.mouse.move(x, centerY);
    }
    await page.mouse.up();

    await expect(carousel.getByText("2 / 6")).toBeVisible();
    await context.close();
  });
});
