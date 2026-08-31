import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** A walk through the product as a person meets it.
 *
 * Not a feature test — those live beside the features. This is the
 * "is it actually running" pass: sign up, land on the dashboard, and
 * visit the screens this session has been changing, checking each one
 * renders its own content rather than a spinner or an error boundary.
 */
test("the product runs, and the screens this session touched render", async ({
  page,
}) => {
  test.slow();

  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(String(error)));

  await signup(page, "smokerun");
  // A brand-new organization lands on onboarding, not the dashboard —
  // the product has nothing to show until it knows who it is working for.
  await expect(page.getByRole("heading", { name: "Set up Veyntra" })).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/run-onboarding.png",
    fullPage: false,
  });

  await page.goto("/dashboard");
  // The nav calls it Dashboard; the page calls itself what it is.
  await expect(
    page.getByRole("heading", { name: "Compliance Overview" }),
  ).toBeVisible();
  await expect(page.getByText("Compliance readiness")).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/run-dashboard.png",
    fullPage: false,
  });

  // --- a customer questionnaire, answered and approved -----------------
  const created = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/questionnaires`,
    {
      data: {
        title: "Agora Origin Security Questionnaire",
        source: "customer_provided",
        customer_name: "Agora Origin",
      },
    },
  );
  expect(created.ok(), await created.text()).toBeTruthy();
  const questionnaireId = (await created.json()).id;

  for (const [text, answer] of [
    [
      "Do you have an incident-response process?",
      "Yes. The organization maintains a documented incident-response process; however, current evidence does not demonstrate completion of the most recent tabletop exercise.",
    ],
    ["Do you encrypt customer data at rest?", "Yes. AES-256 with managed keys."],
  ] as const) {
    const question = await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${questionnaireId}/questions`,
      { data: { text, category: "security" } },
    );
    await page.request.patch(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${questionnaireId}/questions/${
        (await question.json()).id
      }/answer`,
      { data: { answer_text: answer, status: "approved" } },
    );
  }

  // --- an audit, prepared from the framework ---------------------------
  const frameworks = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/frameworks`,
  );
  const iso = (await frameworks.json()).find(
    (framework: { key: string }) => framework.key === "iso42001",
  );
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/audits`, {
    data: {
      title: "ISO 42001 Internal Audit",
      framework_id: iso.id,
      auditor_name: "Zach Warren",
      scope: "AI governance controls and evidence",
    },
  });

  // --- Assessments: all three sections, with real state ----------------
  await page.goto("/compliance/assessments");
  await expect(
    page.getByRole("heading", { name: "Assessments" }),
  ).toBeVisible();
  await expect(
    page
      .locator("#questionnaires-panel")
      .getByText("Agora Origin Security Questionnaire"),
  ).toBeVisible();
  await expect(
    page.locator("#audits-panel").getByText(/0 \/ 18 reviewed/),
  ).toBeVisible();
  await expect(
    page
      .locator("#security-reviews-panel")
      .getByRole("link", { name: /Agora Origin Security Review/ }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/run-assessments.png",
    fullPage: false,
  });

  // --- the engagement, with its export action --------------------------
  await page
    .locator("#security-reviews-panel")
    .getByRole("link", { name: /Agora Origin Security Review/ })
    .click();
  await expect(
    page.getByRole("heading", { name: "Agora Origin Security Review" }),
  ).toBeVisible();
  await expect(page.getByText(/of 2 approved across 1 questionnaire/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Export / Share" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/run-review.png",
    fullPage: false,
  });

  // --- the audit workspace ---------------------------------------------
  await page.goto("/compliance/assessments");
  await page
    .locator("#audits-panel")
    .getByRole("link", { name: /ISO 42001 Internal Audit/ })
    .click();
  await expect(
    page.getByText(/of 18 scoped requirements reviewed/),
  ).toBeVisible();
  await expect(page.getByRole("tab", { name: /Needs attention/ })).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/run-audit.png",
    fullPage: false,
  });

  // --- the rest of the compliance navigation ---------------------------
  for (const [path, heading] of [
    ["/documents", "Documents"],
    ["/compliance/frameworks", "Frameworks"],
    ["/compliance/controls", "Controls & Risk"],
    ["/compliance/policies", "Policies"],
    ["/review", "Review Center"],
    // /reports is deliberately 404 — the route went with the sales and
    // support modules, though its page file is still on disk.
  ] as const) {
    await page.goto(path);
    await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
  }

  // A screen that renders is not the same as one that renders cleanly.
  const real = errors.filter(
    (message) =>
      !/favicon|Download the React DevTools|hydrat/i.test(message),
  );
  expect(real, `console errors: ${real.join(" | ")}`).toHaveLength(0);
});
