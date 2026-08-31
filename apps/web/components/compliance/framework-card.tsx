import Link from "next/link";
import { AlertTriangle, CheckCircle2, ChevronDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { FrameworkReadiness } from "@/lib/types";

/** One framework's readiness, at a glance.
 *
 * The card used to lead with the full scoring methodology — "53.1% ready
 * because, of 24 applicable requirements, 3 satisfied, 18 awaiting review
 * and 3 with an identified deficiency…" — followed by a legal disclaimer,
 * repeated on every card. A founder scanning three frameworks read that
 * sentence three times and still could not tell which one needed them.
 *
 * The counts are the same numbers as the sentence, and they now sum to
 * the applicable total: an earlier version counted only `deficient`,
 * `assessment_failed` and `evidence_missing` as gaps, so a framework
 * whose requirements had no control mapped at all showed "0 satisfied,
 * 0 need review, 0 gaps" beside "2 actions required" — three zeroes and a
 * contradiction. Everything that is not satisfied and not awaiting review
 * is a gap, because that is what it is to the person reading.
 *
 * The methodology is one disclosure away for anyone who wants to check
 * the arithmetic. The disclaimer moved to the bottom of the list, where
 * saying it once is enough.
 */
export function FrameworkCard({ framework }: { framework: FrameworkReadiness }) {
  const { readiness } = framework;
  const percent = Math.round(readiness.percent);

  // Everything that is neither satisfied nor merely awaiting a decision.
  // Includes `not_assessed` — a requirement with no control mapped is a
  // gap in the record, and dropping it made the three counts fail to add
  // up to the total.
  const gaps = Math.max(
    0,
    readiness.total - readiness.satisfied - readiness.needs_review
  );

  const metrics = [
    { value: readiness.satisfied, label: "Satisfied", tone: "text-[var(--success-700)]" },
    { value: readiness.needs_review, label: "Need review", tone: "text-[var(--fg-default)]" },
    { value: gaps, label: gaps === 1 ? "Gap" : "Gaps", tone: "text-[var(--warning-700)]" },
  ];

  // A framework nobody has started is not failing. 0% with nothing
  // recorded against it is a beginning, and painting it like a red
  // failure teaches people to ignore the colour.
  // Nothing has been assessed: every requirement is still in its
  // starting state. Calling those "gaps" beside "No actions required"
  // was a contradiction on the same card — they are not findings, they
  // are requirements nobody has looked at yet.
  const notAssessed =
    readiness.satisfied === 0 &&
    readiness.needs_review === 0 &&
    framework.open_gap_count === 0 &&
    readiness.total > 0;
  const notStarted = readiness.total === 0 || notAssessed;

  return (
    <li className="rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      {/* One grid for every card, so the readiness block and the button
          land in the same place down the page regardless of how long a
          framework's name is. */}
      {/* Every column is a fixed width except the name. An `auto`
          action column sized itself to "View EU AI Act" on one card and
          "View SOC 2" on the next, which shifted the readiness block
          left and right down the page — the columns only line up if
          nothing in them is allowed to decide its own width. */}
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px_120px] md:items-center md:gap-6">
        <div className="min-w-0">
          <Link
            href={`/compliance/frameworks/${framework.framework_id}`}
            className="rounded-sm font-medium text-[var(--fg-default)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
          >
            {framework.framework_name}
          </Link>

          {/* The number carries the weight; the label explains it. */}
          {notAssessed ? (
            <p className="mt-2 text-sm text-[var(--fg-muted)]">
              {readiness.total} requirement{readiness.total === 1 ? "" : "s"} apply, none
              assessed yet
            </p>
          ) : (
            <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1">
              {metrics.map((metric) => (
                <div key={metric.label} className="flex items-baseline gap-1.5">
                  <dt className="sr-only">{metric.label}</dt>
                  <dd className={`text-lg font-semibold leading-none ${metric.tone}`}>
                    {metric.value}
                  </dd>
                  <span aria-hidden="true" className="text-xs text-[var(--fg-subtle)]">
                    {metric.label}
                  </span>
                </div>
              ))}
            </dl>
          )}
        </div>

        <div>
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
              Readiness
            </span>
            <span className="text-2xl font-semibold leading-none text-[var(--fg-default)]">
              {percent}
              <span className="text-sm font-normal text-[var(--fg-muted)]">%</span>
            </span>
          </div>
          <div
            className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-[var(--gray-200)]"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${framework.framework_name} readiness ${percent}%`}
          >
            <div
              className="h-full rounded-full bg-[var(--brand-primary)]"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>

        <Button
          asChild
          size="sm"
          variant="outline"
          className="justify-self-start md:w-full md:justify-self-end"
        >
          {/* The visible label is the same length on every card; the
              framework name is still announced, via aria-label. */}
          <Link
            href={`/compliance/frameworks/${framework.framework_id}`}
            aria-label={`View ${framework.framework_name}`}
          >
            {notStarted ? "Start" : "View"}
          </Link>
        </Button>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-t border-[var(--border-default)] pt-3">
        {/* Never colour alone: each state carries its own icon and words. */}
        {framework.open_gap_count > 0 ? (
          <p className="flex items-center gap-1.5 text-sm font-medium text-[var(--warning-700)]">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            {framework.open_gap_count} action
            {framework.open_gap_count === 1 ? "" : "s"} required
          </p>
        ) : notStarted ? (
          <p className="text-sm text-[var(--fg-muted)]">Not assessed yet</p>
        ) : (
          <p className="flex items-center gap-1.5 text-sm text-[var(--success-700)]">
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            No actions required
          </p>
        )}

        {/* Native disclosure: keyboard-operable and screen-reader
            announced without any state of our own. */}
        <details className="group">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-sm text-xs text-[var(--fg-subtle)] hover:text-[var(--fg-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]">
            <ChevronDown
              className="h-3 w-3 transition-transform group-open:rotate-180"
              aria-hidden="true"
            />
            How readiness is calculated
          </summary>
          <p className="mt-2 max-w-prose text-xs leading-relaxed text-[var(--fg-muted)]">
            {readiness.explanation}
          </p>
        </details>
      </div>
    </li>
  );
}

/** Said once, under the list — not on every card. */
export function ReadinessDisclaimer() {
  return (
    <p className="mt-3 text-xs leading-relaxed text-[var(--fg-subtle)]">
      Readiness reflects the evidence and controls available in Veyntra. It is not a legal
      certification.
    </p>
  );
}
