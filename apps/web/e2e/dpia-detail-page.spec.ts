import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** The DPIA detail page, on a DPIA that has assessed nothing yet.
 *
 * This crashed: `risk_level` became nullable when "0 risks raised,
 * inherent risk Low" was fixed, the frontend type still said it was
 * always a string, so nothing caught the caller and `StatusBadge` threw
 * `Cannot read properties of null (reading 'replace')` — taking the
 * whole page down rather than rendering one empty badge.
 */
test("a DPIA with no risks renders, and claims nothing it has not assessed", async ({
  page,
}) => {
  test.slow();
  await signup(page, "dpiadetail");

  const activity = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/processing-activities`,
      {
        data: {
          name: "Customer Support",
          purpose: "Respond to customer support requests.",
          legal_basis: "contract",
          data_subjects: "Customers",
          retention_period: "24 months",
        },
      },
    )
  ).json();

  const screened = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/dpias/screening/start`,
      { data: { processing_activity_id: activity.id } },
    )
  ).json();
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/screening/decision`,
    { data: { decision: "required" } },
  );

  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto(`/compliance/dpias/${screened.id}`);
  await expect(
    page.getByRole("heading", { name: "Customer Support DPIA" }),
  ).toBeVisible();

  // The crash.
  expect(errors, `page threw: ${errors.join(" | ")}`).toHaveLength(0);

  // §5: no risks, so no inherent level — not "Low", not a blank badge.
  await expect(page.getByText("Risk not assessed")).toBeVisible();
  // Scoped to the risk panel: "Risk not assessed" in the header also
  // contains this text.
  await expect(
    page.getByText("Not assessed", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.getByText("Not yet calculated")).toBeVisible();

  // Nothing to recalculate from, so the calculation is not offered at
  // all — a disabled button still implies a number is waiting to be
  // found, and with no risks and no mitigations there is none.
  await expect(
    page.getByRole("button", { name: "Recalculate residual risk" }),
  ).toHaveCount(0);
  // And the section is not framed as being "after mitigation" when
  // nothing has been mitigated.
  await expect(page.getByRole("heading", { name: /Risk assessment/ })).toBeVisible();
  await expect(page.getByText("Risk after mitigation")).toHaveCount(0);
  // Nothing was proposed for this processing, which is still not the
  // same as there being no risks — the page says so and asks for the
  // review either way.
  await expect(
    page.getByText(/No candidate risks were generated from this processing/),
  ).toBeVisible();
  await expect(
    // Said in the risk panel and again in the completion blocker,
    // which is the same instruction in both places.
    page.getByText(/record that none are material and why/).first(),
  ).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/dpia-detail.png",
    fullPage: false,
  });
});
