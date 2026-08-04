import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Approval, Control, SecurityOverview, Task } from "@/lib/types";

import DashboardPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const tasks: Task[] = [
  { id: "t1", title: "Task 1", status: "open" } as Task,
  { id: "t2", title: "Task 2", status: "done" } as Task,
];
const approvals: Approval[] = [
  { id: "a1", status: "pending", action_type: "test.action", risk_class: "low", module: "compliance" } as Approval,
];
const controls: Control[] = [
  { id: "c1", status: "implemented" } as Control,
  { id: "c2", status: "not_started" } as Control,
];
const securityOverview: SecurityOverview = {
  security_score: 74,
  critical_alerts: 0,
  high_risks: 0,
  assets_monitored: 0,
  vulnerabilities_open: 0,
  identity_issues_open: 0,
  cloud_misconfigurations_open: 0,
  open_incidents: 0,
  evidence_coverage_percent: 0,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DashboardPage />
    </QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  it("computes Compliance Health and Security Posture from real data, not a placeholder", async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/tasks") return tasks;
      if (path === "/api/v1/approvals") return approvals;
      if (path === "/api/v1/compliance/controls") return controls;
      if (path === "/api/v1/security/overview") return securityOverview;
      throw new Error(`Unmocked path: ${path}`);
    });

    renderPage();

    // Open Tasks and Pending Approvals both resolve to "1" — assert the
    // count rather than picking one via findByText.
    expect((await screen.findAllByText("1")).length).toBe(2);
    expect(await screen.findByText("50%")).toBeInTheDocument(); // 1 of 2 controls implemented
    expect(await screen.findByText("74/100")).toBeInTheDocument(); // security score
  });

  it("shows an honest empty state instead of 0% when the org has no controls yet", async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/tasks") return [];
      if (path === "/api/v1/approvals") return [];
      if (path === "/api/v1/compliance/controls") return [];
      if (path === "/api/v1/security/overview") return securityOverview;
      throw new Error(`Unmocked path: ${path}`);
    });

    renderPage();

    expect(await screen.findByText("No controls yet")).toBeInTheDocument();
  });
});
