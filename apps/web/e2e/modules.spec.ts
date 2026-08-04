import { expect, test } from "@playwright/test";

import { signup } from "./helpers";

// Each spec signs up its own org (no onboarding gate blocks other pages)
// and drives a real create-form through the real UI against the real
// running API — not a mock.

test("Tasks: create a task and mark it done", async ({ page }) => {
  await signup(page, "tasks");
  await page.goto("/tasks");

  const title = `E2E task ${Date.now()}`;
  await page.getByPlaceholder("New task title").fill(title);
  await page.getByRole("button", { name: "Add task" }).click();

  const row = page.getByText(title);
  await expect(row).toBeVisible();
  await page.getByRole("button", { name: "Mark done" }).first().click();
  await expect(page.getByRole("button", { name: "Mark done" })).toHaveCount(0);
});

test("Compliance: create a control", async ({ page }) => {
  await signup(page, "compliance");
  await page.goto("/compliance");

  const title = `E2E control ${Date.now()}`;
  await page.getByPlaceholder("New control title").fill(title);
  await page.getByRole("button", { name: "Add control" }).click();

  await expect(page.getByText(title)).toBeVisible();
});

test("Security: open a real incident", async ({ page }) => {
  await signup(page, "security");
  await page.goto("/security");

  const title = `E2E incident ${Date.now()}`;
  await page.getByPlaceholder("New incident title (severity: high)").fill(title);
  await page.getByRole("button", { name: "Open incident" }).click();

  await expect(page.getByText(title)).toBeVisible();
});

test("Sales: create an account", async ({ page }) => {
  await signup(page, "sales");
  await page.goto("/sales");

  const name = `E2E Account ${Date.now()}`;
  await page.getByPlaceholder("New account name").fill(name);
  await page.getByRole("button", { name: "Add account" }).click();

  await expect(page.getByText(name)).toBeVisible();
});

test("Support: create a customer, then open a ticket against them", async ({ page }) => {
  await signup(page, "support");
  await page.goto("/support");

  const customerName = `E2E Customer ${Date.now()}`;
  await page.getByPlaceholder("Customer name").fill(customerName);
  await page.getByPlaceholder("Email").fill(`customer-${Date.now()}@example.com`);
  await page.getByRole("button", { name: "Add customer" }).click();
  // The customer's name renders both as a list row and as an <option> in
  // the ticket form's customer picker below — either is real proof of
  // creation, so .first() is enough rather than an exact single match.
  await expect(page.getByText(customerName).first()).toBeVisible();

  const subject = `E2E ticket ${Date.now()}`;
  await page.getByRole("combobox").filter({ hasText: "Select customer" }).selectOption({ label: customerName });
  await page.getByPlaceholder("Subject").fill(subject);
  await page.getByRole("button", { name: "Create ticket" }).click();

  await expect(page.getByText(subject)).toBeVisible();
});

test("Automation: create a workflow draft", async ({ page }) => {
  await signup(page, "automation");
  await page.goto("/automation");

  const name = `E2E workflow ${Date.now()}`;
  await page.getByPlaceholder("Workflow name").fill(name);
  await page.getByRole("button", { name: "Create workflow (draft)" }).click();

  await expect(page.getByText(name)).toBeVisible();
});
