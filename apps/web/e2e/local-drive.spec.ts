import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

/** Drive the running product through the automation-first journey.
 *
 * Not a regression test — the specs beside this one do that. This is the
 * walkthrough: register a business the ordinary way, then look at what
 * Veyntra did about it without being asked.
 */
test("the automation-first privacy journey, end to end", async ({ page }) => {
  test.slow();
  await signup(page, "drive");

  // --- what a new customer records in the ordinary course --------------
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
      name: "Support Assistant",
      vendor: "OpenAI",
      purpose: "Respond to customer support requests",
      affected_users: ["Customers"],
      processed_data: [
        { name: "Contact details", classification: "confidential" },
        { name: "Conversation history", classification: "confidential" },
      ],
    },
  });

  // --- Review Center: the decision that arrived on its own -------------
  await page.goto("/review");
  await expect(
    page.getByText("Confirm the lawful basis for AI Customer Support"),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/drive-review-center.png",
    fullPage: false,
  });

  // --- Privacy: the draft, with the judgement left open ----------------
  await page.goto("/compliance/privacy/processing-activities");
  await page.getByRole("button", { name: "Review suggestions (1)" }).click();
  await expect(page.getByText("AI Customer Support").first()).toBeVisible();
  await expect(page.getByLabel("Lawful basis")).toHaveValue("");
  await page.screenshot({
    path: "test-results/local-smoke/drive-privacy-draft.png",
    fullPage: false,
  });

  // --- the human supplies what Veyntra would not ------------------------
  await page.getByLabel("Lawful basis").selectOption("contract");
  await page.getByLabel("Retention period").fill("12 months");
  await page.getByRole("button", { name: "Confirm and create" }).click();
  await expect(
    page.getByRole("button", { name: "Review suggestions (0)" }),
  ).toBeVisible();

  // --- and the transfer that followed from it ---------------------------
  await page.goto("/compliance/privacy/transfers");
  await expect(
    page.getByRole("button", { name: "Review suggestions (1)" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Review suggestions (1)" }).click();
  await expect(page.getByText(/AI Customer Support → OpenAI \(US\)/)).toBeVisible();
  await expect(page.getByLabel("Transfer mechanism")).toHaveValue("");
  await page.screenshot({
    path: "test-results/local-smoke/drive-transfer.png",
    fullPage: false,
  });

  // --- the overview, as a worklist --------------------------------------
  await page.goto("/compliance/privacy");
  await expect(page.getByText("Needs attention").first()).toBeVisible();
  await page.screenshot({
    path: "test-results/local-smoke/drive-privacy-overview.png",
    fullPage: false,
  });
});
