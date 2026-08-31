import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** §28: the audit workflow, driven through the browser.
 *
 * Select a framework, let Veyntra prepare the audit, review an
 * exception, raise a finding from it, verify the fix, complete the
 * audit. The auditor reviews and decides; they do not reconstruct the
 * audit from four other screens.
 */
test("an audit opens on prepared work and completes through verification", async ({
  page,
}) => {
  test.slow();
  await signup(page, "audit");

  const frameworks = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/frameworks`,
  );
  const iso = (await frameworks.json()).find(
    (framework: { key: string }) => framework.key === "iso42001",
  );
  expect(iso, "ISO 42001 is in the catalog").toBeTruthy();

  // --- §2 create with a framework and a scope --------------------------
  await page.goto("/compliance/assessments");
  await page.getByRole("button", { name: "Create audit" }).first().click();
  await page.getByLabel("Framework").selectOption(iso.id);
  // Title and scope arrive from the framework; the auditor is a real
  // account, picked once the people list resolves.
  await expect(page.getByLabel("Audit title")).toHaveValue(
    "ISO 42001 Internal Audit",
  );
  const auditor = page.getByLabel("Auditor", { exact: true });
  await expect
    .poll(async () => await auditor.locator("option").count(), { timeout: 15_000 })
    .toBeGreaterThan(1);
  const [, colleague] = await auditor.locator("option").allTextContents();
  await auditor.selectOption({ label: colleague });
  await page.getByLabel("Scope").fill("AI governance controls and evidence for this engagement.");
  // The button says what it then does.
  await page.getByRole("button", { name: /Create (&|and) Prepare Audit/i }).click();

  // --- §20 the card says where the engagement stands -------------------
  const audits = page.locator("#audits-panel");
  await expect(
    audits.getByRole("link", { name: /ISO 42001 Internal Audit/ }),
  ).toBeVisible();
  await expect(audits.getByText(/0 \/ 18 reviewed/)).toBeVisible();
  await expect(audits.getByText("planned")).toBeVisible();
  // §1: a planned audit shows no completion date. That contradiction is
  // the bug this workflow was built around.
  await expect(audits.getByText(/Completed/)).toHaveCount(0);

  await page.screenshot({
    path: "test-results/local-smoke/audit-card.png",
    fullPage: false,
  });

  // --- §3/§19 the audit opens on prepared work -------------------------
  await audits.getByRole("link", { name: /ISO 42001 Internal Audit/ }).click();
  await expect(
    page.getByRole("heading", { name: "ISO 42001 Internal Audit" }),
  ).toBeVisible();
  await expect(page.getByText(/of 18 scoped requirements reviewed/)).toBeVisible();
  await expect(
    page.getByText("AI governance controls and evidence for this engagement."),
  ).toBeVisible();
  // §5: exceptions are the default view, grouped.
  await expect(page.getByRole("tab", { name: /Needs attention/ })).toBeVisible();
  await expect(page.getByText(/Known gaps · /)).toBeVisible();

  // §1/§4/§18: the three things counted apart, each with its own name.
  await expect(page.getByText("Auditor conclusions")).toBeVisible();
  await expect(page.getByText("Remediation").first()).toBeVisible();
  await expect(page.getByText(/18 in scope/)).toBeVisible();
  await expect(page.getByRole("button", { name: "View scope" })).toBeVisible();

  // A row names both claims rather than showing two bare badges.
  await expect(page.getByText("Evidence state").first()).toBeVisible();

  // §17: what is standing in the way, before anybody clicks.
  await expect(page.getByText("Not ready to complete")).toBeVisible();
  await expect(
    page.getByText(/18 scoped requirements have no auditor decision yet/),
  ).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/audit-workspace.png",
    fullPage: false,
  });

  // --- §29 planned -> in progress --------------------------------------
  await page.getByRole("button", { name: "Start audit" }).click();
  await expect(page.getByText("Started")).toBeVisible();

  // --- §6/§8 review an exception ---------------------------------------
  await expect(page.getByText("4.1").first()).toBeVisible();

  // §8: a finding needs a reason, and the form asks for it.
  await page.getByRole("button", { name: "Major finding" }).first().click();
  await expect(page.getByText(/Major finding — reason/)).toBeVisible();
  await page
    .getByLabel(/Major finding — reason/)
    .fill(
      "The AI risk process is documented, but no evidence of periodic execution was found.",
    );
  await page.getByRole("button", { name: /Record major finding/ }).click();

  // --- §9 the finding carries its context ------------------------------
  await page.getByRole("tab", { name: /Findings/ }).click();
  await expect(page.getByText("4.1", { exact: false }).first()).toBeVisible();
  await expect(page.getByText(/no evidence of periodic execution/i)).toBeVisible();

  // --- §15/§16 verification --------------------------------------------
  await page.getByRole("button", { name: "Mark remediation done" }).click();
  await expect(page.getByText("ready for verification")).toBeVisible();

  await page.getByRole("button", { name: "Verify and close" }).first().click();
  await page
    .getByLabel("What you checked, and what it showed")
    .fill(
      "New quarterly AI risk review record demonstrates the process is now operating.",
    );
  await page.getByRole("button", { name: "Verify and close" }).last().click();
  await expect(page.getByText(/Closed \w+ \d+, \d{4}/)).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/audit-finding.png",
    fullPage: false,
  });

  // --- §17 completion is still gated on the unreviewed rows ------------
  await expect(page.getByText("Not ready to complete")).toBeVisible();
  await expect(page.getByRole("button", { name: "Complete audit" })).toBeDisabled();

  // --- §16 refresh: the server holds all of it -------------------------
  await page.reload();
  await page.getByRole("tab", { name: /Findings/ }).click();
  await expect(page.getByText(/Closed \w+ \d+, \d{4}/)).toBeVisible();
});

test("an audit opened without a framework can be scoped from its own page", async ({
  page,
}) => {
  test.slow();
  await signup(page, "auditscope");

  // The shape the reported audit was in: a title, and nothing to scope
  // against. Abandoning it for a second audit of the same engagement is
  // a worse answer than attaching the framework somebody meant.
  const created = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/audits`,
    { data: { title: "ISO 42001 Internal Audit", auditor_name: "Zach Warren" } },
  );
  const auditId = (await created.json()).id;

  await page.goto(`/compliance/audits/${auditId}`);
  await expect(
    page.getByText("This audit has nothing to scope against"),
  ).toBeVisible();

  await page.getByLabel("Framework").selectOption({ label: "ISO 42001" });
  await page.getByLabel("Scope").fill("AI governance controls and evidence");
  await page.getByRole("button", { name: "Prepare audit" }).click();

  await expect(page.getByText(/of 18 scoped requirements reviewed/)).toBeVisible();
  await expect(page.getByText("AI governance controls and evidence")).toBeVisible();
});
