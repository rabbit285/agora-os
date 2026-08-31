import { expect, test } from "@playwright/test";
import { signup } from "./helpers";

/** The reported failure, guarded at the boundary it crossed.
 *
 * "Every framework fails when selected during audit creation" was an
 * AttributeError in evidence resolution, and it is pinned per framework
 * in `tests/test_audit_framework_pipeline.py`, which runs all seven with
 * evidence actually attached — the condition that made it fire.
 *
 * What only a browser can check is the other half: that the form sends
 * a framework the API accepts, and that the audit comes back prepared.
 */
test("the form sends a framework the API accepts, and the audit comes back prepared", async ({
  page,
}) => {
  test.slow();
  await signup(page, "reprofw");

  const failures: string[] = [];
  page.on("response", async (response) => {
    if (
      response.url().includes("/compliance/audits") &&
      response.status() >= 400
    ) {
      let body = "";
      try {
        body = (await response.text()).slice(0, 300);
      } catch {
        body = "(unreadable)";
      }
      failures.push(
        `${response.request().method()} ${response.url()} -> ${response.status()} ${body}`,
      );
    }
  });

  let sent: string | null = null;
  page.on("request", (request) => {
    if (
      request.url().includes("/compliance/audits") &&
      request.method() === "POST"
    ) {
      sent = request.postData();
    }
  });

  await page.goto("/compliance/assessments");
  await page.getByRole("button", { name: "Create audit" }).first().click();

  const frameworkSelect = page.getByLabel("Framework");
  await expect
    .poll(async () => await frameworkSelect.locator("option").count(), {
      timeout: 15_000,
    })
    .toBeGreaterThan(2);
  const labels = await frameworkSelect.locator("option").allTextContents();
  // Every framework in the catalog is offered, not a hand-picked subset.
  expect(labels.length).toBeGreaterThan(5);

  await frameworkSelect.selectOption({ label: "GDPR" });

  const auditor = page.getByLabel("Auditor", { exact: true });
  await expect
    .poll(async () => await auditor.locator("option").count(), {
      timeout: 15_000,
    })
    .toBeGreaterThan(1);
  const [, colleague] = await auditor.locator("option").allTextContents();
  await auditor.selectOption({ label: colleague });

  await page
    .getByRole("button", { name: /Create (&|and) Prepare Audit/i })
    .click();

  const audits = page.locator("#audits-panel");
  await expect(
    audits.getByRole("link", { name: /GDPR Internal Audit/ }),
  ).toBeVisible();
  // Prepared, which is the whole point of choosing a framework — and the
  // step that used to raise.
  await expect(audits.getByText(/0 \/ \d+ reviewed/)).toBeVisible();

  // A catalog UUID, which is what the API expects — not a key or a slug.
  expect(sent, "the create request was sent").toBeTruthy();
  expect(sent).toMatch(
    /"framework_id":"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"/,
  );
  expect(
    failures,
    `audit requests failed: ${failures.join(" | ")}`,
  ).toHaveLength(0);

  await page.screenshot({
    path: "test-results/local-smoke/repro-audit.png",
    fullPage: false,
  });
});
