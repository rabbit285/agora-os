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

// These sections used to be stacked on one /compliance route. They now
// live on the pages that answer their own question, so each suite
// renders the page it belongs to rather than one screen that has
// everything.
import AIIncidentsPage from "../ai-systems/page";
import AssessmentsPage from "./assessments/page";
import ProcessingActivitiesPage from "./privacy/processing-activities/page";
import DpiasPage from "./privacy/dpias/page";
import DataRequestsPage from "./privacy/data-requests/page";
import TransfersPage from "./privacy/transfers/page";
import VendorsPage from "./vendors/page";

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
  verification_status: "pending",
  verification_method: null,
  verified_at: null,
  discovery_findings: null,
  discovery_run_at: null,
  export_generated_at: null,
  due_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
  received_at: null,
  base_due_at: null,
  extension_months: 0,
  extension_reason: null,
  extension_granted_at: null,
  days_remaining: null,
  overdue: false,
  due_soon: false,
  deadline_label: null,
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
  deployment_status: "production",
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
  approval_state: "not_submitted",
  approval_conditions: null,
  approval_decided_at: null,
  compliance_owner_id: null,
  owner_id: null,
  created_at: new Date().toISOString(),
};

const QUESTIONNAIRE_FIXTURE: Questionnaire = {
  id: "33333333-4444-5555-6666-777777777777",
  title: "Nordwind Robotics vendor security questionnaire",
  customer_name: "Nordwind Robotics",
  due_at: null,
  can_delete: true,
  delete_blocked_reason: null,
  archived_at: null,
  archived_by: null,
  source: "customer_provided",
  status: "in_review",
  status_label: "In review",
  // A customer questionnaire with a customer and a review behind it, so
  // the only thing left in its way is the answers themselves.
  readiness: {
    ready: false,
    needs_setup: false,
    blockers: [
      { code: "needs_review", message: "2 answers need a person to decide." },
    ],
  },
  title_looks_like_a_question: false,
  opportunity_id: null,
  owner_id: null,
  created_at: new Date().toISOString(),
  progress: {
    total: 5,
    approved: 2,
    needs_review: 2,
    draft: 0,
    unanswered: 1,
    percent_complete: 40,
    ready_to_share: false,
  },
};

const ISO_FRAMEWORK = {
  id: "aaaa1111-2222-4333-8444-555566667777",
  key: "iso42001",
  name: "ISO 42001",
  description: null,
  is_custom: false,
  suggested_audit_scope:
    "AI governance, risk management, roles and responsibilities, AI system lifecycle controls, impact assessment, monitoring and measurement, and continual improvement.",
};

const PERSON = {
  id: "bbbb1111-2222-4333-8444-555566667777",
  full_name: "Zach Warren",
  email: "zach@example.com",
};

const AUDIT_FIXTURE: Audit = {
  id: "44444444-5555-6666-7777-888888888888",
  title: "Annual ISO 27001 surveillance audit",
  framework_id: null,
  finding_count: 0,
  can_delete: true,
  delete_blocked_reason: null,
  archived_at: null,
  archived_by: null,
  framework_name: null,
  scope: "Information security management system",
  // An external firm: a name, and no account. The record says which.
  auditor_user_id: null,
  auditor_name: "Nordic Assurance Partners",
  // An external firm, recorded as one rather than deduced from the
  // absence of an account id.
  auditor_type: "external" as const,
  auditor_organization: "Nordic Assurance Partners",
  status: "in_progress",
  status_label: "In progress",
  scheduled_at: null,
  // The timestamps follow the status: in progress means started and
  // not completed. There is no state where both are set but the badge
  // says planned — that was the bug.
  started_at: new Date().toISOString(),
  completed_at: null,
  prepared_at: new Date().toISOString(),
  owner_id: null,
  created_at: new Date().toISOString(),
  progress: {
    scoped: 18,
    reviewed: 12,
    unreviewed: 6,
    percent_reviewed: 67,
    no_finding: 11,
    observations: 0,
    minor: 0,
    major: 1,
    critical: 0,
    needs_evidence: 0,
    open_findings: 1,
    ready_for_verification: 0,
    evidence_reviewed: 4,
    remediation_completed: 0,
    // Scope adds up: 18 in scope, 4 the framework has that do not bind
    // this organization, 0 the auditor left out.
    not_applicable: 4,
    excluded: 0,
    // Remediation state, which is not the finding.
    remediation_open: 1,
    remediation_in_progress: 0,
    remediation_ready: 0,
    remediation_closed: 0,
    accepted_risk: 0,
  },
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
  title: "Acme Corp Security Review",
  customer_name: "Acme Corp",
  status: "in_progress",
  status_label: "In progress",
  progress: {
    questionnaires: 1,
    total: 2,
    approved: 1,
    needs_review: 1,
    draft: 0,
    unanswered: 0,
    percent_complete: 50,
    ready_to_share: false,
  },
  archived_at: null,
  archived_by: null,
  // The sales-coupled model this replaced. Carried by rows that predate
  // the change; nothing new sets either.
  opportunity_id: OPPORTUNITY_FIXTURE.id,
  questionnaire_id: "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
  approval_id: null,
  trust_package_file_id: null,
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

function renderPage(Page: () => React.ReactElement | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Page />
    </QueryClientProvider>,
  );
}

