import { expect, test } from "@playwright/test";

import { API_BASE_URL, signup } from "./helpers";

/** §19 and §21 through the interface a person actually uses.
 *
 * The point of the flow is the preview: input → analyse → preview →
 * confirm. Nothing is created until somebody has seen what was found,
 * what already existed and what could not be read.
 */

const PASTE = `SECTION 1 - GOVERNANCE
Do you have an information security policy?
Do you encrypt customer data at rest?
Do you have an incident-response process?
Do you maintain an AI governance policy?
Security controls / yes / no / comments`;

async function setUpQuestionnaire(
  request: import("@playwright/test").APIRequestContext,
): Promise<string> {
  const created = await request.post(`${API_BASE_URL}/api/v1/compliance/questionnaires`, {
    // With the customer it always implied. A customer questionnaire
    // with nobody to send it to cannot be marked complete — the server
    // refuses that now — and this setup is meant to reach the finished
    // state the screenshot shows.
    data: {
      title: "Agora Origin customer",
      source: "customer_provided",
      customer_name: "Agora Origin",
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const id = (await created.json()).id;

  // The screenshot's starting state: one question, approved, complete.
  const question = await request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions`,
    { data: { text: "Do you have an incident-response process?", category: "security" } },
  );
  const questionId = (await question.json()).id;
  await request.patch(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions/${questionId}/answer`,
    { data: { answer_text: "Yes — documented and tested.", status: "approved" } },
  );
  // And marked finished, which is the state the screenshot is in: 1/1
  // approved, 100%, Ready to share. Importing unresolved questions into
  // that has to move it back.
  await request.patch(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/status`,
    { data: { status: "completed" } },
  );
  return id;
}

test("§19 pasted questions are previewed before anything is created", async ({ page }) => {
  test.slow();
  await signup(page, "qimport");
  const id = await setUpQuestionnaire(page.request);

  await page.goto(`/compliance/questionnaires/${id}`);

  // One way in. Pasting a single question into the import dialog is the
  // same action as pasting forty, so a second header button for it was
  // two paths to one outcome.
  await expect(page.getByRole("button", { name: "Import questionnaire" })).toBeVisible();
  await expect(page.getByRole("button", { name: /add manually/i })).toHaveCount(0);

  await page.getByRole("button", { name: "Import questionnaire" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Import customer questionnaire")).toBeVisible();

  // §1 and §2: a real file picker, next to the formats it can actually read.
  await expect(dialog.getByRole("button", { name: /choose file/i })).toBeVisible();
  await expect(dialog.getByText(/supported:/i)).toBeVisible();

  // §3: the example is placeholder text, not a value somebody has to delete.
  const textarea = dialog.getByLabel("Paste questions");
  await expect(textarea).toHaveValue("");
  await expect(textarea).toHaveAttribute("placeholder", /paste questions here/i);

  // §1: says what will happen after the import.
  await expect(dialog.getByText(/draft answers from your existing compliance/i)).toBeVisible();

  await textarea.fill(PASTE);
  await page.screenshot({
    path: "test-results/local-smoke/import-input.png",
    fullPage: true,
  });
  await dialog.getByRole("button", { name: /analyze questions/i }).click();

  // §4: the preview, with every outcome named.
  await expect(dialog.getByText(/4 questions detected/i)).toBeVisible({ timeout: 20_000 });
  await expect(dialog.getByText(/nothing has been created yet/i)).toBeVisible();
  // Scoped to the line's own badge: the headline sentence says "1
  // already here" too, and matching either would not prove the row was
  // marked.
  await expect(dialog.getByText(/^Already here · matches/)).toBeVisible();
  await expect(dialog.getByText(/reads as a section heading/i)).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/import-preview.png",
    fullPage: true,
  });

  // Nothing created yet — the questionnaire still has its one question.
  const midway = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}`,
  );
  expect((await midway.json()).questions).toHaveLength(1);

  await dialog.getByRole("button", { name: /^import 3 questions$/i }).click();

  // §11: a summary rather than a guess.
  await expect(dialog.getByText(/3 questions imported/i)).toBeVisible({ timeout: 20_000 });
  await expect(dialog.getByText(/answers are being drafted/i)).toBeVisible();
  await expect(dialog.getByText(/no longer marked complete/i)).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/import-result.png",
    fullPage: true,
  });

  await dialog.getByRole("button", { name: /^done$/i }).click();
  await expect(dialog).toBeHidden();

  // §19: four total, not five, and no longer ready to share.
  const after = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}`,
  );
  const body = await after.json();
  expect(body.questions).toHaveLength(4);
  expect(body.progress.ready_to_share).toBe(false);
  expect(body.progress.percent_complete).toBe(25);
  // Derived from the answers: three of the four questions are now
  // unanswered, so the questionnaire is a draft again.
  expect(body.status).toBe("draft");
});

test("§20 importing the same questions again creates nothing", async ({ page }) => {
  test.slow();
  await signup(page, "qimport-again");
  const id = await setUpQuestionnaire(page.request);

  const importOnce = async () => {
    const analysis = await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/import/analyze`,
      { data: { questions_text: PASTE } },
    );
    const lines = (await analysis.json()).lines as Array<{
      text: string;
      importable: boolean;
    }>;
    const confirmed = await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/import/confirm`,
      {
        data: {
          questions: lines.filter((l) => l.importable).map((l) => l.text),
          draft_answers: false,
        },
      },
    );
    return confirmed.json();
  };

  expect((await importOnce()).created).toBe(3);
  expect((await importOnce()).created).toBe(0);
  expect((await importOnce()).created).toBe(0);

  const after = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}`,
  );
  expect((await after.json()).questions).toHaveLength(4);
});

