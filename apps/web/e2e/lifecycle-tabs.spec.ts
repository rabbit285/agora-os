import { expect, test } from "@playwright/test";

import { API_BASE_URL, signup } from "./helpers";

/** Active and Archived filter lifecycle, never workflow status.
 *
 * A draft can be archived and a completed questionnaire can be active.
 * The reported bug — "Archived is selected but I still see drafts" — is
 * what happens when an archived row says only "draft": there is nothing
 * on it to say which list you are looking at.
 */

async function seed(request: import("@playwright/test").APIRequestContext) {
  const make = async (title: string) => {
    const response = await request.post(
      `${API_BASE_URL}/api/v1/compliance/questionnaires`,
      // Named, so these are genuinely drafts. A customer questionnaire
      // with no customer reads "Needs setup" whatever its answers say,
      // and these tests are about lifecycle against workflow status —
      // not about a record that has neither yet.
      { data: { title, source: "customer_provided", customer_name: "Acme Corp" } },
    );
    expect(response.ok(), await response.text()).toBeTruthy();
    return (await response.json()).id as string;
  };
  const a = await make("Questionnaire A");
  const b = await make("Questionnaire B");
  // Both are Draft. Only B is archived.
  await request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${b}/archive`,
  );

  const audit = await request.post(`${API_BASE_URL}/api/v1/compliance/audits`, {
    data: { title: "Planned audit", auditor_name: null },
  });
  return { a, b, auditId: (await audit.json()).id as string };
}

const questionnaireTabs = (page: import("@playwright/test").Page) =>
  page.getByRole("tablist", { name: "Show questionnaires" });
const auditTabs = (page: import("@playwright/test").Page) =>
  page.getByRole("tablist", { name: "Show audits" });

test("§15 a draft that is not archived never appears under Archived", async ({
  page,
}) => {
  test.slow();
  await signup(page, "tabs");
  await seed(page.request);

  await page.goto("/compliance/assessments");

  // Active: A only.
  await expect(page.getByRole("link", { name: "Questionnaire A" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Questionnaire B" })).toHaveCount(0);

  // The counts come from the real lifecycle totals.
  const tabs = questionnaireTabs(page);
  await expect(tabs.getByRole("tab", { name: /Active/ })).toContainText("1");
  await expect(tabs.getByRole("tab", { name: /Archived/ })).toContainText("1");
  await expect(tabs.getByRole("tab", { name: /Active/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await page.screenshot({
    path: "test-results/local-smoke/tabs-active.png",
    fullPage: true,
  });

  // Archived: B only — A is a draft too, and must not be here.
  await tabs.getByRole("tab", { name: /Archived/ }).click();
  await expect(page.getByRole("link", { name: "Questionnaire B" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Questionnaire A" })).toHaveCount(0);
  await expect(tabs.getByRole("tab", { name: /Archived/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // §4: the archived row says so, rather than leaving "draft" to imply it.
  await expect(page.getByText(/Archived \w+ \d+, \d{4}/)).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/tabs-archived.png",
    fullPage: true,
  });
});

test("§3 each section's filter is its own", async ({ page }) => {
  test.slow();
  await signup(page, "tabs-independent");
  await seed(page.request);

  await page.goto("/compliance/assessments");

  await questionnaireTabs(page).getByRole("tab", { name: /Archived/ }).click();

  // The audits section did not move.
  await expect(
    auditTabs(page).getByRole("tab", { name: /Active/ }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("link", { name: "Planned audit" })).toBeVisible();

  // And moving the audits filter does not move the questionnaires one.
  await auditTabs(page).getByRole("tab", { name: /Archived/ }).click();
  await expect(
    questionnaireTabs(page).getByRole("tab", { name: /Archived/ }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("No archived audits")).toBeVisible();
});

test("§16 §17 §9 archiving and restoring move the record, and survive a reload", async ({
  page,
}) => {
  test.slow();
  await signup(page, "tabs-move");
  const { a } = await seed(page.request);

  await page.goto("/compliance/assessments");
  const tabs = questionnaireTabs(page);

  // §16: archive A from the row menu.
  await page.getByRole("button", { name: /actions for Questionnaire A/i }).click();
  await page.getByRole("menuitem", { name: /archive/i }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: /^archive$/i }).click();
  await expect(dialog).toBeHidden({ timeout: 15_000 });

  await expect(page.getByRole("link", { name: "Questionnaire A" })).toHaveCount(0);
  await expect(tabs.getByRole("tab", { name: /Active/ })).toContainText("0");
  await expect(tabs.getByRole("tab", { name: /Archived/ })).toContainText("2");

  // §9: it is the server's state, not the page's.
  await page.reload();
  await expect(
    questionnaireTabs(page).getByRole("tab", { name: /Active/ }),
  ).toContainText("0");
  await questionnaireTabs(page).getByRole("tab", { name: /Archived/ }).click();
  await expect(page.getByRole("link", { name: "Questionnaire A" })).toBeVisible();

  // §6: an archived record offers Restore, not Archive.
  await page.getByRole("button", { name: /actions for Questionnaire A/i }).click();
  await expect(page.getByRole("menuitem", { name: /restore/i })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: /^archive$/i })).toHaveCount(0);

  // §17: restore, with the same record.
  await page.getByRole("menuitem", { name: /restore/i }).click();
  await expect(page.getByRole("link", { name: "Questionnaire A" })).toHaveCount(0, {
    timeout: 15_000,
  });

  await page.reload();
  await expect(page.getByRole("link", { name: "Questionnaire A" })).toBeVisible();

  const detail = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${a}`,
  );
  expect(detail.ok()).toBeTruthy();
  expect((await detail.json()).archived_at).toBeNull();

  // No duplicate was made along the way.
  const all = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires?archived=false`,
  );
  const titles = (await all.json()).map((q: { title: string }) => q.title);
  expect(titles.filter((t: string) => t === "Questionnaire A")).toHaveLength(1);
});

test("§14 the tabs work from the keyboard", async ({ page }) => {
  test.slow();
  await signup(page, "tabs-keyboard");
  await seed(page.request);

  await page.goto("/compliance/assessments");
  const tabs = questionnaireTabs(page);

  await tabs.getByRole("tab", { name: /Active/ }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(tabs.getByRole("tab", { name: /Archived/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(tabs.getByRole("tab", { name: /Archived/ })).toBeFocused();

  await page.keyboard.press("ArrowLeft");
  await expect(tabs.getByRole("tab", { name: /Active/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await page.keyboard.press("End");
  await expect(tabs.getByRole("tab", { name: /Archived/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

test("§10 an archived row shows both dimensions, and its menu fits its lifecycle", async ({
  page,
}) => {
  test.slow();
  await signup(page, "tabs-row");
  const { b } = await seed(page.request);

  await page.goto("/compliance/assessments");
  await questionnaireTabs(page).getByRole("tab", { name: /Archived/ }).click();

  // Scoped to the list. The tabs are also called "Archived", and a match
  // on either would not prove the row itself says anything.
  const panel = page.locator("#questionnaires-panel");

  // §1, §2: lifecycle is as visible as workflow status, not implied by
  // the absence of something.
  await expect(panel.getByText("Archived", { exact: true })).toBeVisible();
  await expect(panel.getByText("draft", { exact: true })).toBeVisible();
  await expect(panel.getByText(/Archived \w+ \d+, \d{4}/)).toBeVisible();

  // §4: archived offers where it lives and how to bring it back —
  // nothing that only makes sense for active work.
  await page.getByRole("button", { name: /actions for Questionnaire B/i }).click();
  await expect(page.getByRole("menuitem", { name: /^open$/i })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: /restore/i })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: /^archive$/i })).toHaveCount(0);
  await expect(page.getByRole("menuitem", { name: /delete/i })).toHaveCount(0);

  await page.screenshot({
    path: "test-results/local-smoke/tabs-archived-row.png",
    fullPage: true,
  });
  await page.keyboard.press("Escape");

  // §5: restoring keeps the workflow status exactly where it was.
  await page.getByRole("button", { name: /actions for Questionnaire B/i }).click();
  await page.getByRole("menuitem", { name: /restore/i }).click();

  await questionnaireTabs(page).getByRole("tab", { name: /Active/ }).click();
  await expect(page.getByRole("link", { name: "Questionnaire B" })).toBeVisible({
    timeout: 15_000,
  });
  // §3 of this task: no Archived badge, and no archived date, on an
  // active row. "Not archived" is the ordinary case and needs no saying.
  await expect(panel.getByText("Archived", { exact: true })).toHaveCount(0);
  await expect(panel.getByText(/Archived \w+ \d+, \d{4}/)).toHaveCount(0);

  const detail = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/questionnaires/${b}`,
  );
  const body = await detail.json();
  expect(body.archived_at).toBeNull();
  expect(body.status, "archiving is not a workflow transition").toBe("draft");

  // §4: an active draft offers Archive again.
  await page.getByRole("button", { name: /actions for Questionnaire B/i }).click();
  await expect(page.getByRole("menuitem", { name: /^archive$/i })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: /restore/i })).toHaveCount(0);
});
