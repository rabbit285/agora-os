import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Briefing } from "@/lib/types";

import BriefingPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const briefing: Briefing = {
  id: "briefing-1",
  briefing_date: "2026-08-04",
  ai_suggestion: "Remediate 1 critical/high security finding. Triage and remediate the open critical/high findings.",
  created_at: "2026-08-04T06:00:00Z",
  sections: [
    { key: "urgent", label: "Urgent", headline: "1 critical security alert needs attention", items: [{ text: "Live alert", link: "/security" }] },
    { key: "revenue", label: "Revenue", headline: "No open opportunities need follow-up", items: [] },
    { key: "customers", label: "Customers", headline: "No support activity this week", items: [] },
    { key: "risk", label: "Risk", headline: "No DSARs approaching deadline", items: [] },
    { key: "operations", label: "Operations", headline: "No workflow failures in the last 24 hours", items: [] },
  ],
};

describe("BriefingPage", () => {
  it("renders all 5 sections and the AI suggestion", async () => {
    mockedApiFetch.mockResolvedValue(briefing);
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <BriefingPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Urgent")).toBeInTheDocument();
    expect(await screen.findByText("1 critical security alert needs attention")).toBeInTheDocument();
    expect(await screen.findByText("Live alert")).toBeInTheDocument();
    expect(await screen.findByText(/Remediate 1 critical\/high security finding/)).toBeInTheDocument();
    expect(await screen.findByText("Operations")).toBeInTheDocument();
  });

  it("omits the AI suggestion card when there is none", async () => {
    mockedApiFetch.mockResolvedValue({ ...briefing, ai_suggestion: null });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <BriefingPage />
      </QueryClientProvider>,
    );

    await screen.findByText("Urgent");
    expect(screen.queryByText("AI suggestion")).not.toBeInTheDocument();
  });
});
