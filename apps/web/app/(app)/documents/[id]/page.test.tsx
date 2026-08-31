/**
 * The one Document Detail page.
 *
 * A row in the document library and a Copilot citation both open it. The
 * citation adds a passage and the page lands on it; without one the page
 * opens at the top, which is what arriving from the library should do.
 *
 * None of the chunk numbers, token counts or ids the old citation exposed
 * appear here — this is the document as the customer would read it, plus
 * what Veyntra found in it.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import { Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentChunk, DocumentDetail } from "@/lib/types";

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

const PASSAGE = "monitored continuously for model drift";
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/documents/x",
  useSearchParams: () => search,
}));

import { apiFetch } from "@/lib/api";

import DocumentDetailPage from "./page";

const mockedApiFetch = vi.mocked(apiFetch);

const DOCUMENT_ID = "da7966ef-1c22-4b0a-9f31-8c5e2d7a41bb";
const POLICY_ID = "bbbbbbbb-1111-4222-8333-444444444444";
const FILENAME = "10_Special_Category_Data_Processing_Policy.docx";
const OVERLAP = "and every incident is reviewed monthly.";

const DETAIL: DocumentDetail = {
  document_id: DOCUMENT_ID,
  file_id: "cccccccc-1111-4222-8333-444444444444",
  href: `/documents/${DOCUMENT_ID}`,
  title: "Special Category Data Processing Policy",
  filename: FILENAME,
  document_type: "Policy",
  document_domain: "Privacy / GDPR",
  classification: "confidential",
  processing_status: "ready",
  processing_error: null,
  content_status: "ready",
  content_error: null,
  index_status: "indexed",
  index_error: null,
  extracted_characters: 8400,
  size_bytes: 20000,
  created_at: new Date().toISOString(),
  processed_at: new Date().toISOString(),
  policy_id: POLICY_ID,
  policy_title: "Special Category Data Processing Policy",
  policy_status: "needs_review",
  evidence_count: 6,
  control_count: 4,
  requirement_count: 3,
  proposed_count: 0,
  approved_count: 6,
  unverifiable_count: 0,
  mapping_state: "mapped" as const,
  versions: [],
  version_label: null,
  version_candidate: null,
  evidence: [
    {
      id: "e1",
      source_location: "1. Purpose",
      quoted_passage: "This policy governs special category data.",
      evidence_type: "policy_statement",
      status: "approved",
      confidence: 1,
      control_id: "ctrl-1",
      control_title: "Control processing of special category data",
      requirement_id: "req-1",
      requirement_reference: "Art. 9",
      requirement_title: "Processing of special categories of personal data",
      framework_name: "GDPR",
    },
    {
      id: "e2",
      source_location: "5. Article 9 condition review",
      quoted_passage: "Each activity records its Article 9 condition.",
      evidence_type: "procedure",
      status: "proposed",
      confidence: 0.82,
      control_id: "ctrl-1",
      control_title: "Control processing of special category data",
      requirement_id: null,
      requirement_reference: null,
      requirement_title: null,
      framework_name: null,
    },
  ],
};

const CHUNKS: DocumentChunk[] = [
  {
    id: "chunk-a",
    chunk_index: 0,
    content: "1. Purpose\nThis policy sets out how we govern AI.",
    token_count: 12,
    section_label: "1. Purpose",
    page_number: 1,
  },
  {
    id: "chunk-b",
    chunk_index: 1,
    content: `All production AI systems are ${PASSAGE}, ${OVERLAP}`,
    token_count: 20,
    section_label: "7. Monitoring",
    page_number: 4,
  },
  {
    id: "chunk-c",
    chunk_index: 2,
    content: `${OVERLAP} Records are retained for three years.`,
    token_count: 14,
    section_label: "7. Monitoring",
    page_number: 4,
  },
];

function mockApi(detail: DocumentDetail = DETAIL, chunks: DocumentChunk[] = CHUNKS) {
  mockedApiFetch.mockReset();
  mockedApiFetch.mockImplementation(async (path: string) => {
    if (path.endsWith("/chunks")) return chunks as never;
    return detail as never;
  });
}

async function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        {/* `use(params)` suspends, so the test tree needs a boundary
            above it just as the router provides one in the app. */}
        <Suspense fallback={null}>
          <DocumentDetailPage params={Promise.resolve({ id: DOCUMENT_ID })} />
        </Suspense>
      </QueryClientProvider>
    );
  });
}

beforeEach(() => {
  search = new URLSearchParams({ passage: PASSAGE });
  mockApi();
  // jsdom has no layout, so scrollIntoView is not implemented.
  Element.prototype.scrollIntoView = vi.fn();
});

describe("the document header", () => {
  it("is named for the document, with the filename underneath", async () => {
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByText("Special Category Data Processing Policy", { selector: "h1" })
      ).toBeInTheDocument()
    );
    expect(screen.getByText(FILENAME)).toBeInTheDocument();
  });

  it("separates what was read from what the Copilot can see", async () => {
    // Two pipelines that fail separately. One badge for both is how
    // somebody ended up asking the Copilot about a document it had never
    // been given.
    await renderPage();
    await waitFor(() => expect(screen.getByText("Processing")).toBeInTheDocument());
    expect(screen.getByText("Analyzed")).toBeInTheDocument();
    expect(screen.getByText("Copilot")).toBeInTheDocument();
    expect(screen.getByText("Indexed")).toBeInTheDocument();
  });

  it("shows the document type and category", async () => {
    await renderPage();
    await waitFor(() => expect(screen.getByText("Policy")).toBeInTheDocument());
    expect(screen.getByText("Privacy / GDPR")).toBeInTheDocument();
  });
});

