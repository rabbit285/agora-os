/**
 * The framework screen, after the state logic was untangled.
 *
 * The reported screenshot showed one requirement reading "Needs review"
 * beside a medium-severity gap and a "Remediating" badge, with one
 * evidence item, one mapped control and no completed assessment. Two of
 * those came from the UI itself: a label map with `partial` reading
 * "Needs review" and `needs_review` reading "Assessment failed", and a
 * counts line printing the raw `latest_assessment_status`.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ComplianceGap,
  FrameworkActivation,
  FrameworkAssessmentResult,
  FrameworkDashboard,
  RequirementEvaluation,
} from "@/lib/types";

import FrameworkDashboardPage from "./page";

vi.mock("@/lib/api", () => ({
  API_URL: "http://test-api.invalid",
  apiFetch: vi.fn(),
  uploadFile: vi.fn(),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.status = status;
    }
  },
}));

import { apiFetch } from "@/lib/api";

const mockedApiFetch = vi.mocked(apiFetch);

const FRAMEWORK_ID = "aaaaaaaa-0000-0000-0000-000000000001";
const REQ_DEFICIENT = "bbbbbbbb-0000-0000-0000-000000000001";
const REQ_AWAITING = "bbbbbbbb-0000-0000-0000-000000000002";
const REQ_UNMAPPED = "bbbbbbbb-0000-0000-0000-000000000003";
const CONTROL_ID = "cccccccc-0000-0000-0000-000000000001";

const DASHBOARD: FrameworkDashboard = {
  framework: {
    id: FRAMEWORK_ID,
    key: "eu_ai_act",
    name: "EU AI Act",
    description: null,
    is_custom: false,
  },
  requirements: [
    {
      id: REQ_DEFICIENT,
      reference_code: "Art. 4",
      title: "AI literacy",
      controls: [{ id: CONTROL_ID, title: "Ensure staff competence in AI use", status: "not_started" }],
    },
    {
      id: REQ_AWAITING,
      reference_code: "Art. 12",
      title: "Record-keeping",
      controls: [{ id: CONTROL_ID, title: "Ensure staff competence in AI use", status: "not_started" }],
    },
    {
      id: REQ_UNMAPPED,
      reference_code: "Art. 9",
      title: "Risk management system",
      controls: [],
    },
  ],
  coverage_percent: 0,
};

const ACTIVATIONS: FrameworkActivation[] = [
  {
    id: "dddddddd-0000-0000-0000-000000000001",
    framework_id: FRAMEWORK_ID,
    status: "active",
    activated_at: new Date().toISOString(),
  } as FrameworkActivation,
];

function evaluation(overrides: Partial<RequirementEvaluation>): RequirementEvaluation {
  return {
    requirement_id: REQ_DEFICIENT,
    reference_code: "Art. 4",
    title: "AI literacy",
    status: "deficient",
    control_ids: [CONTROL_ID],
    evidence_count: 1,
    latest_assessment_status: null,
    summary: "",
    gap_id: null,
    missing_conditions: [],
    uncertainty: null,
    ...overrides,
  };
}

const ASSESSMENT: FrameworkAssessmentResult = {
  framework_id: FRAMEWORK_ID,
  assessed_at: new Date().toISOString(),
  requirements: [
    evaluation({
      requirement_id: REQ_DEFICIENT,
      status: "deficient",
      gap_id: "eeeeeeee-0000-0000-0000-000000000001",
      summary: "Evidence covers the policy, but nothing on file provides completion records.",
      missing_conditions: ["Attendance or completion records naming the people trained"],
    }),
    evaluation({
      requirement_id: REQ_AWAITING,
      reference_code: "Art. 12",
      title: "Record-keeping",
      status: "needs_review",
      gap_id: null,
      summary: "One document is mapped and nothing has been found wrong with it.",
      uncertainty: "Veyntra has no itemised expectation set for this requirement yet.",
    }),
    evaluation({
      requirement_id: REQ_UNMAPPED,
      reference_code: "Art. 9",
      title: "Risk management system",
      status: "not_assessed",
      control_ids: [],
      evidence_count: 0,
      gap_id: "eeeeeeee-0000-0000-0000-000000000002",
      summary: "No control is mapped to this requirement.",
    }),
  ],
  satisfied_count: 0,
  gap_count: 2,
  evidence_coverage_percent: 33.3,
  readiness: {
    percent: 8.3,
    satisfied: 0,
    needs_review: 1,
    deficient: 1,
    assessment_failed: 0,
    evidence_missing: 0,
    not_assessed: 1,
    total: 3,
    not_applicable: 15,
    explanation: "8.3% ready because, of 3 applicable requirements, 1 awaiting review…",
  },
};

const GAPS: ComplianceGap[] = [];

function route(path: string): unknown {
  if (path === `/api/v1/compliance/frameworks/${FRAMEWORK_ID}/dashboard`) return DASHBOARD;
  if (path === "/api/v1/compliance/frameworks/activations") return ACTIVATIONS;
  if (path === `/api/v1/compliance/gaps?framework_id=${FRAMEWORK_ID}`) return GAPS;
  if (path === `/api/v1/compliance/frameworks/${FRAMEWORK_ID}/assess`) return ASSESSMENT;
  if (path === "/api/v1/compliance/controls") return [];
  if (path === "/api/v1/organizations/current/members") return [];
  throw new Error(`unexpected fetch: ${path}`);
}

async function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <Suspense fallback={null}>
          <FrameworkDashboardPage params={Promise.resolve({ id: FRAMEWORK_ID })} />
        </Suspense>
      </QueryClientProvider>
    );
  });
}

/** The assessment result only exists after the button is pressed. */
async function runAssessment() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /Run assessment/i }));
  return user;
}

