import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BusinessRule } from "@/lib/types";

import BusinessRulesPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const rule: BusinessRule = {
  id: "rule-1",
  name: "Critical alerts notify security manager",
  trigger_type: "security_alert",
  condition_field: "severity",
  condition_operator: "==",
  condition_value: "critical",
  action_type: "notify",
  action_role_key: "security_manager",
  action_risk_class: null,
  is_active: true,
  created_at: "2026-08-04T07:00:00Z",
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BusinessRulesPage />
    </QueryClientProvider>,
  );
}

describe("BusinessRulesPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders a rule with its real condition and action", async () => {
    mockedApiFetch.mockResolvedValue([rule]);
    renderPage();

    expect(await screen.findByText("Critical alerts notify security manager")).toBeInTheDocument();
    expect(await screen.findByText(/severity == critical/)).toBeInTheDocument();
    expect(await screen.findByText("Active")).toBeInTheDocument();
  });

  it("deactivates a rule", async () => {
    mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/v1/business-rules" && (options?.method ?? "GET") === "GET") return [rule];
      if (path === "/api/v1/business-rules/rule-1" && options?.method === "PATCH") {
        return { ...rule, is_active: false };
      }
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Deactivate" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/business-rules/rule-1", {
        method: "PATCH",
        body: { is_active: false },
      }),
    );
  });

  it("shows an honest empty state when no rules are configured", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText("No business rules configured yet.")).toBeInTheDocument();
  });
});
