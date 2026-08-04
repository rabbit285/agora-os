import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OrganizationSettings } from "@/lib/types";

import DataManagementPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const activeOrg: OrganizationSettings = {
  id: "org-1",
  name: "Acme Inc",
  slug: "acme-inc",
  notification_webhook_url: null,
  deletion_requested_at: null,
};

const pendingOrg: OrganizationSettings = { ...activeOrg, deletion_requested_at: "2026-08-04T09:00:00Z" };

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DataManagementPage />
    </QueryClientProvider>,
  );
}

describe("DataManagementPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    Object.defineProperty(window, "location", {
      value: { ...window.location, href: "" },
      writable: true,
    });
  });

  it("requires typing the org name before Request deletion is enabled", async () => {
    mockedApiFetch.mockResolvedValue(activeOrg);
    renderPage();

    const button = await screen.findByRole("button", { name: "Request deletion" });
    expect(button).toBeDisabled();
  });

  it("requests deletion once the name is typed", async () => {
    mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/v1/organizations/current" && (options?.method ?? "GET") === "GET") return activeOrg;
      if (path === "/api/v1/organizations/current/deletion-request" && options?.method === "POST") {
        return pendingOrg;
      }
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();
    const user = userEvent.setup();

    const input = await screen.findByPlaceholderText("Type the organization name to confirm");
    await user.type(input, "Acme Inc");
    await user.click(screen.getByRole("button", { name: "Request deletion" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/organizations/current/deletion-request", {
        method: "POST",
        body: { confirm_name: "Acme Inc" },
      }),
    );
  });

  it("shows the pending-deletion state with cancel and execute controls", async () => {
    mockedApiFetch.mockResolvedValue(pendingOrg);
    renderPage();

    expect(await screen.findByText("Deletion requested")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Cancel deletion request" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Permanently delete now" })).toBeInTheDocument();
  });

  it("downloads the export via a real signed link", async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/organizations/current") return activeOrg;
      if (path.startsWith("/api/v1/organizations/current/data-export")) {
        return { download_url: "https://storage.example.com/export.xlsx" };
      }
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Download export" }));

    await waitFor(() => expect(window.location.href).toBe("https://storage.example.com/export.xlsx"));
  });
});
