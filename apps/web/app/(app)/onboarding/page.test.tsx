import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Framework, OnboardingProfile, Readiness } from "@/lib/types";

import OnboardingPage from "./page";

vi.mock("@/lib/api", () => ({
  apiFetch: vi.fn(),
}));
const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OnboardingPage />
    </QueryClientProvider>,
  );
}

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

describe("OnboardingPage", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    pushMock.mockReset();
  });

  it("resumes at the company step for a brand-new profile", async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/onboarding/status") return freshProfile;
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();

    expect(await screen.findByText(/Tell us about your company/)).toBeInTheDocument();
  });

  it("resumes at the goals step when current_step indicates progress", async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/onboarding/status") return { ...freshProfile, current_step: 2 };
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();

    expect(await screen.findByText(/What do you want to improve/)).toBeInTheDocument();
  });

  it("submits the company step and advances to goals", async () => {
    mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/v1/onboarding/status") return freshProfile;
      if (path === "/api/v1/onboarding/company" && options?.method === "PUT") {
        return { ...freshProfile, current_step: 2 };
      }
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();
    const user = userEvent.setup();

    const industryInput = await screen.findByLabelText("Industry");
    await user.type(industryInput, "Software");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/onboarding/company", {
        method: "PUT",
        body: { industry: "Software", employee_count_range: "1-10" },
      }),
    );
    expect(await screen.findByText(/What do you want to improve/)).toBeInTheDocument();
  });

  it("shows the real computed readiness dimensions on the final step", async () => {
    const readiness: Readiness = {
      compliance: { label: "Compliance", percent: 50 },
      security: { label: "Security", percent: 100 },
      sales_automation: { label: "Sales Automation", percent: 0 },
      support_automation: { label: "Support Automation", percent: 0 },
      process_automation: { label: "Process Automation", percent: 0 },
      opportunities: [{ title: "Enable MFA for 1 administrator", detail: "detail here" }],
    };
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === "/api/v1/onboarding/status") return { ...freshProfile, current_step: 9 };
      if (path === "/api/v1/onboarding/readiness") return readiness;
      if (path === "/api/v1/compliance/frameworks") return [] as Framework[];
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();

    expect(await screen.findByText("Your Business AI Readiness")).toBeInTheDocument();
    expect(await screen.findByText("50%")).toBeInTheDocument();
    expect(await screen.findByText(/Enable MFA for 1 administrator/)).toBeInTheDocument();
  });

  it("completing the readiness step navigates to the dashboard", async () => {
    const readiness: Readiness = {
      compliance: { label: "Compliance", percent: 0 },
      security: { label: "Security", percent: 100 },
      sales_automation: { label: "Sales Automation", percent: 0 },
      support_automation: { label: "Support Automation", percent: 0 },
      process_automation: { label: "Process Automation", percent: 0 },
      opportunities: [],
    };
    mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === "/api/v1/onboarding/status") return { ...freshProfile, current_step: 9 };
      if (path === "/api/v1/onboarding/readiness") return readiness;
      if (path === "/api/v1/onboarding/complete" && options?.method === "POST") {
        return { ...freshProfile, current_step: 10, completed_at: new Date().toISOString() };
      }
      throw new Error(`Unmocked path: ${path}`);
    });
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Open Business Command Center" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/"));
  });
});
