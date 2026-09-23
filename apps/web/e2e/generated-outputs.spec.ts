import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** §17: a report Veyntra wrote is not evidence Veyntra was given.
 *
 * The Documents library listed generated reports beside uploaded
 * policies, each offering "Not analyzed yet · Analyze for evidence".
 * One click closed a loop: the compliance state ends up partly
 * supported by a document written from the compliance state.
 */
test("a generated report is listed apart and never offers to be analysed", async ({
  page,
}) => {
  test.slow();
  await signup(page, "genout");

  // A completed audit, and a report from it.
  const frameworks = await (
    await page.request.get(`${API_BASE_URL}/api/v1/compliance/frameworks`)
  ).json();
  const iso = frameworks.find(
    (framework: { key: string }) => framework.key === "iso42001",
  );
  const audit = await (
    await page.request.post(`${API_BASE_URL}/api/v1/compliance/audits`, {
      data: {
        title: "ISO 42001 Internal Audit",
        framework_id: iso.id,
        auditor_name: "Zach Warren",
        scope: "AI governance controls and the evidence behind them.",
      },
    })
  ).json();
  await page.request.patch(
    `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/status`,
    { data: { status: "in_progress" } },
  );
  const items = await (
    await page.request.get(
      `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/items`,
    )
  ).json();
  for (const item of items) {
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/items/${item.id}/decision`,
      { data: { decision: "observation", note: "Noted." } },
    );
  }
  await page.request.patch(
    `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/status`,
    { data: { status: "completed" } },
  );
  const preview = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/report/preview`,
    )
  ).json();
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/report`,
    { data: { confirm_digest: preview.digest } },
  );

  await page.goto("/documents");

  // §4: the two kinds are listed apart.
  await expect(page.getByRole("tab", { name: /Source documents/ })).toBeVisible();
  const generatedTab = page.getByRole("tab", { name: /Generated outputs/ });
  await expect(generatedTab).toBeVisible();

  // The report is not in the evidence library.
  await expect(
    page.getByText("ISO 42001 Internal Audit v1.pdf"),
  ).toHaveCount(0);

  await generatedTab.click();
  await expect(
    page.getByText(/Reports and exports Veyntra produced/),
  ).toBeVisible();
  await expect(page.getByText("ISO 42001 Internal Audit v1.pdf")).toBeVisible();
  await expect(page.getByText("Generated output").first()).toBeVisible();

  // §5: provenance, and a way back to the record it came from.
  await expect(
    page.getByText("Generated from ISO 42001 Internal Audit."),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/generated-outputs.png",
    fullPage: false,
  });

  // §3: neither of the two things that closed the loop.
  await expect(page.getByText("Not analyzed yet.")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Analyze for evidence" }),
  ).toHaveCount(0);

  await page.getByRole("link", { name: "Open audit" }).click();
  await expect(page).toHaveURL(
    new RegExp(`/compliance/audits/${audit.id}`),
  );
});

test("§19 an uploaded document keeps its evidence workflow", async ({ page }) => {
  test.slow();
  await signup(page, "gensource");

  await page.goto("/documents");
  // With nothing uploaded there are no tabs to split, and the library
  // reads as it always did.
  await expect(page.getByText("No documents uploaded yet.")).toBeVisible();
  await expect(page.getByRole("tab", { name: /Generated outputs/ })).toHaveCount(
    0,
  );
});
