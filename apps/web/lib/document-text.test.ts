/**
 * Reassembling a document from the pieces it was indexed as.
 *
 * Chunks overlap by 150 characters so a sentence cut by one boundary
 * survives whole in its neighbour. Rendered naively that repeats a
 * paragraph's tail at the head of the next chunk, and the document reads
 * as though it stutters.
 */
import { describe, expect, it } from "vitest";

import { assembleSections, findPassage } from "./document-text";
import type { DocumentChunk } from "@/lib/types";

function chunk(
  index: number,
  content: string,
  section: string | null = null,
  page: number | null = null
): DocumentChunk {
  return {
    id: `chunk-${index}`,
    chunk_index: index,
    content,
    token_count: Math.ceil(content.length / 4),
    section_label: section,
    page_number: page,
  };
}

describe("assembleSections", () => {
  it("removes the overlap between neighbouring chunks", () => {
    const overlap = "and every incident is reviewed monthly.";
    const sections = assembleSections([
      chunk(0, `Systems are monitored continuously. ${overlap}`, "7 Monitoring"),
      chunk(1, `${overlap} Records are retained for three years.`, "7 Monitoring"),
    ]);

    expect(sections).toHaveLength(1);
    // The repeated sentence appears once.
    expect(sections[0].text.split(overlap)).toHaveLength(2);
    expect(sections[0].text).toContain("Records are retained for three years.");
  });

  it("keeps the document's own headings as the boundaries", () => {
    const sections = assembleSections([
      chunk(0, "The purpose of this policy.", "1 Purpose", 1),
      chunk(1, "How systems are monitored.", "7 Monitoring", 4),
      chunk(2, "More on monitoring.", "7 Monitoring", 4),
    ]);

    expect(sections.map((section) => section.label)).toEqual(["1 Purpose", "7 Monitoring"]);
    expect(sections[1].page).toBe(4);
  });

  it("invents no heading for a document that has none", () => {
    const sections = assembleSections([chunk(0, "Just some text."), chunk(1, "And more.")]);
    expect(sections).toHaveLength(1);
    expect(sections[0].label).toBeNull();
    expect(sections[0].page).toBeNull();
  });

  it("reads chunks in order regardless of how they arrived", () => {
    const sections = assembleSections([chunk(1, "Second."), chunk(0, "First.")]);
    expect(sections[0].text.indexOf("First.")).toBeLessThan(sections[0].text.indexOf("Second."));
  });

  it("handles an empty document without inventing a section", () => {
    expect(assembleSections([])).toEqual([]);
  });
});

describe("findPassage", () => {
  const TEXT =
    "7. Monitoring\nAll production AI systems are monitored continuously\nfor model drift, and every incident is reviewed monthly.";

  it("finds a passage whose whitespace was flattened by the API", () => {
    // The citation's passage arrives on one line; the document keeps its
    // line breaks. Matching only works on a common form.
    const range = findPassage(TEXT, "monitored continuously for model drift");
    expect(range).not.toBeNull();
    expect(TEXT.slice(range!.start, range!.end)).toContain("monitored continuously");
    expect(TEXT.slice(range!.start, range!.end)).toContain("model drift");
  });

  it("ignores the ellipses the API added at a chunk boundary", () => {
    const range = findPassage(TEXT, "…monitored continuously for model drift…");
    expect(range).not.toBeNull();
  });

  it("falls back to the opening when the passage was trimmed differently", () => {
    const range = findPassage(
      TEXT,
      "All production AI systems are monitored continuously for model drift, and every incident is reviewed weekly by a different team."
    );
    expect(range).not.toBeNull();
    expect(TEXT.slice(range!.start, range!.end)).toContain("All production AI systems");
  });

  it("returns null for a section the passage is not in", () => {
    expect(findPassage(TEXT, "Employees complete AI literacy training annually.")).toBeNull();
  });

  it("refuses to match on a fragment too short to be meaningful", () => {
    // Highlighting on "the" would scatter marks across the document.
    expect(findPassage(TEXT, "the")).toBeNull();
  });
});
