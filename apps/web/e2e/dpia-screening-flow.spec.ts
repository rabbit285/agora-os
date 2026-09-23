import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** §16: screening first, and a decision before there is an assessment.
 *
 * Selecting a processing activity used to open a full DPIA — four empty
 * prose boxes, no risks, "Inherent risk: Low" on a document where
 * nobody had assessed anything, and no sign a screening had happened.
 */
async function aiCustomerSupport(page: import("@playwright/test").Page) {
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/vendors`, {
    data: { name: "OpenAI", category: "ai", country: "US" },
  });
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/ai-systems`, {
    data: {
      name: "AI Support Assistant",
      vendor: "OpenAI",
      purpose: "Respond to customer support requests",
      affected_users: ["Customers"],
      processed_data: [
        { name: "Contact details", classification: "confidential" },
        { name: "Support conversation content", classification: "confidential" },
      ],
    },
  });
  const drafts = await (
    await page.request.get(`${API_BASE_URL}/api/v1/compliance/privacy/suggestions`)
  ).json();
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/privacy/suggestions/${drafts[0].id}/accept`,
    {
      data: {
        legal_basis: "contract",
        retention_period: "24 months",
        special_category: true,
        special_category_condition: "explicit_consent",
      },
    },
  );
}

test("screening shows its result before any assessment exists", async ({
  page,
}) => {
  test.slow();
  await signup(page, "dpiaflow");
  await aiCustomerSupport(page);

  await page.goto("/compliance/privacy/dpias");
  await page.getByRole("button", { name: "Start DPIA screening" }).click();

  const dialog = page.getByRole("dialog");
  const record = dialog.getByLabel("Record to assess");
  await expect
    .poll(async () => await record.locator("option").count(), { timeout: 15_000 })
    .toBeGreaterThan(1);
  const [, first] = await record.locator("option").allTextContents();
  await record.selectOption({ label: first });

  // §5: what Veyntra already knows, before anything is assessed.
  await expect(dialog.getByText("What Veyntra already knows")).toBeVisible();
  await expect(dialog.getByText("AI Support Assistant").first()).toBeVisible();

  await dialog.getByRole("button", { name: "Run screening" }).click();

  // §3: the recommendation, why, and whose decision it remains.
  await expect(
    dialog.getByText("A DPIA appears to be required"),
  ).toBeVisible();
  await expect(dialog.getByText(/EDPB/).first()).toBeVisible();
  await expect(
    dialog.getByText(/not a determination. The decision — and the record of it — is yours/),
  ).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/dpia-screening-result.png",
    fullPage: false,
  });

  // §3: both answers are decisions, and declining needs a reason.
  const decline = dialog.getByRole("button", { name: "DPIA not required" });
  await expect(decline).toBeDisabled();

  await dialog.getByRole("button", { name: "Confirm DPIA required" }).click();
  await expect(dialog).toHaveCount(0);

  // §5/§6: the assessment exists now, and claims nothing it has not
  // assessed.
  const dpias = await (
    await page.request.get(`${API_BASE_URL}/api/v1/compliance/dpias`)
  ).json();
  expect(dpias).toHaveLength(1);
  expect(dpias[0].status).toBe("draft");
  expect(dpias[0].risk_level).toBeNull();
  expect(dpias[0].screening_decision).toBe("required");

  const workflow = await (
    await page.request.get(
      `${API_BASE_URL}/api/v1/compliance/dpias/${dpias[0].id}/workflow`,
    )
  ).json();
  expect(workflow.inherent_risk).toBeNull();
  expect(workflow.residual_risk).toBeNull();
  expect(workflow.can_calculate_residual).toBe(false);
  expect(workflow.suggested_risks.length).toBeGreaterThanOrEqual(3);
  // §7: drafted, not four empty boxes.
  expect(workflow.processing_description).toContain("Veyntra draft");
});

test("§4 screening the same activity twice continues the same assessment", async ({
  page,
}) => {
  test.slow();
  await signup(page, "dpiareuse");
  await aiCustomerSupport(page);

  const activities = await (
    await page.request.get(
      `${API_BASE_URL}/api/v1/compliance/processing-activities`,
    )
  ).json();
  const body = { processing_activity_id: activities[0].id };

  const first = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/dpias/screening/start`,
      { data: body },
    )
  ).json();
  const second = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/dpias/screening/start`,
      { data: body },
    )
  ).json();

  expect(second.id).toBe(first.id);
  expect(second.reused_existing).toBe(true);

  const dpias = await (
    await page.request.get(`${API_BASE_URL}/api/v1/compliance/dpias`)
  ).json();
  expect(dpias).toHaveLength(1);
});
