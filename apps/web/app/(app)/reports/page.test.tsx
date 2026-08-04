import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Report, ReportType } from "@/lib/types";

import ReportsPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const reportTypes: ReportType[] = [
  { key: "board", label: "Board Report" },
  { key: "risk", label: "Risk Report" },
];

const existingReport: Report = {
  id: "report-1",
  report_type: "board",
  format: "pdf",
  status: "completed",
  error_message: null,
  created_at: "2026-07-30T12:00:00Z",
};

describe("ReportsPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    Object.defineProperty(window, "location", {
      value: { ...window.location, href: "" },
      writable: true,
    });
    mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/v1/reports/types") return reportTypes;
      if (path === "/api/v1/reports" && (options?.method ?? "GET") === "GET") return [existingReport];
      if (path === "/api/v1/reports" && options?.method === "POST") {
        return { ...existingReport, id: "report-2" };
      }
      if (path === "/api/v1/reports/report-1/download") {
        return { download_url: "https://storage.example.com/signed-link" };
      }
      throw new Error(`Unmocked path: ${path}`);
    });
  });

  it("lists previously generated reports", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ReportsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/board report/i)).toBeInTheDocument();
    expect(await screen.findByText("completed")).toBeInTheDocument();
  });

  it("generates a new report with the selected type and format", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ReportsPage />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();

    await screen.findByText(/board report/i);
    await user.selectOptions(await screen.findByLabelText("Report"), "risk");
    await user.selectOptions(screen.getByLabelText("Format"), "csv");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/reports", {
        method: "POST",
        body: { report_type: "risk", format: "csv" },
      }),
    );
  });

  it("fetches a secure download link and navigates to it when Download is clicked", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ReportsPage />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Download" }));

    await waitFor(() => expect(window.location.href).toBe("https://storage.example.com/signed-link"));
  });
});
