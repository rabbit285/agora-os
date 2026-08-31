"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2 } from "lucide-react";

import { AssessmentBadge } from "@/components/compliance/assessment-badge";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { Control, ControlAssessmentStatus } from "@/lib/types";

/** The controls list as one table, not twenty loosely positioned forms.
 *
 * Every row shares a single grid template, so the columns line up down
 * the page whatever a badge happens to be called. The uppercase
 * EVIDENCE COVERAGE / STATUS captions that repeated on every card are now
 * a header row shown once — repeating them made the labels louder than
 * the values, and the reader was scanning the same two words twenty
 * times to find the one control that needed them.
 *
 * Sorted by what needs doing. A page that opens on a wall of "Not
 * applicable" makes the reader hunt for the problems; the problems come
 * first here, and the settled controls sit underneath where they belong.
 */

/** Lower sorts first. The order a person would triage in: a confirmed
 * failure, then evidence that proves nothing, then nothing at all, then
 * partial progress, then things merely awaiting a decision, then what is
 * already settled. */
const URGENCY: Record<ControlAssessmentStatus, number> = {
  failed: 0,
  evidence_insufficient: 1,
  no_evidence: 2,
  partially_implemented: 3,
  partially_evidenced: 3,
  needs_review: 4,
  passed: 5,
  evidenced: 5,
  not_applicable: 6,
};

/** The next thing to do, per state. A row that names its action saves the
 * reader working out what "Evidence insufficient" wants from them. */
const ACTION: Record<ControlAssessmentStatus, string> = {
  failed: "See findings",
  evidence_insufficient: "See missing",
  no_evidence: "See needed",
  partially_implemented: "View gaps",
  partially_evidenced: "View gaps",
  needs_review: "Review",
  passed: "View",
  evidenced: "View",
  not_applicable: "View",
};