test("§21 a CSV file is read, previewed and imported without retyping", async ({
  page,
}) => {
  test.slow();
  await signup(page, "qimport-file");
  const id = await setUpQuestionnaire(page.request);

  await page.goto(`/compliance/questionnaires/${id}`);
  await page.getByRole("button", { name: "Import questionnaire" }).click();
  const dialog = page.getByRole("dialog");

  await dialog.getByLabel("Questionnaire file").setInputFiles({
    name: "Acme_Security_Questionnaire.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Question,Response\n" +
        "Do you have an information security policy?,\n" +
        "Do you encrypt customer data at rest?,\n" +
        "Do you have an incident-response process?,\n",
    ),
  });

  await expect(dialog.getByText(/questions? detected/i)).toBeVisible({ timeout: 30_000 });
  // Scoped to the line's own badge: the headline sentence says "1
  // already here" too, and matching either would not prove the row was
  // marked.
  await expect(dialog.getByText(/^Already here · matches/)).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/import-file-preview.png",
    fullPage: true,
  });

  await dialog.getByRole("button", { name: /^import \d+ questions?$/i }).click();
  await expect(dialog.getByText(/questions? imported/i)).toBeVisible({ timeout: 20_000 });

  const after = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}`,
  );
  const texts = (await after.json()).questions.map(
    (q: { text: string }) => q.text,
  );
  expect(texts).toContain("Do you have an information security policy?");
  expect(texts).toContain("Do you encrypt customer data at rest?");
  // The one that already existed was not created twice.
  expect(
    texts.filter((t: string) => t.includes("incident-response")),
  ).toHaveLength(1);
});

test("a single pasted question goes through the same import flow", async ({ page }) => {
  test.slow();
  await signup(page, "qimport-one");
  const id = await setUpQuestionnaire(page.request);

  await page.goto(`/compliance/questionnaires/${id}`);

  // The header offers one action, and it covers the one-question case.
  await expect(page.getByRole("button", { name: /add manually/i })).toHaveCount(0);
  await page.getByRole("button", { name: "Import questionnaire" }).click();

  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Paste questions")
    .fill("Do you run penetration tests annually?");
  await dialog.getByRole("button", { name: /analyze questions/i }).click();

  await expect(dialog.getByText(/1 question detected/i)).toBeVisible({ timeout: 20_000 });
  await dialog.getByRole("button", { name: /^import 1 question$/i }).click();
  await expect(dialog.getByText(/1 question imported/i)).toBeVisible({ timeout: 20_000 });
  await dialog.getByRole("button", { name: /^done$/i }).click();

  const after = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}`,
  );
  const texts = (await after.json()).questions.map((q: { text: string }) => q.text);
  expect(texts).toContain("Do you run penetration tests annually?");
});
