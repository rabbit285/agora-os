import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ProviderStatusOut } from "@/lib/types";

import { ProviderStatusCard } from "./provider-status-card";

vi.mock("@/lib/api", () => ({
  API_URL: "http://test-api.invalid",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

function baseProvider(overrides: Partial<ProviderStatusOut> = {}): ProviderStatusOut {
  return {
    provider_key: "apollo",
    status: "ready_to_connect",
    capabilities: {
      company_search: true,
      people_search: true,
      company_enrichment: true,
      person_enrichment: true,
      decision_makers: true,
      credit_estimation: true,
    },
    configured: false,
    connection_id: null,
    connected_user_email: null,
    connected_workspace_name: null,
    granted_scopes: [],
    can_manage_connection: true,
    ...overrides,
  };
}

function renderCard(provider: ProviderStatusOut) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProviderStatusCard provider={provider} />
    </QueryClientProvider>,
  );
}

describe("ProviderStatusCard (Apollo customer connection)", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("offers Connect to an authorized user when nothing is connected", () => {
    renderCard(baseProvider());
    expect(screen.getByRole("button", { name: "Connect Apollo" })).toBeInTheDocument();
    expect(screen.getByText(/Connect Apollo to search real companies/)).toBeInTheDocument();
  });

  it("tells an unauthorized user to contact their administrator instead", () => {
    renderCard(baseProvider({ can_manage_connection: false }));
    expect(screen.queryByRole("button", { name: "Connect Apollo" })).not.toBeInTheDocument();
    expect(screen.getByText(/Contact your administrator to connect Apollo/)).toBeInTheDocument();
  });

  it("shows a permission preview naming customer credit ownership before redirecting", async () => {
    const user = userEvent.setup();
    renderCard(baseProvider());

    await user.click(screen.getByRole("button", { name: "Connect Apollo" }));

    expect(screen.getByText("Connect your Apollo workspace")).toBeInTheDocument();
    expect(
      screen.getByText(
        /use your organization.s Apollo account, permissions, rate\s+limits, and credits/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/consume your own Apollo credits/i)).toBeInTheDocument();
    // No OAuth request is made until the user explicitly continues.
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });

  it("starts the OAuth flow only after the preview is confirmed", async () => {
    const user = userEvent.setup();
    mockedApiFetch.mockResolvedValue({
      connection_id: "conn-1",
      authorization_url: "https://app.apollo.io/#/oauth/authorize?state=abc",
    });
    renderCard(baseProvider());

    await user.click(screen.getByRole("button", { name: "Connect Apollo" }));
    await user.click(screen.getByRole("button", { name: /Continue to Apollo/ }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        "/api/v1/integrations/connections/oauth/apollo/start",
        { method: "POST" },
      ),
    );
  });

  it("shows the connected Apollo user and workspace once connected", () => {
    renderCard(
      baseProvider({
        status: "connected",
        configured: true,
        connection_id: "conn-1",
        connected_user_email: "rep@customer.example",
        connected_workspace_name: "Customer GTM",
        granted_scopes: ["mixed_companies_search"],
      }),
    );

    expect(screen.getByText(/rep@customer\.example/)).toBeInTheDocument();
    expect(screen.getByText(/Customer GTM/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Connect Apollo" })).not.toBeInTheDocument();
    expect(screen.queryByText(/demo data/i)).not.toBeInTheDocument();
  });

  it("surfaces a reauthorization prompt when the grant is no longer usable", () => {
    renderCard(baseProvider({ status: "revoked", configured: false }));
    expect(screen.getByText(/needs to be authorized again/i)).toBeInTheDocument();
  });

  it("explains demo data honestly when the deployment has no Apollo application", () => {
    renderCard(baseProvider({ status: "not_configured" }));
    expect(screen.getByText(/not available in this deployment yet/i)).toBeInTheDocument();
    // Must not invite a connection that cannot possibly succeed.
    expect(screen.queryByRole("button", { name: "Connect Apollo" })).not.toBeInTheDocument();
  });

  it("never renders a token or secret", () => {
    const { container } = renderCard(
      baseProvider({
        status: "connected",
        configured: true,
        connection_id: "conn-1",
        connected_user_email: "rep@customer.example",
        granted_scopes: ["mixed_companies_search"],
      }),
    );
    expect(container.textContent).not.toMatch(/access_token|refresh_token|client_secret|Bearer /i);
  });
});
