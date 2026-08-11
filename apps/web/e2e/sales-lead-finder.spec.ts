import { expect, test, type Page } from "@playwright/test";

import { API_BASE_URL, getLatestInvitationUrl, signup } from "./helpers";

// Real E2E journeys against the real running dev stack (Apollo
// unconfigured, so every result is demo-labeled) — no mocked API. Maps
// 1:1 to the brief's 19 numbered journeys
// (docs/SALES_LEAD_FINDER_IMPLEMENTATION_PLAN.md's Testing section).

async function openLeadFinder(page: Page): Promise<void> {
  await page.goto("/sales/lead-finder");
  await page.getByRole("heading", { name: "Lead Finder" }).waitFor();
}

async function searchCompanies(page: Page, industry: string): Promise<void> {
  const sidebar = page.locator("aside");
  await sidebar.getByLabel("Industries").fill(industry);
  await sidebar.getByRole("button", { name: "Search", exact: true }).click();
}

async function searchPeopleBySeniority(page: Page, seniority: string): Promise<void> {
  await page.getByRole("tab", { name: "People" }).click();
  const sidebar = page.locator("aside");
  await sidebar.getByLabel("Seniorities").fill(seniority);
  await sidebar.getByRole("button", { name: "Search", exact: true }).click();
}

test("1. Open Lead Finder", async ({ page }) => {
  await signup(page, "lf01");
  await openLeadFinder(page);
  await expect(page.getByRole("tab", { name: "Companies" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "People" })).toBeVisible();
  await expect(page.getByText("Filters", { exact: true })).toBeVisible();
});

test("2. Manual company search", async ({ page }) => {
  await signup(page, "lf02");
  await openLeadFinder(page);
  await searchCompanies(page, "B2B SaaS");
  await expect(page.getByText(/result.*via demo/)).toBeVisible();
});

test("3. Open company detail", async ({ page }) => {
  await signup(page, "lf03");
  await openLeadFinder(page);
  const sidebar = page.locator("aside");
  await sidebar.getByLabel("Name").fill("Northwind");
  await sidebar.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByText("Northwind Robotics").first().click();
  await expect(page.getByRole("dialog").getByText("Northwind Robotics")).toBeVisible();
});

test("4. Find decision-makers", async ({ page }) => {
  await signup(page, "lf04");
  await openLeadFinder(page);
  const sidebar = page.locator("aside");
  await sidebar.getByLabel("Name").fill("Northwind");
  await sidebar.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByText("Northwind Robotics").first().click();
  await page.getByRole("button", { name: "Find decision-makers" }).click();
  await expect(page.getByText("Decision-makers")).toBeVisible();
});

test("5. People search", async ({ page }) => {
  await signup(page, "lf05");
  await openLeadFinder(page);
  await searchPeopleBySeniority(page, "c_suite");
  await expect(page.getByText(/result.*via demo/)).toBeVisible();
});

test("6. Open person drawer", async ({ page }) => {
  await signup(page, "lf06");
  await openLeadFinder(page);
  await searchPeopleBySeniority(page, "c_suite");
  const firstRow = page.locator("table tbody tr").first();
  const personName = await firstRow.locator("td").nth(1).innerText();
  await firstRow.click();
  await expect(page.getByRole("dialog").getByText(personName.split("\n")[0])).toBeVisible();
});

test("7. Save company as Account", async ({ page }) => {
  await signup(page, "lf07");
  await openLeadFinder(page);
  await searchCompanies(page, "B2B SaaS");
  await page.locator("table").getByRole("button", { name: "Save" }).first().click();
  await expect(page.locator("table").getByText("Saved").first()).toBeVisible();
});

test("8. Save person as Contact", async ({ page }) => {
  await signup(page, "lf08");
  await openLeadFinder(page);
  await searchPeopleBySeniority(page, "c_suite");
  await page.locator("table").getByRole("button", { name: "Save" }).first().click();
  await expect(page.locator("table").getByText("Saved").first()).toBeVisible();
});

test("9. Create Lead", async ({ page }) => {
  await signup(page, "lf09");
  await openLeadFinder(page);
  await searchCompanies(page, "B2B SaaS");
  await page.locator("table").getByRole("button", { name: "Save" }).first().click();
  await expect(page.locator("table").getByText("Saved").first()).toBeVisible();
  await page.getByRole("button", { name: "Create Lead" }).click();
  await expect(page.getByText("Lead created")).toBeVisible();
});

test("10. Save and rerun search", async ({ page }) => {
  await signup(page, "lf10");
  await openLeadFinder(page);
  await searchCompanies(page, "B2B SaaS");
  const searchName = `E2E saved search ${Date.now()}`;
  await page.getByRole("button", { name: "Save search" }).click();
  await page.getByLabel("Search name").fill(searchName);
  await page.getByRole("button", { name: "Save search" }).click();

  await page.goto("/sales/lead-finder/saved-searches");
  const row = page.getByText(searchName);
  await expect(row).toBeVisible();
  await page.getByRole("button", { name: `Run ${searchName}` }).click();
  await expect(page.getByRole("dialog").getByText("Search results")).toBeVisible();
});

test("11. Add to list", async ({ page }) => {
  await signup(page, "lf11");
  await openLeadFinder(page);
  await searchCompanies(page, "B2B SaaS");
  await page.locator("table tbody tr").first().getByLabel(/^Select /).check();
  await page.getByRole("button", { name: "Add to list" }).click();

  const listName = `E2E list ${Date.now()}`;
  await page.getByPlaceholder("New list name").fill(listName);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByLabel("Existing list")).toHaveValue(/.+/);
  await page.getByRole("button", { name: "Add to list" }).click();

  await page.goto("/sales/lists");
  await expect(page.getByText(listName)).toBeVisible();
});

