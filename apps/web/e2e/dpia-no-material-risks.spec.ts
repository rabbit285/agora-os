import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** §15: the case the page could not previously express.
 *
 * A reviewer reads every candidate risk, judges none material, and
 * records that. Completion used to require a risk on the register, so
 * the only way to finish was to write down one they did not believe.
 *
 * And the consultation is one record: deciding it is the review, so the
 * page never shows "No consultation performed" beside "Nobody has
 * approved the consultation record".
 */
test("a reviewer can conclude no material risks and complete the DPIA", async ({
  page,
}) => {
  test.slow();
  await signup(page, "nomaterial");

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
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/screening/decision`,
    { data: { decision: "required" } },
  );

  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`/compliance/dpias/${screened.id}`);
  await expect(
    page.getByRole("heading", { name: "Support ticket triage DPIA" }),
  ).toBeVisible();

  // §1/§2: exactly one Consultation heading on the page, inside the
  // Article 35(7) assessment. It used to appear twice — a summary here
  // and a card that owned the decision — which is how two states drift.
  await expect(page.getByText("Consultation", { exact: true })).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "No consultation performed" }),
  ).toBeVisible();
  // Only the three narrative sections are approved as prose.
  await expect(
    page.getByRole("button", { name: "Approve this section" }),
  ).toHaveCount(3);

  // §3: not "Risk after mitigation" when nothing has been mitigated.
  await expect(
    page.getByRole("heading", { name: /Risk assessment/ }),
  ).toBeVisible();
  await expect(page.getByText("Risk after mitigation")).toHaveCount(0);
  await expect(page.getByText("Not reviewed")).toBeVisible();

  // §11: before review, "not assessed" — and the conclusion is not yet
  // offered, because a suggestion is still open.
  await expect(page.getByText("Not assessed", { exact: true })).toBeVisible();
  const confirm = page.getByRole("button", {
    name: "Confirm no material risks identified",
  });
  await expect(confirm).toBeDisabled();

  // Review the candidates: dismiss each with a reason.
  let open = await page.getByRole("button", { name: "Dismiss", exact: true }).count();
  expect(open).toBeGreaterThan(0);
  while (open > 0) {
    await page.getByRole("button", { name: "Dismiss", exact: true }).first().click();
    await page
      .getByLabel("Why this is not a risk here (required)")
      .first()
      .fill("Contact details only, retained under the standard schedule.");
    await page.getByRole("button", { name: "Dismiss with this reason" }).first().click();
    await expect
      .poll(async () =>
        page.getByRole("button", { name: "Dismiss", exact: true }).count(),
      )
      .toBeLessThan(open);
    open = await page.getByRole("button", { name: "Dismiss", exact: true }).count();
  }

  // §9: the accounting proves the suggestions were reviewed.
  await expect(page.getByText("Suggested risks")).toBeVisible();
  await expect(page.getByText(/^\d+ \/ \d+$/)).toBeVisible();

  await expect(confirm).toBeEnabled();
  await confirm.click();
  // §4: not one click — a rationale is required, and the field says what
  // it has to account for.
  await expect(
    page.getByText("Confirm no material privacy risks identified"),
  ).toBeVisible();
  const rationale = page.getByLabel(/does not present\s+material privacy risks/);
  await expect(
    page.getByRole("button", { name: "Confirm conclusion" }),
  ).toBeDisabled();
  await rationale.fill(
    "The processing is limited to support-related information, no solely automated significant decisions are made, access is restricted, retention is limited, and existing safeguards reduce the identified privacy concerns below the organization's material-risk threshold.",
  );
  await page.getByRole("button", { name: "Confirm conclusion" }).click();

  // §6: the review completed, so the section says so — and never
  // "Not assessed", which would read as though nobody had looked.
  await expect(page.getByText("Reviewed", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Conclusion", { exact: true })).toBeVisible();
  await expect(
    page.getByText("No material privacy risks identified", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Rationale", { exact: true })).toBeVisible();
  await expect(page.getByText("Reviewed by", { exact: true })).toBeVisible();
  await expect(page.getByText("No material risks identified")).toBeVisible();
  await expect(page.getByText("Not applicable")).toBeVisible();
  await expect(page.getByText("Not assessed", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Not yet calculated")).toHaveCount(0);

  // The consultation, decided the other way, with a reason — in the one
  // place it is decided.
  await page.getByRole("button", { name: "No consultation performed" }).first().click();
  await page
    .getByLabel("Why no consultation was needed (required)")
    .fill(
      "No DPO consultation was considered necessary for this processing after the screening and risk review.",
    );
  await page.getByRole("button", { name: "Record consultation" }).last().click();

  // Resolved, shown once, with no contradictory approval blocker.
  await expect(page.getByText("Recorded by", { exact: false })).toBeVisible();
  await expect(page.getByText(/^Reason: /)).toBeVisible();
  await expect(page.getByText("Nobody has approved the consultation")).toHaveCount(0);
  await expect(page.getByText("Consultation", { exact: true })).toHaveCount(1);

  await page.screenshot({
    path: "test-results/local-smoke/dpia-no-material-risks.png",
    fullPage: false,
  });

  // §13: with the three narrative sections approved, it completes —
  // with no invented risk on the register.
  for (const section of [
    "processing_description",
    "necessity_assessment",
    "proportionality_assessment",
  ]) {
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/sections/approve`,
      { data: { section } },
    );
  }
  await page.reload();
  const complete = page.getByRole("button", { name: "Complete DPIA" });
  await expect(complete).toBeEnabled();
  await complete.click();
  await expect(page.getByRole("heading", { name: "Completed" })).toBeVisible();

  expect(errors, `page threw: ${errors.join(" | ")}`).toHaveLength(0);

  const workflow = await (
    await page.request.get(
      `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/workflow`,
    )
  ).json();
  expect(workflow.status).toBe("completed");
  expect(workflow.snapshot.risks).toEqual([]);
  expect(workflow.snapshot.risk_review.conclusion).toBe("no_material_risks");
  expect(workflow.snapshot.consultation.state).toBe("no_consultation");
});
