/**
 * A document row is a way into the document.
 *
 * The library listed filenames and offered nowhere to click, while the
 * Copilot's citations opened a detail page nobody could reach any other
 * way. One document now has one page, and the row is a real link to it —
 * not a click handler on a div, so it keeps its keyboard semantics and
 * its accessible name.
 *
 * The rest of the row still works: the policy link opens the policy, the
 * retry button retries. A stretched link that swallows its own row's
 * controls is a worse bug than the one it fixed.
 */
import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ComplianceDocument } from "@/lib/types";
import { RETIRED_MODULE_PREFIXES } from "@/middleware";

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

vi.mock("@/lib/upload", () => ({ uploadFile: vi.fn() }));

import { apiFetch } from "@/lib/api";

import { DocumentLibrary } from "./document-library";

const mockedApiFetch = vi.mocked(apiFetch);

const DOCUMENT_ID = "aaaaaaaa-1111-4222-8333-444444444444";
const POLICY_ID = "bbbbbbbb-1111-4222-8333-444444444444";
const FILENAME = "10_Special_Category_Data_Processing_Policy.docx";

function document(
  overrides: Partial<ComplianceDocument> = {},
): ComplianceDocument {
  return {
    id: "cccccccc-1111-4222-8333-444444444444",
    original_filename: FILENAME,
    // An uploaded document unless a test says otherwise, which is what
    // every existing case here is about.
    artifact_type: "source",
    artifact_label: "Source document",
    origin_type: null,
    origin_id: null,
    origin_label: null,
    origin_href: null,
    content_type:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    size_bytes: 20_000,
    classification: "confidential",
    mapping_state: "mapped" as const,
    version_count: 1,
    version_label: null,
    has_pending_version: false,
    processing_status: "ready",
    processing_error: null,
    processed_at: new Date().toISOString(),
    policy_id: POLICY_ID,
    policy_title: "Special Category Data Processing Policy",
    policy_status: "needs_review",
    index_status: "indexed",
    index_error: null,
    indexed_at: new Date().toISOString(),
    extracted_characters: 8_400,
    document_type: "Policy",
    document_domain: "Privacy / GDPR",
    created_at: new Date().toISOString(),
    proposed_count: 0,
    approved_count: 6,
    unverifiable_count: 0,
    title: "Special Category Data Processing Policy",
    document_id: DOCUMENT_ID,
    href: `/documents/${DOCUMENT_ID}`,
    ...overrides,
  };
}

function renderLibrary(documents: ComplianceDocument[]) {
  mockedApiFetch.mockReset();
  mockedApiFetch.mockImplementation(async () => documents as never);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DocumentLibrary />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockedApiFetch.mockReset();
});

describe("a document row opens the document", () => {
  it("names the document and links to its detail page", async () => {
    renderLibrary([document()]);

    const link = await screen.findByRole("link", {
      name: "Special Category Data Processing Policy",
    });
    expect(link.getAttribute("href")).toBe(`/documents/${DOCUMENT_ID}`);
  });

  it("keeps the filename visible under the name", async () => {
    renderLibrary([document()]);
    // The name is what the document is; the filename is how the customer
    // finds it on their own disk. Both, not one.
    expect(await screen.findByText(FILENAME)).toBeInTheDocument();
  });

  it("uses the server's href rather than composing one", async () => {
    // The server decides the route (app/core/routes.py). A component that
    // builds its own is how citations went on opening `/knowledge/<id>`.
    const custom = `/documents/${DOCUMENT_ID}?from=library`;
    renderLibrary([document({ href: custom })]);

    const link = await screen.findByRole("link", {
      name: "Special Category Data Processing Policy",
    });
    expect(link.getAttribute("href")).toBe(custom);
  });

  it("never links into a module the middleware 404s", async () => {
    renderLibrary([document()]);
    await screen.findByRole("link", {
      name: "Special Category Data Processing Policy",
    });

    for (const link of screen.getAllByRole("link")) {
      const href = link.getAttribute("href") ?? "";
      for (const prefix of RETIRED_MODULE_PREFIXES) {
        expect(
          href.startsWith(prefix),
          `${href} points at retired ${prefix}`,
        ).toBe(false);
      }
    }
  });

  it("points at a route this app actually has", async () => {
    renderLibrary([document()]);
    const link = await screen.findByRole("link", {
      name: "Special Category Data Processing Policy",
    });
    const segments = (link.getAttribute("href") ?? "")
      .split("/")
      .filter(Boolean);
    const route = resolve(
      __dirname,
      "..",
      "..",
      "app",
      "(app)",
      segments[0],
      "[id]",
      "page.tsx",
    );
    expect(existsSync(route), `no route file at ${route}`).toBe(true);
  });

  it("is reachable and activatable from the keyboard", async () => {
    const user = userEvent.setup();
    renderLibrary([document()]);
    const link = await screen.findByRole("link", {
      name: "Special Category Data Processing Policy",
    });

    // A real anchor with a real href: it is in the tab order, and the
    // browser activates it on Enter. A div with an onClick is neither,
    // which is why the primary navigation is a link rather than a
    // handler on the card. Tabbing forward from the top of the page has
    // to arrive at it — the upload input comes first.
    expect(link.tagName).toBe("A");
    expect(link.getAttribute("href")).toBeTruthy();

    // In the tab order, and focusable — the two things a div with an
    // onClick is not.
    const focusable = Array.from(
      globalThis.document.querySelectorAll<HTMLElement>(
        "a[href], button, input",
      ),
    );
    expect(focusable).toContain(link);

    link.focus();
    expect(link).toHaveFocus();

    // And tabbing moves on to the next control rather than trapping.
    await user.tab();
    expect(link).not.toHaveFocus();
  });

  it("offers no link when the document has not been indexed", async () => {
    // Nothing to open yet. A link to a page that does not exist is worse
    // than a plain filename.
    renderLibrary([
      document({ href: null, document_id: null, index_status: "pending" }),
    ]);

    expect(
      await screen.findByText("Special Category Data Processing Policy"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", {
        name: "Special Category Data Processing Policy",
      }),
    ).not.toBeInTheDocument();
  });
});

