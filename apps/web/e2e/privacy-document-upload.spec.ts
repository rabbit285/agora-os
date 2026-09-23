import path from "node:path";

import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** The reported bug, driven through the real UI with the real file.
 *
 * A privacy document was uploaded, analysed, indexed for the Copilot and
 * mapped to nine controls — while Privacy → Processing activities said
 * "Review suggestions (0)". Three things were wrong, and this exercises
 * all of them at once: the .docx parser dropped every table (where the
 * document's facts live), the domain filter compared "Privacy / GDPR"
 * for equality against "privacy", and the extractor only understood
 * labels the tables had been hiding.
 *
 * Uploaded through the browser, not seeded — the point is the pipeline.
 */
const DOCUMENT = path.join(
  __dirname,
  "fixtures",
  "Veyntra_Privacy_Test_AI_Customer_Support.docx",
);

test("an uploaded privacy document becomes a visible suggestion", async ({
  page,
}) => {
  test.slow();
  await signup(page, "docupload");

  await page.goto("/documents");
  await page.setInputFiles('input[type="file"]', DOCUMENT);

  // Analysis is the slow part: parse, classify, embed, map to controls.
  await expect(
    page.getByText("Veyntra_Privacy_Test_AI_Customer_Support.docx").first(),
  ).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("Analyzed").first()).toBeVisible({
    timeout: 240_000,
  });
  await page.screenshot({
    path: "test-results/local-smoke/upload-analyzed.png",
    fullPage: false,
  });

  // The screen the report was filed against.
  await page.goto("/compliance/privacy/processing-activities");
  const review = page.getByRole("button", {
    name: /Review suggestions \(\d+\)/,
  });
  await expect(review).toBeVisible();
  // The count that was stuck at zero.
  // If the count is stuck, say whether the API has the suggestion —
  // that separates "drafting never ran" from "the screen did not
  // refresh", which are different bugs with different fixes.
  try {
    await expect(review).not.toHaveText(/\(0\)/, { timeout: 90_000 });
  } catch (failure) {
    const probe = await page.request.get(
      `${API_BASE_URL}/api/v1/compliance/privacy/suggestions?kind=processing_activity`,
    );
    const rows = await probe.json();
    const n = Array.isArray(rows) ? rows.length : -1;
    console.log(`PROBE: API has ${n} suggestion(s) while the UI shows 0`);
    throw failure;
  }

  await review.click();
  await expect(page.getByText("AI Customer Support").first()).toBeVisible();
  await expect(
    page.getByText(/Veyntra_Privacy_Test_AI_Customer_Support/),
  ).toBeVisible();

  // The facts the tables were hiding.
  await expect(page.getByText(/Respond to customer support requests/)).toBeVisible();
  await expect(page.getByText(/Customers, prospective customers/)).toBeVisible();
  await expect(page.getByLabel("Lawful basis")).toHaveValue("");

  await page.screenshot({
    path: "test-results/local-smoke/upload-suggestion.png",
    fullPage: false,
  });
});
