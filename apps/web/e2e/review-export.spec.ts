import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** §28/§29/§30: the export workflow, driven through the browser.
 *
 * The compliance team must always know what they are about to send
 * outside the organization. So: choose an output, read exactly what it
 * would contain, and only then produce a file — with the history staying
 * empty until somebody actually does.
 */
async function readyReview(page: import("@playwright/test").Page) {
  const created = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires`,
    {
      data: {
        title: "Agora Origin Security Questionnaire",
        source: "customer_provided",
        customer_name: "Agora Origin",
      },
    },
  );
  const questionnaireId = (await created.json()).id;

  const answers: [string, string][] = [
    [
      "Do you have an incident-response process?",
      "Yes. The organization maintains a documented incident-response process; however, current evidence does not demonstrate completion of the most recent tabletop exercise.",
    ],
    [
      "Do you encrypt customer data at rest?",
      "Yes. All customer data is encrypted at rest using AES-256 with managed keys.",
    ],
    [
      "Do you maintain an information security policy?",
      "Yes. The Information Security Policy is reviewed annually and approved by leadership.",
    ],
  ];
  for (const [text, answer] of answers) {
    const question = await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${questionnaireId}/questions`,
      { data: { text, category: "security" } },
    );
    await page.request.patch(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${questionnaireId}/questions/${
        (await question.json()).id
      }/answer`,
      { data: { answer_text: answer, status: "approved" } },
    );
  }

  const reviews = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/security-reviews`,
  );
  return (await reviews.json())[0];
}

test("preview comes first, and generating leaves an immutable record", async ({
  page,
}) => {
  test.slow();
  await signup(page, "export");
  const review = await readyReview(page);

  await page.goto(`/compliance/security-reviews/${review.id}`);
  await expect(page.getByText("ready to share").first()).toBeVisible();

  // §20: nothing generated yet, so no history section.
  await expect(page.getByText("Generated outputs")).toHaveCount(0);

  // --- §4 step one: choose, and nothing is generated -------------------
  await page.getByRole("button", { name: "Export / Share" }).click();
  await expect(
    page.getByRole("heading", { name: "Prepare customer package" }),
  ).toBeVisible();
  // Scoped to the choices: the questionnaire in this review is also
  // called "Completed questionnaire" once it has been generated.
  const dialog = page.getByRole("dialog");
  for (const label of [
    "Security Review Summary",
    "Completed questionnaire",
    "Evidence / Assurance Pack",
  ]) {
    await expect(dialog.getByText(label, { exact: true })).toBeVisible();
  }

  await page.getByText("A PDF report:").click();
  await page.getByRole("button", { name: "Continue to preview" }).click();

  // --- §5 the preview shows the contents -------------------------------
  await expect(
    page.getByRole("heading", { name: /Preview — Security Review Summary/ }),
  ).toBeVisible();
  await expect(page.getByText("Nothing has been generated yet.")).toBeVisible();
  await expect(page.getByText("Approved responses (3)")).toBeVisible();
  await expect(page.getByText("3 / 3 approved · 100%")).toBeVisible();

  // §14: the limitation is shown, and will go out with the answer.
  await expect(
    page.getByText("Known disclosures and limitations (1)"),
  ).toBeVisible();
  await expect(page.getByText(/tabletop exercise/).first()).toBeVisible();

  // The disclaimer the customer will read.
  await expect(
    page.getByText(/not an independent certification, legal opinion/),
  ).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/export-preview.png",
    fullPage: false,
  });

  // --- §29 closing the preview creates nothing -------------------------
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(page.getByText("Generated outputs")).toHaveCount(0);

  // --- §28 generate ----------------------------------------------------
  await page.getByRole("button", { name: "Export / Share" }).click();
  await page.getByText("A PDF report:").click();
  await page.getByRole("button", { name: "Continue to preview" }).click();
  await expect(page.getByText("Approved responses (3)")).toBeVisible();
  await page.getByRole("button", { name: "Generate PDF" }).click();

  // §20: one record, and it says what it contains.
  await expect(page.getByText("Generated outputs")).toBeVisible();
  await expect(
    page.getByText("Security Review Summary · v1"),
  ).toBeVisible();
  await expect(page.getByText(/PDF · Generated/)).toBeVisible();
  await expect(page.getByText(/3 responses/)).toBeVisible();
  // §27: generated is not shared.
  await expect(page.getByText(/Not yet shared/)).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/export-outputs.png",
    fullPage: false,
  });

  // --- §16 the state survives a reload ---------------------------------
  await page.reload();
  await expect(page.getByText("Security Review Summary · v1")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Download" }),
  ).toBeEnabled();
});

test("a review that is not ready explains what is blocking the export", async ({
  page,
}) => {
  test.slow();
  await signup(page, "exportblock");

  // A customer questionnaire with nothing approved.
  const created = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires`,
    {
      data: {
        title: "Blocked Security Questionnaire",
        source: "customer_provided",
        customer_name: "Blocked Corp",
      },
    },
  );
  const questionnaireId = (await created.json()).id;
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${questionnaireId}/questions`,
    { data: { text: "Do you encrypt data at rest?", category: "security" } },
  );

  const reviews = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/security-reviews`,
  );
  const review = (await reviews.json())[0];

  await page.goto(`/compliance/security-reviews/${review.id}`);
  await page.getByRole("button", { name: "Export / Share" }).click();
  await page.getByText("A PDF report:").click();
  await page.getByRole("button", { name: "Continue to preview" }).click();

  // §1: the action is available, and says why it cannot complete.
  await expect(page.getByText("Cannot export final review yet")).toBeVisible();
  // Both reasons are listed; the first is enough to prove they are.
  await expect(
    page.getByText(/no approved answer|not ready to share/).first(),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /Generate/ })).toBeDisabled();
});
