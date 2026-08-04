import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Recommendation } from "@/lib/types";

import RecommendationsPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const recommendation: Recommendation = {
  id: "rec-1",
  category: "compliance",
  title: "Address 3 compliance control gaps",
  business_impact: "Unimplemented controls reduce your compliance posture.",
  reason: "3 controls have not been started.",
  sources: ["control:a", "control:b", "control:c"],
  confidence: "high",
  estimated_value: null,
  suggested_action: "Review and assign owners to unimplemented controls.",
  risk: "medium",
  required_approval: false,
  status: "new",
  created_at: "2026-08-04T12:00:00Z",
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RecommendationsPage />
    </QueryClientProvider>,
  );
}

describe("RecommendationsPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("shows an honest empty state when there are no recommendations", async () => {
    mockedApiFetch.mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText(/nothing in your data currently crosses a threshold/i)).toBeInTheDocument();
  });

  it("renders a recommendation with its real source count and category", async () => {
    mockedApiFetch.mockResolvedValue([recommendation]);
    renderPage();

    expect(await screen.findByText("Address 3 compliance control gaps")).toBeInTheDocument();
    expect(await screen.findByText("3 sources")).toBeInTheDocument();
    expect(await screen.findByText("compliance")).toBeInTheDocument();
  });

  it("dismisses a recommendation and refetches the list", async () => {
    mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/v1/recommendations" && (options?.method ?? "GET") === "GET") {
        return [recommendation];
      }
      if (path === "/api/v1/recommendations/rec-1/dismiss") {
        return { ...recommendation, status: "dismissed" };
      }
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Dismiss" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/recommendations/rec-1/dismiss", {
        method: "POST",
      }),
    );
  });
});
