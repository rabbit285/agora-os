import { expect, test } from "@playwright/test";

import { API_BASE_URL, signup } from "./helpers";

/** The Assessments page reads comfortably, closed and open.
 *
 * The create form expands from a button into a card inside the same
 * control row as the Active/Archived filter, so the open state is the
 * one worth looking at — a card squeezed beside a filter would be worse
 * than the crowding it replaced.
 */

test("the section controls have room, and the create form still fits", async ({
  page,
}) => {
  test.slow();
  await signup(page, "assess");

  // Enough content that the sections are not empty states.
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/questionnaires`, {
    data: { title: "Agora Origin customer", source: "customer_provided" },
  });
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/audits`, {
    data: { title: "ISO 42001 Internal Audit", auditor_name: "Zach Warren" },
  });

  await page.goto("/compliance/assessments");
  await expect(page.getByRole("heading", { name: "Assessments" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Agora Origin customer" })).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/assessments-closed.png",
    fullPage: true,
  });

  // The section's action sits with its heading; the lifecycle filter
  // gets its own row below, so a create button never looks like it
  // belongs to whichever tab happens to be open.
  await expect(page.getByRole("tablist", { name: "Show questionnaires" })).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Show audits" })).toBeVisible();
  await expect(page.getByRole("button", { name: /create questionnaire/i })).toBeVisible();

  // Opening the form must not squeeze it beside anything.
  await page.getByRole("button", { name: /create questionnaire/i }).click();
  const titleField = page.getByPlaceholder("Questionnaire title");
  await expect(titleField).toBeVisible();
  const box = await titleField.boundingBox();
  expect(box, "the title field should be laid out").not.toBeNull();
  expect(box!.width, "the create form must not be squeezed").toBeGreaterThan(200);

  await page.screenshot({
    path: "test-results/local-smoke/assessments-create-open.png",
    fullPage: true,
  });

  // And it still works from there.
  await titleField.fill("Acme security review");
  await page.getByRole("button", { name: /^create questionnaire$/i }).last().click();
  await expect(page.getByRole("link", { name: "Acme security review" })).toBeVisible({
    timeout: 15_000,
  });
});
