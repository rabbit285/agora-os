import { expect, test } from "@playwright/test";

import { signup } from "./helpers";

test("Business Rules: create a rule, then deactivate it", async ({ page }) => {
  await signup(page, "bizrules");
  await page.goto("/settings/business-rules");

  const name = `E2E rule ${Date.now()}`;
  await page.getByPlaceholder("Rule name").fill(name);
  await page.getByPlaceholder("field (e.g. severity)").fill("severity");
  await page.getByPlaceholder("value (e.g. critical)").fill("critical");
  await page.getByRole("button", { name: "Save rule" }).click();

  await expect(page.getByText(name)).toBeVisible();
  await expect(page.getByText("Active")).toBeVisible();

  await page.getByRole("button", { name: "Deactivate" }).click();
  await expect(page.getByText("Inactive")).toBeVisible();
});

test("Business Memory: create a manual entry", async ({ page }) => {
  await signup(page, "memory");
  await page.goto("/settings/memory");

  const content = `E2E policy fact ${Date.now()}`;
  await page.getByPlaceholder(/Refunds over/).fill(content);
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByText(content)).toBeVisible();
});

test("Recommendations: a real compliance gap surfaces a real recommendation", async ({ page }) => {
  await signup(page, "recommendations");

  await page.goto("/compliance");
  const controlTitle = `E2E gap control ${Date.now()}`;
  await page.getByPlaceholder("New control title").fill(controlTitle);
  await page.getByRole("button", { name: "Add control" }).click();
  await expect(page.getByText(controlTitle)).toBeVisible();

  await page.goto("/recommendations");
  await expect(page.getByText(/compliance control gap/i)).toBeVisible();
});

test("Daily Briefing: all 5 spec §88 sections render with real data", async ({ page }) => {
  await signup(page, "briefing");
  await page.goto("/briefing");

  const main = page.getByRole("main");
  for (const section of ["Urgent", "Revenue", "Customers", "Risk", "Operations"]) {
    await expect(main.getByText(section, { exact: true })).toBeVisible();
  }
});
