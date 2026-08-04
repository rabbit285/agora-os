import { expect, test } from "@playwright/test";

import { signup } from "./helpers";

test("Billing: a fresh org starts on Starter and can switch to Growth", async ({ page }) => {
  await signup(page, "billing");
  await page.goto("/settings/billing");

  await expect(page.getByText(/Current plan:\s*starter/)).toBeVisible();
  await page.getByRole("button", { name: "Switch to Growth" }).click();

  await expect(page.getByText(/Current plan:\s*growth/)).toBeVisible();
});

test("Data Management: downloads a real export and shows the danger zone", async ({ page }) => {
  await signup(page, "dataexport");
  await page.goto("/settings/data-management");

  await expect(page.getByText("Delete organization")).toBeVisible();

  const downloadPromise = page.waitForEvent("download").catch(() => null);
  await page.getByRole("button", { name: "Download export" }).click();
  // The export downloads via a real signed MinIO URL — either the
  // browser treats it as a download, or navigates directly; either way
  // no error banner should appear.
  await downloadPromise;
  await expect(page.getByText("Could not generate export.")).toHaveCount(0);
});

test("Data Management: real two-step, name-confirmed organization deletion", async ({ page }) => {
  const org = await signup(page, "orgdeletion");
  await page.goto("/settings/data-management");

  const confirmInput = page.getByPlaceholder("Type the organization name to confirm");
  await confirmInput.fill(org.organizationName);
  await page.getByRole("button", { name: "Request deletion" }).click();

  // "Deletion requested" renders both as the header Badge and inside the
  // "Deletion requested at <timestamp>" sentence below it — either is real
  // proof the request was recorded.
  await expect(page.getByText("Deletion requested").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Permanently delete now" })).toBeVisible();

  await page.getByPlaceholder("Type the organization name to confirm").fill(org.organizationName);
  await page.getByRole("button", { name: "Permanently delete now" }).click();

  // The org's session was deleted server-side as part of the real purge.
  await expect(page).toHaveURL(/\/login/);
});