/** Creation forms sit behind a button now rather than standing open on
 * every section. Nine permanently-visible forms on one screen was most
 * of why the old page felt like GRC administration software. */
async function openForm(user: ReturnType<typeof userEvent.setup>, label: string) {
  await user.click(await screen.findByRole("button", { name: label }));
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
  people?: { id: string; full_name: string | null; email: string }[];
  frameworks?: {
    id: string;
    key: string;
    name: string;
    description: string | null;
    is_custom: boolean;
    suggested_audit_scope?: string | null;
  }[];
  archivedSecurityReviews?: SecurityReview[];
  opportunities?: SalesOpportunity[];
  dataTransfers?: DataTransfer[];
}) {
  mockedApiFetch.mockImplementation(async (raw: string, options?: { method?: string }) => {
    // Routes are matched on the path alone. Comparing whole URLs meant
    // that the moment an endpoint grew a query parameter its list
    // silently rendered empty, which looks like a broken component
    // rather than a stale test.
    const path = raw.split("?")[0];
    if (path === "/api/v1/compliance/controls") return [];
    if (path === "/api/v1/compliance/risks") return [];
    if (path === "/api/v1/compliance/ai-systems") return overrides.aiSystems ?? [];
    if (path === "/api/v1/organizations/current/people") {
      return overrides.people ?? [];
    }
    if (path === "/api/v1/compliance/frameworks") return overrides.frameworks ?? [];
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
    if (path === "/api/v1/compliance/security-reviews") {
      // The one route where the query matters: Active and Archived are
      // two different lists, and a test about which one the empty state
      // is describing cannot be written if both return the same rows.
      return raw.includes("archived=true")
        ? (overrides.archivedSecurityReviews ?? [])
        : (overrides.securityReviews ?? []);
    }
    if (path === "/api/v1/sales/opportunities") return overrides.opportunities ?? [];
    if (options?.method === "POST" && path === "/api/v1/compliance/data-transfers") {
      return { ...DATA_TRANSFER_FIXTURE };
    }
    if (path === "/api/v1/compliance/data-transfers") return overrides.dataTransfers ?? [];
    throw new Error(`Unmocked path: ${path} (${options?.method ?? "GET"})`);
  });
}

describe("Privacy", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  // The three record types used to share one page and now have one
  // route each — which is the point of the change, so the test checks
  // each route rather than one page that no longer holds them all.
  it.each([
    [
      "processing activities",
      ProcessingActivitiesPage,
      "Record of Processing Activities (RoPA)",
      "Candidate application processing",
    ],
    [
      "DPIAs",
      DpiasPage,
      "Data Protection Impact Assessments (DPIA)",
      "Candidate application processing DPIA",
    ],
    [
      "data requests",
      DataRequestsPage,
      "Data Subject Access Requests (DSAR)",
      "Priya Nandakumar",
    ],
  ])("renders %s with their seeded data", async (_label, Page, heading, record) => {
    mockRoutes({
      processingActivities: [PROCESSING_ACTIVITY],
      dpias: [DPIA_FIXTURE],
      dsars: [DSAR_FIXTURE],
    });
    renderPage(Page);

    expect(await screen.findByText(heading)).toBeInTheDocument();
    expect(await screen.findByText(record)).toBeInTheDocument();
  });

  it("logs a new DSAR with the selected request type", async () => {
    mockRoutes({});
    renderPage(DataRequestsPage);
    const user = userEvent.setup();

    await openForm(user, "Log a request");

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
    renderPage(DpiasPage);

    expect(await screen.findByText("Linked to an AI system")).toBeInTheDocument();
  });
});

