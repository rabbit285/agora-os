import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AIProviderStatus } from "@/lib/types";

import AIProvidersSettingsPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AIProvidersSettingsPage />
    </QueryClientProvider>,
  );
}

describe("AIProvidersSettingsPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("shows a demo-mode banner when no provider is active", async () => {
    const providers: AIProviderStatus[] = [
      { provider_key: "anthropic", name: "Anthropic", has_adapter: true, configured: false, active: false },
      { provider_key: "azure_openai", name: "Azure OpenAI", has_adapter: false, configured: false, active: false },
    ];
    mockedApiFetch.mockResolvedValue(providers);
    renderPage();

    expect(await screen.findByText(/running in demo mode/)).toBeInTheDocument();
    expect(await screen.findByText("Not configured")).toBeInTheDocument();
    expect(await screen.findByText("Not built")).toBeInTheDocument();
  });

  it("shows the active provider without a demo-mode banner", async () => {
    const providers: AIProviderStatus[] = [
      { provider_key: "anthropic", name: "Anthropic", has_adapter: true, configured: true, active: true },
    ];
    mockedApiFetch.mockResolvedValue(providers);
    renderPage();

    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.queryByText(/running in demo mode/)).not.toBeInTheDocument();
  });
});
