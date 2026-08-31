import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** §1–§8: the completed audit's last step, in the browser.
 *
 * A completed audit used to end at 18/18 reviewed with nowhere to go.
 * These drive what a person actually does: open the completed audit, see
 * the next action in the header, read the report, and only then issue it.
 *
 * The audit is driven to `completed` over the API because that part is
 * already pinned elsewhere — `audit-workspace.spec.ts` walks it through
 * the UI. What only a browser can prove is the half after it.
 */
async function completedAudit(page: import("@playwright/test").Page) {
  const frameworks = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/frameworks`,
  );
  const iso = (await frameworks.json()).find(
    (framework: { key: string }) => framework.key === "iso42001",
  );

  const created = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/audits`,
    {
      data: {
        title: "ISO 42001 Internal Audit",
        framework_id: iso.id,
        auditor_name: "Zach Warren",
        scope: "AI governance controls and the evidence behind them.",
      },
    },
  );
  const audit = await created.json();

  await page.request.patch(
    `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/status`,
    { data: { status: "in_progress" } },
  );
  const items = await (
    await page.request.get(
      `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/items`,
    )
  ).json();
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
  return audit.id as string;
}

test("§8 a completed audit goes preview → generate → download", async ({
  page,
}) => {
  test.slow();
  await signup(page, "auditreport");
  const auditId = await completedAudit(page);

  await page.goto(`/compliance/audits/${auditId}`);

  // §1: the next action is in the header, beside the status, not behind
  // a menu. Reviewing everything and having nowhere to go is where this
  // page stopped.
  await expect(page.getByText("completed").first()).toBeVisible();
  const preview = page.getByRole("button", { name: "Preview audit report" });
  await expect(preview).toBeVisible();

  // Nothing has been generated, so there is nothing to list yet.
  await expect(page.getByText("Generated reports")).toHaveCount(0);

  await preview.click();

  // §2: a preview, not a PDF — and the same sections, in the same order,
  // as the document it will produce.
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("This is the report as it will be issued"),
  ).toBeVisible();
  for (const heading of [
    "1. Audit information",
    "2. Executive summary",
    "3. Scope and methodology",
    "4. Audit results summary",
    "5. Findings",
    "6. Remediation and verification",
    "7. Evidence index",
    "8. Known limitations",
    "9. Auditor sign-off",
    "Appendix A — Requirement-by-requirement results",
  ]) {
    await expect(dialog.getByText(heading, { exact: true })).toBeVisible();
  }
  await expect(dialog.getByText("ISO 42001", { exact: false }).first()).toBeVisible();
  await expect(dialog.getByText("Zach Warren").first()).toBeVisible();
  await expect(dialog.getByText("Confidential").first()).toBeVisible();

  // §2: the result in sentences, before any table.
  await expect(
    dialog.getByText(
      /This internal audit assessed 18 ISO 42001 requirements within the defined scope/,
    ),
  ).toBeVisible();
  await expect(
    dialog.getByText(/No major or critical findings were raised/),
  ).toBeVisible();
  await expect(dialog.getByText("18 / 18")).toBeVisible();

  // §9: every conclusion on the scale, zeros included.
  for (const conclusion of ["No finding", "Minor finding", "Critical finding"]) {
    await expect(dialog.getByText(conclusion, { exact: true }).first()).toBeVisible();
  }

  // §4/§10: the requirement is the subject of a finding, not the
  // diagnostic sentence that explained the evidence state.
  await expect(dialog.getByText(/^Minor findings \(1\)$/)).toBeVisible();
  await expect(
    dialog.getByText("4.1 — Understanding the organization and its context"),
  ).toBeVisible();
  await expect(dialog.getByText("itemised expectation set")).toHaveCount(0);

  // §3/§13: the two clocks, both named.
  await expect(dialog.getByText("Auditor conclusion").first()).toBeVisible();
  await expect(dialog.getByText("Current remediation").first()).toBeVisible();
  await expect(dialog.getByText("Veyntra assessment").first()).toBeVisible();

  // §15: the appendix column says what it means.
  await expect(
    dialog.getByText("Current remediation status", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByText("Evidence state at audit", { exact: true }).first(),
  ).toBeVisible();

  // §8: the methodology, and what it says Veyntra did not conclude.
  await expect(
    dialog.getByText(/it is not an audit conclusion/),
  ).toBeVisible();

  // §4: the disclaimer, in the words the product stands behind.
  await expect(
    dialog.getByText(
      /This report represents an internal audit based on the scope and evidence recorded in Veyntra\. It is not an independent certification or legal opinion\./,
    ),
  ).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/audit-report-preview.png",
    fullPage: false,
  });

  // §5: only now.
  await dialog.getByRole("button", { name: "Generate PDF" }).click();

  // §6: the issued report, and what it says about itself.
  await expect(page.getByText("Generated reports")).toBeVisible();
  await expect(
    page.getByText(/Internal Audit Report · Version 1/),
  ).toBeVisible();
  await expect(page.getByText(/PDF · Generated/)).toBeVisible();
  await expect(page.getByText(/18 requirements reviewed · 18 findings/)).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/audit-report-generated.png",
    fullPage: false,
  });

  // §10: a real user can open the file. The button asks the API for a
  // signed, time-limited link and opens it; a PDF popup renders no DOM,
  // so the test follows the link the click actually produced rather
  // than inspecting a blank window.
  const [linkResponse] = await Promise.all([
    page.waitForResponse((response) =>
      response.url().includes("/reports/") && response.url().endsWith("/download"),
    ),
    page.locator("#generated-reports").getByRole("button", { name: "View" }).click(),
  ]);
  const link = await linkResponse.json();
  expect(link.filename).toContain(".pdf");
  const fetched = await page.request.get(link.url);
  expect(fetched.status()).toBe(200);
  expect((await fetched.body()).subarray(0, 5).toString()).toBe("%PDF-");

  // And Download offers the same file rather than a second artifact.
  const [downloadResponse] = await Promise.all([
    page.waitForResponse((response) =>
      response.url().includes("/reports/") && response.url().endsWith("/download"),
    ),
    page.locator("#generated-reports").getByRole("button", { name: "Download" }).click(),
  ]);
  expect((await downloadResponse.json()).filename).toBe(link.filename);
});

