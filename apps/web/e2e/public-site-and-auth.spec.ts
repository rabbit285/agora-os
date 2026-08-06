import { expect, test } from "@playwright/test";

import {
  API_BASE_URL,
  getLatestInvitationUrl,
  getLatestPasswordResetUrl,
  getLatestVerificationUrl,
  login,
  logout,
  signup,
} from "./helpers";

// The 17 real journeys this effort's own brief requires (§22 — item 18,
// "run axe checks on homepage/login/signup/onboarding", lives in
// public-site-and-auth-accessibility.spec.ts rather than being
// duplicated here). Journeys 1-11 are one continuous flow, matching how
// a real visitor actually moves through the product; 12-17 each need
// their own fresh setup and are separate tests.

test("1-11. homepage through password reset: the full real user journey", async ({ page }) => {
  // 1. Visit the homepage.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Run compliance, security, sales, and operations/ })).toBeVisible();

  // 2. Navigate through the public menu. Scoped to the header's primary
  // nav landmark — the footer repeats the same link text ("Product",
  // "Pricing", ...), which a page-wide getByRole would ambiguously match.
  const primaryNav = page.getByRole("navigation", { name: "Site" });
  await primaryNav.getByRole("link", { name: "Product" }).click();
  await expect(page).toHaveURL(/\/features/);
  await primaryNav.getByRole("link", { name: "Solutions" }).click();
  await expect(page).toHaveURL(/\/solutions/);
  await primaryNav.getByRole("link", { name: "Pricing" }).click();
  await expect(page).toHaveURL(/\/pricing/);

  // 3. Open sign-up.
  await page.getByRole("link", { name: "Start free" }).first().click();
  await expect(page).toHaveURL(/\/signup/);

  // 4. Create an organization through the real UI.
  const unique = `journey-${Date.now()}`;
  const email = `${unique}@example.com`;
  const password = "CorrectHorseBattery9!";
  await page.getByLabel("Full name").fill("Journey Tester");
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Organization name").fill(`${unique} Org`);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("checkbox", { name: /Terms of Service/ }).check();
  await page.getByRole("button", { name: "Start free" }).click();
  await expect(page).toHaveURL(/\/onboarding/);

  // 5. Complete email verification using the supported test method (the
  // link is logged, not emailed — see helpers.ts).
  const verifyUrl = await getLatestVerificationUrl(email);
  const verifyPage = await page.context().newPage();
  await verifyPage.goto(verifyUrl);
  await expect(verifyPage.getByText("Your email is verified")).toBeVisible();
  await verifyPage.close();

  // 6. Complete onboarding.
  await page.getByLabel("Industry").fill("Software");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Improve compliance").check();
  await page.getByRole("button", { name: "Continue" }).click();
  const firstFrameworkCheckbox = page.locator('input[type="checkbox"]').first();
  await firstFrameworkCheckbox.check();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("combobox").selectOption("aws");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByPlaceholder("e.g. Enterprise SaaS accounts in Europe").fill("Mid-market fintech");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("email").check();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Configure later" }).click();
  await page.getByRole("button", { name: "Configure later" }).click();
  await expect(page.getByText("Your Business AI Readiness")).toBeVisible();
  await page.getByRole("button", { name: "Open Business Command Center" }).click();

  // 7. Reach the authenticated dashboard.
  await expect(page).toHaveURL("/dashboard");

  // 8. Sign out.
  await logout(page);
  await expect(page).toHaveURL(/\/login/);

  // 9. Sign in.
  await login(page, { email, password });
  await expect(page).toHaveURL("/dashboard");
  await logout(page);

  // 10. Request a password reset.
  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();

  // 11. Reset the password.
  const resetUrl = await getLatestPasswordResetUrl(email);
  const newPassword = "BrandNewPassword9!";
  await page.goto(resetUrl);
  await page.getByLabel("New password").fill(newPassword);
  await page.getByLabel("Confirm password").fill(newPassword);
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(page.getByRole("heading", { name: "Password updated" })).toBeVisible();
  await page.getByRole("link", { name: "Sign in" }).click();
  await login(page, { email, password: newPassword });
  await expect(page).toHaveURL("/dashboard");
});