describe("the document content", () => {
  it("reads as the document, not as the index", async () => {
    await renderPage();
    await waitFor(() => expect(screen.getByText("7. Monitoring")).toBeInTheDocument());

    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/chunk[\s_-]*\d+/i);
    expect(body).not.toMatch(/tokens/i);
  });

  it("does not repeat the overlap between neighbouring chunks", async () => {
    await renderPage();
    await waitFor(() => expect(screen.getByText("7. Monitoring")).toBeInTheDocument());
    expect((document.body.textContent ?? "").split(OVERLAP)).toHaveLength(2);
  });

  it("keeps the document's own headings and pages", async () => {
    await renderPage();
    await waitFor(() => expect(screen.getByText("7. Monitoring")).toBeInTheDocument());
    expect(screen.getByText("1. Purpose", { selector: "h2" })).toBeInTheDocument();
    expect(screen.getAllByText("page 4").length).toBeGreaterThan(0);
  });
});

describe("arriving from a Copilot citation", () => {
  it("highlights the cited passage", async () => {
    await renderPage();
    await waitFor(() => expect(document.querySelector("mark")).not.toBeNull());

    const mark = document.querySelector("mark") as HTMLElement;
    expect(mark.textContent).toContain(PASSAGE);
    // Not colour alone.
    expect(mark.textContent).toContain("cited passage");
  });

  it("scrolls to the passage rather than the top", async () => {
    await renderPage();
    await waitFor(() => expect(document.querySelector("mark")).not.toBeNull());
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("says why the page opened where it did", async () => {
    await renderPage();
    await waitFor(() =>
      expect(
        screen.getByText("Opened at the passage cited by your Copilot.")
      ).toBeInTheDocument()
    );
  });
});

describe("arriving from the document library", () => {
  it("opens at the top with nothing highlighted", async () => {
    search = new URLSearchParams();
    await renderPage();
    await waitFor(() => expect(screen.getByText("7. Monitoring")).toBeInTheDocument());

    expect(document.querySelector("mark")).toBeNull();
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("offers the way back without breaking browser history", async () => {
    // A plain link, so Back still returns wherever the reader came from
    // — the library, or the Copilot.
    await renderPage();
    const back = await screen.findByRole("link", { name: /All documents/ });
    expect(back.getAttribute("href")).toBe("/documents");
  });
});

describe("document intelligence", () => {
  it("reports what the analysis found", async () => {
    await renderPage();
    await waitFor(() => expect(screen.getByText("Analysis")).toBeInTheDocument());

    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("evidence items")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("controls")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("framework requirements")).toBeInTheDocument();
  });

  it("shows the chain from passage to control to requirement", async () => {
    await renderPage();
    await waitFor(() => expect(screen.getByText("Evidence extracted")).toBeInTheDocument());

    expect(screen.getByText("1. Purpose", { selector: "p" })).toBeInTheDocument();
    expect(
      screen.getAllByText("Control processing of special category data").length
    ).toBeGreaterThan(0);
    expect(screen.getByText(/GDPR Art\. 9/)).toBeInTheDocument();
  });

  it("keeps a proposal distinct from an approved mapping", async () => {
    // Flattening the two is how unreviewed suggestions start reading as
    // compliance evidence.
    await renderPage();
    await waitFor(() => expect(screen.getByText("Evidence extracted")).toBeInTheDocument());

    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Awaiting review")).toBeInTheDocument();
  });

  it("links evidence to the control it supports", async () => {
    await renderPage();
    await waitFor(() => expect(screen.getByText("Evidence extracted")).toBeInTheDocument());

    const controlLink = screen.getAllByRole("link", {
      name: "Control processing of special category data",
    })[0];
    expect(controlLink.getAttribute("href")).toBe("/compliance/controls/ctrl-1");
  });
});

describe("policy governance", () => {
  it("links to the policy record rather than editing it here", async () => {
    // Approving a policy has a screen that does it properly. Two places
    // to do one thing is how they end up disagreeing.
    await renderPage();
    const link = await screen.findByRole("link", { name: /Open policy/ });
    expect(link.getAttribute("href")).toBe(`/compliance/policies/${POLICY_ID}`);
    expect(screen.getByText("Needs governance review")).toBeInTheDocument();
  });

  it("says nothing at all when the document is not a policy", async () => {
    mockApi({ ...DETAIL, policy_id: null, policy_title: null, policy_status: null });
    await renderPage();
    await waitFor(() => expect(screen.getByText("Analysis")).toBeInTheDocument());
    expect(screen.queryByText("Policy governance")).not.toBeInTheDocument();
  });
});

describe("a document that is not readable", () => {
  it("says so instead of rendering an empty page", async () => {
    // Keyed on whether the text was ingested, not on whether the
    // compliance analysis ran — a document can be perfectly readable
    // here with no analysis ever requested, which is the state every
    // attachment from elsewhere in Veyntra is in.
    mockApi(
      {
        ...DETAIL,
        content_status: "failed",
        content_error: "The file could not be read.",
      },
      []
    );
    await renderPage();
    await waitFor(() =>
      expect(screen.getByText("This document is not readable yet")).toBeInTheDocument()
    );
    expect(screen.getByText("The file could not be read.")).toBeInTheDocument();
  });
});
