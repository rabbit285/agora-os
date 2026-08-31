import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** The privacy workspace, in the browser.
 *
 * The module used to be one page with four lists stacked vertically. A
 * privacy officer with fifty processing activities could not find one,
 * and the question they actually open the product with — "what needs me
 * this week" — was not asked anywhere.
 */
test("the workspace opens on the worklist and each number leads somewhere", async ({
  page,
}) => {
  test.slow();
  await signup(page, "privacyws");

  // Two records with real gaps in them: a transfer whose mechanism is
  // recorded but whose safeguards are not, and a request nobody has
  // verified the identity for.
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/data-transfers`, {
    data: {
      recipient_name: "OpenAI",
      destination_country: "US",
      transfer_mechanism: "sccs",
    },
  });
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/dsars`, {
    data: {
      requester_name: "Dana Okafor",
      requester_email: "dana@example.com",
      request_type: "access",
    },
  });

  await page.goto("/compliance/privacy");

  // The tabs, rather than four headings on one scroll.
  for (const label of [
    "Overview",
    "Processing activities",
    "DPIAs",
    "Data requests",
    "Transfers",
  ]) {
    await expect(page.getByRole("link", { name: label, exact: false }).first()).toBeVisible();
  }

  await expect(page.getByText("Needs attention").first()).toBeVisible();
  await expect(
    page.getByText("Transfer to OpenAI records no safeguards"),
  ).toBeVisible();
  await expect(page.getByText("Identity verification pending")).toBeVisible();

  // And it says what it does not decide.
  await expect(
    page.getByText(/It does not choose a lawful basis/),
  ).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/privacy-overview.png",
    fullPage: false,
  });

  // A metric is a route to its records, not a decoration.
  await page.getByRole("link", { name: /International transfers/ }).click();
  await expect(page).toHaveURL(/\/compliance\/privacy\/transfers/);
  await expect(page.getByText("OpenAI").first()).toBeVisible();

  // An attention item leads to the record it is about.
  await page.goto("/compliance/privacy");
  await page.getByText("Transfer to OpenAI records no safeguards").click();
  await expect(page).toHaveURL(/\/compliance\/privacy\/transfers\//);
});

test("§13 a data request says one month, and the deadline reads as words", async ({
  page,
}) => {
  test.slow();
  await signup(page, "privacydsar");

  await page.goto("/compliance/privacy/data-requests");
  await page.getByRole("button", { name: "Log a request" }).click();

  // The wording that was wrong: thirty days is not one month.
  await expect(
    page.getByText(/Response due within one month of receipt/),
  ).toBeVisible();
  await expect(page.getByText(/Due 30 days from receipt/)).toHaveCount(0);

  await page.getByPlaceholder("Requester name").fill("Dana Okafor");
  await page.getByPlaceholder("Requester email").fill("dana@example.com");
  await page.getByRole("button", { name: "Log DSAR" }).click();

  // The deadline reads as words, because that is what a person is
  // judged on — not a date to subtract today from.
  await expect(page.getByText(/Due in \d+ days/)).toBeVisible();

  // And the list can be filtered by what is urgent.
  for (const label of ["Due soon", "Overdue", "Identity pending"]) {
    await expect(page.getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  // "Open" is also a status badge on the rows, so it is matched inside
  // the filter row rather than across the page.
  await expect(
    page.getByRole("button", { name: "Open", exact: true }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Overdue" }).click();
  await expect(page.getByText("No requests match this filter.")).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/privacy-data-requests.png",
    fullPage: false,
  });
});

test("each record type has its own route, and the tab follows", async ({
  page,
}) => {
  test.slow();
  await signup(page, "privacyroutes");

  for (const [path, heading] of [
    ["/compliance/privacy/processing-activities", "Record of Processing"],
    ["/compliance/privacy/dpias", "Data Protection Impact"],
    ["/compliance/privacy/data-requests", "Data Subject Access Requests"],
    ["/compliance/privacy/transfers", "Data Transfers"],
  ] as const) {
    await page.goto(path);
    await expect(page.getByText(heading, { exact: false }).first()).toBeVisible();
    // The workspace header stays, so the four views read as one job.
    await expect(page.getByRole("heading", { name: "Privacy" })).toBeVisible();
  }
});
