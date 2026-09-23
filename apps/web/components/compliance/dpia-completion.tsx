"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, Lock, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { DpiaWorkflow } from "@/lib/types";

/** Completing a DPIA, and what a completed one says afterwards.
 *
 * Completion is a gate rather than a status change: everything
 * outstanding is listed together, so the work can be finished in one
 * pass instead of discovering the next missing thing on each press.
 *
 * Once complete, the assessment is frozen. When the processing
 * underneath it moves — a vendor changing country, a new data category —
 * this says so and asks for a reassessment. It never edits what was
 * concluded, because a record that quietly absorbed a change would be
 * claiming somebody assessed something they never saw.
 */
export function DpiaCompletion({ workflow }: { workflow: DpiaWorkflow }) {
  const queryClient = useQueryClient();

  const complete = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/dpias/${workflow.id}/complete`, {
        method: "POST",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance"] }),
  });

  if (workflow.status === "completed") {
    return (
      <Card className="mb-6">
        <CardContent className="pt-6">
          <h2 className="mb-2 flex items-center gap-2 font-medium text-[var(--fg-default)]">
            <Lock className="h-4 w-4" aria-hidden="true" />
            Completed
          </h2>
          <p className="text-sm text-[var(--fg-muted)]">
            Completed
            {workflow.completed_at &&
              ` on ${new Date(workflow.completed_at).toLocaleDateString()}`}
            {workflow.completed_by_name && ` by ${workflow.completed_by_name}`}.
            The assessment above is the record as it stood then and is no
            longer editable.
          </p>

          {workflow.review_reason && (
            <div className="mt-3 flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-3 text-sm text-[var(--warning-700)]">
              <RefreshCw className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                <strong className="font-medium">Reassessment recommended.</strong>{" "}
                {workflow.review_reason} The completed record above is
                unchanged — this asks whether it still holds.
              </span>
            </div>
          )}
        </CardContent>
      </Card>
    );
  }

  if (workflow.status === "screening" || workflow.status === "not_required") {
    return null;
  }

  const blockers = workflow.completion_blockers;

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-medium text-[var(--fg-default)]">
            Complete this DPIA
          </h2>
          <Button
            size="sm"
            disabled={!workflow.can_complete || complete.isPending}
            onClick={() => complete.mutate()}
          >
            {complete.isPending ? "Completing…" : "Complete DPIA"}
          </Button>
        </div>

        {blockers.length > 0 ? (
          <div>
            <p className="mb-2 flex items-center gap-2 text-sm text-[var(--fg-default)]">
              <CircleAlert className="h-4 w-4 text-[var(--warning-700)]" aria-hidden="true" />
              Cannot complete DPIA. Remaining:
            </p>
            <ul className="flex list-disc flex-col gap-1 pl-5">
              {blockers.map((blocker) => (
                <li key={blocker.code} className="text-sm text-[var(--fg-muted)]">
                  {blocker.message}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-sm text-[var(--fg-muted)]">
            Everything Article 35(7) requires is recorded and reviewed.
            Completing freezes this assessment as an auditable record of what
            was decided.
          </p>
        )}

        {complete.error && (
          <p role="alert" className="mt-3 text-sm text-[var(--fg-danger)]">
            {complete.error instanceof ApiError
              ? complete.error.message
              : "Could not complete this DPIA."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
