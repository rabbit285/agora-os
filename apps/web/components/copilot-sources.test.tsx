/**
 * Citations are for the reader, not for us.
 *
 * The old citation rendered `Document da7966ef · chunk 5`. A UUID is a
 * primary key; a chunk number is an artefact of slicing a file into
 * 1000-character windows. Neither can be found in the customer's own copy
 * of the document, which is the only thing a citation is for.
 *
 * These tests hold three lines:
 *
 * - nothing a person reads contains an identifier;
 * - long answers keep their sources folded away;
 * - values read from Veyntra's records are never presented as though a
 *   document said them.
 */
import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ComplianceFacts, CopilotSources } from "./copilot-sources";
import { RETIRED_MODULE_PREFIXES } from "@/middleware";
import type { Citation, ComplianceFact } from "@/lib/types";

const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
/** The short form the old UI rendered — `da7966ef · chunk 5`. */
const SHORT_ID = /\b[0-9a-f]{8}\b/i;
const CHUNK = /chunk[\s_-]*\d+/i;

const DOCUMENT_ID = "da7966ef-1c22-4b0a-9f31-8c5e2d7a41bb";
const PASSAGE =
  "…all production AI systems are monitored continuously for model drift, and every incident is reviewed monthly.";
const SECTION = "7 Monitoring";

const CITATION: Citation = {
  reference: "AI Governance Policy — §7 Monitoring",
  document_title: "AI Governance Policy",
  section: SECTION,
  page: 4,
  passage: PASSAGE,
  source_type: "Policy",
  document_id: DOCUMENT_ID,
  // Shaped exactly as app/ai/citations.py composes it. Written out here
  // rather than generated, so a change to the server's route shows up as
  // a failing test instead of a fixture that quietly follows along.
  href:
    `/documents/${DOCUMENT_ID}?` +
    new URLSearchParams({ passage: PASSAGE, section: SECTION }).toString(),
};

function citations(count: number): Citation[] {
  return Array.from({ length: count }, (_, index) => ({
    ...CITATION,
    reference: `AI Governance Policy — §${index + 1} Section`,
    section: `${index + 1} Section`,
    page: index + 1,
  }));
}

describe("CopilotSources", () => {
  it("names the document, its section and its page — never an identifier", () => {
    render(<CopilotSources citations={[CITATION]} answerLength={80} />);

    expect(screen.getByText("AI Governance Policy — §7 Monitoring")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(UUID);
    expect(document.body.textContent).not.toMatch(CHUNK);
    expect(document.body.textContent).not.toMatch(SHORT_ID);
  });

  it("shows the passage the answer actually rests on", () => {
    render(<CopilotSources citations={[CITATION]} answerLength={80} />);
    expect(screen.getByText(/monitored continuously for model drift/)).toBeInTheDocument();
  });

  it("counts its sources in the summary", () => {
    render(<CopilotSources citations={citations(5)} answerLength={80} />);
    expect(screen.getByText("Sources (5)")).toBeInTheDocument();
  });

  it("stays folded away under a long answer, and open under a short one", () => {
    const { unmount } = render(<CopilotSources citations={citations(5)} answerLength={2000} />);
    // A native <details>: `open` is the state, and the browser handles
    // the keyboard and the announcement.
    expect(document.querySelector("details")?.open).toBe(false);
    unmount();

    render(<CopilotSources citations={citations(5)} answerLength={80} />);
    expect(document.querySelector("details")?.open).toBe(true);
  });

  it("renders nothing at all when there are no sources", () => {
    const { container } = render(<CopilotSources citations={[]} answerLength={80} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("uses the server's href verbatim, building no URL of its own", () => {
    // The root cause of the 404: this component inlined
    // `/knowledge/${citation.document_id}`, and kept doing it after that
    // module was withdrawn. Routes are decided server-side now.
    render(<CopilotSources citations={[CITATION]} answerLength={80} />);
    const link = screen.getByRole("link", { name: /AI Governance Policy/ });

    expect(link.getAttribute("href")).toBe(CITATION.href);
    // The id is a link target, never text — the visible label is the
    // reference.
    expect(link.textContent).not.toMatch(UUID);
  });

  it("shows the source type only as its own chip", () => {
    render(<CopilotSources citations={[CITATION]} answerLength={80} />);
    expect(screen.getByText("Policy")).toBeInTheDocument();
  });
});

describe("where a citation leads", () => {
  it("never points into a module the middleware 404s", () => {
    // Asserted against the middleware's own list, not a copy of it, so
    // retiring another module can never leave a citation behind.
    render(<CopilotSources citations={citations(5)} answerLength={80} />);

    for (const link of screen.getAllByRole("link")) {
      const href = link.getAttribute("href") ?? "";
      for (const prefix of RETIRED_MODULE_PREFIXES) {
        expect(href.startsWith(prefix), `${href} points at retired ${prefix}`).toBe(false);
      }
    }
  });

  it("points at a route this app actually has", () => {
    // `/knowledge/<id>` was a route that existed as a file and was
    // unreachable behind the middleware. This checks the file, and the
    // test above checks the middleware; a citation has to pass both.
    const path = new URL(CITATION.href, "http://x").pathname;
    const segments = path.split("/").filter(Boolean);
    expect(segments[0]).toBe("documents");

    const route = resolve(__dirname, "..", "app", "(app)", segments[0], "[id]", "page.tsx");
    expect(existsSync(route), `no route file at ${route}`).toBe(true);
  });

  it("carries the passage so the viewer can highlight it", () => {
    // Read the way the viewer reads it — `useSearchParams`, not a raw
    // decode, since a query string encodes spaces as "+".
    const query = new URLSearchParams(CITATION.href.split("?")[1]);
    expect(query.get("passage")).toBe(CITATION.passage);
    expect(query.get("section")).toBe(CITATION.section);
  });
});

describe("ComplianceFacts", () => {
  const FACTS: ComplianceFact[] = [
    { label: "Current status", value: "Needs review", detail: "Monitor AI systems in production" },
    { label: "Open gaps", value: "3", detail: "1 high or critical severity." },
  ];

  it("says where the value came from, in its own block", () => {
    render(<ComplianceFacts facts={FACTS} />);

    // The label and its value sit together, as a definition pair.
    const label = screen.getByText("Current status");
    expect(label.tagName).toBe("DT");
    expect(within(label.parentElement as HTMLElement).getByText("Needs review")).toBeInTheDocument();
    expect(screen.getByText("From your Veyntra records")).toBeInTheDocument();
    expect(
      screen.getByText("Read from your compliance data, not from an uploaded document.")
    ).toBeInTheDocument();
  });

  it("never presents a record as a document citation", () => {
    // Rendered side by side, the two blocks stay distinguishable: the
    // facts block says where its values came from, and the sources block
    // counts documents.
    render(
      <>
        <ComplianceFacts facts={FACTS} />
        <CopilotSources citations={[CITATION]} answerLength={80} />
      </>
    );

    expect(screen.getByText("From your Veyntra records")).toBeInTheDocument();
    expect(screen.getByText("Sources (1)")).toBeInTheDocument();
    // "Needs review" is a determination, so it appears once — under the
    // records, never inside a source.
    expect(screen.getAllByText("Needs review")).toHaveLength(1);
  });

  it("renders nothing when the question needed no records", () => {
    const { container } = render(<ComplianceFacts facts={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