describe("AI Incidents", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders logged incidents with severity and the linked AI system's name", async () => {
    mockRoutes({ aiSystems: [AI_SYSTEM_FIXTURE], aiIncidents: [AI_INCIDENT_FIXTURE] });
    renderPage(AIIncidentsPage);

    expect(await screen.findByText("Resume screener showed gender bias")).toBeInTheDocument();
    // "Resume Screening Assistant" also appears in the AI System Inventory
    // list and the incident-logging dropdown, so there's more than one match.
    expect((await screen.findAllByText("Resume Screening Assistant")).length).toBeGreaterThan(0);
    expect(screen.getByText("critical")).toBeInTheDocument();
  });

  it("logs a new AI incident against the selected system", async () => {
    mockRoutes({ aiSystems: [AI_SYSTEM_FIXTURE] });
    renderPage(AIIncidentsPage);
    const user = userEvent.setup();

    await openForm(user, "Log incident");

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

describe("Vendors", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders vendors with their risk tier and status", async () => {
    mockRoutes({ vendors: [VENDOR_FIXTURE] });
    renderPage(VendorsPage);

    expect(await screen.findByText("QuickScribe Transcription LLC")).toBeInTheDocument();
    expect(screen.getByText("data_processor")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
  });

  it("adds a new vendor with the entered name and category", async () => {
    mockRoutes({});
    renderPage(VendorsPage);
    const user = userEvent.setup();

    await openForm(user, "Add vendor");

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

describe("Questionnaires", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders questionnaires with their source and status", async () => {
    mockRoutes({ questionnaires: [QUESTIONNAIRE_FIXTURE] });
    renderPage(AssessmentsPage);

    expect(
      await screen.findByText("Nordwind Robotics vendor security questionnaire"),
    ).toBeInTheDocument();
    // The source now shares its line with the question count, so this
    // matches the part of it this test is about.
    expect(screen.getByText(/customer provided/)).toBeInTheDocument();
    // The workflow vocabulary says what is *needed*, not that work is
    // happening: "in review" means a person has to decide.
    expect(screen.getByText("in review")).toBeInTheDocument();
  });

  it("creates a new questionnaire with the entered title and source", async () => {
    mockRoutes({});
    renderPage(AssessmentsPage);
    const user = userEvent.setup();

    await openForm(user, "Create questionnaire");

    await user.type(
      await screen.findByPlaceholderText("Questionnaire title"),
      "New Customer Questionnaire",
    );
    await user.selectOptions(
      screen.getByDisplayValue("Internal assessment"),
      "customer_provided",
    );
    // A customer questionnaire has a customer. The form asks here rather
    // than leaving the record to be repaired later from its title.
    await user.type(
      screen.getByLabelText("Customer", { exact: true }),
      "Acme Corp",
    );
    await user.click(screen.getByRole("button", { name: "Create questionnaire" }));

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/compliance/questionnaires", {
        method: "POST",
        body: {
          title: "New Customer Questionnaire",
          source: "customer_provided",
          customer_name: "Acme Corp",
        },
      }),
    );
  });

  it("will not create a customer questionnaire with no customer", async () => {
    mockRoutes({});
    renderPage(AssessmentsPage);
    const user = userEvent.setup();

    await openForm(user, "Create questionnaire");
    await user.type(
      await screen.findByPlaceholderText("Questionnaire title"),
      "Acme Customer Security Questionnaire",
    );
    await user.selectOptions(
      screen.getByDisplayValue("Internal assessment"),
      "customer_provided",
    );

    // Every questionnaire created this way without a customer is one more
    // record that has to be repaired by reading its title later.
    expect(
      screen.getByRole("button", { name: "Create questionnaire" }),
    ).toBeDisabled();
    expect(
      screen.getByText("Name the customer so this joins their security review."),
    ).toBeInTheDocument();

    await user.type(
      screen.getByLabelText("Customer", { exact: true }),
      "Acme Corp",
    );
    expect(
      screen.getByRole("button", { name: "Create questionnaire" }),
    ).toBeEnabled();
    expect(
      screen.getByText("Joins Acme Corp's security review."),
    ).toBeInTheDocument();
  });

  it("says when a title reads like one of the questions", async () => {
    mockRoutes({});
    renderPage(AssessmentsPage);
    const user = userEvent.setup();

    await openForm(user, "Create questionnaire");
    await user.type(
      await screen.findByPlaceholderText("Questionnaire title"),
      "Do you encrypt customer data at rest?",
    );

    expect(
      screen.getByText(/looks like one of the questions/),
    ).toBeInTheDocument();
    // Said, not enforced.
    expect(
      screen.getByRole("button", { name: "Create questionnaire" }),
    ).toBeEnabled();
  });
});

