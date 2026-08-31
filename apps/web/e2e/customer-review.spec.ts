import { expect, test } from "@playwright/test";
import { API_BASE_URL, signup } from "./helpers";

test("a customer questionnaire opens its own security review", async ({ page }) => {
  test.slow();
  await signup(page, "engagement");

  const make = async (title: string, source: string, customer: string | null) => {
    const r = await page.request.post(`${API_BASE_URL}/api/v1/compliance/questionnaires`, {
      data: { title, source, customer_name: customer },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    const id = (await r.json()).id;
    const q = await page.request.post(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions`,
      { data: { text: "Do you encrypt customer data at rest?", category: "security" } },
    );
    await page.request.patch(
      `${API_BASE_URL}/api/v1/compliance/questionnaires/${id}/questions/${(await q.json()).id}/answer`,
      { data: { answer_text: "Yes.", status: "approved" } },
    );
    return id;
  };

  await make("Agora Origin customer", "customer_provided", "Agora Origin");
  await make("Quarterly Internal GDPR Assessment", "internal_template", null);

  await page.goto("/compliance/assessments");

  await expect(page.getByText("No customer security reviews")).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: /Agora Origin Security Review/ }),
  ).toBeVisible();
  await expect(page.getByText(/Agora Origin · 1 questionnaire/)).toBeVisible();
  await expect(page.getByText(/1\/1 approved · 100%/)).toBeVisible();

  await page.screenshot({
    path: "test-results/local-smoke/customer-review.png",
    fullPage: true,
  });
});