describe("the rest of the row still works", () => {
  it("sends the policy link to the policy, not the document", async () => {
    renderLibrary([document()]);
    const policyLink = await screen.findByRole("link", {
      name: /Policy detected/,
    });

    expect(policyLink.getAttribute("href")).toBe(
      `/compliance/policies/${POLICY_ID}`,
    );
    expect(policyLink.getAttribute("href")).not.toContain("/documents/");
  });

  it("leaves a row's own button clickable rather than navigating", async () => {
    const user = userEvent.setup();
    renderLibrary([
      document({
        processing_status: "not_analyzed",
        policy_id: null,
        policy_title: null,
      }),
    ]);

    const analyze = await screen.findByRole("button", {
      name: /Analyze for evidence/,
    });
    await user.click(analyze);

    // The button ran its own action — a POST — rather than the row's
    // navigation swallowing the click.
    await waitFor(() =>
      expect(
        mockedApiFetch.mock.calls.some(
          ([path, init]) =>
            String(path).includes("/documents/process") &&
            (init as { method?: string } | undefined)?.method === "POST",
        ),
      ).toBe(true),
    );
  });

  it("puts every interactive control above the stretched link", async () => {
    // The row link covers the card with `after:absolute after:inset-0`.
    // Anything interactive has to sit above it on its own stacking
    // context, or it becomes unclickable.
    const { container } = renderLibrary([document()]);
    await screen.findByRole("link", {
      name: "Special Category Data Processing Policy",
    });

    const policyLink = screen.getByRole("link", { name: /Policy detected/ });
    expect(policyLink.className).toContain("z-10");

    const card = container.querySelector(".relative");
    expect(card).not.toBeNull();
    expect(
      within(card as HTMLElement).getByRole("link", {
        name: "Special Category Data Processing Policy",
      }).className,
    ).toContain("after:inset-0");
  });
});

describe("what a document says about its control mappings", () => {
  it("does not report a negative finding when there is nothing to map against", async () => {
    // A brand-new organization. "No control matches proposed" is
    // literally true and badly misleading — it reads as "we looked and
    // your policy evidences nothing", when nothing was looked against.
    renderLibrary([
      document({
        mapping_state: "no_controls",
        proposed_count: 0,
        approved_count: 0,
        document_type: "AI Governance Policy",
      }),
    ]);

    expect(
      await screen.findByText(
        /evidence mapping starts when you adopt a framework/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/no control matches proposed/i),
    ).not.toBeInTheDocument();
  });

  it("does report it when there were controls and none matched", async () => {
    renderLibrary([
      document({
        mapping_state: "no_matches",
        proposed_count: 0,
        approved_count: 0,
      }),
    ]);

    expect(
      await screen.findByText(/no control matches proposed/i),
    ).toBeInTheDocument();
  });

  it("still shows what the document is when nothing is mapped", async () => {
    renderLibrary([
      document({
        mapping_state: "no_controls",
        proposed_count: 0,
        approved_count: 0,
        document_type: "AI Governance Policy",
      }),
    ]);

    expect(await screen.findByText("AI Governance Policy")).toBeInTheDocument();
  });
});
