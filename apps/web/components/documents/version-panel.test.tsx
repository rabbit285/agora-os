import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiFetch: vi.fn() };
});

import { apiFetch } from "@/lib/api";
import type { DocumentVersion, VersionCandidate } from "@/lib/types";

import {
  SupersededNotice,
  VersionBanner,
  VersionHistory,
} from "./version-panel";

const mockedApiFetch = vi.mocked(apiFetch);

const DOCUMENT_ID = "aaaaaaaa-1111-4222-8333-444444444444";
const OLD_FILE = "bbbbbbbb-1111-4222-8333-444444444444";
const NEW_FILE = "cccccccc-1111-4222-8333-444444444444";

function candidate(
  overrides: Partial<VersionCandidate> = {},
): VersionCandidate {
  return {
    file_id: OLD_FILE,
    title: "AI Governance Policy",
    confidence: "high",
    reasons: [
      "Most of the text is the same as AI Governance Policy.",
      "The document calls itself version 2.0; the one you have is 1.0.",
    ],
    current_version: "1.0",
    current_effective_date: "May 2026",
    current_approved_at: "2026-05-12T09:00:00Z",
    current_filename: "AI_Governance_Policy.docx",
    detected_version: "2.0",
    detected_effective_date: "August 2026",
    uploaded_filename: "Updated_AI_Governance_August.docx",
    ...overrides,
  };
}

function version(overrides: Partial<DocumentVersion> = {}): DocumentVersion {
  return {
    file_id: OLD_FILE,
    document_id: DOCUMENT_ID,
    href: `/documents/${DOCUMENT_ID}`,
    filename: "AI_Governance_Policy.docx",
    version_label: "1.0",
    status: "superseded",
    uploaded_at: "2026-05-02T10:00:00Z",
    uploaded_by: null,
    evidence_count: 4,
    ...overrides,
  };
}

function renderWithClient(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>,
  );
}

beforeEach(() => {
  mockedApiFetch.mockReset();
  mockedApiFetch.mockResolvedValue({});
});

describe("VersionBanner", () => {
  it("asks rather than announces, and links nothing before the answer", () => {
    renderWithClient(
      <VersionBanner documentId={DOCUMENT_ID} candidate={candidate()} />,
    );

    expect(
      screen.getByRole("heading", {
        name: /is this a new version of AI Governance Policy\?/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/nothing has been linked yet/i),
    ).toBeInTheDocument();
    expect(mockedApiFetch).not.toHaveBeenCalled();
  });

  it("shows the reasons it thinks so, so the reader can disagree with them", () => {
    renderWithClient(
      <VersionBanner documentId={DOCUMENT_ID} candidate={candidate()} />,
    );

    expect(
      screen.getByText(/most of the text is the same/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/calls itself version 2\.0/i)).toBeInTheDocument();
  });

  it("gives 'separate document' the same weight as accepting the version", () => {
    renderWithClient(
      <VersionBanner documentId={DOCUMENT_ID} candidate={candidate()} />,
    );

    expect(
      screen.getByRole("button", { name: /use as a new version/i }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: /treat as separate document/i }),
    ).toBeEnabled();
  });

  it("says what accepting will do to approvals before it is accepted", () => {
    renderWithClient(
      <VersionBanner documentId={DOCUMENT_ID} candidate={candidate()} />,
    );

    expect(
      screen.getByText(/keeps the older version and its history/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/goes back for\s+review/i)).toBeInTheDocument();
  });

  it("hedges the language when it is only a medium-confidence guess", () => {
    renderWithClient(
      <VersionBanner
        documentId={DOCUMENT_ID}
        candidate={candidate({ confidence: "medium" })}
      />,
    );

    expect(screen.getByText(/this might be a revision/i)).toBeInTheDocument();
  });

  it("accepts the version with the file it supersedes and the version it read", async () => {
    const user = userEvent.setup();
    renderWithClient(
      <VersionBanner documentId={DOCUMENT_ID} candidate={candidate()} />,
    );

    await user.click(
      screen.getByRole("button", { name: /use as a new version/i }),
    );

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(1));
    const [path, init] = mockedApiFetch.mock.calls[0];
    expect(path).toBe(
      `/api/v1/compliance/documents/${DOCUMENT_ID}/accept-version`,
    );
    // A plain object: apiFetch does the serializing, and stringifying
    // here would send a JSON string the API cannot read.
    expect(init?.body).toEqual({
      supersedes_file_id: OLD_FILE,
      version_label: "2.0",
    });
  });

  it("keeps them apart on the other choice, without a version label", async () => {
    const user = userEvent.setup();
    renderWithClient(
      <VersionBanner documentId={DOCUMENT_ID} candidate={candidate()} />,
    );

    await user.click(
      screen.getByRole("button", { name: /treat as separate document/i }),
    );

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalledTimes(1));
    expect(mockedApiFetch.mock.calls[0][0]).toBe(
      `/api/v1/compliance/documents/${DOCUMENT_ID}/separate-document`,
    );
  });

  it("reports a failure as an alert and says nothing changed", async () => {
    const user = userEvent.setup();
    mockedApiFetch.mockRejectedValue(new Error("network"));
    renderWithClient(
      <VersionBanner documentId={DOCUMENT_ID} candidate={candidate()} />,
    );

    await user.click(
      screen.getByRole("button", { name: /use as a new version/i }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/nothing was changed/i);
  });
});

