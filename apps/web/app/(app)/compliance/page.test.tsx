import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  AIIncident,
  AISystem,
  Audit,
  DataTransfer,
  DPIA,
  DSAR,
  EvidenceRequest,
  ProcessingActivity,
  Questionnaire,
  SalesOpportunity,
  SecurityReview,
  TrustCenterItem,
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
  processing_description: null,
  necessity_assessment: null,
  proportionality_assessment: null,
  consultation_notes: null,
  residual_risk_level: null,
  screening_outcome: null,
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
  vendor_id: null,
  purpose: "Ranks job applicants",
  description: null,
  model_name: null,
  internal_users: [],
  affected_users: [],
  processed_data: [],
  business_owner_id: null,
  technical_owner_id: null,
  governance_owner_id: null,
  last_reviewed_at: null,
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
  dpa_status: "pending",
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

const AUDIT_FIXTURE: Audit = {
  id: "44444444-5555-6666-7777-888888888888",
  title: "Annual ISO 27001 surveillance audit",
  framework_id: null,
  auditor_name: "Nordic Assurance Partners",
  status: "in_progress",
  scheduled_at: null,
  completed_at: null,
  owner_id: null,
  created_at: new Date().toISOString(),
};

const TRUST_CENTER_ITEM_FIXTURE: TrustCenterItem = {
  id: "55555555-6666-7777-8888-999999999999",
  category: "security_overview",
  title: "Security Overview",
  content: "We encrypt data at rest and in transit.",
  status: "implemented",
  is_public: true,
  policy_id: null,
  owner_id: null,
  created_at: new Date().toISOString(),
};

const EVIDENCE_REQUEST_FIXTURE: EvidenceRequest = {
  id: "66666666-7777-8888-9999-aaaaaaaaaaaa",
  requester_name: "Priya Nandakumar",
  requester_email: "priya@prospect.example",
  company_name: "Prospect Robotics",
  message: "Please share your latest SOC 2 report.",
  status: "open",
  related_task_id: "77777777-8888-9999-aaaa-bbbbbbbbbbbb",
  created_at: new Date().toISOString(),
};

const OPPORTUNITY_FIXTURE: SalesOpportunity = {
  id: "88888888-9999-aaaa-bbbb-cccccccccccc",
  account_id: "99999999-aaaa-bbbb-cccc-dddddddddddd",
  title: "Security Review Corp — Platform deal",
  stage: "security_review",
  value: 42000,
  probability: 40,
  expected_close_at: null,
  owner_id: null,
  onboarding_customer_id: null,
  created_at: new Date().toISOString(),
};

const SECURITY_REVIEW_FIXTURE: SecurityReview = {
  id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
  opportunity_id: OPPORTUNITY_FIXTURE.id,
  questionnaire_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
  approval_id: null,
  trust_package_file_id: null,
  status: "in_progress",
  is_deal_blocker: true,
  created_at: new Date().toISOString(),
};

const DATA_TRANSFER_FIXTURE: DataTransfer = {
  id: "cccccccc-dddd-eeee-ffff-000000000000",
  processing_activity_id: null,
  recipient_name: "Applicant Tracking Systems Inc",
  destination_country: "US",
  transfer_mechanism: "sccs",
  safeguards_description: "EU Standard Contractual Clauses executed with the processor.",
  status: "active",
  related_risk_id: null,
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
  audits?: Audit[];
  trustCenterItems?: TrustCenterItem[];
  evidenceRequests?: EvidenceRequest[];
  securityReviews?: SecurityReview[];
  opportunities?: SalesOpportunity[];
  dataTransfers?: DataTransfer[];
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
    if (options?.method === "POST" && path === "/api/v1/compliance/audits") {
      return { ...AUDIT_FIXTURE };
    }
    if (path === "/api/v1/compliance/audits") return overrides.audits ?? [];
    if (options?.method === "POST" && path === "/api/v1/trust-center/items") {
      return { ...TRUST_CENTER_ITEM_FIXTURE };
    }
    if (path === "/api/v1/trust-center/items") return overrides.trustCenterItems ?? [];
    if (path === "/api/v1/trust-center/evidence-requests") return overrides.evidenceRequests ?? [];
    if (options?.method === "POST" && path === "/api/v1/compliance/security-reviews") {
      return { ...SECURITY_REVIEW_FIXTURE };
    }
    if (path === "/api/v1/compliance/security-reviews") return overrides.securityReviews ?? [];
    if (path === "/api/v1/sales/opportunities") return overrides.opportunities ?? [];
    if (options?.method === "POST" && path === "/api/v1/compliance/data-transfers") {
      return { ...DATA_TRANSFER_FIXTURE };
    }
    if (path === "/api/v1/compliance/data-transfers") return overrides.dataTransfers ?? [];
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

describe("CompliancePage — Audits section", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders audits with their auditor name and status", async () => {
    mockRoutes({ audits: [AUDIT_FIXTURE] });
    renderPage();

    expect(await screen.findByText("Annual ISO 27001 surveillance audit")).toBeInTheDocument();
    expect(screen.getByText("Nordic Assurance Partners")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
  });

  it("creates a new audit with the entered title and auditor name", async () => {
    mockRoutes({});
    renderPage();
    const user = userEvent.setup();

    await user.type(await screen.findByPlaceholderText("Audit title"), "New Compliance Audit");
    await user.type(screen.getByPlaceholderText("Auditor name"), "Big Four LLP");
    await user.click(screen.getByRole("button", { name: "Create audit" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/compliance/audits", {
        method: "POST",
        body: { title: "New Compliance Audit", auditor_name: "Big Four LLP" },
      }),
    );
  });
});

