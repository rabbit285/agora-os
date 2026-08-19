import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { OnboardingProfile, Readiness } from "@/lib/types";

import OnboardingPage from "./page";

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
  ApiError: class ApiError extends Error {},
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const freshProfile: OnboardingProfile = {
  industry: null,
  employee_count_range: null,
  selected_goals: [],
  selected_framework_keys: [],
  primary_cloud_provider: null,
  sales_focus: null,
  support_channels: [],
  current_step: 1,
  completed_at: null,
};

const readiness: Readiness = {
  compliance: { label: "Controls implemented", percent: 50 },
  evidence_coverage: { label: "Evidence coverage", percent: 25 },
  framework_adoption: { label: "Frameworks adopted", percent: 40 },
  security: { label: "Security", percent: 100 },
  opportunities: [{ title: "Adopt your first framework", detail: "detail here" }],
};

/** Every step pulls from a different endpoint, and several reuse the same
 * components the main product does. Routing by path keeps the mock honest
 * about which call each step actually makes. */
function mockPaths(overrides: Record<string, unknown> = {}) {
  mockedApiFetch.mockImplementation(async (path: string) => {
    for (const [prefix, value] of Object.entries(overrides)) {
      if (path.startsWith(prefix)) return value;
    }
    if (path.startsWith("/api/v1/onboarding/status")) return freshProfile;
    if (path.startsWith("/api/v1/onboarding/readiness")) return readiness;
    if (path.startsWith("/api/v1/compliance/framework-recommendations")) {
      return { recommendations: [], facts_declared: false };
    }
    if (path.startsWith("/api/v1/compliance/ai-systems")) return [];
    if (path.startsWith("/api/v1/compliance/documents")) return [];
    if (path.startsWith("/api/v1/compliance/evidence/suggestions")) return [];
    if (path.startsWith("/api/v1/compliance/controls")) return [];
    return {};
  });
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <OnboardingPage />
    </QueryClientProvider>,
  );
}

describe("OnboardingPage", () => {
  beforeEach(() => {
    pushMock.mockReset();
    mockedApiFetch.mockReset();
  });

  it("starts by asking what the company is", async () => {
    mockPaths();
    renderPage();

    expect(await screen.findByText("Tell us about your company")).toBeInTheDocument();
    expect(await screen.findByLabelText("Industry")).toBeInTheDocument();
  });

  it("does not ask for a sales focus or support channels", async () => {
    // Those steps belonged to modules the product no longer has, and
    // asked for information that changes no compliance obligation.
    mockPaths();
    renderPage();

    await screen.findByText("Tell us about your company");
    expect(screen.queryByText(/sales focus/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/support channels/i)).not.toBeInTheDocument();
  });

  it("resumes where the customer left off", async () => {
    mockPaths({ "/api/v1/onboarding/status": { ...freshProfile, current_step: 3 } });
    renderPage();

    expect(await screen.findByText("What AI do you run?")).toBeInTheDocument();
  });

  it("lets a company without AI move past that step", async () => {
    mockPaths({ "/api/v1/onboarding/status": { ...freshProfile, current_step: 3 } });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "We don't use AI yet" }));

    expect(await screen.findByText("Upload your documents")).toBeInTheDocument();
  });

  it("shows the real computed readiness dimensions on the final step", async () => {
    mockPaths({ "/api/v1/onboarding/status": { ...freshProfile, current_step: 5 } });
    renderPage();

    expect(await screen.findByText("Where you stand")).toBeInTheDocument();
    expect(await screen.findByText("50%")).toBeInTheDocument();
    expect(await screen.findByText(/Adopt your first framework/)).toBeInTheDocument();
  });

  it("completing the readiness step navigates to the dashboard", async () => {
    mockPaths({ "/api/v1/onboarding/status": { ...freshProfile, current_step: 5 } });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Go to my dashboard" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard"));
  });
});
