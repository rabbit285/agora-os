import { expect, test } from "@playwright/test";
import { signup } from "./helpers";

/** §15–§18: the Create Audit form, framework first.
 *
 * The framework is what makes an audit preparable, so it is the choice
 * the form is built around. "Custom / No framework" used to be the
 * default, which made the path that prepares nothing look like the
 * normal one.
 */
async function openForm(page: import("@playwright/test").Page) {
  await page.goto("/compliance/assessments");
  await page.getByRole("button", { name: "Create audit" }).first().click();
  // The catalog arrives from its own query; reading before it resolves
  // measures the race rather than the form.
  await expect
    .poll(async () => await page.getByLabel("Framework").locator("option").count(), {
      timeout: 15_000,
    })
    .toBeGreaterThan(2);
}

test("§15 nothing is chosen until somebody chooses", async ({ page }) => {
  test.slow();
  await signup(page, "cadefault");
  await openForm(page);

  const framework = page.getByLabel("Framework");
  // The default is a prompt, not a path.
  await expect(framework).toHaveValue("");
  const options = await framework.locator("option").allTextContents();
  expect(options[0]).toBe("Select framework…");
  // And custom is last, where an alternative belongs.
  expect(options[options.length - 1]).toBe("Custom / No framework");

  // §2: labels that survive typing.
  for (const label of ["Audit title", "Framework", "Auditor", "Scope"]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }

  // §10: the CTA waits for what it needs.
  await expect(
    page.getByRole("button", { name: /Create & Prepare Audit/ }),
  ).toBeDisabled();
});

test("§16 choosing a framework fills the form and prepares the audit", async ({
  page,
}) => {
  test.slow();
  await signup(page, "caframework");
  await openForm(page);

  await page.getByLabel("Framework").selectOption({ label: "ISO 42001" });

  // §9/§8: a title and a scope that match the standard, both editable.
  await expect(page.getByLabel("Audit title")).toHaveValue(
    "ISO 42001 Internal Audit",
  );
  await expect(page.getByLabel("Scope")).toHaveValue(/AI governance/);

  // §4: the helper text says what the button will do.
  await expect(
    page.getByText(/prepare applicable requirements, controls, current evidence/),
  ).toBeVisible();

  // §7: a colleague, not free text. The people list is its own query,
  // so wait for it rather than racing it.
  const auditor = page.getByLabel("Auditor", { exact: true });
  await expect
    .poll(async () => await auditor.locator("option").count(), { timeout: 15_000 })
    .toBeGreaterThan(1);
  // Whoever signed up — the helper names them after the test, and the
  // point is that a real account is offered, not which one.
  const [, colleague] = await auditor.locator("option").allTextContents();
  await auditor.selectOption({ label: colleague });

  await page.getByLabel("Scope").scrollIntoViewIfNeeded();
  await page.screenshot({
    path: "test-results/local-smoke/create-audit-framework.png",
    fullPage: false,
  });

  const cta = page.getByRole("button", { name: /Create & Prepare Audit/ });
  await expect(cta).toBeEnabled();
  await cta.click();

  const audits = page.locator("#audits-panel");
  await expect(
    audits.getByRole("link", { name: /ISO 42001 Internal Audit/ }),
  ).toBeVisible();
  // §3/§12: prepared, and Planned until somebody starts it.
  await expect(audits.getByText(/0 \/ 18 reviewed/)).toBeVisible();
  await expect(audits.getByText("planned")).toBeVisible();
});

