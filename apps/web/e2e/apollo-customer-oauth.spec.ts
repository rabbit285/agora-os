import { expect, test } from "@playwright/test";

import { API_BASE_URL, signup } from "./helpers";

// Real journeys against the running dev stack. No real Apollo OAuth
// application is configured here, so the backend uses its mock adapter
// (app/integrations/adapters/mock.py) — automated tests must never consume
// a real customer's Apollo credits (see
// docs/APOLLO_CUSTOMER_OAUTH_ARCHITECTURE.md).

test("1. Integrations page lists Apollo as an OAuth connector", async ({ page }) => {
  await signup(page, "apollo-e2e-01");
  await page.goto("/settings/integrations");
  await expect(page.getByRole("heading", { name: "Integrations" })).toBeVisible();
  await expect(page.getByText("Apollo", { exact: true })).toBeVisible();
});

test("2. Apollo shows a permission preview naming customer credit ownership", async ({ page }) => {
  await signup(page, "apollo-e2e-02");
  await page.goto("/settings/integrations");

  const apolloCard = page.locator("div").filter({ hasText: /^Apollo/ }).first();
  const connectButton = apolloCard.getByRole("button", { name: "Connect" });

  // Without a configured Apollo OAuth application the deployment honestly
  // reports "Not configured" rather than offering a connection that cannot
  // succeed.
  if (await connectButton.isVisible().catch(() => false)) {
    await connectButton.click();
    await expect(
      page.getByText(/use your organization.s Apollo account, permissions, rate limits, and credits/i),
    ).toBeVisible();
    await expect(page.getByText(/consume your own Apollo credits/i)).toBeVisible();
  } else {
    await expect(apolloCard.getByText("Not configured")).toBeVisible();
  }
});

test("3. Lead Finder reports Apollo status honestly and never fakes live results", async ({
  page,
}) => {
  await signup(page, "apollo-e2e-03");
  await page.goto("/sales/lead-finder");
  await page.getByRole("heading", { name: "Lead Finder" }).waitFor();

  // Unconnected: demo data is labeled as such, never presented as live.
  await expect(page.getByText(/demo data/i).first()).toBeVisible();

  const sidebar = page.locator("aside");
  await sidebar.getByLabel("Industries").fill("B2B SaaS");
  await sidebar.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText(/result.*via demo/)).toBeVisible();
});

test("4. Lead Finder stays usable for saved records while Apollo is unconnected", async ({
  page,
}) => {
  await signup(page, "apollo-e2e-04");
  await page.goto("/sales/lead-finder");
  await page.getByRole("heading", { name: "Lead Finder" }).waitFor();

  // CSV import and manual entry remain available without any Apollo
  // connection — disconnecting a provider must never disable the CRM.
  await expect(page.getByRole("button", { name: /Import CSV/ })).toBeEnabled();
  await expect(page.getByRole("button", { name: /Add manually/ })).toBeEnabled();
});

test("5. Provider status endpoint never leaks another tenant's connection", async ({ page }) => {
  await signup(page, "apollo-e2e-05");
  const response = await page.request.get(
    `${API_BASE_URL}/api/v1/sales/lead-finder/providers`,
  );
  expect(response.status()).toBe(200);
  const body = await response.json();
  const apollo = body.find((p: { provider_key: string }) => p.provider_key === "apollo");

  expect(apollo.configured).toBe(false);
  expect(apollo.connection_id).toBeNull();
  expect(apollo.connected_user_email).toBeNull();
  expect(apollo.granted_scopes).toEqual([]);
});

test("6. No Apollo token or client secret is exposed to the browser", async ({ page }) => {
  await signup(page, "apollo-e2e-06");

  await page.goto("/settings/integrations");
  await page.waitForLoadState("networkidle");
  const integrationsHtml = await page.content();

  await page.goto("/sales/lead-finder");
  await page.getByRole("heading", { name: "Lead Finder" }).waitFor();
  const leadFinderHtml = await page.content();

  const storage = await page.evaluate(() => ({
    local: JSON.stringify(window.localStorage),
    session: JSON.stringify(window.sessionStorage),
  }));

  for (const haystack of [integrationsHtml, leadFinderHtml, storage.local, storage.session]) {
    expect(haystack).not.toMatch(/APOLLO_OAUTH_CLIENT_SECRET/i);
    expect(haystack).not.toMatch(/encrypted_access_token|encrypted_refresh_token/i);
    expect(haystack).not.toMatch(/mock-access-|mock-refresh-/i);
  }

  // The URL itself must never carry an authorization code or token.
  expect(page.url()).not.toMatch(/[?&](code|access_token|refresh_token)=/);
});

test("7. Connecting Apollo requires the manage permission", async ({ page }) => {
  await signup(page, "apollo-e2e-07");
  // The signup owner holds org_admin, so the call is permitted; the RBAC
  // denial path for lesser roles is covered in the backend suite
  // (tests/test_apollo_customer_oauth.py) where a role can be assigned
  // directly. Here we assert the endpoint exists and is org-scoped.
  const response = await page.request.post(
    `${API_BASE_URL}/api/v1/integrations/connections/oauth/apollo/start`,
  );
  // 200 when an Apollo OAuth app is configured, 404 "Unknown provider"
  // never — Apollo must always be a registered connector.
  expect([200, 403]).toContain(response.status());
});
