import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** §17/§19: privacy records that draft themselves, in the browser.
 *
 * The organization registers an AI system and a vendor in the ordinary
 * course. Veyntra reads those and drafts the processing activity and
 * the transfer they imply — leaving the lawful basis and the transfer
 * mechanism blank, because those are the judgements the review exists
 * to obtain.
 */
async function declaredRecords(page: import("@playwright/test").Page) {
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/vendors`, {
    data: {
      name: "OpenAI",
      category: "ai",
      country: "US",
      data_location: "United States",
    },
  });
  await page.request.post(`${API_BASE_URL}/api/v1/compliance/ai-systems`, {
    data: {
      name: "AI Customer Support",
      vendor: "OpenAI",
      purpose: "Answering customer product questions in the support inbox.",
      affected_users: ["Customers"],
      processed_data: [
        { name: "Contact information", classification: "confidential" },
        { name: "Conversation history", classification: "confidential" },
      ],
    },
  });
}

test("§17 Veyntra drafts a processing activity, and asks for the lawful basis", async ({
  page,
}) => {
  test.slow();
  await signup(page, "privacyauto");
  await declaredRecords(page);

  await page.goto("/compliance/privacy/processing-activities");

  // Nothing yet — the drafts do not exist until somebody asks.
  await page.getByRole("button", { name: "Review suggestions (0)" }).click();
  await expect(
    page.getByRole("button", { name: "Review suggestions (1)" }),
  ).toBeVisible();

  // The draft, and what it was read out of.
  await expect(page.getByText("AI Customer Support").first()).toBeVisible();
  await expect(page.getByText(/Drafted from/).first()).toBeVisible();
  await expect(page.getByText("Contact information, Conversation history")).toBeVisible();
  await expect(page.getByText("Customers").first()).toBeVisible();

  // §12: the line between what was drafted and what is being asked.
  await expect(
    page.getByText("Your decision — Veyntra cannot make these"),
  ).toBeVisible();
  const basis = page.getByLabel("Lawful basis");
  await expect(basis).toHaveValue("");
  // Never pre-selected, and never "Legitimate interests" by default.
  const options = await basis.locator("option").allTextContents();
  expect(options[0]).toBe("Select lawful basis…");

  const confirm = page.getByRole("button", { name: "Confirm and create" });
  await expect(confirm).toBeDisabled();

  await page.screenshot({
    path: "test-results/local-smoke/privacy-suggestion.png",
    fullPage: false,
  });

  await basis.selectOption("contract");
  await page.getByLabel("Retention period").fill("24 months");
  await expect(confirm).toBeEnabled();
  await confirm.click();

  // The record exists now, and only now. The card leaves the list once
  // it does; reading the API before that measures the mutation rather
  // than the outcome.
  await expect(
    page.getByRole("button", { name: "Review suggestions (1)" }),
  ).toHaveCount(0);
  const activities = await page.request.get(
    `${API_BASE_URL}/api/v1/compliance/processing-activities`,
  );
  const body = await activities.json();
  expect(body).toHaveLength(1);
  expect(body[0].name).toBe("AI Customer Support");
  expect(body[0].legal_basis).toBe("contract");
});

test("§19 a processor outside the EEA surfaces a transfer to review", async ({
  page,
}) => {
  test.slow();
  await signup(page, "privacyxfer");
  await declaredRecords(page);

  // Accept the activity first, so a processor is linked to it.
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/privacy/suggestions/analyse`,
  );
  const drafts = await (
    await page.request.get(`${API_BASE_URL}/api/v1/compliance/privacy/suggestions`)
  ).json();
  await page.request.post(
    `${API_BASE_URL}/api/v1/compliance/privacy/suggestions/${drafts[0].id}/accept`,
    { data: { legal_basis: "contract", retention_period: "24 months" } },
  );

  await page.goto("/compliance/privacy/transfers");
  await page.getByRole("button", { name: "Review suggestions (0)" }).click();
  await expect(
    page.getByRole("button", { name: "Review suggestions (1)" }),
  ).toBeVisible();

  await expect(page.getByText(/AI Customer Support → OpenAI \(US\)/)).toBeVisible();
  await expect(page.getByText(/needs a mechanism/)).toBeVisible();

  // §17: never defaulted to Standard Contractual Clauses.
  const mechanism = page.getByLabel("Transfer mechanism");
  await expect(mechanism).toHaveValue("");
  const confirm = page.getByRole("button", { name: "Confirm and create" });
  await expect(confirm).toBeDisabled();

  await mechanism.selectOption("sccs");
  await expect(confirm).toBeEnabled();
  await confirm.click();

  // The card leaves the list once the record exists; reading the API
  // before that measures the mutation rather than the outcome.
  await expect(
    page.getByRole("button", { name: "Review suggestions (1)" }),
  ).toHaveCount(0);

  const transfers = await (
    await page.request.get(`${API_BASE_URL}/api/v1/compliance/data-transfers`)
  ).json();
  expect(transfers).toHaveLength(1);
  expect(transfers[0].transfer_mechanism).toBe("sccs");
});

test("§1/§17 neither form pre-answers a legal question", async ({ page }) => {
  test.slow();
  await signup(page, "privacydefaults");

  await page.goto("/compliance/privacy/processing-activities");
  await page.getByRole("button", { name: "Add manually" }).click();
  const basis = page.locator("select").first();
  await expect(basis).toHaveValue("");
  expect(await basis.locator("option").first().textContent()).toBe(
    "Select lawful basis…",
  );

  await page.goto("/compliance/privacy/transfers");
  await page.getByRole("button", { name: "Add manually" }).click();
  const mechanism = page.locator("select").first();
  await expect(mechanism).toHaveValue("");
  expect(await mechanism.locator("option").first().textContent()).toBe(
    "Select transfer mechanism…",
  );
});
