import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DPIA, DSAR, ProcessingActivity } from "@/lib/types";

import CompliancePage from "./page";

vi.mock("@/lib/api", () => ({
  API_URL: "http://test-api.invalid",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const PROCESSING_ACTIVITY: ProcessingActivity = {
  id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  name: "Candidate application processing",
  purpose: "Collect and evaluate job applications",
  legal_basis: "legitimate_interests",
  data_categories: ["contact_info"],
  data_subjects: "job applicants",
  retention_period: "12 months",
  status: "active",
  owner_id: null,
  created_at: new Date().toISOString(),
};

const DPIA_FIXTURE: DPIA = {
  id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  processing_activity_id: PROCESSING_ACTIVITY.id,
  ai_system_id: null,
  title: "Candidate application processing DPIA",
  risk_level: "medium",
  status: "draft",
  findings: null,
  approval_id: null,
  owner_id: null,
  created_at: new Date().toISOString(),
};

const DSAR_FIXTURE: DSAR = {
  id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
  requester_name: "Priya Nandakumar",
  requester_email: "priya@example.com",
  request_type: "access",
  status: "received",
  due_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
  fulfilled_at: null,
  notes: null,
  assigned_to: null,
  created_at: new Date().toISOString(),
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CompliancePage />
    </QueryClientProvider>,
  );
}

function mockRoutes(overrides: {
  processingActivities?: ProcessingActivity[];
  dpias?: DPIA[];
  dsars?: DSAR[];
}) {
  mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
    if (path === "/api/v1/compliance/controls") return [];
    if (path === "/api/v1/compliance/risks") return [];
    if (path === "/api/v1/compliance/ai-systems") return [];
    if (path === "/api/v1/compliance/frameworks") return [];
    if (path === "/api/v1/compliance/processing-activities") {
      return overrides.processingActivities ?? [];
    }
    if (path === "/api/v1/compliance/dpias") return overrides.dpias ?? [];
    if (path === "/api/v1/compliance/dsars") return overrides.dsars ?? [];
    throw new Error(`Unmocked path: ${path} (${options?.method ?? "GET"})`);
  });
}

describe("CompliancePage — Privacy sections", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders the RoPA, DPIA, and DSAR sections with their seeded data", async () => {
    mockRoutes({
      processingActivities: [PROCESSING_ACTIVITY],
      dpias: [DPIA_FIXTURE],
      dsars: [DSAR_FIXTURE],
    });
    renderPage();

    expect(await screen.findByText("Record of Processing Activities (RoPA)")).toBeInTheDocument();
    expect(await screen.findByText("Candidate application processing")).toBeInTheDocument();

    expect(screen.getByText("Data Protection Impact Assessments (DPIA)")).toBeInTheDocument();
    expect(await screen.findByText("Candidate application processing DPIA")).toBeInTheDocument();

    expect(screen.getByText("Data Subject Access Requests (DSAR)")).toBeInTheDocument();
    expect(await screen.findByText("Priya Nandakumar")).toBeInTheDocument();
  });

  it("logs a new DSAR with the selected request type", async () => {
    mockRoutes({});
    renderPage();
    const user = userEvent.setup();

    await user.type(await screen.findByPlaceholderText("Requester name"), "New Requester");
    await user.type(screen.getByPlaceholderText("Requester email"), "new@example.com");
    await user.selectOptions(screen.getByDisplayValue("Access"), "deletion");
    await user.click(screen.getByRole("button", { name: "Log DSAR" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/compliance/dsars", {
        method: "POST",
        body: {
          requester_name: "New Requester",
          requester_email: "new@example.com",
          request_type: "deletion",
        },
      }),
    );
  });

  it("shows a linked-AI-system hint for a DPIA created via the registration hook", async () => {
    mockRoutes({
      dpias: [{ ...DPIA_FIXTURE, processing_activity_id: null, ai_system_id: "some-ai-system-id" }],
    });
    renderPage();

    expect(await screen.findByText("Linked to an AI system")).toBeInTheDocument();
  });
});