test("12. accept an invitation as a brand-new account", async ({ page, browser }) => {
  const org = await signup(page, "invite-journey");

  const inviteeEmail = `invitee-journey-${Date.now()}@example.com`;
  const inviteResp = await page.request.post(`${API_BASE_URL}/api/v1/organizations/current/invitations`, {
    data: { email: inviteeEmail, role_key: "employee" },
  });
  expect(inviteResp.status()).toBe(201);
  const inviteUrl = await getLatestInvitationUrl(inviteeEmail);

  const inviteeContext = await browser.newContext();
  const inviteePage = await inviteeContext.newPage();
  await inviteePage.goto(inviteUrl);
  await expect(inviteePage.getByText(org.organizationName)).toBeVisible();
  await inviteePage.getByLabel("Your name").fill("Invited Journey Tester");
  await inviteePage.getByLabel("Set a password").fill("CorrectHorseBattery9!");
  await inviteePage.getByRole("button", { name: "Accept and join" }).click();
  await expect(inviteePage).toHaveURL("/dashboard");
  await inviteeContext.close();
});

test("13. an invalid invitation link is handled honestly", async ({ page }) => {
  await page.goto("/invite/this-token-does-not-exist");
  await expect(page.getByText("We couldn't find this invitation")).toBeVisible();
});

test("14. an authenticated user cannot unnecessarily access login or signup", async ({ page }) => {
  await signup(page, "no-relogin");
  await page.goto("/login");
  await expect(page).toHaveURL("/dashboard");
  await page.goto("/signup");
  await expect(page).toHaveURL("/dashboard");
});

test("15. redirect-back: a protected route bounces to login and returns after sign-in", async ({ page }) => {
  const org = await signup(page, "redirect-back-journey");
  await logout(page);

  await page.goto("/sales");
  await expect(page).toHaveURL(/\/login\?redirect=%2Fsales/);

  await page.getByLabel("Email").fill(org.email);
  await page.getByLabel("Password", { exact: true }).fill(org.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/sales");
});

test("16. mobile navigation works end to end", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open menu" }).click();

  const mobileMenu = page.locator("#public-mobile-menu");
  await expect(mobileMenu.getByRole("link", { name: "Pricing" })).toBeVisible();
  await mobileMenu.getByRole("link", { name: "Pricing" }).click();
  await expect(page).toHaveURL(/\/pricing/);
});

test("17. keyboard-only sign-up completes a real account", async ({ page }) => {
  await page.goto("/signup");
  const unique = `kbd-signup-${Date.now()}`;
  const email = `${unique}@example.com`;

  await page.getByLabel("Full name").focus();
  await page.keyboard.type("Keyboard Journey");
  await page.keyboard.press("Tab");
  await page.keyboard.type(email);
  await page.keyboard.press("Tab");
  await page.keyboard.type(`${unique} Org`);
  await page.keyboard.press("Tab");
  await page.keyboard.type("CorrectHorseBattery9!");
  await page.keyboard.press("Tab"); // -> the Password field's own show/hide toggle button
  await page.keyboard.press("Tab"); // -> Confirm password
  await page.keyboard.type("CorrectHorseBattery9!");
  await page.keyboard.press("Tab"); // -> Confirm password's own show/hide toggle button
  await page.keyboard.press("Tab"); // -> accept_terms checkbox
  await page.keyboard.press("Space"); // check it
  await page.keyboard.press("Tab"); // -> "Terms of Service" link (sits inside the checkbox's own label)
  await page.keyboard.press("Tab"); // -> "Privacy Policy" link
  await page.keyboard.press("Tab"); // -> marketing_consent checkbox (left unchecked, on purpose)
  await page.keyboard.press("Tab"); // -> "Start free" submit button
  await expect(page.getByRole("button", { name: "Start free" })).toBeFocused();
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/\/onboarding/);
});
