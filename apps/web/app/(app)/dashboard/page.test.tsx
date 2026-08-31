import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ComplianceDashboard } from "@/lib/types";

import DashboardPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const dashboard: ComplianceDashboard = {
  readiness_percent: 41.5,
  readiness_explanation:
    "41.5% across 2 adopted frameworks, weighted by their 43 requirements. This measures the evidence held in Veyntra, not a legal conclusion about compliance.",
  critical_gap_count: 4,
  open_risk_count: 7,
  ai_system_count: 3,
  high_risk_ai_system_count: 1,
  overdue_action_count: 2,
  frameworks: [
    {
      framework_id: "f1",
      key: "gdpr",
      name: "GDPR",
      readiness_percent: 52,
      explanation: "52% because ...",
      open_gap_count: 3,
    },
  ],
  critical_issues: [],
  systems_at_risk: [
    {
      ai_system_id: "s1",
      name: "Customer Support AI",
      risk_classification: "limited",
      readiness_percent: 30,
      open_action_count: 2,
    },
  ],
  recent_activity: [{ count: 8, label: "evidence mappings accepted automatically" }],
  recommended_next_actions: [
    {
      title: "Review 5 evidence mappings",
      detail: "Approving evidence can close gaps without any remediation work.",
      href: "/review",
      priority: "high",
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DashboardPage />
    </QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  it("shows readiness together with the arithmetic behind it", async () => {
    // The number must never appear alone: a bare percentage invites the
    // reader to treat it as a verdict, and it is not one.
    mockedApiFetch.mockResolvedValue(dashboard);
    renderPage();

    expect(await screen.findByText("41.5%")).toBeInTheDocument();
    expect(
      await screen.findByText(/weighted by their 43 requirements/),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/not a legal conclusion about compliance/),
    ).toBeInTheDocument();
  });

  it("renders the headline counts from real data rather than placeholders", async () => {
    mockedApiFetch.mockResolvedValue(dashboard);
    renderPage();

    expect(await screen.findByText("Critical gaps")).toBeInTheDocument();
    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(await screen.findByText("7")).toBeInTheDocument();
    expect(await screen.findByText("Overdue actions")).toBeInTheDocument();
  });

  it("tells the customer what to do next, linking to where it is done", async () => {
    mockedApiFetch.mockResolvedValue(dashboard);
    renderPage();

    const action = await screen.findByText("Review 5 evidence mappings");
    expect(action).toBeInTheDocument();
    expect(action.closest("a")).toHaveAttribute("href", "/review");
  });

  it("attributes recent activity to the audit trail rather than narrating it", async () => {
    mockedApiFetch.mockResolvedValue(dashboard);
    renderPage();

    expect(
      await screen.findByText(/evidence mappings accepted automatically/),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Counted from your audit trail/)).toBeInTheDocument();
  });

  it("says plainly that nothing is adopted rather than showing a bare 0%", async () => {
    mockedApiFetch.mockResolvedValue({
      ...dashboard,
      readiness_percent: 0,
      readiness_explanation:
        "No framework adopted yet, so there is nothing to measure against.",
      frameworks: [],
    } satisfies ComplianceDashboard);
    renderPage();

    expect(
      await screen.findByText(/No framework adopted yet, so there is nothing to measure/),
    ).toBeInTheDocument();
    expect(await screen.findByText("No framework adopted yet.")).toBeInTheDocument();
  });
});
