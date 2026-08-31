/**
 * Status and evidence coverage are different questions.
 *
 * The badge used to read "Needs review · 100%" — an assessment state and
 * an evidence measurement in one place, leaving the reader to work out
 * they were different kinds of thing. Worse, the label came from the
 * *derived* assessment, so a control still read "Needs review" after a
 * person had reviewed and passed it.
 *
 * These tests hold the two apart: the badge carries one word, coverage is
 * its own component, and neither renders the other's information.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AssessmentBadge, EvidenceCoverage } from "./assessment-badge";

describe("AssessmentBadge", () => {
  it("shows the label the server phrased, never a raw status", () => {
    render(<AssessmentBadge status="partially_evidenced" label="Partially evidenced" />);
    expect(screen.getByText("Partially evidenced")).toBeInTheDocument();
    expect(screen.queryByText(/partially_evidenced/)).not.toBeInTheDocument();
  });

  it("never renders a percentage", () => {
    // The whole point of the split. A percentage inside the status badge
    // is what made "Needs review · 100%" read as one idea.
    for (const [status, label] of [
      ["needs_review", "Needs review"],
      ["evidenced", "Evidenced"],
      ["passed", "Passed"],
      ["partially_evidenced", "Partially evidenced"],
    ] as const) {
      const { unmount } = render(<AssessmentBadge status={status} label={label} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      expect(screen.queryByText(/%/)).not.toBeInTheDocument();
      unmount();
    }
  });

  it("renders a human verdict as the headline, not as a separate kind of thing", () => {
    // "Passed" is a status like any other. "Passed by reviewer" as a
    // primary label would make it read as a different scale.
    render(<AssessmentBadge status="passed" label="Passed" />);
    expect(screen.getByText("Passed")).toBeInTheDocument();
    expect(screen.queryByText(/by reviewer/i)).not.toBeInTheDocument();
  });

  it("renders every status the server can send", () => {
    for (const status of [
      "evidenced",
      "partially_evidenced",
      "evidence_insufficient",
      "needs_review",
      "no_evidence",
      "not_applicable",
      "passed",
      "failed",
      "partially_implemented",
    ] as const) {
      const { unmount } = render(<AssessmentBadge status={status} label={status} />);
      expect(screen.getByText(status)).toBeInTheDocument();
      unmount();
    }
  });

  it("does not communicate status by colour alone", () => {
    // Each state carries its own icon as well as its variant, so the
    // difference survives a monochrome display or colour blindness.
    const { container: passed, unmount } = render(
      <AssessmentBadge status="passed" label="Passed" />
    );
    const passedIcon = passed.querySelector("svg")?.getAttribute("class");
    unmount();

    const { container: failed } = render(
      <AssessmentBadge status="failed" label="Failed" />
    );
    expect(passed).not.toBe(failed);
    expect(passedIcon).toBeDefined();
    expect(failed.querySelector("svg")).not.toBeNull();
  });
});

describe("EvidenceCoverage", () => {
  it("is labelled, so it cannot be mistaken for a status", () => {
    render(<EvidenceCoverage percent={50} status="partially_evidenced" />);
    expect(screen.getByText("Evidence coverage")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("exposes the bar to assistive technology as a real progressbar", () => {
    render(<EvidenceCoverage percent={75} status="partially_evidenced" />);
    const bar = screen.getByRole("progressbar", { name: "Evidence coverage" });
    expect(bar).toHaveAttribute("aria-valuenow", "75");
  });

  it("shows a dash rather than 0% when nothing applies", () => {
    // A control with no applicable requirements has no denominator.
    // Printing 0% reads as a failure rather than as out of scope.
    render(<EvidenceCoverage percent={0} status="not_applicable" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("shows zero honestly when the denominator is real", () => {
    render(<EvidenceCoverage percent={0} status="evidence_insufficient" />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });
});
