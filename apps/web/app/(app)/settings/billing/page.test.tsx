import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OrganizationPlan, Plan } from "@/lib/types";

import BillingSettingsPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const plans: Plan[] = [
  { key: "starter", name: "Starter", entitlements: { max_users: 5, sso_enabled: false } },
  { key: "growth", name: "Growth", entitlements: { max_users: 25, sso_enabled: true } },
];

const current: OrganizationPlan = {
  plan_key: "starter",
  entitlements: { max_users: 5, sso_enabled: false },
  current_users: 1,
};

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
    mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/v1/billing/plans") return plans;
      if (path === "/api/v1/billing/current" && (options?.method ?? "GET") === "GET") return current;
      if (path === "/api/v1/billing/current" && options?.method === "PUT") {
        return { ...current, plan_key: "growth" };
      }
      throw new Error(`Unmocked path: ${path}`);
    });
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

  it("switches plans when a non-current plan's button is clicked", async () => {
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Switch to Growth" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/billing/current", {
        method: "PUT",
        body: { plan_key: "growth" },
      }),
    );
  });
});
