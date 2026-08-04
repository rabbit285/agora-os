import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MemoryEntry } from "@/lib/types";

import BusinessMemoryPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const entries: MemoryEntry[] = [
  {
    id: "entry-1",
    entry_type: "policy",
    content: 'Policy published: "Data Retention Policy"',
    provenance_type: "policy",
    provenance_id: "policy-1",
    created_by: null,
    status: "active",
    created_at: "2026-08-04T06:00:00Z",
    updated_at: "2026-08-04T06:00:00Z",
  },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BusinessMemoryPage />
    </QueryClientProvider>,
  );
}

describe("BusinessMemoryPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("shows the manage form and correct/delete controls for a user with business_memory.manage", async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/memory") return entries;
      if (path === "/api/v1/organizations/current/my-permissions") return ["business_memory.manage"];
      throw new Error(`Unmocked path: ${path}`);
    });

    renderPage();

    expect(await screen.findByText("Add a memory entry")).toBeInTheDocument();
    expect(await screen.findByText(/Data Retention Policy/)).toBeInTheDocument();
    expect(await screen.findByText("From published policy")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Correct" })).toBeInTheDocument();
  });

  it("hides write controls for a user without business_memory.manage", async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/memory") return entries;
      if (path === "/api/v1/organizations/current/my-permissions") return ["core.tasks.manage"];
      throw new Error(`Unmocked path: ${path}`);
    });

    renderPage();

    await screen.findByText(/Data Retention Policy/);
    expect(screen.queryByText("Add a memory entry")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Correct" })).not.toBeInTheDocument();
  });

  it("creates a new memory entry", async () => {
    mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/v1/memory" && (options?.method ?? "GET") === "GET") return [];
      if (path === "/api/v1/organizations/current/my-permissions") return ["business_memory.manage"];
      if (path === "/api/v1/memory" && options?.method === "POST") {
        return { ...entries[0], id: "entry-2", content: options.body };
      }
      throw new Error(`Unmocked path: ${path}`);
    });

    renderPage();
    const user = userEvent.setup();

    const textarea = await screen.findByPlaceholderText(/Refunds over/);
    await user.type(textarea, "New rule text");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        "/api/v1/memory",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });
});