describe("framework requirement states", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    mockedApiFetch.mockImplementation((path: string) => Promise.resolve(route(path)) as never);
  });

  it("never shows a manual-mapping button as primary once a control is mapped", async () => {
    await renderPage();
    await screen.findByText("AI literacy");

    // Art. 9 has nothing mapped, so mapping really is the next thing to do.
    expect(screen.getByRole("button", { name: /Map control/i })).toBeInTheDocument();

    // The two requirements that already have a control offer More instead.
    const more = screen.getAllByRole("button", { name: /More/i });
    expect(more).toHaveLength(2);
    expect(screen.queryByRole("button", { name: /^Attach evidence$/i })).not.toBeInTheDocument();
  });

  it("keeps map and attach available under More", async () => {
    await renderPage();
    await screen.findByText("AI literacy");

    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: /More/i })[0]);

    await waitFor(() =>
      expect(screen.getByText("Map another control")).toBeInTheDocument()
    );
    expect(screen.getByText("Attach evidence")).toBeInTheDocument();
  });

  it("labels each state as itself, not as a neighbouring one", async () => {
    await renderPage();
    await screen.findByText("AI literacy");
    await runAssessment();

    // `deficient` is a finding and says so; `needs_review` is an open
    // question and must not read as one.
    await waitFor(() => expect(screen.getByText("Gap identified")).toBeInTheDocument());
    expect(screen.getByText("Awaiting review")).toBeInTheDocument();
    expect(screen.getByText("No control mapped")).toBeInTheDocument();
    expect(screen.queryByText("Assessment failed")).not.toBeInTheDocument();
  });

  it("names the missing condition instead of asking the reader to find it", async () => {
    await renderPage();
    await screen.findByText("AI literacy");
    await runAssessment();

    await waitFor(() =>
      expect(screen.getByText("Not covered by the evidence on file")).toBeInTheDocument()
    );
    expect(
      screen.getByText("Attendance or completion records naming the people trained")
    ).toBeInTheDocument();
  });

  it("says Assessment pending rather than a raw null", async () => {
    await renderPage();
    await screen.findByText("AI literacy");
    await runAssessment();

    await waitFor(() => expect(screen.getAllByText(/Assessment pending/).length).toBeGreaterThan(0));
    expect(screen.queryByText(/last assessment: none/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/nothing yet/i)).not.toBeInTheDocument();
  });
});
