import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";

// The shared InteractiveCard hover/focus/press/selected system
// (components/marketing/interactive-card.tsx), applied to the homepage
// module carousel and module-overview cards. See
// docs/PUBLIC_SITE_DESIGN.md §12 for the full design.
//
// Module-overview card queries are scoped to the "Platform modules"
// landmark (module-overview.tsx's own aria-label) — an unscoped
// getByRole("link", { name: /^Security/ }) is ambiguous: the top nav
// also has a real "Security" link (to /trust), and would otherwise match
// both.
//
// Tailwind v4 compiles scale-[...]/translate-y-[...] utilities to the
// standalone CSS `scale`/`translate` properties, not a composed legacy
// `transform` string — so assertions read those two properties directly
// rather than `getComputedStyle(el).transform`, which never changes.

function platformModules(page: Page) {
  return page.getByRole("region", { name: "Platform modules" });
}

async function motionState(locator: Locator) {
  return locator.evaluate((el) => {
    const s = getComputedStyle(el);
    return { scale: s.scale, translate: s.translate, boxShadow: s.boxShadow, borderColor: s.borderColor };
  });
}

test.describe("Interactive card system", () => {
  test("hovering a module-overview card grows it and gives it a real border/shadow shift", async ({
    page,
  }) => {
    await page.goto("/");
    const card = platformModules(page).getByRole("link", { name: /^Compliance/ });
    await card.scrollIntoViewIfNeeded();

    const before = await motionState(card);

    const box = await card.boundingBox();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.waitForTimeout(350);

    const after = await motionState(card);

    expect(after.scale).not.toBe(before.scale);
    expect(after.translate).not.toBe(before.translate);
    expect(after.boxShadow).not.toBe(before.boxShadow);
    expect(after.borderColor).not.toBe(before.borderColor);
  });

  test("keyboard focus on the same card produces equivalent feedback to hover", async ({ page }) => {
    await page.goto("/");
    const card = platformModules(page).getByRole("link", { name: /^Compliance/ });
    await card.scrollIntoViewIfNeeded();

    const unfocused = await motionState(card);
    // :focus-visible only reliably matches real keyboard-driven focus, not
    // a bare scripted .focus() call — Tab into it for a realistic check.
    let reached = false;
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press("Tab");
      if (await card.evaluate((el) => el === document.activeElement)) {
        reached = true;
        break;
      }
    }
    expect(reached, "Tabbed 40 times without reaching the Compliance card").toBe(true);
    await page.waitForTimeout(350);
    const focused = await motionState(card);

    expect(focused.scale).not.toBe(unfocused.scale);
    expect(focused.boxShadow).not.toBe(unfocused.boxShadow);
    await expect(card).toBeFocused();
  });

  test("activating a module-overview card with Enter navigates to its real /features section", async ({
    page,
  }) => {
    await page.goto("/");
    const card = platformModules(page).getByRole("link", { name: /^Security/ });
    await card.scrollIntoViewIfNeeded();
    await card.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/features#security$/);
    await expect(page.getByRole("heading", { name: "Security", exact: true })).toBeVisible();
  });

  test("selecting a neighboring carousel slide makes it visually and functionally dominant", async ({
    page,
  }) => {
    await page.goto("/");
    const carousel = page.getByRole("region", { name: "Product modules" });
    await carousel.scrollIntoViewIfNeeded();

    const activeBefore = page.locator('[aria-roledescription="slide"][aria-hidden="false"]');
    await expect(activeBefore).toContainText("Compliance");

    const neighborBefore = await motionState(page.locator('[aria-label="2 of 6: Security"] button'));

    // Non-active slides sit under an aria-hidden ancestor (see
    // module-carousel.tsx) — excluded from the a11y tree on purpose, but
    // still really there for a sighted mouse click; includeHidden finds
    // it the way a real mouse user would reach it.
    await page
      .getByRole("button", { name: "Show the Security module", includeHidden: true })
      .click();

    const activeAfter = page.locator('[aria-roledescription="slide"][aria-hidden="false"]');
    await expect(activeAfter).toContainText("Security");
    await expect(carousel.getByText("2 / 6")).toBeVisible();

    // The now-active slide's scale differs from what the same slide
    // measured while it was still an unselected, scaled-down neighbor.
    // The active slide's own InteractiveCard is a plain <div> (its CTA
    // <a> is nested inside it, not the card itself — only inactive
    // slides' whole card is the clickable element) — "> .group" matches
    // either shape via the class every InteractiveCard variant shares.
    const activeAfterState = await motionState(activeAfter.locator("> .group"));
    expect(activeAfterState.scale).not.toBe(neighborBefore.scale);
  });

  test("arrow-key navigation moves the selected carousel slide", async ({ page }) => {
    await page.goto("/");
    const carousel = page.getByRole("region", { name: "Product modules" });
    await carousel.scrollIntoViewIfNeeded();
    const nextButton = page.getByRole("button", { name: "Next module" });
    await nextButton.focus();
    // Confirms the focus change has actually settled before the keypress
    // — see e2e/homepage-module-carousel.spec.ts's identical precaution.
    await expect(nextButton).toBeFocused();
    // On a page that has had zero prior interaction (this test's first
    // and only action), a keypress immediately after .focus() has been
    // observed to fire before React's event listeners fully settle post-
    // hydration, even once DOM focus itself is confirmed — reproduced and
    // confirmed via direct debugging: identical Playwright automation
    // outside the test runner, and this same runner with an added delay,
    // both reliably worked. A short settle delay is the fix, not a
    // deeper one — the underlying feature works correctly either way.
    await page.waitForTimeout(500);
    await page.keyboard.press("ArrowRight");
    await expect(carousel.getByText("2 / 6")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator('[aria-roledescription="slide"][aria-hidden="false"]')).toContainText(
      "Security",
    );
  });

  test("reduced motion removes scale/translate but keeps the border/shadow state change", async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");
    const card = platformModules(page).getByRole("link", { name: /^Compliance/ });
    await card.scrollIntoViewIfNeeded();

    const before = await motionState(card);
    const box = await card.boundingBox();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await page.waitForTimeout(200);
    const after = await motionState(card);

    // motion-reduce: forces scale/translate back to their identity values
    // regardless of hover — browsers report "no movement" in a few
    // equivalent forms ("none" when the property was never set at all,
    // vs. an explicit zero value once a motion-reduce:*-0 utility
    // actively forces it), so any of these count as "did not move".
    const noScale = ["none", "100% 100%", "1 1", "1"];
    const noTranslate = ["none", "0px", "0px 0px", "0px 0px 0px"];
    expect(noScale).toContain(after.scale);
    expect(noTranslate).toContain(after.translate);
    // Border/shadow are still allowed (and expected) to change — only the
    // scale/translate *motion* is suppressed, per docs/PUBLIC_SITE_DESIGN.md §12.
    expect(after.boxShadow).not.toBe(before.boxShadow);
  });

  test("mobile: tapping the active carousel slide's CTA navigates exactly once", async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
    const page = await context.newPage();
    await page.goto("/");
    const carousel = page.getByRole("region", { name: "Product modules" });
    await carousel.scrollIntoViewIfNeeded();
    await carousel.getByRole("link", { name: /Explore Compliance/ }).tap();
    await expect(page).toHaveURL(/\/features#compliance$/);
    await context.close();
  });

  test("axe: homepage with a card hovered/focused has no new violations", async ({ page }) => {
    await page.goto("/");
    const card = platformModules(page).getByRole("link", { name: /^Compliance/ });
    await card.scrollIntoViewIfNeeded();
    await card.focus();
    await page.waitForTimeout(200);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .exclude('nav[aria-label="Primary"]')
      .analyze();
    expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
  });

  test("disabled/non-clickable cards are never given the interactive scale/translate treatment", async ({
    page,
  }) => {
    await page.goto("/pricing");
    await page.getByText("Contact sales").first().waitFor();
    // The pricing card itself has no href/onClick of its own (only its
    // nested CTA button does) — hovering it must not scale/translate it,
    // only the restrained border/shadow lift.
    const starterHeading = page.getByText("Starter", { exact: true });
    const box = await starterHeading.boundingBox();
    const card = starterHeading.locator("xpath=ancestor::*[contains(@class,'group')][1]");
    const before = await motionState(card);
    await page.mouse.move(box!.x + 20, box!.y + 10);
    await page.waitForTimeout(300);
    const after = await motionState(card);
    expect(after.scale).toBe(before.scale);
    expect(after.translate).toBe(before.translate);
  });
});
