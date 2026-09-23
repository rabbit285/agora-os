import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** The DPIA lifecycle as a person meets it.
 *
 * §27's acceptance test, driven through the UI: screening opens on the
 * screening — not a blank Article 35 form — the assessment appears only
 * after somebody confirms one is required, and it arrives drafted with
 * risks proposed against it.
 */
async function aiCustomerSupport(page: import("@playwright/test").Page) {
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/vendors`, {
    data: { name: "OpenAI", category: "ai", country: "US" },
  });
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/ai-systems`, {
    data: {
      name: "AI Customer Support",
      vendor: "OpenAI",
      purpose: "Answering customer product questions in the support inbox",
      affected_users: ["Customers"],
      processed_data: [
        { name: "Contact information", classification: "confidential" },
        { name: "Support conversation content", classification: "confidential" },
      ],
    },
  });
  const drafts = await (
    await page.request.get(`${API_BASE_URL}/api/v1/compliance/privacy/suggestions`)
  ).json();
  const accepted = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/privacy/suggestions/${drafts[0].id}/accept`,
      {
        data: {
          legal_basis: "contract",
          retention_period: "24 months",
          special_category: true,
          special_category_condition: "explicit_consent",
        },
      },
    )
  ).json();
  return accepted.created_record_id as string;
}

test("§21 a DPIA in screening shows the screening, not a blank assessment", async ({
  page,
}) => {
  test.slow();
  await signup(page, "dpialife");
  const activityId = await aiCustomerSupport(page);

  const screened = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/dpias/screening/start`,
      { data: { processing_activity_id: activityId } },
    )
  ).json();

  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto(`/compliance/dpias/${screened.id}`);
  await expect(
    page.getByRole("heading", { name: "AI Customer Support DPIA" }),
  ).toBeVisible();
  expect(errors, `page threw: ${errors.join(" | ")}`).toHaveLength(0);

  // §26: one status control, and it does not offer a way around the
  // decision. In screening there is nowhere to go by hand at all.
  await expect(page.getByText("Screening", { exact: true }).first()).toBeVisible();
  await expect(page.locator("select#dpia-status")).toHaveCount(0);

  // The screening's two claims, shown as two.
  await expect(page.getByText("Veyntra's recommendation")).toBeVisible();
  await expect(page.getByText("A DPIA appears to be required")).toBeVisible();
  await expect(
    page.getByText(/Veyntra counted the criteria; whether a DPIA is required is your call/),
  ).toBeVisible();

  // §21: no Article 35(7) boxes before anybody said an assessment is needed.
  await expect(page.getByText("Assessment (Article 35(7))")).toHaveCount(0);
  await expect(page.getByText("Waiting on your decision")).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/dpia-screening-stage.png",
    fullPage: false,
  });
});

test("§27 confirming opens a drafted assessment with risks proposed against it", async ({
  page,
}) => {
  test.slow();
  await signup(page, "dpiaconf");
  const activityId = await aiCustomerSupport(page);

  const screened = await (
    await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/dpias/screening/start`,
      { data: { processing_activity_id: activityId } },
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
    page.getByRole("heading", { name: "AI Customer Support DPIA" }),
  ).toBeVisible();
  expect(errors, `page threw: ${errors.join(" | ")}`).toHaveLength(0);

  // §7/§8: drafted, and labelled as Veyntra's words rather than a
  // conclusion the organization has signed.
  await expect(page.getByText("Assessment (Article 35(7))")).toBeVisible();
  await expect(
    page.getByText("Veyntra draft — review required").first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve this section" }).first(),
  ).toBeVisible();

  // §13: proposals, waiting on a decision, each with the fact behind it.
  await expect(page.getByText("Risks Veyntra suggests")).toBeVisible();
  await expect(page.getByText(/Why Veyntra raised this/).first()).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Approve as a risk" }).first(),
  ).toBeVisible();

  // §14: and still nothing rated, because nobody has rated anything.
  await expect(page.getByText("Risk not assessed")).toBeVisible();
  await expect(page.getByText("Not yet calculated")).toBeVisible();

  // §22: completion says everything outstanding, together.
  await expect(page.getByText("Cannot complete DPIA. Remaining:")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Complete DPIA" }),
  ).toBeDisabled();

  await page.screenshot({
    path: "test-results/local-smoke/dpia-draft-stage.png",
    fullPage: false,
  });

  // §8: approving a section is a decision about the words, not an edit
  // to them. The prose survives; only the "whose words" signal moves
  // from an inline marker to the badge.
  const drafted = await page
    .getByText(/^\[Veyntra draft — review required\] The processing exists to/)
    .first()
    .innerText();
  const prose = drafted.replace(/^\[Veyntra draft[^\]]*\]\s*/, "");

  await page.getByRole("button", { name: "Approve this section" }).first().click();
  await expect(page.getByText("Approved").first()).toBeVisible();
  await expect(page.getByText(prose, { exact: true })).toBeVisible();
  await expect(
    page.getByText(/^\[Veyntra draft — review required\] The processing exists to/),
  ).toHaveCount(0);

  // §12: consultation is asked for, never drafted — and it is one
  // record, so there is a decision to make rather than a section to
  // approve on top of it.
  await expect(page.getByText("Needs decision").first()).toBeVisible();
  await expect(
    page.getByText(/Veyntra has no record of either and will not draft one/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Record consultation" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "No consultation performed" }),
  ).toBeVisible();
});
