/**
 * Each page answers one question.
 *
 * `/compliance` used to be a 1,553-line route rendering fifteen unrelated
 * sections — framework readiness, document upload, controls, the risk
 * register, policies, questionnaires, audits, a second AI system
 * inventory, DPIAs, DSARs, data transfers, vendors, the Trust Center and
 * framework administration — with every Compliance item in the sidebar
 * pointing at an anchor inside it. The customer could not tell which of
 * the fifteen workflows the product had taken them to, because it had
 * taken them to all of them.
 *
 * These tests assert the split held: a page renders what belongs to it,
 * and does not render what belongs somewhere else. That second half is
 * the one that catches a regression — re-adding a section to the wrong
 * page is easy and looks harmless in a diff.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/compliance",
  useSearchParams: () => new URLSearchParams(),
}));

import { apiFetch } from "@/lib/api";

import CompliancePage from "./page";
import ControlsPage from "./controls/page";
import FrameworksPage from "./frameworks/page";
import PoliciesPage from "./policies/page";
import DataRequestsPage from "./privacy/data-requests/page";
import VendorsPage from "./vendors/page";
import { NAVIGATION } from "@/lib/navigation";

const mockedApiFetch = vi.mocked(apiFetch);

/** Everything the split pages fetch, all empty. The question here is
 * which sections mount, not what they show. */
function mockEmpty() {
  mockedApiFetch.mockImplementation((path: string) => {
    if (path.includes("/overview")) {
      return Promise.resolve({
        frameworks: [],
        total_open_gaps: 0,
        proposals_awaiting_review: 0,
        documents_processing: 0,
        controls_needing_reassessment: 0,
      }) as never;
    }
    if (path.includes("/framework-applicability")) {
      return Promise.resolve({ recommendations: [], facts_declared: false }) as never;
    }
    return Promise.resolve([]) as never;
  });
}

function renderPage(Page: () => React.ReactElement | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Page />
    </QueryClientProvider>,
  );
}

describe("compliance information architecture", () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    replace.mockReset();
    mockEmpty();
  });

  it("keeps Controls & Risk off the Frameworks page", async () => {
    renderPage(FrameworksPage);
    // Both the page title and the framework catalog say "Frameworks".
    await screen.findAllByText("Frameworks");

    // The sections that used to sit under the same heading.
    expect(screen.queryByText(/Risk register/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Data Subject Access Requests/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Vendors")).not.toBeInTheDocument();
    expect(screen.queryByText(/Trust Center/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Questionnaires")).not.toBeInTheDocument();
  });

  it("lists each framework once, not three times", async () => {
    // Readiness, applicability and a raw catalog chip list all rendered
    // the same eight frameworks on one screen. The catalog carried no
    // state and existed beside a permanently open form for creating
    // custom ones — a third answer to a question nobody asked twice.
    renderPage(FrameworksPage);
    await screen.findAllByText("Frameworks");

    expect(
      screen.queryByPlaceholderText("Custom framework name"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Add custom framework/i }),
    ).not.toBeInTheDocument();
  });

  it("offers no way to type a policy in by hand", async () => {
    // A governance record without a document is a title in a list: it
    // governs nothing, evidences nothing, and the first thing anyone
    // would do with it is attach the document that would have created it
    // anyway. Policies come from uploads.
    renderPage(PoliciesPage);
    await screen.findByText("Policies");

    expect(
      screen.queryByRole("button", { name: /Add policy/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Policy title/i)).not.toBeInTheDocument();
  });

  it("keeps policy management off the Controls page", async () => {
    // Controls & Risk was the policy-management screen as well, which put
    // "No managed policies yet" under a list of ten analysed policy
    // documents.
    renderPage(ControlsPage);
    await screen.findByText("Controls & Risk");
    expect(screen.queryByText(/Policies/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/No managed policies/i)).not.toBeInTheDocument();
  });

  it("keeps privacy operations off the Controls page", async () => {
    renderPage(ControlsPage);
    await screen.findByText("Controls & Risk");

    expect(screen.getByText(/Risk register/i)).toBeInTheDocument();
    expect(screen.queryByText(/Data Subject Access Requests/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Trust Center/i)).not.toBeInTheDocument();
  });

  it("puts privacy operations under the Privacy workspace", async () => {
    // The four record types moved to their own routes under
    // /compliance/privacy. The claim being tested is unchanged — privacy
    // operations live in Privacy and nowhere else — but the page that
    // holds them is now one tab of a workspace rather than a stack of
    // four sections.
    renderPage(DataRequestsPage);
    await waitFor(() =>
      expect(screen.getByText(/Data Subject Access Requests/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/Risk register/i)).not.toBeInTheDocument();
  });

  it("puts vendors and the trust center on the Vendors page", async () => {
    renderPage(VendorsPage);
    await screen.findByText("Vendors & Trust");
    await waitFor(() =>
      expect(screen.getAllByText(/Trust Center/i).length).toBeGreaterThan(0),
    );
    expect(screen.queryByText(/Risk register/i)).not.toBeInTheDocument();
  });

  it("redirects the old anchor deep links rather than breaking them", async () => {
    window.location.hash = "#privacy";
    renderPage(CompliancePage);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/compliance/privacy"));
  });

  it("sends an unrecognised /compliance visit somewhere useful", async () => {
    window.location.hash = "";
    renderPage(CompliancePage);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
  });

  it("navigates by route, never by anchor", () => {
    // A sidebar whose items all point at one page is not navigation. Every
    // compliance destination has to be somewhere a browser can go back to.
    const compliance = NAVIGATION.find((group) => group.label === "Compliance");
    expect(compliance).toBeDefined();
    for (const item of compliance!.items) {
      expect(item.href).not.toContain("#");
      expect(item.href.startsWith("/")).toBe(true);
    }
  });

  it("offers no route that lands back on the retired stacked page", () => {
    for (const group of NAVIGATION) {
      for (const item of group.items) {
        expect(item.href).not.toBe("/compliance");
      }
    }
  });
});
