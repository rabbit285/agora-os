"use client";

import { ClipboardCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { DpiaWorkflow } from "@/lib/types";

/** What the screening counted, and what a person decided about it.
 *
 * Two claims by two parties, shown as two rows. Veyntra applied Article
 * 35(3) and the EDPB's nine criteria to reported answers — arithmetic
 * over a published rule. Whether a DPIA is required is a decision
 * somebody made. A panel showing only the first would imply the product
 * made the call.
 */
const OUTCOME: Record<string, string> = {
  required: "A DPIA appears to be required",
  recommended: "A DPIA may be required",
  not_indicated: "A DPIA does not currently appear necessary",
};

const DECISION: Record<string, string> = {
  required: "DPIA required",
  not_required: "DPIA not required",
};

function when(value: string | null) {
  if (!value) return null;
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function DpiaScreeningPanel({ workflow }: { workflow: DpiaWorkflow }) {
  if (!workflow.screening_outcome) return null;

  const decided = workflow.screening_decision;
  const screenedOn = when(workflow.screened_at);
  const decidedOn = when(workflow.screening_decided_at);

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 font-medium text-[var(--fg-default)]">
            <ClipboardCheck className="h-4 w-4" aria-hidden="true" />
            Screening
          </h2>
          {screenedOn && (
            <span className="text-xs text-[var(--fg-subtle)]">
              Screened {screenedOn}
            </span>
          )}
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
              Veyntra&apos;s recommendation
            </p>
            <p className="text-sm text-[var(--fg-default)]">
              {OUTCOME[workflow.screening_outcome] ?? workflow.screening_outcome}
            </p>
            {workflow.screening_rationale_text && (
              <p className="mt-1 text-xs leading-relaxed text-[var(--fg-muted)]">
                {workflow.screening_rationale_text}
              </p>
            )}
            {workflow.screening_criteria_met.length > 0 && (
              <ul className="mt-2 flex list-disc flex-col gap-0.5 pl-4">
                {workflow.screening_criteria_met.map((criterion) => (
                  <li key={criterion} className="text-xs text-[var(--fg-muted)]">
                    {criterion}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <p className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
              Decision
            </p>
            {decided ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={decided === "required" ? "secondary" : "success"}>
                  {DECISION[decided] ?? decided}
                </Badge>
                {decidedOn && (
                  <span className="text-xs text-[var(--fg-subtle)]">
                    Confirmed {decidedOn}
                  </span>
                )}
              </div>
            ) : (
              // The screening is a count, not a conclusion. Saying so
              // here is the difference between a product that recommends
              // and one that appears to have decided.
              <p className="text-sm text-[var(--warning-700)]">
                Not yet decided. Veyntra counted the criteria; whether a DPIA
                is required is your call.
              </p>
            )}
            {workflow.screening_decision_rationale && (
              <p className="mt-1 text-xs leading-relaxed text-[var(--fg-muted)]">
                {workflow.screening_decision_rationale}
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