describe("Audits", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders audits with their auditor, progress and open findings", async () => {
    mockRoutes({ audits: [AUDIT_FIXTURE] });
    renderPage(AssessmentsPage);

    expect(await screen.findByText("Annual ISO 27001 surveillance audit")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
    // §20: where the engagement actually stands, not just its status.
    // "planned" on its own tells a reader nothing they can act on.
    expect(
      screen.getByText(/Auditor: Nordic Assurance Partners/),
    ).toBeInTheDocument();
    expect(screen.getByText(/12 \/ 18 reviewed/)).toBeInTheDocument();
    expect(screen.getByText(/1 open finding/)).toBeInTheDocument();
  });

  it("opens with nothing chosen, and custom last", async () => {
    // The default used to be "Custom / No framework", which quietly
    // opted everybody into the path that prepares nothing.
    mockRoutes({ frameworks: [ISO_FRAMEWORK] });
    renderPage(AssessmentsPage);
    const user = userEvent.setup();

    await openForm(user, "Create audit");

    const framework = (await screen.findByLabelText(
      "Framework",
    )) as HTMLSelectElement;
    expect(framework.value).toBe("");
    const options = [...framework.options].map((option) => option.textContent);
    expect(options[0]).toBe("Select framework…");
    expect(options[options.length - 1]).toBe("Custom / No framework");

    // §2: labels that survive typing, not placeholders that vanish.
    for (const label of ["Audit title", "Framework", "Auditor", "Scope"]) {
      expect(screen.getByText(label, { exact: true })).toBeInTheDocument();
    }

    // §10: the CTA waits for what it needs.
    expect(
      screen.getByRole("button", { name: /Create & Prepare Audit/ }),
    ).toBeDisabled();
  });

  it("creates a framework audit with the auditor as a real account", async () => {
    mockRoutes({ frameworks: [ISO_FRAMEWORK], people: [PERSON] });
    renderPage(AssessmentsPage);
    const user = userEvent.setup();

    await openForm(user, "Create audit");
    await user.selectOptions(
      await screen.findByLabelText("Framework"),
      ISO_FRAMEWORK.id,
    );

    // §9/§8: title and scope suggested from the framework, both editable.
    expect(screen.getByLabelText("Audit title")).toHaveValue(
      "ISO 42001 Internal Audit",
    );
    expect(screen.getByLabelText("Scope")).toHaveValue(
      ISO_FRAMEWORK.suggested_audit_scope,
    );

    await user.selectOptions(screen.getByLabelText("Auditor"), PERSON.id);
    await user.click(
      screen.getByRole("button", { name: /Create & Prepare Audit/ }),
    );

    await waitFor(() =>
      expect(mockedApiFetch).toHaveBeenCalledWith("/api/v1/compliance/audits", {
        method: "POST",
        body: {
          title: "ISO 42001 Internal Audit",
          framework_id: ISO_FRAMEWORK.id,
          // §7: a colleague is an account, not a string.
          auditor_user_id: PERSON.id,
          auditor_name: PERSON.full_name,
          // Recorded, not inferred. A missing account id used to mean
          // "external", which is how a colleague's internal audit was
          // reported as externally conducted.
          auditor_type: "internal",
          auditor_organization: null,
          scope: ISO_FRAMEWORK.suggested_audit_scope,
        },
      }),
    );
  });

  it("custom is an explicit alternative with its own wording", async () => {
    mockRoutes({ frameworks: [ISO_FRAMEWORK] });
    renderPage(AssessmentsPage);
    const user = userEvent.setup();

    await openForm(user, "Create audit");
    await user.selectOptions(await screen.findByLabelText("Framework"), "custom");

    // §6: the old line claimed a custom audit "scopes itself", which is
    // not a thing an audit does.
    expect(
      screen.getByText(/Custom audits are scoped manually./),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/custom audit scopes itself/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create Custom Audit" }),
    ).toBeDisabled();
  });
});