describe("CompliancePage — Trust Center section", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders trust center items and evidence requests", async () => {
    mockRoutes({
      trustCenterItems: [TRUST_CENTER_ITEM_FIXTURE],
      evidenceRequests: [EVIDENCE_REQUEST_FIXTURE],
    });
    renderPage();

    expect(await screen.findByText("Security Overview")).toBeInTheDocument();
    expect(screen.getByText("public")).toBeInTheDocument();
    expect(screen.getByText("implemented")).toBeInTheDocument();
    expect(screen.getByText("Priya Nandakumar (Prospect Robotics)")).toBeInTheDocument();
  });

  it("saves a trust center item with the entered title and category", async () => {
    mockRoutes({});
    renderPage();
    const user = userEvent.setup();

    await user.type(await screen.findByPlaceholderText("Title"), "Security Overview");
    await user.click(screen.getByRole("button", { name: "Save item" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/trust-center/items", {
        method: "POST",
        body: {
          category: "security_overview",
          title: "Security Overview",
          content: null,
          status: "planned",
          is_public: false,
        },
      }),
    );
  });

  it("fulfills an open evidence request", async () => {
    mockRoutes({ evidenceRequests: [EVIDENCE_REQUEST_FIXTURE] });
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Mark fulfilled" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith(
        `/api/v1/trust-center/evidence-requests/${EVIDENCE_REQUEST_FIXTURE.id}/status`,
        { method: "PATCH", body: { status: "fulfilled" } },
      ),
    );
  });
});

describe("CompliancePage — Security Reviews section", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders security reviews with the opportunity title, status, and deal-blocker note", async () => {
    mockRoutes({
      securityReviews: [SECURITY_REVIEW_FIXTURE],
      opportunities: [OPPORTUNITY_FIXTURE],
    });
    renderPage();

    // The opportunity title also appears in the "Select opportunity…"
    // dropdown, so there's more than one match.
    expect(
      (await screen.findAllByText("Security Review Corp — Platform deal")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Deal blocker")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
  });

  it("starts a security review for the selected opportunity", async () => {
    mockRoutes({ opportunities: [OPPORTUNITY_FIXTURE] });
    renderPage();
    const user = userEvent.setup();

    await screen.findAllByText(OPPORTUNITY_FIXTURE.title);
    await user.selectOptions(
      screen.getByDisplayValue("Select opportunity…"),
      OPPORTUNITY_FIXTURE.id,
    );
    await user.click(screen.getByRole("button", { name: "Start review" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/compliance/security-reviews", {
        method: "POST",
        body: { opportunity_id: OPPORTUNITY_FIXTURE.id, questionnaire_id: null },
      }),
    );
  });
});

describe("CompliancePage — Data Transfers section", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders data transfers with their destination country and mechanism", async () => {
    mockRoutes({ dataTransfers: [DATA_TRANSFER_FIXTURE] });
    renderPage();

    expect(
      await screen.findByText("Applicant Tracking Systems Inc"),
    ).toBeInTheDocument();
    expect(screen.getByText("US · sccs")).toBeInTheDocument();
  });

  it("logs a new data transfer with the entered recipient and mechanism", async () => {
    mockRoutes({});
    renderPage();
    const user = userEvent.setup();

    await user.type(
      await screen.findByPlaceholderText("Recipient name"),
      "New Recipient GmbH",
    );
    await user.type(screen.getByPlaceholderText("Destination country (e.g. US)"), "de");
    await user.selectOptions(
      screen.getByDisplayValue("Standard Contractual Clauses"),
      "derogation",
    );
    await user.click(screen.getByRole("button", { name: "Log transfer" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/compliance/data-transfers", {
        method: "POST",
        body: {
          recipient_name: "New Recipient GmbH",
          destination_country: "DE",
          transfer_mechanism: "derogation",
        },
      }),
    );
  });
});
