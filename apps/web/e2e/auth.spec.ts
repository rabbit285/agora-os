import { expect, test } from "@playwright/test";

import { login, logout, signup } from "./helpers";

test.describe("Signup and login", () => {
  test("a new user can sign up and lands on the onboarding wizard", async ({ page }) => {
    await signup(page, "auth-signup");
    await expect(page).toHaveURL(/\/onboarding/);
    await expect(page.getByLabel("Industry")).toBeVisible();
  });

  test("an existing user can log back in with the same credentials", async ({ page }) => {
    const org = await signup(page, "auth-relogin");

    // Real session round trip: log out, then log back in with the same
    // real credentials created moments ago.
    await logout(page);
    await expect(page).toHaveURL(/\/login/);

    await login(page, org);
    await page.getByRole("button", { name: "User menu" }).click();
    await expect(page.getByText(org.organizationName)).toBeVisible();
  });

  test("a wrong password is rejected with a real error, not a silent failure", async ({ page }) => {
    const org = await signup(page, "auth-wrongpw");
    await logout(page);

    await page.goto("/login");
    await page.getByLabel("Email").fill(org.email);
    await page.getByLabel("Password").fill("definitely-the-wrong-password");
    await page.getByRole("button", { name: "Log in" }).click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText("Invalid email or password")).toBeVisible();
  });
});