test("§7 opening the preview and cancelling generates nothing", async ({
  page,
}) => {
  test.slow();
  await signup(page, "auditcancel");
  const auditId = await completedAudit(page);

  await page.goto(`/compliance/audits/${auditId}`);
  await page.getByRole("button", { name: "Preview audit report" }).click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("8. Known limitations")).toBeVisible();

  // Back, which is what a person clicks when they were only looking.
  await dialog.getByRole("button", { name: "Back" }).click();
  await expect(dialog).toHaveCount(0);

  // No PDF, no record, no section.
  await expect(page.getByText("Generated reports")).toHaveCount(0);
  const reports = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/audits/${auditId}/reports`,
  );
  expect(await reports.json()).toEqual([]);

  // And no generation event in the trail.
  const events = await page.request.get(
    `${API_BASE_URL}/api/v1/audit-events?action_prefix=compliance.audit_report&limit=50`,
  );
  expect(await events.json()).toEqual([]);
});

test("§6 remediation moves, version 1 does not", async ({ page }) => {
  test.slow();
  await signup(page, "auditversion");
  const auditId = await completedAudit(page);

  await page.goto(`/compliance/audits/${auditId}`);
  await page.getByRole("button", { name: "Preview audit report" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Generate PDF" })
    .click();
  await expect(page.getByText(/Internal Audit Report · Version 1/)).toBeVisible();

  // The team fixes the minor finding and the auditor verifies it. A
  // completed audit is read-only on screen — correctly, because an audit
  // that closed is not still being conducted — so this happens the way
  // it happens in life: afterwards, through the endpoints the
  // remediation board uses.
  const detail = await (
    await page.request.get(
      `${API_BASE_URL}/api/v1/compliance/audits/${auditId}`,
    )
  ).json();
  const minor = detail.findings.find(
    (finding: { severity: string }) => finding.severity === "medium",
  );
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/audits/${auditId}/findings/${minor.id}/verify`,
    {
      data: {
        note: "A quarterly review record now demonstrates the process operating.",
      },
    },
  );

  await page.reload();

  // §6: the report is unchanged, and says so rather than quietly
  // updating itself.
  await expect(
    page.getByText("Audit/remediation has changed since this report was generated."),
  ).toBeVisible();
  await expect(page.getByText(/Internal Audit Report · Version 1/)).toBeVisible();

  // The CTA now offers the updated one.
  const updated = page.getByRole("button", { name: "Preview updated report" });
  await expect(updated).toBeVisible();
  await updated.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Report version").first()).toBeVisible();
  await expect(dialog.getByText("2", { exact: true }).first()).toBeVisible();
  await dialog.getByRole("button", { name: "Generate new version" }).click();

  // Both versions, and version 1 still reporting what it reported.
  await expect(page.getByText(/Internal Audit Report · Version 2/)).toBeVisible();
  await expect(page.getByText(/Internal Audit Report · Version 1/)).toBeVisible();
});

test("§9 a replaced conclusion is kept, labelled, and out of the count", async ({
  page,
}) => {
  test.slow();
  await signup(page, "auditsuperseded");

  // The exact shape behind "18 conclusions, 19 findings": an observation
  // verified and closed, then revised to a minor finding.
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

  const decide = (itemId: string, decision: string, note: string) =>
    page.request.post(
      `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/items/${itemId}/decision`,
      { data: { decision, note } },
    );

  const first = await (
    await decide(items[0].id, "observation", "Noted for the next cycle.")
  ).json();
  const findingId = first.finding?.id ?? first.finding_id;
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/findings/${findingId}/verify`,
    { data: { note: "Closed after review." } },
  );
  // The auditor changes their mind about that same requirement.
  await decide(
    items[0].id,
    "minor",
    "On reflection this is a minor nonconformity, not an observation.",
  );
  for (const item of items.slice(1)) {
    await decide(item.id, "observation", "Noted for the next cycle.");
  }
  await page.request.patch(
    `${API_BASE_URL}/api/v1/compliance/audits/${audit.id}/status`,
    { data: { status: "completed" } },
  );

  await page.goto(`/compliance/audits/${audit.id}`);

  // 18 conclusions, 18 findings — and the 19th row accounted for.
  await expect(page.getByText(/of 18 scoped requirements reviewed/)).toBeVisible();
  await expect(page.getByRole("tab", { name: "Findings (18)" })).toBeVisible();

  await page.getByRole("tab", { name: /Findings/ }).click();
  await expect(page.getByText("Replaced conclusions (1)")).toBeVisible();
  await expect(
    page.getByText(/retained for traceability and are not counted as findings/),
  ).toBeVisible();

  // And the report says the same thing.
  await page.getByRole("button", { name: "Preview audit report" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Conclusions replaced")).toBeVisible();
  await expect(dialog.getByText("Replaced conclusions")).toBeVisible();
  // §9: the live count excludes it, and the summary reconciles.
  await expect(dialog.getByText("18 / 18")).toBeVisible();
  await expect(
    dialog.getByText(/1 earlier conclusion was replaced during the audit/),
  ).toBeVisible();
});
