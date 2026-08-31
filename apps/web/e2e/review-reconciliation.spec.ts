import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** The reported case, reproduced and then repaired in the browser.
 *
 * A customer-provided questionnaire with no customer recorded on it,
 * archived, ready to share — and an Assessments page saying "Active 0 /
 * Archived 0 / No customer security reviews". Everything on that screen
 * was true and the product still had nothing useful to say.
 */
async function makeUnnamedCustomerQuestionnaire(
  page: import("@playwright/test").Page,
  title: string,
  answers: number,
) {
  const created = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires`,
    { data: { title, source: "customer_provided" } },
  );
  expect(created.ok(), await created.text()).toBeTruthy();
  const id = (await created.json()).id;

  for (let i = 0; i < answers; i += 1) {
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
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/archive`,
  );
  return id;
}

test("an unlinked customer questionnaire can be repaired from its own page", async ({
  page,
}) => {
  test.slow();
  await signup(page, "reconcile");

  const agora = await makeUnnamedCustomerQuestionnaire(
    page,
    "Agora Origin cusotmer",
    3,
  );
  // The other record from the report: a question pasted in as a title.
  // Nothing here identifies a customer and nothing should pretend to.
  await makeUnnamedCustomerQuestionnaire(
    page,
    "Do you encrypt customer data at rest?",
    2,
  );

  // --- the reported screen ---------------------------------------------
  await page.goto("/compliance/assessments");
  const reviews = page.locator("#security-reviews-panel");
  await expect(
    reviews.getByText("No active customer security reviews"),
  ).toBeVisible();
  // Both questionnaires here are archived, so the setup panel is on the
  // Archived tab with them. It follows the list it sits above rather
  // than advertising records that list is not showing.
  await expect(page.getByText(/questionnaires? needs? setup/)).toHaveCount(0);
  await page.locator("#questionnaires-tab-archived").click();
  await expect(page.getByText("2 questionnaires need setup")).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Set customer for Agora Origin cusotmer/ }),
  ).toBeVisible();

  // --- the repair -------------------------------------------------------
  await page.goto(`/compliance/questionnaires/${agora}`);
  await expect(
    page.getByRole("heading", {
      name: "Not linked to a customer security review",
    }),
  ).toBeVisible();

  const field = page.getByLabel("Customer");
  // The suggestion is filled in and editable, with its reasoning shown.
  await expect(field).toHaveValue("Agora Origin");
  await expect(page.getByText(/Suggested from the questionnaire title/)).toBeVisible();

  await page
    .getByRole("button", { name: /Set customer and create review/ })
    .click();

  // §8: the questionnaire now says which engagement it is in, and keeps
  // the two dimensions apart.
  await expect(page.getByText("Agora Origin Security Review")).toBeVisible();
  await expect(page.getByText("Review status")).toBeVisible();
  await expect(page.getByText("Review lifecycle")).toBeVisible();

  // --- §16: the server holds it, not the page ---------------------------
  await page.goto("/compliance/assessments");
  await page.reload();

  await page.locator("#security-reviews-tab-archived").click();
  await expect(
    reviews.getByRole("link", { name: /Agora Origin Security Review/ }),
  ).toBeVisible();
  // §7: the engagement reports what it held, not zeros.
  await expect(
    reviews.getByText(/Agora Origin · 1 questionnaire · 3 questions · 3\/3 approved · 100%/),
  ).toBeVisible();
  await expect(reviews.getByText(/Archived/).first()).toBeVisible();

  // Active is still empty, and one questionnaire is left needing a
  // customer — the one nothing can be inferred about.
  await page.locator("#security-reviews-tab-active").click();
  await expect(
    reviews.getByText("No active customer security reviews"),
  ).toBeVisible();
  await page.locator("#questionnaires-tab-archived").click();
  await expect(page.getByText("1 questionnaire needs setup")).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: /Set customer for Do you encrypt customer data at rest\?/,
    }),
  ).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/review-reconciliation.png",
    fullPage: true,
  });
});

test("a review can be archived and restored without losing anything", async ({
  page,
}) => {
  test.slow();
  await signup(page, "reviewlife");

  const created = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires`,
    {
      data: {
        title: "Acme Customer Security Questionnaire",
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

  await page.goto("/compliance/assessments");
  const reviews = page.locator("#security-reviews-panel");
  const row = reviews.getByRole("link", { name: /Acme Corp Security Review/ });
  await expect(row).toBeVisible();

  // Archive the engagement itself.
  await reviews
    .getByRole("button", { name: /Actions for Acme Corp Security Review/ })
    .click();
  await page.getByRole("menuitem", { name: "Archive" }).click();
  await page.getByRole("button", { name: "Archive" }).last().click();

  await expect(row).toHaveCount(0);
  await page.locator("#security-reviews-tab-archived").click();
  await expect(row).toBeVisible();

  // The questionnaire went nowhere: closing a conversation is not an
  // instruction to bury the evidence.
  const questionnaires = page.locator("#questionnaires-panel");
  await expect(
    questionnaires.getByRole("link", {
      name: /Acme Customer Security Questionnaire/,
    }),
  ).toBeVisible();

  // Restore, and it is the same row.
  await reviews
    .getByRole("button", { name: /Actions for Acme Corp Security Review/ })
    .click();
  await page.getByRole("menuitem", { name: "Restore" }).click();
  await page.locator("#security-reviews-tab-active").click();
  await expect(row).toBeVisible();
  await expect(reviews.getByText(/1\/1 approved · 100%/)).toBeVisible();
});