describe("VersionHistory", () => {
  it("says nothing for a document uploaded only once", () => {
    const { container } = renderWithClient(
      <VersionHistory
        versions={[version({ status: "current", file_id: NEW_FILE })]}
        currentFileId={NEW_FILE}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("lists newest first, marking which one is current", () => {
    renderWithClient(
      <VersionHistory
        versions={[
          version(),
          version({
            file_id: NEW_FILE,
            version_label: "2.0",
            status: "current",
          }),
        ]}
        currentFileId={NEW_FILE}
      />,
    );

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("2.0");
    expect(items[0]).toHaveTextContent(/current/i);
    expect(items[1]).toHaveTextContent("1.0");
    expect(items[1]).toHaveTextContent(/superseded/i);
  });

  it("tells the reader which version they are looking at", () => {
    renderWithClient(
      <VersionHistory
        versions={[
          version(),
          version({ file_id: NEW_FILE, status: "current" }),
        ]}
        currentFileId={OLD_FILE}
      />,
    );

    expect(screen.getByText(/you are here/i)).toBeInTheDocument();
  });

  it("keeps superseded versions readable — history a citation can still open", () => {
    renderWithClient(
      <VersionHistory
        versions={[
          version(),
          version({ file_id: NEW_FILE, status: "current" }),
        ]}
        currentFileId={NEW_FILE}
      />,
    );

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", `/documents/${DOCUMENT_ID}`);
  });

  it("never renders a link to a version that has no page", () => {
    renderWithClient(
      <VersionHistory
        versions={[
          version({ href: null, document_id: null }),
          version({ file_id: NEW_FILE, status: "current" }),
        ]}
        currentFileId={NEW_FILE}
      />,
    );

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows no raw file or document identifiers", () => {
    const { container } = renderWithClient(
      <VersionHistory
        versions={[
          version(),
          version({ file_id: NEW_FILE, status: "current" }),
        ]}
        currentFileId={NEW_FILE}
      />,
    );

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/i);
  });

  it("counts evidence per version, so the reader sees what moved", () => {
    renderWithClient(
      <VersionHistory
        versions={[
          version({ evidence_count: 1 }),
          version({ file_id: NEW_FILE, status: "current", evidence_count: 5 }),
        ]}
        currentFileId={NEW_FILE}
      />,
    );

    expect(screen.getByText(/5 pieces of evidence/)).toBeInTheDocument();
    expect(screen.getByText(/1 piece of evidence/)).toBeInTheDocument();
  });
});

describe("SupersededNotice", () => {
  it("tells the reader the wording is not what the organization is held to", () => {
    renderWithClient(
      <SupersededNotice
        currentHref={`/documents/${DOCUMENT_ID}`}
        currentLabel="2.0"
      />,
    );

    expect(screen.getByRole("note")).toHaveTextContent(
      /earlier version of this document/i,
    );
    expect(screen.getByRole("note")).toHaveTextContent(
      /not what your organization is held to/i,
    );
  });

  it("offers one click to the version that is current", () => {
    renderWithClient(
      <SupersededNotice
        currentHref={`/documents/${DOCUMENT_ID}`}
        currentLabel="2.0"
      />,
    );

    const link = screen.getByRole("link", {
      name: "Go to the current version (2.0)",
    });
    expect(link).toHaveAttribute("href", `/documents/${DOCUMENT_ID}`);
  });

  it("still explains where the reader is when the current version has no page", () => {
    renderWithClient(
      <SupersededNotice currentHref={null} currentLabel={null} />,
    );

    expect(screen.getByRole("note")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});

describe("VersionBanner comparison", () => {
  it("puts both documents side by side, as they describe themselves", () => {
    renderWithClient(
      <VersionBanner documentId={DOCUMENT_ID} candidate={candidate()} />,
    );

    expect(screen.getByText("What you have")).toBeInTheDocument();
    expect(screen.getByText("What you uploaded")).toBeInTheDocument();
    expect(screen.getByText("Version 1.0")).toBeInTheDocument();
    expect(screen.getByText("Version 2.0")).toBeInTheDocument();
    expect(screen.getByText("Effective May 2026")).toBeInTheDocument();
    expect(screen.getByText("Effective August 2026")).toBeInTheDocument();
  });

  it("shows when the document you have was approved", () => {
    renderWithClient(
      <VersionBanner documentId={DOCUMENT_ID} candidate={candidate()} />,
    );

    expect(screen.getByText(/approved May 12, 2026/i)).toBeInTheDocument();
  });

  it("never invents a version number a document does not state", () => {
    renderWithClient(
      <VersionBanner
        documentId={DOCUMENT_ID}
        candidate={candidate({
          current_version: null,
          detected_version: null,
          current_effective_date: null,
          detected_effective_date: null,
        })}
      />,
    );

    expect(screen.getAllByText("No version stated")).toHaveLength(2);
    expect(screen.queryByText(/^Effective/)).not.toBeInTheDocument();
  });

  it("names the uploaded file, so the reader knows which upload this is about", () => {
    renderWithClient(
      <VersionBanner documentId={DOCUMENT_ID} candidate={candidate()} />,
    );

    expect(
      screen.getByText("Updated_AI_Governance_August.docx"),
    ).toBeInTheDocument();
  });
});
