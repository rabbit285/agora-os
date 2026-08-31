import { expect, test } from "@playwright/test";

import { API_BASE_URL, signup } from "./helpers";

/** Cleaning up mistakes without being able to destroy history.
 *
 * §17-§20 driven through the interface a person actually uses: the
 * overflow menu, the confirmation, and what the list says afterwards.
 */

async function createQuestionnaire(
  request: import("@playwright/test").APIRequestContext,
  title: string,
): Promise<string> {
  const response = await request.post(`${API_BASE_URL}/api/v1/compliance/questionnaires`, {
    data: { title, source: "customer_provided" },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()).id;
}

async function addQuestion(
  request: import("@playwright/test").APIRequestContext,
  questionnaireId: string,
  text: string,
): Promise<string> {
  const response = await request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${questionnaireId}/questions`,
    { data: { text, category: "security" } },
  );
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()).id;
}

test("§17 a draft nobody used can be deleted, with a confirmation first", async ({
  page,
}) => {
  test.slow();
  await signup(page, "lifecycle");

  const id = await createQuestionnaire(page.request, "Test Questionnaire");
  await addQuestion(page.request, id, "Do you encrypt data at rest?");
  await addQuestion(page.request, id, "Do you run penetration tests?");

  await page.goto("/compliance/assessments");
  await expect(page.getByRole("link", { name: /Test Questionnaire/ })).toBeVisible();
  // §7: the row says how much is in it.
  await expect(page.getByText(/2 questions/)).toBeVisible();

  // §1: destructive actions live behind the overflow menu, not on the row.
  await page.getByRole("button", { name: /actions for Test Questionnaire/i }).click();
  await page.getByRole("menuitem", { name: /delete draft/i }).click();

  // §3: a confirmation, naming the thing, saying what goes.
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Test Questionnaire");
  await expect(dialog).toContainText(/draft questions and answers/i);
  await expect(dialog).toContainText(/cannot be undone/i);
  await page.screenshot({
    path: "test-results/local-smoke/lifecycle-delete-confirm.png",
    fullPage: true,
  });

  await dialog.getByRole("button", { name: /^delete draft$/i }).click();

  // Wait for the dialog to close, not for the row to vanish. An open
  // modal hides the page behind it from the accessibility tree, so
  // "the row is gone" is satisfied the moment the dialog opens —
  // which would pass this test without anything being deleted.
  await expect(dialog).toBeHidden({ timeout: 15_000 });
  await expect(page.getByRole("link", { name: /Test Questionnaire/ })).toHaveCount(0);

  // Gone from the API too, not just hidden.
  const remaining = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires`,
  );
  expect(await remaining.json()).toHaveLength(0);
});

test("§18 a questionnaire with an approved answer is archived, not deleted", async ({
  page,
}) => {
  test.slow();
  await signup(page, "lifecycle-used");

  const id = await createQuestionnaire(
    page.request,
    "Acme Customer Security Questionnaire",
  );
  const questionId = await addQuestion(page.request, id, "Do you hold ISO 27001?");

  // Answer it and approve the answer.
  const answered = await page.request.patch(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions/${questionId}/answer`,
    { data: { answer_text: "Yes, certified since 2024.", status: "approved" } },
  );
  expect(answered.ok(), await answered.text()).toBeTruthy();

  await page.goto("/compliance/assessments");
  await page
    .getByRole("button", { name: /actions for Acme Customer Security Questionnaire/i })
    .click();

  // §8: no Delete offered, and the menu says why.
  await expect(page.getByRole("menuitem", { name: /delete/i })).toHaveCount(0);
  await expect(page.getByText(/archive it instead/i)).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/lifecycle-delete-blocked.png",
    fullPage: true,
  });

  // §15: the backend refuses even if the client asks directly.
  const forced = await page.request.delete(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}`,
  );
  expect(forced.status()).toBe(409);

  // §4: archive instead.
  await page.getByRole("menuitem", { name: /archive/i }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText(/answers, approvals, source citations and audit history/i);
  await dialog.getByRole("button", { name: /^archive$/i }).click();
  await expect(dialog).toBeHidden({ timeout: 15_000 });

  // §5: off the active list, present under Archived.
  await expect(
    page.getByRole("link", { name: /Acme Customer Security Questionnaire/ }),
  ).toHaveCount(0);

  await page
    .getByRole("tablist", { name: "Show questionnaires" })
    .getByRole("tab", { name: /Archived/ })
    .click();
  await expect(
    page.getByRole("link", { name: /Acme Customer Security Questionnaire/ }),
  ).toBeVisible();

  // The answer and its approval survived.
  const detail = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}`,
  );
  const body = await detail.json();
  expect(body.questions).toHaveLength(1);
  expect(body.questions[0].answer.status).toBe("approved");
});

test("§19 restoring puts it back unchanged", async ({ page }) => {
  test.slow();
  await signup(page, "lifecycle-restore");

  const id = await createQuestionnaire(page.request, "Archived then restored");
  await addQuestion(page.request, id, "Do you have an incident response plan?");
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/archive`,
  );

  await page.goto("/compliance/assessments");
  await page
    .getByRole("tablist", { name: "Show questionnaires" })
    .getByRole("tab", { name: /Archived/ })
    .click();
  await expect(page.getByRole("link", { name: /Archived then restored/ })).toBeVisible();

  await page
    .getByRole("button", { name: /actions for Archived then restored/i })
    .click();
  await page.getByRole("menuitem", { name: /restore/i }).click();

  // Back on the active list, with its question intact.
  await page
    .getByRole("tablist", { name: "Show questionnaires" })
    .getByRole("tab", { name: /Active/ })
    .click();
  await expect(page.getByRole("link", { name: /Archived then restored/ })).toBeVisible({
    timeout: 15_000,
  });

  const detail = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}`,
  );
  expect((await detail.json()).questions).toHaveLength(1);
});

test("§20 an audit with findings cannot be deleted", async ({ page }) => {
  test.slow();
  await signup(page, "lifecycle-audit");

  const planned = await page.request.post(`${API_BASE_URL}/api/v1/compliance/audits`, {
    data: { title: "Planned audit", auditor_name: null },
  });
  const plannedId = (await planned.json()).id;

  const withFindings = await page.request.post(`${API_BASE_URL}/api/v1/compliance/audits`, {
    data: { title: "Audit with findings", auditor_name: "Northwind Assurance" },
  });
  const findingsId = (await withFindings.json()).id;
  const finding = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/audits/${findingsId}/findings`,
    { data: { title: "Key rotation not evidenced", severity: "high" } },
  );
  expect(finding.ok(), await finding.text()).toBeTruthy();

  await page.goto("/compliance/assessments");

  // Empty and planned: deletable.
  await page.getByRole("button", { name: /actions for Planned audit/i }).click();
  await expect(page.getByRole("menuitem", { name: /delete draft/i })).toBeVisible();
  await page.keyboard.press("Escape");

  // Has findings: not deletable, and the menu says why.
  await page.getByRole("button", { name: /actions for Audit with findings/i }).click();
  await expect(page.getByRole("menuitem", { name: /delete/i })).toHaveCount(0);
  await expect(page.getByText(/finding/i).last()).toBeVisible();
  await expect(page.getByRole("menuitem", { name: /archive/i })).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/lifecycle-audit-menu.png",
    fullPage: true,
  });

  const forced = await page.request.delete(
    `${API_BASE_URL}/api/v1/compliance/audits/${findingsId}`,
  );
  expect(forced.status()).toBe(409);
  expect(plannedId).toBeTruthy();
});
