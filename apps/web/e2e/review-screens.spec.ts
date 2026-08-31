import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** Screens for the reconciled engagement, for looking at.
 *
 * The assertions here are the same ones the reconciliation spec makes;
 * what this adds is a picture of each screen at the moment it matters,
 * because "Archived 1" being in the DOM and the row reading correctly to
 * somebody are different claims.
 */
test("the reconciled engagement, on screen", async ({ page }) => {
  test.slow();
  await signup(page, "screens");

  const created = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires`,
    { data: { title: "Agora Origin cusotmer", source: "customer_provided" } },
  );
  const id = (await created.json()).id;
  for (const text of [
    "Do you have an information security policy?",
    "Do you have an incident-response process?",
    "Do you encrypt customer data at rest?",
  ]) {
    const question = await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions`,
      { data: { text, category: "security" } },
    );
    await page.request.patch(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions/${
        (await question.json()).id
      }/answer`,
      { data: { answer_text: "Yes.", status: "approved" } },
    );
  }
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/archive`,
  );

  // The repair, as it appears on the questionnaire.
  await page.goto(`/compliance/questionnaires/${id}`);
  await expect(page.getByLabel("Customer")).toHaveValue("Agora Origin");
  await page.screenshot({
    path: "test-results/local-smoke/repair-panel.png",
    fullPage: false,
  });

  await page
    .getByRole("button", { name: /Set customer and create review/ })
    .click();
  await expect(page.getByText("Agora Origin Security Review")).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/questionnaire-engagement.png",
    fullPage: false,
  });

  // And the archived engagement on the Assessments page.
  await page.goto("/compliance/assessments");
  await page.locator("#security-reviews-tab-archived").click();
  await expect(
    page
      .locator("#security-reviews-panel")
      .getByRole("link", { name: /Agora Origin Security Review/ }),
  ).toBeVisible();
  await page
    .locator("#security-reviews-panel")
    .scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "test-results/local-smoke/archived-engagement.png",
    fullPage: false,
  });
});

test("the review page shows the engagement, not an opportunity", async ({ page }) => {
  test.slow();
  await signup(page, "reviewpage");

  const make = async (title: string, answers: string[]) => {
    const created = await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/questionnaires`,
      {
        data: {
          title,
          source: "customer_provided",
          customer_name: "Nordwind Robotics",
        },
      },
    );
    const id = (await created.json()).id;
    for (const status of answers) {
      const question = await page.request.post(
        `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions`,
        { data: { text: `Question ${status}?`, category: "security" } },
      );
      await page.request.patch(
        `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions/${
          (await question.json()).id
        }/answer`,
        { data: { answer_text: "Yes.", status } },
      );
    }
    return id;
  };

  await make("Nordwind security questionnaire", ["approved", "approved"]);
  await make("Nordwind privacy questionnaire", ["needs_review"]);

  await page.goto("/compliance/assessments");
  await page
    .locator("#security-reviews-panel")
    .getByRole("link", { name: /Nordwind Robotics Security Review/ })
    .click();

  // The engagement, named for the customer — not a blank opportunity.
  await expect(
    page.getByRole("heading", { name: "Nordwind Robotics Security Review" }),
  ).toBeVisible();
  await expect(
    page.getByText("Security review for Nordwind Robotics"),
  ).toBeVisible();

  // Both questionnaires, added up: 2 of 3 approved across 2.
  await expect(
    page.getByText(/of 3 approved across 2 questionnaires/),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Questionnaires in this review" }),
  ).toBeVisible();
  await expect(page.getByText("Nordwind security questionnaire")).toBeVisible();
  await expect(page.getByText("Nordwind privacy questionnaire")).toBeVisible();

  // The engagement is not ready while part of it is not.
  await expect(page.getByText("needs review").first()).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/review-page.png",
    fullPage: false,
  });
});