const FILTERS = [
  { key: "all", label: "All" },
  { key: "attention", label: "Needs attention" },
  { key: "review", label: "Needs review" },
  { key: "settled", label: "Passed" },
  { key: "not_applicable", label: "Not applicable" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

/** Statuses that mean somebody has to do something about the evidence. */
const NEEDS_ATTENTION = new Set<ControlAssessmentStatus>([
  "failed",
  "evidence_insufficient",
  "no_evidence",
  "partially_evidenced",
  "partially_implemented",
]);

const SETTLED = new Set<ControlAssessmentStatus>(["passed", "evidenced"]);

function matches(control: Control, filter: FilterKey): boolean {
  const status = control.assessment_status;
  if (filter === "all") return true;
  if (filter === "attention") return NEEDS_ATTENTION.has(status);
  if (filter === "review") return status === "needs_review";
  if (filter === "settled") return SETTLED.has(status);
  return status === "not_applicable";
}

/** The one grid template every row and the header share.
 *
 * Named once so a column cannot drift between the header and the rows —
 * which is exactly how a "table" made of cards stops lining up. Below
 * `md` it collapses to a single column and each row stacks. */
const GRID =
  "grid grid-cols-1 gap-x-4 gap-y-2 md:grid-cols-[minmax(0,1fr)_140px_180px_110px] md:items-center md:gap-y-0";

function CoverageBar({
  percent,
  status,
}: {
  percent: number;
  status: ControlAssessmentStatus;
}) {
  // A control with no applicable requirements has no denominator.
  // Printing 0% reads as a failure rather than as out of scope.
  if (status === "not_applicable") {
    return <span className="text-sm text-[var(--fg-subtle)]">—</span>;
  }

  return (
    <div>
      <span className="text-sm font-medium text-[var(--fg-default)]">
        {percent}%
        <span className="ml-1 font-normal text-[var(--fg-subtle)] md:hidden">coverage</span>
      </span>
      {/* The track is drawn even at 0%: an invisible track reads as
          a missing bar rather than an empty one. */}
      <span
        className="mt-1 block h-2 w-full max-w-[120px] overflow-hidden rounded-full bg-[var(--gray-200)]"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`Evidence coverage ${percent}%`}
      >
        <span
          className="block h-full rounded-full bg-[var(--brand-primary)]"
          style={{ width: `${percent}%` }}
        />
      </span>
    </div>
  );
}

export function ControlsList() {
  const [filter, setFilter] = useState<FilterKey>("all");

  const { data: controls } = useQuery<Control[]>({
    queryKey: ["compliance", "controls"],
    queryFn: () => apiFetch<Control[]>("/api/v1/compliance/controls?limit=200"),
  });

  const sorted = useMemo(() => {
    return [...(controls ?? [])].sort((a, b) => {
      const byUrgency =
        (URGENCY[a.assessment_status] ?? 9) - (URGENCY[b.assessment_status] ?? 9);
      if (byUrgency !== 0) return byUrgency;
      // Within a band, the least-covered first: those are the ones where
      // the work has not started.
      if (a.coverage_percent !== b.coverage_percent) {
        return a.coverage_percent - b.coverage_percent;
      }
      return a.title.localeCompare(b.title);
    });
  }, [controls]);

  const visible = sorted.filter((control) => matches(control, filter));
  const outstanding = sorted.filter((c) => NEEDS_ATTENTION.has(c.assessment_status));
  const applicable = sorted.filter((c) => c.assessment_status !== "not_applicable");

  if (controls && controls.length === 0) {
    return (
      <EmptyState
        title="No controls yet"
        description="Adopting a framework creates the controls its requirements need, and uploading a document maps evidence to them."
      />
    );
  }

  return (
    <div className="mb-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Controls
        </h2>
        {/* Said once, here, rather than captioned on every row. */}
        <p className="text-xs text-[var(--fg-subtle)]">
          Coverage is the share of applicable requirements the evidence on file supports.
        </p>
      </div>

      {controls && controls.length > 0 && (
        <div
          className="mb-4 flex flex-wrap gap-2"
          role="group"
          aria-label="Filter controls"
        >
          {FILTERS.map((option) => (
            <Button
              key={option.key}
              size="sm"
              variant={filter === option.key ? "default" : "outline"}
              aria-pressed={filter === option.key}
              onClick={() => setFilter(option.key)}
            >
              {option.label}
            </Button>
          ))}
        </div>
      )}

      {/* Nothing to chase is worth saying plainly, rather than leaving the
          reader to scroll a wall of green looking for a problem. */}
      {applicable.length > 0 && outstanding.length === 0 && filter === "all" && (
        <p className="mb-4 flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--success-600)]/25 bg-[var(--success-50)] px-3 py-2 text-sm text-[var(--success-700)]">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          All applicable controls are currently satisfied.
        </p>
      )}

      {/* The captions, once. Hidden below md, where each row stacks and
          carries its own inline labels instead. */}
      <div
        className={`${GRID} hidden border-b border-[var(--border-default)] px-4 pb-2 md:grid`}
        aria-hidden="true"
      >
        <span className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
          Control
        </span>
        <span className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
          Coverage
        </span>
        <span className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
          Status
        </span>
        <span className="sr-only">Action</span>
      </div>

      <ul className="flex flex-col">
        {visible.map((control) => (
          <li key={control.id} className="border-b border-[var(--border-default)]">
            <Link
              href={`/compliance/controls/${control.id}`}
              className={`${GRID} rounded-[var(--radius-md)] px-4 py-3 transition-colors hover:bg-[var(--bg-app)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--border-focus)]`}
            >
              <span className="min-w-0">
                <span className="block truncate font-medium text-[var(--fg-default)]">
                  {control.title}
                </span>
                <span className="mt-0.5 block text-xs text-[var(--fg-subtle)]">
                  {control.evidence_count} evidence item
                  {control.evidence_count === 1 ? "" : "s"} ·{" "}
                  {control.applicable_requirement_count} applicable requirement
                  {control.applicable_requirement_count === 1 ? "" : "s"}
                  {control.human_assessment_status && <> · human reviewed</>}
                </span>
              </span>

              <CoverageBar
                percent={control.coverage_percent}
                status={control.assessment_status}
              />

              <span>
                <AssessmentBadge
                  status={control.assessment_status}
                  label={control.assessment_label}
                />
              </span>

              <span className="flex items-center gap-1 text-sm text-[var(--fg-muted)] md:justify-end">
                {ACTION[control.assessment_status] ?? "View"}
                <ArrowRight className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              </span>
            </Link>
          </li>
        ))}
      </ul>

      {controls && controls.length > 0 && visible.length === 0 && (
        <p className="py-6 text-sm text-[var(--fg-muted)]">
          No controls match this filter.
        </p>
      )}
    </div>
  );
}
