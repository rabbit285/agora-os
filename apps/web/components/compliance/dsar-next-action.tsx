"use client";

import { ArrowRight, CheckCircle2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { DsarWorkflowState } from "@/lib/types";

/** The phases, in the order a request moves through them.
 *
 * "Blocked" is absent on purpose: it is a condition on a phase, not a
 * step between two of them, and putting it in the line would suggest a
 * request travels through it. */
const PHASES = [
  { key: "received", label: "Received" },
  { key: "identity_verification", label: "Identity" },
  { key: "scope_review", label: "Scope" },
  { key: "discovery", label: "Discovery" },
  { key: "response_review", label: "Review" },
  { key: "ready_to_respond", label: "Ready" },
  { key: "completed", label: "Completed" },
];

/** §15: the single next thing to do, at the top of the page.
 *
 * The old page showed a status that read "in progress" — true of
 * everything between logging a request and sending it, which is exactly
 * the span where somebody needs to know what to do. This says the one
 * action, and the deadline beside it, because those are the two facts
 * that decide what happens next.
 */
export function DsarNextAction({
  workflow,
  dueAt,
  daysRemaining,
  overdue,
}: {
  workflow: DsarWorkflowState;
  dueAt: string;
  daysRemaining: number | null;
  overdue: boolean;
}) {
  const currentIndex = PHASES.findIndex((phase) => phase.key === workflow.phase);
  const blocked = workflow.phase === "blocked";
  const done = workflow.phase === "completed";

  return (
    <Card
      className={`mb-6 ${blocked ? "border-[var(--critical-300)] bg-[var(--critical-50)]" : ""}`}
    >
      <CardContent className="pt-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
              {blocked ? "Blocked" : done ? "Complete" : "Next action"}
            </p>
            {workflow.next_action ? (
              <>
                <p className="mt-1 flex items-center gap-2 text-base font-medium text-[var(--fg-default)]">
                  {workflow.next_action.label}
                  <ArrowRight className="h-4 w-4 text-[var(--fg-subtle)]" aria-hidden="true" />
                </p>
                <p className="mt-1 text-sm leading-relaxed text-[var(--fg-muted)]">
                  {workflow.next_action.detail}
                </p>
              </>
            ) : (
              <p className="mt-1 flex items-center gap-2 text-base font-medium text-[var(--fg-default)]">
                <CheckCircle2 className="h-4 w-4 text-[var(--success-600)]" aria-hidden="true" />
                This request is complete.
              </p>
            )}
          </div>

          <div className="text-right">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
              Response due
            </p>
            <p className="mt-1 text-sm text-[var(--fg-default)]">
              {new Date(dueAt).toLocaleDateString(undefined, {
                year: "numeric",
                month: "short",
                day: "numeric",
              })}
            </p>
            {!done && daysRemaining !== null && (
              <p
                className={`text-sm ${
                  overdue
                    ? "text-[var(--critical-600)]"
                    : daysRemaining <= 7
                      ? "text-[var(--warning-600)]"
                      : "text-[var(--fg-muted)]"
                }`}
              >
                {overdue
                  ? `${Math.abs(daysRemaining)} days overdue`
                  : `${daysRemaining} days remaining`}
              </p>
            )}
          </div>
        </div>

        {/* The phase line. Shows where the request is without letting
            anybody drag it somewhere it has not earned. */}
        <ol className="mt-4 flex flex-wrap items-center gap-x-1 gap-y-1">
          {PHASES.map((phase, index) => {
            const reached = currentIndex >= 0 && index <= currentIndex;
            const current = phase.key === workflow.phase;
            return (
              <li key={phase.key} className="flex items-center gap-1">
                <span
                  className={`rounded-full px-2 py-0.5 text-xs ${
                    current
                      ? "bg-[var(--accent-100)] font-medium text-[var(--accent-700)]"
                      : reached
                        ? "text-[var(--fg-muted)]"
                        : "text-[var(--fg-subtle)]"
                  }`}
                >
                  {phase.label}
                </span>
                {index < PHASES.length - 1 && (
                  <span className="text-[var(--fg-subtle)]" aria-hidden="true">
                    ·
                  </span>
                )}
              </li>
            );
          })}
        </ol>

        {workflow.blockers.length > 0 && (
          <ul className="mt-3 space-y-1">
            {workflow.blockers.map((blocker) => (
              <li key={blocker.code} className="text-sm text-[var(--fg-muted)]">
                {blocker.message}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
