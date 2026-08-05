import { expect, type Page } from "@playwright/test";

export type SignedUpOrg = {
  email: string;
  password: string;
  fullName: string;
  organizationName: string;
};

/** Real signup through the actual UI form against the real running API —
 * every E2E spec gets its own fresh, disposable organization so tests
 * never interfere with each other or with seeded demo data. */
export async function signup(page: Page, label: string): Promise<SignedUpOrg> {
  const unique = `${label}-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
  const org: SignedUpOrg = {
    email: `${unique}@example.com`,
    password: "CorrectHorseBattery9!",
    fullName: `${label} Tester`,
    organizationName: `${label} Org ${unique}`,
  };

  await page.goto("/signup");
  await page.getByLabel("Your name").fill(org.fullName);
  await page.getByLabel("Organization name").fill(org.organizationName);
  await page.getByLabel("Work email").fill(org.email);
  await page.getByLabel("Password").fill(org.password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  return org;
}

export async function login(page: Page, org: Pick<SignedUpOrg, "email" | "password">): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(org.email);
  await page.getByLabel("Password").fill(org.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL("/");
}

/** Log out is a menu item inside the top-nav user menu, not a standalone
 * button — open the menu first. */
export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "User menu" }).click();
  await page.getByRole("menuitem", { name: "Log out" }).click();
}
