import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AIIncident,
  AISystem,
  DPIA,
  DSAR,
  ProcessingActivity,
  Questionnaire,
  Vendor,
} from "@/lib/types";

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

const AI_SYSTEM_FIXTURE: AISystem = {
  id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
  name: "Resume Screening Assistant",
  vendor: null,
  purpose: "Ranks job applicants",
  risk_classification: "high",
  status: "in_review",
  owner_id: null,
  approval_id: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
  created_at: new Date().toISOString(),
};

const AI_INCIDENT_FIXTURE: AIIncident = {
  id: "ffffffff-ffff-ffff-ffff-ffffffffffff",
  ai_system_id: AI_SYSTEM_FIXTURE.id,
  title: "Resume screener showed gender bias",
  description: null,
  severity: "critical",
  status: "open",
  related_risk_id: "11111111-2222-3333-4444-555555555555",
  related_task_id: "66666666-7777-8888-9999-000000000000",
  owner_id: null,
  created_at: new Date().toISOString(),
};

const VENDOR_FIXTURE: Vendor = {
  id: "22222222-3333-4444-5555-666666666666",
  name: "QuickScribe Transcription LLC",
  description: "Third-party transcription service.",
  category: "data_processor",
  website: null,
  contact_email: null,
  risk_tier: "critical",
  status: "active",
  owner_id: null,
  created_at: new Date().toISOString(),
};

const QUESTIONNAIRE_FIXTURE: Questionnaire = {
  id: "33333333-4444-5555-6666-777777777777",
  title: "Nordwind Robotics vendor security questionnaire",
  source: "customer_provided",
  status: "in_progress",
  opportunity_id: null,
  owner_id: null,
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
  aiSystems?: AISystem[];
  aiIncidents?: AIIncident[];
  vendors?: Vendor[];
  questionnaires?: Questionnaire[];
}) {
  mockedApiFetch.mockImplementation(async (path: string, options?: { method?: string }) => {
    if (path === "/api/v1/compliance/controls") return [];
    if (path === "/api/v1/compliance/risks") return [];
    if (path === "/api/v1/compliance/ai-systems") return overrides.aiSystems ?? [];
    if (path === "/api/v1/compliance/frameworks") return [];
    if (path === "/api/v1/compliance/processing-activities") {
      return overrides.processingActivities ?? [];
    }
    if (path === "/api/v1/compliance/dpias") return overrides.dpias ?? [];
    if (path === "/api/v1/compliance/dsars") return overrides.dsars ?? [];
    if (options?.method === "POST" && path === "/api/v1/compliance/ai-incidents") {
      return { ...AI_INCIDENT_FIXTURE };
    }
    if (path === "/api/v1/compliance/ai-incidents") return overrides.aiIncidents ?? [];
    if (options?.method === "POST" && path === "/api/v1/compliance/vendors") {
      return { ...VENDOR_FIXTURE };
    }
    if (path === "/api/v1/compliance/vendors") return overrides.vendors ?? [];
    if (options?.method === "POST" && path === "/api/v1/compliance/questionnaires") {
      return { ...QUESTIONNAIRE_FIXTURE };
    }
    if (path === "/api/v1/compliance/questionnaires") return overrides.questionnaires ?? [];
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

describe("CompliancePage — AI Incidents section", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders logged incidents with severity and the linked AI system's name", async () => {
    mockRoutes({ aiSystems: [AI_SYSTEM_FIXTURE], aiIncidents: [AI_INCIDENT_FIXTURE] });
    renderPage();

    expect(await screen.findByText("Resume screener showed gender bias")).toBeInTheDocument();
    // "Resume Screening Assistant" also appears in the AI System Inventory
    // list and the incident-logging dropdown, so there's more than one match.
    expect((await screen.findAllByText("Resume Screening Assistant")).length).toBeGreaterThan(0);
    expect(screen.getByText("critical")).toBeInTheDocument();
  });

  it("logs a new AI incident against the selected system", async () => {
    mockRoutes({ aiSystems: [AI_SYSTEM_FIXTURE] });
    renderPage();
    const user = userEvent.setup();

    // Wait for the AI system list to load before the dropdown has the
    // option to select.
    await screen.findAllByText(AI_SYSTEM_FIXTURE.name);
    await user.selectOptions(
      screen.getByDisplayValue("Select AI system…"),
      AI_SYSTEM_FIXTURE.id,
    );
    await user.type(
      screen.getByPlaceholderText("Incident title"),
      "Model drifted after retraining",
    );
    await user.selectOptions(screen.getByDisplayValue("Low"), "critical");
    await user.click(screen.getByRole("button", { name: "Log incident" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/compliance/ai-incidents", {
        method: "POST",
        body: {
          ai_system_id: AI_SYSTEM_FIXTURE.id,
          title: "Model drifted after retraining",
          severity: "critical",
        },
      }),
    );
  });
});

describe("CompliancePage — Vendors section", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders vendors with their risk tier and status", async () => {
    mockRoutes({ vendors: [VENDOR_FIXTURE] });
    renderPage();

    expect(await screen.findByText("QuickScribe Transcription LLC")).toBeInTheDocument();
    expect(screen.getByText("data_processor")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
  });

  it("adds a new vendor with the entered name and category", async () => {
    mockRoutes({});
    renderPage();
    const user = userEvent.setup();

    await user.type(await screen.findByPlaceholderText("Vendor name"), "New Vendor Inc");
    await user.type(
      screen.getByPlaceholderText("Category (e.g. cloud_infrastructure)"),
      "cloud_infrastructure",
    );
    await user.click(screen.getByRole("button", { name: "Add vendor" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/compliance/vendors", {
        method: "POST",
        body: { name: "New Vendor Inc", category: "cloud_infrastructure" },
      }),
    );
  });
});

describe("CompliancePage — Questionnaires section", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders questionnaires with their source and status", async () => {
    mockRoutes({ questionnaires: [QUESTIONNAIRE_FIXTURE] });
    renderPage();

    expect(
      await screen.findByText("Nordwind Robotics vendor security questionnaire"),
    ).toBeInTheDocument();
    expect(screen.getByText("customer provided")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
  });

  it("creates a new questionnaire with the entered title and source", async () => {
    mockRoutes({});
    renderPage();
    const user = userEvent.setup();

    await user.type(
      await screen.findByPlaceholderText("Questionnaire title"),
      "New Customer Questionnaire",
    );
    await user.selectOptions(screen.getByDisplayValue("Internal template"), "customer_provided");
    await user.click(screen.getByRole("button", { name: "Create questionnaire" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/compliance/questionnaires", {
        method: "POST",
        body: { title: "New Customer Questionnaire", source: "customer_provided" },
      }),
    );
  });
});