test("12. Start selective enrichment", async ({ page }) => {
  await signup(page, "lf12");
  await openLeadFinder(page);
  await searchCompanies(page, "B2B SaaS");
  await page.locator("table tbody tr").first().getByLabel(/^Select /).check();
  await page.getByRole("button", { name: "Save & enrich" }).click();
  await expect(page.getByRole("button", { name: "Confirm enrichment" })).toBeEnabled();
  await page.getByRole("button", { name: "Confirm enrichment" }).click();
  // The confirm click starts a real Temporal workflow (a live client
  // connection, not instant) before the dialog closes on success.
  await expect(page.getByRole("dialog")).toBeHidden({ timeout: 15000 });
});

test("13. Credit preview shown before enrichment runs", async ({ page }) => {
  await signup(page, "lf13");
  await openLeadFinder(page);
  await searchCompanies(page, "B2B SaaS");
  await page.locator("table tbody tr").first().getByLabel(/^Select /).check();
  await page.getByRole("button", { name: "Save & enrich" }).click();
  await expect(page.getByText(/estimated credit/)).toBeVisible();
});

test("14. Provider not-configured state", async ({ page }) => {
  // Apollo is now a per-organization OAuth connection, so the status
  // distinguishes "this deployment has no Apollo application"
  // (not_configured) from "your organization hasn't connected one yet"
  // (ready_to_connect) — both still return clearly-labeled demo data
  // rather than fake live results (see
  // docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md §11).
  await signup(page, "lf14");
  await openLeadFinder(page);
  // StatusBadge renders the status with underscores replaced by spaces.
  await expect(page.getByText(/not configured|ready to connect/)).toBeVisible();
  await expect(page.getByText(/Showing labeled demo data/)).toBeVisible();
});

test("15. Demo labeling on results", async ({ page }) => {
  await signup(page, "lf15");
  await openLeadFinder(page);
  await searchCompanies(page, "B2B SaaS");
  await expect(page.getByText(/via demo/)).toBeVisible();
});

test("16. Duplicate detection after saving", async ({ page }) => {
  await signup(page, "lf16");
  await openLeadFinder(page);
  const sidebar = page.locator("aside");
  await sidebar.getByLabel("Name").fill("Northwind");
  await sidebar.getByRole("button", { name: "Search", exact: true }).click();
  await page.locator("table").getByRole("button", { name: "Save" }).first().click();
  await expect(page.locator("table").getByText("Saved").first()).toBeVisible();

  await sidebar.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.locator("table").getByText("Existing").first()).toBeVisible();
});

test("17. Campaign compliance blocks a suppressed contact", async ({ page }) => {
  await signup(page, "lf17");
  const contact = await page.request.post(`${API_BASE_URL}/api/v1/sales/contacts`, {
    data: { full_name: "Suppressed E2E Contact", email: `suppressed-e2e-${Date.now()}@example.com` },
  });
  const contactBody = await contact.json();

  await page.request.post(`${API_BASE_URL}/api/v1/sales/lead-finder/suppression`, {
    data: { contact_id: contactBody.id, reason: "E2E compliance block test" },
  });

  await page.goto(`/sales/contacts/${contactBody.id}`);
  await expect(page.getByText("Blocked — do not contact")).toBeVisible();
});

test("18. Restricted-role denial", async ({ page, browser }) => {
  await signup(page, "lf18");
  await page.goto("/settings/users");
  const email = `lf18-employee-${Date.now()}@example.com`;
  await page.getByPlaceholder("email@example.com").fill(email);
  await page.getByRole("combobox").selectOption({ label: "Employee" });
  await page.getByRole("button", { name: "Send invite" }).click();
  await expect(page.getByText(email)).toBeVisible();

  const inviteUrl = await getLatestInvitationUrl(email);
  const employeeContext = await browser.newContext();
  const employeePage = await employeeContext.newPage();
  await employeePage.goto(inviteUrl);
  await employeePage.getByLabel("Your name").fill("LF18 Employee");
  await employeePage.getByLabel("Set a password").fill("CorrectHorseBattery9!");
  await employeePage.getByRole("button", { name: "Accept and join" }).click();
  await expect(employeePage).toHaveURL("/dashboard");

  await employeePage.goto("/sales/lead-finder");
  await expect(employeePage.getByText(/don't have permission/)).toBeVisible();
  await employeeContext.close();
});

test("19. Cross-tenant denial", async ({ page, browser }) => {
  await signup(page, "lf19a");
  await openLeadFinder(page);
  await searchCompanies(page, "B2B SaaS");
  const searchName = `Cross-tenant E2E ${Date.now()}`;
  await page.getByRole("button", { name: "Save search" }).click();
  await page.getByLabel("Search name").fill(searchName);
  await page.getByRole("button", { name: "Save search" }).click();

  const savedSearches = await page.request.get(`${API_BASE_URL}/api/v1/sales/lead-finder/saved-searches`);
  const savedSearchList = await savedSearches.json();
  const created = savedSearchList.find((s: { name: string }) => s.name === searchName);
  expect(created).toBeTruthy();

  const contextB = await browser.newContext();
  const pageB = await contextB.newPage();
  await signup(pageB, "lf19b");
  const crossTenantAttempt = await pageB.request.patch(
    `${API_BASE_URL}/api/v1/sales/lead-finder/saved-searches/${created.id}`,
    { data: { name: "hijacked" } },
  );
  expect(crossTenantAttempt.status()).toBe(404);
  await contextB.close();
});
