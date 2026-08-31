import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** §19–§23: what "ready to share" means, on screen.
 *
 * A customer questionnaire with every answer approved and no customer on
 * it is not ready to share with anybody, because there is nobody to
 * share it with. These drive that through the browser: the state, the
 * repair, and the empty state that has to describe the tab you are
 * looking at rather than the section as a whole.
 */
async function customerQuestionnaireWithNoCustomer(
  page: import("@playwright/test").Page,
  title: string,
  approvedAnswers: number,
) {
  const created = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires`,
    { data: { title, source: "customer_provided" } },
  );
  expect(created.ok(), await created.text()).toBeTruthy();
  const id = (await created.json()).id;
  for (let i = 0; i < approvedAnswers; i += 1) {
    const question = await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions`,
      { data: { text: `Question ${i + 1}?`, category: "security" } },
    );
    await page.request.patch(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions/${
        (await question.json()).id
      }/answer`,
      { data: { answer_text: "Yes.", status: "approved" } },
    );
  }
  return id;
}

test("§19/§20 approved answers do not make it shareable without a customer", async ({
  page,
}) => {
  test.slow();
  await signup(page, "readiness");

  const id = await customerQuestionnaireWithNoCustomer(
    page,
    "Do you encrypt customer data at rest?",
    2,
  );

  await page.goto("/compliance/assessments");
  const questionnaires = page.locator("#questionnaires-panel");

  // §19: 2 of 2 approved, and not ready.
  await expect(questionnaires.getByText("needs setup").first()).toBeVisible();
  await expect(
    questionnaires.getByText("ready to share"),
  ).toHaveCount(0);

  // §6: the repair is right here, not buried in the record.
  await expect(page.getByText("1 questionnaire needs setup")).toBeVisible();
  await expect(
    page.getByText("Customer required before this questionnaire can be shared."),
  ).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/needs-setup.png",
    fullPage: false,
  });

  // §20: name the customer, and everything unblocks at once.
  await page
    .getByRole("button", {
      name: "Set customer for Do you encrypt customer data at rest?",
    })
    .click();
  await page.getByLabel("Customer", { exact: true }).fill("Agora Origin");
  await page
    .getByRole("button", { name: /Set customer and create review/ })
    .click();

  await expect(page.getByText("1 questionnaire needs setup")).toHaveCount(0);
  await expect(questionnaires.getByText("ready to share")).toBeVisible();

  const reviews = page.locator("#security-reviews-panel");
  await expect(
    reviews.getByRole("link", { name: /Agora Origin Security Review/ }),
  ).toBeVisible();
  await expect(reviews.getByText("ready to share")).toBeVisible();

  // §16: the server holds it, not the page.
  await page.reload();
  await expect(questionnaires.getByText("ready to share")).toBeVisible();
  await expect(page.getByText("1 questionnaire needs setup")).toHaveCount(0);

  // §18: the title is still the question somebody pasted in. Flagged on
  // the record, and not rewritten.
  await page.goto(`/compliance/questionnaires/${id}`);
  await expect(
    page.getByText("This title looks like one of the questions"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Rename" }).click();
  await page
    .getByLabel("Questionnaire title")
    .fill("Agora Origin Security Questionnaire");
  await page.getByRole("button", { name: "Rename" }).last().click();
  await expect(
    page.getByRole("heading", { name: "Agora Origin Security Questionnaire" }),
  ).toBeVisible();
  // Renaming moved nothing else.
  await expect(page.getByText("Agora Origin Security Review")).toBeVisible();
});

test("§23 the empty state describes the tab, not the section", async ({
  page,
}) => {
  test.slow();
  await signup(page, "emptystate");

  // One review, archived — so Active is 0 and Archived is 1.
  const created = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires`,
    {
      data: {
        title: "Acme Corp Security Questionnaire",
        source: "customer_provided",
        customer_name: "Acme Corp",
      },
    },
  );
  const id = (await created.json()).id;
  const question = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions`,
    { data: { text: "Do you encrypt data at rest?", category: "security" } },
  );
  await page.request.patch(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions/${
      (await question.json()).id
    }/answer`,
    { data: { answer_text: "Yes.", status: "approved" } },
  );
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/archive`,
  );

  await page.goto("/compliance/assessments");
  const reviews = page.locator("#security-reviews-panel");

  // Active 0, Archived 1 — and the Active tab must not claim there are
  // no reviews at all.
  await expect(page.locator("#security-reviews-tab-archived")).toContainText("1");
  await expect(
    reviews.getByText("No active customer security reviews"),
  ).toBeVisible();
  await expect(reviews.getByText("No customer security reviews")).toHaveCount(0);
  // And it points at where the missing one actually is.
  await expect(
    reviews.getByText(/finished and archived are under Archived/),
  ).toBeVisible();

  await reviews.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "test-results/local-smoke/empty-state.png",
    fullPage: false,
  });

  await page.locator("#security-reviews-tab-archived").click();
  await expect(
    reviews.getByRole("link", { name: /Acme Corp Security Review/ }),
  ).toBeVisible();
});
