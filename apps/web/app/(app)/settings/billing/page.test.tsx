import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OrganizationPlan, Plan, Subscription } from "@/lib/types";

import BillingSettingsPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

const searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams,
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const plans: Plan[] = [
  { key: "starter", name: "Starter", entitlements: { max_users: 5, sso_enabled: false } },
  { key: "growth", name: "Growth", entitlements: { max_users: 25, sso_enabled: true } },
];

const trialingSubscription: Subscription = {
  status: "trialing",
  access_state: "trialing",
  plan_key: "starter",
  trial_ends_at: "2026-09-01T00:00:00Z",
  trial_days_remaining: 9,
  current_period_end: null,
  cancel_at_period_end: false,
  payments_configured: true,
  has_payment_method: false,
  tax_id: null,
};

const current: OrganizationPlan = {
  plan_key: "starter",
  entitlements: { max_users: 5, sso_enabled: false },
  current_users: 1,
  subscription: trialingSubscription,
};

function mockApi(overrides: Partial<OrganizationPlan> = {}) {
  mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
    if (path === "/api/v1/billing/plans") return plans;
    if (path === "/api/v1/billing/current" && (options?.method ?? "GET") === "GET") {
      return { ...current, ...overrides };
    }
    if (path === "/api/v1/billing/checkout") {
      return { checkout_url: "https://checkout.stripe.com/c/pay/cs_test_123" };
    }
    if (path === "/api/v1/billing/current" && options?.method === "PUT") {
      return { ...current, ...overrides, plan_key: "starter" };
    }
    throw new Error(`Unmocked path: ${path}`);
  });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BillingSettingsPage />
    </QueryClientProvider>,
  );
}

describe("BillingSettingsPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    mockApi();
  });

  it("shows the current plan and marks it with a badge", async () => {
    renderPage();

    expect(await screen.findByText(/Current plan:/)).toBeInTheDocument();
    expect(await screen.findByText("Current")).toBeInTheDocument();
    expect(await screen.findByText("1 user active")).toBeInTheDocument();
  });

  it("shows entitlements per plan, including unlimited/boolean formatting", async () => {
    renderPage();

    expect((await screen.findAllByText("Users")).length).toBe(2);
    expect(await screen.findByText("5")).toBeInTheDocument();
    expect(await screen.findByText("Not included")).toBeInTheDocument();
    expect(await screen.findByText("Included")).toBeInTheDocument();
  });

  it("tells a trialing customer how long they have left and that no card is on file", async () => {
    renderPage();

    expect(await screen.findByText("9 days left in your free trial")).toBeInTheDocument();
    expect(await screen.findByText(/No card is on file/)).toBeInTheDocument();
  });

  it("sends an upgrade to Stripe Checkout rather than changing the plan directly", async () => {
    // The regression that matters: a paid plan must never be granted by a
    // PUT from the browser. The button starts a checkout session instead.
    const assign = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { href: "http://localhost/settings/billing", assign },
    });

    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Upgrade to Growth" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/billing/checkout", {
        method: "POST",
        body: { plan_key: "growth" },
      }),
    );
    expect(mockedApiFetch).not.toHaveBeenCalledWith(
      "/api/v1/billing/current",
      expect.objectContaining({ body: { plan_key: "growth" } }),
    );
  });

  it("shows the upgrade screen, not a dead end, once the trial has lapsed", async () => {
    mockApi({
      subscription: { ...trialingSubscription, status: "trial_expired", access_state: "locked" },
    });
    renderPage();

    expect(await screen.findByText("Your free trial has ended")).toBeInTheDocument();
    // The promise that makes locking acceptable: the data is still there.
    expect(await screen.findByText(/kept exactly as you left it/)).toBeInTheDocument();
  });

  it("disables upgrading and says so when the deployment cannot take payments", async () => {
    mockApi({
      subscription: { ...trialingSubscription, payments_configured: false },
    });
    renderPage();

    expect(await screen.findByText(/Online payment is not configured/)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Upgrade to Growth" })).toBeDisabled();
  });

  it("keeps a past-due customer working while telling them to fix their card", async () => {
    mockApi({
      subscription: { ...trialingSubscription, status: "past_due", access_state: "past_due" },
    });
    renderPage();

    expect(await screen.findByText(/could not take your last payment/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Update payment method" })).toBeInTheDocument();
  });
});
