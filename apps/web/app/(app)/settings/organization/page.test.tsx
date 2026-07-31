import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { LegalEntity, Organization, Team } from "@/lib/types";

import OrganizationSettingsPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const organization: Organization = {
  id: "org-1",
  name: "Agora Test Org",
  slug: "agora-test-org",
  notification_webhook_url: null,
};

const defaultEntity: LegalEntity = {
  id: "entity-1",
  name: "Agora Test Org",
  country: null,
  is_default: true,
  is_active: true,
  created_at: new Date().toISOString(),
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrganizationSettingsPage />
    </QueryClientProvider>,
  );
}

describe("OrganizationSettingsPage — notification webhook URL", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string; body?: unknown }) => {
      if (path === "/api/v1/organizations/current" && (options?.method ?? "GET") === "GET") {
        return organization;
      }
      if (path === "/api/v1/organizations/current" && options?.method === "PATCH") {
        return { ...organization, ...(options.body as object) };
      }
      if (path === "/api/v1/organizations/current/legal-entities") return [defaultEntity] as LegalEntity[];
      if (path === "/api/v1/organizations/current/teams") return [] as Team[];
      throw new Error(`Unmocked path: ${path} (${options?.method ?? "GET"})`);
    });
  });

  it("saves the notification webhook URL without clobbering the org name", async () => {
    renderPage();
    const user = userEvent.setup();

    const webhookInput = await screen.findByPlaceholderText("https://hooks.example.com/agora");
    await user.type(webhookInput, "https://hooks.example.test/agora");

    await user.click(await screen.findByRole("button", { name: "Save webhook URL" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/organizations/current", {
        method: "PATCH",
        body: {
          name: "Agora Test Org",
          notification_webhook_url: "https://hooks.example.test/agora",
        },
      }),
    );
  });
});
