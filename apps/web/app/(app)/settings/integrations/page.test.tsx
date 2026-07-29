import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  IntegrationConnection,
  ProviderCatalogEntry,
  SyncRun,
  Workflow,
} from "@/lib/types";

import IntegrationsSettingsPage from "./page";

vi.mock("@/lib/api", () => ({
  API_URL: "http://test-api.invalid",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const PROVIDERS: ProviderCatalogEntry[] = [
  { connector_key: "webhook", name: "Webhook", auth_type: "hmac", configured: true, scopes: [] },
  {
    connector_key: "hubspot",
    name: "HubSpot",
    auth_type: "oauth2",
    configured: false,
    scopes: ["crm.objects.contacts.read", "crm.objects.companies.read"],
  },
  {
    connector_key: "google",
    name: "Google",
    auth_type: "oauth2",
    configured: true,
    scopes: ["openid", "email", "https://www.googleapis.com/auth/calendar.readonly"],
  },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <IntegrationsSettingsPage />
    </QueryClientProvider>,
  );
}

function mockRoutes(overrides: {
  connections?: IntegrationConnection[];
  workflows?: Workflow[];
  syncRuns?: SyncRun[];
}) {
  mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
    if (path === "/api/v1/integrations/providers") return PROVIDERS;
    if (path === "/api/v1/integrations/connections") return overrides.connections ?? [];
    if (path === "/api/v1/automation/workflows") return overrides.workflows ?? [];
    if (path.endsWith("/sync-runs")) return overrides.syncRuns ?? [];
    if (path.endsWith("/events")) return [];
    if (options?.method === "POST" && path.endsWith("/disconnect")) {
      const connection = overrides.connections?.[0];
      return { ...connection, status: "disconnected", health_status: null };
    }
    if (options?.method === "POST" && path.includes("/oauth/") && path.endsWith("/start")) {
      return {
        connection_id: "11111111-1111-1111-1111-111111111111",
        authorization_url: "https://provider.example.invalid/authorize?mock=1",
      };
    }
    throw new Error(`Unmocked path: ${path} (${options?.method ?? "GET"})`);
  });
}

describe("IntegrationsSettingsPage — provider catalog", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    // jsdom doesn't implement navigation; stub href assignment so a
    // successful "Connect" flow doesn't throw during the test.
    Object.defineProperty(window, "location", {
      value: { ...window.location, href: "" },
      writable: true,
    });
  });

  it("shows Not configured for providers without real credentials, and a Connect button for configured ones", async () => {
    mockRoutes({});
    renderPage();

    const hubspotCard = (await screen.findByText("HubSpot")).closest(
      "div.flex.items-center.justify-between",
    ) as HTMLElement;
    expect(within(hubspotCard).getByText("Not configured")).toBeInTheDocument();

    const googleCard = screen.getByText("Google").closest(
      "div.flex.items-center.justify-between",
    ) as HTMLElement;
    expect(within(googleCard).getByRole("button", { name: "Connect" })).toBeInTheDocument();
  });

  it("previews the requested scopes before redirecting, and only calls the OAuth start endpoint after Authorize is clicked", async () => {
    mockRoutes({});
    renderPage();
    const user = userEvent.setup();

    const connectButton = await screen.findByRole("button", { name: "Connect" });
    await user.click(connectButton);

    expect(screen.getByText("Connecting Google will request:")).toBeInTheDocument();
    expect(screen.getByText("openid")).toBeInTheDocument();
    expect(
      screen.getByText("https://www.googleapis.com/auth/calendar.readonly"),
    ).toBeInTheDocument();

    // Merely previewing must never start the real OAuth flow.
    expect(mockedApiFetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/oauth/google/start"),
      expect.anything(),
    );

    await user.click(screen.getByRole("button", { name: "Authorize on Google" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        "/api/v1/integrations/connections/oauth/google/start",
        { method: "POST" },
      ),
    );
  });
});

describe("IntegrationsSettingsPage — OAuth connection lifecycle", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  const connectedGoogle: IntegrationConnection = {
    id: "22222222-2222-2222-2222-222222222222",
    connector_key: "google",
    name: "Google",
    status: "connected",
    webhook_secret: null,
    linked_workflow_id: null,
    scopes: ["openid", "email"],
    external_account_id: "mock-google-account-0001",
    health_status: "ok",
    last_health_check_at: new Date().toISOString(),
    last_synced_at: null,
    last_error: null,
    created_at: new Date().toISOString(),
  };

  it("shows health/refresh/sync/disconnect controls for a connected OAuth connection", async () => {
    mockRoutes({ connections: [connectedGoogle] });
    renderPage();

    expect(await screen.findByText(/mock-google-account-0001/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check health" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh token" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Disconnect" })).toBeInTheDocument();
  });

  it("disabled the Sync now button and shows Syncing while a sync run is in flight", async () => {
    mockRoutes({
      connections: [connectedGoogle],
      syncRuns: [
        {
          id: "33333333-3333-3333-3333-333333333333",
          connection_id: connectedGoogle.id,
          status: "running",
          items_synced: null,
          error: null,
          started_at: new Date().toISOString(),
          completed_at: null,
        },
      ],
    });
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Show sync history" }));

    expect(await screen.findByRole("button", { name: "Syncing…" })).toBeDisabled();
  });

  it("calls the disconnect endpoint when Disconnect is clicked", async () => {
    mockRoutes({ connections: [connectedGoogle] });
    renderPage();
    const user = userEvent.setup();

    const disconnectButton = await screen.findByRole("button", { name: "Disconnect" });
    await user.click(disconnectButton);

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        `/api/v1/integrations/connections/${connectedGoogle.id}/disconnect`,
        { method: "POST" },
      ),
    );
  });
});
