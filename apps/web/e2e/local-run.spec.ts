import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** A walk through the running product, ending in a screenshot of each
 * screen. Not an acceptance test — the specs beside it do that. This is
 * what a person sees when the stack is up, captured so it can be looked
 * at rather than described.
 */
test("walk the running product", async ({ page }) => {
  test.slow();
  await signup(page, "localrun");

  const shot = async (name: string) => {
    await page.waitForTimeout(900);
    await page.screenshot({
      path: `test-results/local-smoke/run-${name}.png`,
      fullPage: false,
    });
  };

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: /Dashboard|Overview/ })).toBeVisible();
  await shot("dashboard");

  await page.goto("/compliance");
  await expect(
    page.getByRole("heading", { name: "Compliance Overview" }),
  ).toBeVisible();
  await shot("compliance");

  // Build a completed audit so the report workflow has something real to
  // stand on, then walk the screens it added.
  const frameworks = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/frameworks`,
  );
  const iso = (await frameworks.json()).find(
    (framework: { key: string }) => framework.key === "iso42001",
  );
  const audit = await (
    await page.request.post(`${API_BASE_URL}/api/v1/compliance/audits`, {
      data: {
        title: "ISO 42001 Internal Audit",
        framework_id: iso.id,
        auditor_name: "Zach Warren",
        scope:
          "AI governance, risk management, roles and responsibilities, and the evidence behind them.",
      },
    })
  ).json();

  await page.goto("/compliance/assessments");
  await expect(page.locator("#audits-panel")).toBeVisible();
  await shot("assessments");

  await page.request.patch(
    `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/status`,
    { data: { status: "in_progress" } },
  );
  const items = await (
    await page.request.get(
      `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/items`,
    )
  ).json();

  await page.goto(`/compliance/audits/${audit.id}`);
  await expect(page.getByText(/of 18 scoped requirements reviewed/)).toBeVisible();
  await shot("audit-workspace");

  for (const [index, item] of items.entries()) {
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/items/${item.id}/decision`,
      {
        data: {
          decision: index === 0 ? "minor" : "observation",
          note:
            index === 0
              ? "The process is documented but no evidence of periodic execution was found."
              : "Noted for the next review cycle.",
        },
      },
    );
  }
  await page.request.patch(
    `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/status`,
    { data: { status: "completed" } },
  );

  await page.goto(`/compliance/audits/${audit.id}`);
  await expect(
    page.getByRole("button", { name: "Preview audit report" }),
  ).toBeVisible();
  await shot("audit-completed");

  await page.getByRole("button", { name: "Preview audit report" }).click();
  await expect(page.getByRole("dialog").getByText("Known limitations")).toBeVisible();
  await shot("audit-report-preview");

  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Generate PDF" })
    .click();
  await expect(page.getByText(/Internal Audit Report · Version 1/)).toBeVisible();
  await shot("audit-report-issued");

  await page.goto("/review");
  await shot("review-center");

  await page.goto("/documents");
  await shot("documents");
});
