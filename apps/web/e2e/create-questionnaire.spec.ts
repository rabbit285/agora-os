import { expect, test } from "@playwright/test";
import { signup } from "./helpers";

/** §13/§14: where new questionnaires get their engagement.
 *
 * The reconciliation repairs records that already exist. This is the
 * path that stops new ones needing repair: the form asks for the
 * customer at the only moment anybody actually knows who it is.
 */
test("a customer questionnaire cannot be created without a customer", async ({
  page,
}) => {
  test.slow();
  await signup(page, "createq");

  await page.goto("/compliance/assessments");
  await page.getByRole("button", { name: "Create questionnaire" }).first().click();

  await page
    .getByLabel("Questionnaire title")
    .fill("Acme Customer Security Questionnaire");
  await page
    .getByLabel("Questionnaire type")
    .selectOption("customer_provided");

  // The customer field appears, and the button waits for it.
  const submit = page.getByRole("button", { name: "Create questionnaire" }).last();
  await expect(submit).toBeDisabled();
  await expect(
    page.getByText("Name the customer so this joins their security review."),
  ).toBeVisible();

  await page.getByLabel("Customer", { exact: true }).fill("Acme Corp");
  await expect(page.getByText("Joins Acme Corp's security review.")).toBeVisible();
  await expect(submit).toBeEnabled();
  await page.screenshot({
    path: "test-results/local-smoke/create-questionnaire.png",
    fullPage: false,
  });
  await submit.click();

  // §13: the engagement is there without anybody asking for it.
  const reviews = page.locator("#security-reviews-panel");
  await expect(
    reviews.getByRole("link", { name: /Acme Corp Security Review/ }),
  ).toBeVisible();

  // §14: an internal assessment is nobody's engagement but our own.
  // The panel stays open with the type reset to internal, so the
  // customer field is gone on its own.
  await page.getByLabel("Questionnaire title").fill("Internal ISO 42001 Assessment");
  await expect(page.getByLabel("Customer", { exact: true })).toHaveCount(0);
  await submit.click();

  await expect(reviews.getByRole("link", { name: /Security Review/ })).toHaveCount(1);
});

test("a title that is really a question says so", async ({ page }) => {
  test.slow();
  await signup(page, "titlehint");

  await page.goto("/compliance/assessments");
  await page.getByRole("button", { name: "Create questionnaire" }).first().click();

  await page
    .getByLabel("Questionnaire title")
    .fill("Do you encrypt customer data at rest?");

  await expect(
    page.getByText(/looks like one of the questions/),
  ).toBeVisible();
  // Said, not enforced: the button still works.
  await expect(
    page.getByRole("button", { name: "Create questionnaire" }).last(),
  ).toBeEnabled();

  await page
    .getByLabel("Questionnaire title")
    .fill("Acme Customer Security Questionnaire");
  await expect(page.getByText(/looks like one of the questions/)).toHaveCount(0);
});