test("§17 custom is an explicit alternative with its own flow", async ({
  page,
}) => {
  test.slow();
  await signup(page, "cacustom");
  await openForm(page);

  await page.getByLabel("Framework").selectOption({ label: "Custom / No framework" });

  // §5/§6: the field becomes a type, and the wording stops claiming a
  // custom audit "scopes itself".
  await expect(page.getByText("Audit type", { exact: true })).toBeVisible();
  await expect(
    page.getByText(/Custom audits are scoped manually\./),
  ).toBeVisible();
  await expect(
    page.getByText(/A custom audit scopes itself/),
  ).toHaveCount(0);

  // §5: no framework wording is suggested for a scope only they know.
  await expect(page.getByLabel("Scope")).toHaveValue("");

  const cta = page.getByRole("button", { name: "Create Custom Audit" });
  await expect(cta).toBeDisabled();

  await page.getByLabel("Audit title").fill("Frankfurt datacentre walkthrough");
  // The auditor is internal by default and external by an explicit
  // choice, so the report never has to infer which somebody meant.
  await page.getByRole("button", { name: "Use external auditor" }).click();
  await page.getByLabel("External auditor", { exact: true }).fill("Jane Smith");
  await page
    .getByLabel("External auditor organization")
    .fill("ABC Compliance Ltd.");
  await page
    .getByLabel("Scope")
    .fill("Physical access controls at the Frankfurt colocation facility.");

  await expect(cta).toBeEnabled();
  await page.screenshot({
    path: "test-results/local-smoke/create-audit-custom.png",
    fullPage: false,
  });
  await cta.click();

  const audits = page.locator("#audits-panel");
  await expect(
    audits.getByRole("link", { name: /Frankfurt datacentre walkthrough/ }),
  ).toBeVisible();
  // §17: a custom audit does not report framework requirement counts.
  await expect(audits.getByText(/\d+ \/ \d+ reviewed/)).toHaveCount(0);
});

test("§18 switching framework never silently overwrites a written scope", async ({
  page,
}) => {
  test.slow();
  await signup(page, "caswitch");
  await openForm(page);

  await page.getByLabel("Framework").selectOption({ label: "ISO 42001" });
  const scope = page.getByLabel("Scope");
  await expect(scope).toHaveValue(/AI governance/);

  // The auditor writes their own.
  const mine = "A limited review of model change management only.";
  await scope.fill(mine);

  await page.getByLabel("Framework").selectOption({ label: "GDPR" });

  // Their words stand, and the swap is offered rather than performed.
  await expect(scope).toHaveValue(mine);
  await expect(
    page.getByText(/You have written your own scope/),
  ).toBeVisible();

  await page.getByRole("button", { name: "Keep mine" }).click();
  await expect(scope).toHaveValue(mine);

  // Offered again on the next switch, and accepted this time.
  await page.getByLabel("Framework").selectOption({ label: "ISO 42001" });
  await page.getByRole("button", { name: "Use suggested scope" }).click();
  await expect(scope).toHaveValue(/AI governance/);
});

test("§16/§18 the auditor is internal by default, external only by choice", async ({
  page,
}) => {
  test.slow();
  await signup(page, "caidentity");
  await openForm(page);

  // Internal is the ordinary case, and the picker is the primary input.
  const auditor = page.getByLabel("Auditor", { exact: true });
  await expect
    .poll(async () => await auditor.locator("option").count(), { timeout: 15_000 })
    .toBeGreaterThan(1);
  const options = await auditor.locator("option").allTextContents();
  expect(options[0]).toBe("Select team member…");
  // The old form's blank option meant "external", which is what let a
  // colleague's audit be reported as externally conducted.
  expect(options).not.toContain("External auditor…");

  let sent: string | null = null;
  page.on("request", (request) => {
    if (
      request.url().includes("/compliance/audits") &&
      request.method() === "POST"
    ) {
      sent = request.postData();
    }
  });

  await page.getByLabel("Framework").selectOption({ label: "ISO 42001" });
  const [, colleague] = options;
  await auditor.selectOption({ label: colleague });
  await page.getByRole("button", { name: /Create (&|and) Prepare Audit/i }).click();

  const audits = page.locator("#audits-panel");
  await expect(
    audits.getByRole("link", { name: /ISO 42001 Internal Audit/ }),
  ).toBeVisible();
  expect(sent).toContain('"auditor_type":"internal"');

  // And the audit says internal on its own page — never "(external)".
  await audits.getByRole("link", { name: /ISO 42001 Internal Audit/ }).click();
  await expect(page.getByText(/Internal auditor/)).toBeVisible();
  await expect(page.getByText(/external/i)).toHaveCount(0);
});