describe("Trust Center", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders trust center items and evidence requests", async () => {
    mockRoutes({
      trustCenterItems: [TRUST_CENTER_ITEM_FIXTURE],
      evidenceRequests: [EVIDENCE_REQUEST_FIXTURE],
    });
    renderPage(VendorsPage);

    expect(await screen.findByText("Security Overview")).toBeInTheDocument();
    expect(screen.getByText("public")).toBeInTheDocument();
    expect(screen.getByText("implemented")).toBeInTheDocument();
    expect(screen.getByText("Priya Nandakumar (Prospect Robotics)")).toBeInTheDocument();
  });

  it("saves a trust center item with the entered title and category", async () => {
    mockRoutes({});
    renderPage(VendorsPage);
    const user = userEvent.setup();

    await openForm(user, "Save item");

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
          // Sent as null for ordinary statuses. Only
          // independently_assessed and certified require them, and the
          // API refuses those without an attestation.
          attestation_file_id: null,
          attestation_note: null,
        },
      }),
    );
  });

  it("fulfills an open evidence request", async () => {
    mockRoutes({ evidenceRequests: [EVIDENCE_REQUEST_FIXTURE] });
    renderPage(VendorsPage);
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

describe("Security Reviews", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("lists existing reviews with their status and deal impact", async () => {
    mockRoutes({ securityReviews: [SECURITY_REVIEW_FIXTURE] });
    renderPage(AssessmentsPage);

    // The engagement's own name and the customer it belongs to. The
    // card used to render a placeholder because the list endpoint
    // carried neither.
    expect(
      await screen.findByText("Acme Corp Security Review"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Acme Corp · 1 questionnaire/)).toBeInTheDocument();
    expect(screen.getByText(/1\/2 approved · 50%/)).toBeInTheDocument();
    // Urgency in compliance terms rather than sales ones. "Blocking a
    // deal" came from the withdrawn CRM framing; what a reviewer needs
    // to know is how much is waiting on them.
    expect(screen.getByText(/1 answer needs a decision/)).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
  });

  it("offers no control that cannot succeed", async () => {
    // Starting a review required picking a sales opportunity, and
    // nothing in the product creates one any more — the dropdown was
    // permanently empty and the button permanently disabled. Dead UI
    // dressed as a feature is worse than an honest empty state.
    mockRoutes({});
    renderPage(AssessmentsPage);

    expect(
      await screen.findByText("No active customer security reviews"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Select opportunity/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start review" })).not.toBeInTheDocument();
  });

  it("does not claim there are no reviews while an archived one exists", async () => {
    // Active 0, Archived 1, Active tab open. "No customer security
    // reviews" is simply untrue on that screen — the empty state
    // describes the view that is open, not the whole section.
    mockRoutes({ securityReviews: [], archivedSecurityReviews: [SECURITY_REVIEW_FIXTURE] });
    renderPage(AssessmentsPage);

    expect(
      await screen.findByText("No active customer security reviews"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No customer security reviews"),
    ).not.toBeInTheDocument();
    // And it says where the one they have actually is.
    expect(
      screen.getByText(/finished and archived are under Archived/),
    ).toBeInTheDocument();
  });

  it("never calls the retired sales module", async () => {
    mockRoutes({ securityReviews: [SECURITY_REVIEW_FIXTURE] });
    renderPage(AssessmentsPage);
    await screen.findByText("Acme Corp Security Review");

    for (const call of mockedApiFetch.mock.calls) {
      expect(String(call[0])).not.toContain("/sales/");
    }
  });
});

describe("Data Transfers", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
  });

  it("renders data transfers with their destination country and mechanism", async () => {
    mockRoutes({ dataTransfers: [DATA_TRANSFER_FIXTURE] });
    renderPage(TransfersPage);

    expect(
      await screen.findByText("Applicant Tracking Systems Inc"),
    ).toBeInTheDocument();
    expect(screen.getByText("US · sccs")).toBeInTheDocument();
  });

  it("logs a new data transfer with the entered recipient and mechanism", async () => {
    mockRoutes({});
    renderPage(TransfersPage);
    const user = userEvent.setup();

    await openForm(user, "Log a transfer");

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
