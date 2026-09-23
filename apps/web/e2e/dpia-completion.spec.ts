import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** §22/§23/§30: finishing a DPIA, and what it says once finished.
 *
 * Completion is a gate. Everything outstanding is listed together so the
 * work can be finished in one pass, and what gets frozen is the record
 * of what was concluded — not a status word.
 */
test("a DPIA completes only when everything is recorded, then freezes", async ({
  page,
}) => {
  test.slow();
  await signup(page, "dpiadone");

  const activity = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/processing-activities`,
      {
        data: {
          name: "Support ticket triage",
          purpose: "Route incoming customer support tickets to the right team.",
          legal_basis: "contract",
          data_subjects: "Customers",
          // Completion now needs a retention period; the free-text
          // category keeps one candidate risk in play so the review
          // these specs are about still happens.
          data_categories: ["Contact details", "Support conversation content"],
          retention_period: "12 months",
        },
      },
    )
  ).json();

  const screened = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/dpias/screening/start`,
      { data: { processing_activity_id: activity.id } },
    )
  ).json();
  const confirmed = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/screening/decision`,
      { data: { decision: "required" } },
    )
  ).json();

  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  // §13: approve one proposal through the UI, with a rating a person chose.
  await page.goto(`/compliance/dpias/${screened.id}`);
  await expect(page.getByText("Risks Veyntra suggests")).toBeVisible();
  await page.getByRole("button", { name: "Approve as a risk" }).first().click();
  await page.getByLabel("Likelihood").selectOption("medium");
  await page.getByLabel("Impact").selectOption("high");
  await page.getByRole("button", { name: "Add to the risk register" }).click();

  // §29: the inherent rating exists now, because somebody supplied one.
  await expect(page.getByText("high").first()).toBeVisible();

  // Dismiss the rest, each with a reason.
  let remaining = await page
    .getByRole("button", { name: "Dismiss", exact: true })
    .count();
  while (remaining > 0) {
    await page.getByRole("button", { name: "Dismiss", exact: true }).first().click();
    await page
      .getByLabel("Why this is not a risk here (required)")
      .first()
      .fill("Covered by the existing access-control programme.");
    await page
      .getByRole("button", { name: "Dismiss with this reason" })
      .first()
      .click();
    await expect
      .poll(async () =>
        page.getByRole("button", { name: "Dismiss", exact: true }).count(),
      )
      .toBeLessThan(remaining);
    remaining = await page
      .getByRole("button", { name: "Dismiss", exact: true })
      .count();
  }

  // Mitigate it, so a residual rating has something behind it.
  const risks = await (
    await page.request.get(`${API_BASE_URL}/api/v1/compliance/risks`)
  ).json();
  const risk = risks.find(
    (row: { dpia_id: string | null }) => row.dpia_id === screened.id,
  );
  await page.request.patch(
    `${API_BASE_URL}/api/v1/compliance/risks/${risk.id}/residual`,
    { data: { residual_likelihood: "low", residual_impact: "low" } },
  );

  // §12: the consultation answer, which Veyntra never supplies.
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/consultation`,
    {
      data: {
        performed: false,
        notes: "No DPO is appointed; the processing is routine and low risk.",
      },
    },
  );
  for (const section of [
    "processing_description",
    "necessity_assessment",
    "proportionality_assessment",
    "consultation_notes",
  ]) {
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/sections/approve`,
      { data: { section } },
    );
  }
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/recalculate-residual`,
  );

  await page.reload();
  await expect(
    page.getByText("Everything Article 35(7) requires is recorded and reviewed."),
  ).toBeVisible();

  const complete = page.getByRole("button", { name: "Complete DPIA" });
  await expect(complete).toBeEnabled();
  await complete.click();

  // §23: frozen, and it says who finished it and when.
  await expect(page.getByText(/The assessment above is the record as it stood then/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Completed" })).toBeVisible();
  // Nothing is editable any more.
  await expect(page.getByRole("button", { name: "Edit assessment" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Approve this section" }),
  ).toHaveCount(0);

  expect(errors, `page threw: ${errors.join(" | ")}`).toHaveLength(0);

  await page.screenshot({
    path: "test-results/local-smoke/dpia-completed.png",
    fullPage: false,
  });

  // The snapshot exists and holds what was concluded.
  const workflow = await (
    await page.request.get(
      `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/workflow`,
    )
  ).json();
  expect(workflow.status).toBe("completed");
  expect(workflow.snapshot.risks).toHaveLength(1);
  expect(workflow.snapshot.risks[0].likelihood).toBe("medium");
  expect(workflow.snapshot.consultation.performed).toBe(false);
  expect(confirmed.status).toBe("draft");
});
