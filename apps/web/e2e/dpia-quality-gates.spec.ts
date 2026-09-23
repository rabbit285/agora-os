import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** §19/§22: the medical-leave case, driven through the UI.
 *
 * Veyntra could complete a DPIA whose necessity argument was the prompt
 * for writing one, whose risk conclusion rested on "ok", and which
 * reported "no personal-data categories are recorded" for processing
 * about employee medical leave. Every assertion here is about the same
 * rule: absent information must not become a positive conclusion.
 */
const STRONG_RATIONALE =
  "The processing is limited to absence dates needed to administer leave, " +
  "access is restricted to the two HR administrators who action requests, " +
  "records are retained for six years and then deleted, no automated " +
  "decisions are made about employees, and no data reaches a processor " +
  "outside the organization, so the remaining impact on individuals is " +
  "minimal.";

test("a medical-leave DPIA cannot complete on missing context or weak content", async ({
  page,
}) => {
  test.slow();
  await signup(page, "dpiaquality");

  // §19: the activity that prompted this — no data categories recorded.
  const activity = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/processing-activities`,
      {
        data: {
          name: "Employee medical-leave administration",
          purpose:
            "Administer statutory and contractual employee medical leave obligations",
          legal_basis: "legal_obligation",
          data_subjects: "Employees",
          data_categories: [],
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
    page.getByRole("heading", { name: "Employee medical-leave administration DPIA" }),
  ).toBeVisible();

  // §5/§7: the gaps are named, and each links to where it is fixed.
  await expect(
    page.getByRole("heading", { name: "Missing processing context" }),
  ).toBeVisible();
  // Said in the gaps panel and again in the completion blockers —
  // the same instruction in both places.
  await expect(
    page.getByText(/Personal-data categories have not been recorded/).first(),
  ).toBeVisible();
  await expect(
    page.getByText(/Missing information is not a finding that there is nothing to find/),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Review processing activity →" }).first(),
  ).toBeVisible();

  // §6: the health signal, with the text it was read from.
  await expect(
    page.getByRole("heading", { name: "Special-category data" }),
  ).toBeVisible();
  await expect(page.getByText("Needs human confirmation")).toBeVisible();
  await expect(page.getByText(/health or medical information/).first()).toBeVisible();
  await expect(page.getByText(/detected in the activity name/)).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/dpia-quality-gates.png",
    fullPage: false,
  });

  // §3/§18: the drafted necessity is an argument, not a prompt — so it
  // can be approved.
  await expect(page.getByText(/State why this processing is necessary/)).toHaveCount(0);
  await expect(page.getByText(/Assess whether the data collected is limited/)).toHaveCount(0);
  await expect(page.getByText(/necessary to administer statutory/)).toBeVisible();

  // §17: guidance is refused. Put some in and press Approve.
  await page.request.patch(
    `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/sections`,
    {
      data: {
        necessity_assessment:
          "State why this processing is necessary to achieve it, and what less " +
          "intrusive alternative was considered and rejected.",
      },
    },
  );
  await page.reload();
  await page
    .getByRole("button", { name: "Approve this section" })
    .nth(1)
    .click();
  await expect(
    page.getByText(/This is guidance, not a completed assessment/),
  ).toBeVisible();

  // §20: and a weak rationale is refused too.
  let open = await page.getByRole("button", { name: "Dismiss", exact: true }).count();
  while (open > 0) {
    await page.getByRole("button", { name: "Dismiss", exact: true }).first().click();
    await page
      .getByLabel("Why this is not a risk here (required)")
      .first()
      .fill("Absence dates only, held under the existing HR retention schedule.");
    await page.getByRole("button", { name: "Dismiss with this reason" }).first().click();
    await expect
      .poll(async () =>
        page.getByRole("button", { name: "Dismiss", exact: true }).count(),
      )
      .toBeLessThan(open);
    open = await page.getByRole("button", { name: "Dismiss", exact: true }).count();
  }

  const weak = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/risk-conclusion`,
    { data: { rationale: "ok" } },
  );
  expect(weak.status()).toBe(422);
  expect(await weak.text()).toContain("rationale somebody could rely on");

  // §21: the substantive one is accepted.
  const strong = await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/dpias/${screened.id}/risk-conclusion`,
    { data: { rationale: STRONG_RATIONALE } },
  );
  expect(strong.status()).toBe(200);

  // §13: completion still blocked, and it says exactly why.
  await page.reload();
  await expect(page.getByText("Cannot complete DPIA. Remaining:")).toBeVisible();
  const blockers = await page.getByRole("listitem").allTextContents();
  expect(blockers.join(" ")).toContain("Personal-data categories have not been recorded");
  expect(blockers.join(" ")).toContain("special-category data");
  await expect(page.getByRole("button", { name: "Complete DPIA" })).toBeDisabled();

  expect(errors, `page threw: ${errors.join(" | ")}`).toHaveLength(0);
});
