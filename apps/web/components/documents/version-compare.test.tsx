import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, apiFetch: vi.fn() };
});

import { apiFetch } from "@/lib/api";
import type { DocumentVersion, VersionDiff } from "@/lib/types";

import { VersionCompare } from "./version-compare";

const mockedApiFetch = vi.mocked(apiFetch);

const DOCUMENT_ID = "aaaaaaaa-1111-4222-8333-444444444444";
const OLD_FILE = "bbbbbbbb-1111-4222-8333-444444444444";
const NEW_FILE = "cccccccc-1111-4222-8333-444444444444";

const VERSIONS: DocumentVersion[] = [
  {
    file_id: OLD_FILE,
    document_id: DOCUMENT_ID,
    href: `/documents/${DOCUMENT_ID}`,
    filename: "AI_Governance_Policy.docx",
    version_label: "1.0",
    status: "superseded",
    uploaded_at: "2026-05-02T10:00:00Z",
    uploaded_by: null,
    evidence_count: 4,
  },
  {
    file_id: NEW_FILE,
    document_id: DOCUMENT_ID,
    href: `/documents/${DOCUMENT_ID}`,
    filename: "AI_Governance_Policy.docx",
    version_label: "2.0",
    status: "current",
    uploaded_at: "2026-08-02T10:00:00Z",
    uploaded_by: null,
    evidence_count: 5,
  },
];

const DIFF: VersionDiff = {
  previous_file_id: OLD_FILE,
  current_file_id: NEW_FILE,
  previous_label: "1.0",
  current_label: "2.0",
  headline: "1 section changed, 1 added, 1 removed.",
  added: 1,
  removed: 1,
  modified: 1,
  unchanged: 2,
  changes: [
    {
      change: "rewritten",
      section: "7. Monitoring",
      summary: "7. Monitoring has been substantially rewritten.",
      previous_text: "AI systems should be monitored.",
      current_text: "Production AI systems are reviewed monthly for drift.",
    },
    {
      change: "added",
      section: "8. Human oversight",
      summary: "8. Human oversight is new in this version.",
      previous_text: null,
      current_text: "Every production AI system has a named human owner.",
    },
    {
      change: "removed",
      section: "10. Retention",
      summary: "10. Retention is no longer in the document.",
      previous_text: "Model training data is retained for two years.",
      current_text: null,
    },
    {
      change: "unchanged",
      section: "1. Purpose",
      summary: "1. Purpose is unchanged.",
      previous_text: "This policy sets out how the company governs AI.",
      current_text: "This policy sets out how the company governs AI.",
    },
  ],
};

function renderCompare(currentFileId = NEW_FILE) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <VersionCompare
        documentId={DOCUMENT_ID}
        versions={VERSIONS}
        currentFileId={currentFileId}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockedApiFetch.mockReset();
  mockedApiFetch.mockResolvedValue(DIFF);
});

describe("VersionCompare", () => {
  it("says nothing for a document with only one version", () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { container } = render(
      <QueryClientProvider client={client}>
        <VersionCompare
          documentId={DOCUMENT_ID}
          versions={[VERSIONS[1]]}
          currentFileId={NEW_FILE}
        />
      </QueryClientProvider>,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("compares against the version immediately before, without being asked", async () => {
    renderCompare();

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalled());
    expect(mockedApiFetch.mock.calls[0][0]).toBe(
      `/api/v1/compliance/documents/${DOCUMENT_ID}/compare?against=${OLD_FILE}`,
    );
  });

  it("leads with one sentence, so the reader knows whether to look further", async () => {
    renderCompare();

    expect(
      await screen.findByText("1 section changed, 1 added, 1 removed."),
    ).toBeInTheDocument();
  });

  it("names each section and what happened to it", async () => {
    renderCompare();

    expect(await screen.findByText("7. Monitoring")).toBeInTheDocument();
    expect(screen.getByText(/substantially rewritten/i)).toBeInTheDocument();
    expect(screen.getByText("8. Human oversight")).toBeInTheDocument();
    expect(screen.getByText("10. Retention")).toBeInTheDocument();
  });

  it("shows both wordings, because that is what the reviewer is deciding about", async () => {
    renderCompare();

    expect(
      await screen.findByText("AI systems should be monitored."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Production AI systems are reviewed monthly for drift."),
    ).toBeInTheDocument();
  });

  it("hides unchanged sections until asked — a diff that cries wolf is unread", async () => {
    const user = userEvent.setup();
    renderCompare();

    await screen.findByText("7. Monitoring");
    expect(screen.queryByText("1. Purpose")).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /show 2 unchanged sections/i }),
    );
    expect(screen.getByText("1. Purpose")).toBeInTheDocument();
  });

  it("lets the reader compare against any other version", async () => {
    const user = userEvent.setup();
    renderCompare(OLD_FILE);

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalled());
    const select = screen.getByRole("combobox", { name: /compare with/i });
    // Reading the oldest version, the only other version is the newer one.
    expect(select).toHaveValue(NEW_FILE);

    await user.selectOptions(select, NEW_FILE);
    expect(select).toHaveValue(NEW_FILE);
  });

  it("shows no raw file or document identifiers", async () => {
    const { container } = renderCompare();

    await screen.findByText("7. Monitoring");
    // The select carries file ids as option values, which is markup, not
    // something a reader sees. The visible text must be free of them.
    expect(container.textContent ?? "").not.toMatch(
      /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/i,
    );
  });

  it("says so plainly when two versions have identical text", async () => {
    mockedApiFetch.mockResolvedValue({
      ...DIFF,
      headline:
        "The text of this document did not change between these versions.",
      added: 0,
      removed: 0,
      modified: 0,
      unchanged: 4,
      changes: DIFF.changes.map((change) => ({
        ...change,
        change: "unchanged" as const,
      })),
    });
    renderCompare();

    expect(
      await screen.findByText(/did not change between these versions/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/nothing changed between these two versions/i),
    ).toBeInTheDocument();
  });
});

describe("VersionCompare when the second version appears", () => {
  it("compares as soon as there is something to compare against", async () => {
    // The panel first renders while the document has one version — which
    // is exactly the state a reader is in a moment before they accept
    // one. A default captured at mount is captured as null and never
    // recovers, leaving the panel blank for the one person who just made
    // the version.
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <VersionCompare
          documentId={DOCUMENT_ID}
          versions={[VERSIONS[1]]}
          currentFileId={NEW_FILE}
        />
      </QueryClientProvider>,
    );

    expect(mockedApiFetch).not.toHaveBeenCalled();

    rerender(
      <QueryClientProvider client={client}>
        <VersionCompare
          documentId={DOCUMENT_ID}
          versions={VERSIONS}
          currentFileId={NEW_FILE}
        />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(mockedApiFetch).toHaveBeenCalled());
    expect(mockedApiFetch.mock.calls[0][0]).toBe(
      `/api/v1/compliance/documents/${DOCUMENT_ID}/compare?against=${OLD_FILE}`,
    );
    expect(
      await screen.findByText("1 section changed, 1 added, 1 removed."),
    ).toBeInTheDocument();
  });
});
