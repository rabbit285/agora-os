"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, ShieldQuestion } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { DpiaWorkflow } from "@/lib/types";

/** What the assessment does not know, and the question it raises.
 *
 * Both halves exist to stop the same failure: **absent information
 * turning into a positive conclusion.** A DPIA once completed while
 * reporting "no personal-data categories are recorded" for a
 * medical-leave activity — the record said nothing, and the document
 * read as though there were nothing to say.
 *
 * Veyntra detects; a person decides. The signals below are read out of
 * the processing record and shown with the text they came from, so a
 * reviewer checks the detection rather than trusting it. Whether Article
 * 9 applies, and on what condition, is never concluded here.
 */
export function DpiaContextGaps({
  workflow,
  readOnly,
}: {
  workflow: DpiaWorkflow;
  readOnly: boolean;
}) {
  const queryClient = useQueryClient();
  const [answering, setAnswering] = useState<"confirm" | "rule-out" | null>(null);
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);

  const decide = useMutation({
    mutationFn: (confirmed: boolean) =>
      apiFetch(`/api/v1/compliance/dpias/${workflow.id}/special-category`, {
        method: "POST",
        body: { confirmed, rationale: rationale.trim() || null },
      }),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setAnswering(null);
      setRationale("");
      await queryClient.invalidateQueries({ queryKey: ["compliance"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was recorded.",
      ),
  });

  const gaps = workflow.missing_facts;
  const signals = workflow.special_category_signals;
  const decided = workflow.special_category_confirmed !== null;

  if (gaps.length === 0 && signals.length === 0 && !decided) return null;

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        {gaps.length > 0 && (
          <div className="mb-4">
            <h2 className="mb-1 flex items-center gap-2 font-medium text-[var(--fg-default)]">
              <CircleAlert className="h-4 w-4 text-[var(--warning-700)]" aria-hidden="true" />
              Missing processing context
            </h2>
            <p className="mb-2 text-xs leading-relaxed text-[var(--fg-subtle)]">
              An assessment written against a record this incomplete cannot say
              what it covered. Missing information is not a finding that there
              is nothing to find.
            </p>
            <ul className="flex list-disc flex-col gap-1 pl-5">
              {gaps.map((gap) => (
                <li key={gap.code} className="text-sm text-[var(--fg-muted)]">
                  {gap.message}{" "}
                  <a href={gap.href} className="hover:underline text-[var(--fg-default)]">
                    Review processing activity →
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}

        {(signals.length > 0 || decided) && (
          <div>
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <h2 className="flex items-center gap-2 font-medium text-[var(--fg-default)]">
                <ShieldQuestion className="h-4 w-4" aria-hidden="true" />
                Special-category data
              </h2>
              {decided ? (
                <Badge variant={workflow.special_category_confirmed ? "warning" : "secondary"}>
                  {workflow.special_category_confirmed
                    ? "Confirmed present"
                    : "Not applicable"}
                </Badge>
              ) : (
                <Badge variant="warning">Needs human confirmation</Badge>
              )}
            </div>

            {decided ? (
              <p className="text-sm text-[var(--fg-muted)]">
                {workflow.special_category_rationale}
              </p>
            ) : (
              <>
                <p className="mb-2 text-xs leading-relaxed text-[var(--fg-subtle)]">
                  Veyntra read these hints out of the recorded processing. It
                  does not decide whether Article 9 applies, or on what
                  condition — that is your call, and the record needs it either
                  way.
                </p>
                <ul className="mb-3 flex flex-col gap-1">
                  {signals.map((signal) => (
                    <li key={signal.kind} className="text-sm text-[var(--fg-muted)]">
                      <span className="font-medium text-[var(--fg-default)]">
                        {signal.kind}
                      </span>{" "}
                      — detected in {signal.evidence}
                    </li>
                  ))}
                </ul>

                {!readOnly && answering === null && (
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => setAnswering("confirm")}>
                      Confirm
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setAnswering("rule-out")}
                    >
                      Not applicable — explain
                    </Button>
                  </div>
                )}

                {answering !== null && (
                  <div className="flex flex-col gap-2 rounded-[var(--radius-md)] bg-[var(--bg-subtle)] p-3">
                    <label
                      className="text-xs leading-relaxed text-[var(--fg-muted)]"
                      htmlFor="special-category-rationale"
                    >
                      {answering === "confirm"
                        ? "What special-category data is involved, and where it comes from"
                        : // Required: an unexplained dismissal is
                          // indistinguishable from nobody having looked.
                          "Why the detected signal does not mean special-category data is processed here (required)"}
                    </label>
                    <textarea
                      id="special-category-rationale"
                      rows={3}
                      className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 text-sm text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                      value={rationale}
                      onChange={(e) => setRationale(e.target.value)}
                    />
                    {error && (
                      <p role="alert" className="text-xs text-[var(--fg-danger)]">
                        {error}
                      </p>
                    )}
                    <div className="flex gap-2">
                      <Button size="sm" variant="ghost" onClick={() => setAnswering(null)}>
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        disabled={
                          decide.isPending ||
                          (answering === "rule-out" && !rationale.trim())
                        }
                        onClick={() => decide.mutate(answering === "confirm")}
                      >
                        {decide.isPending
                          ? "Recording…"
                          : answering === "confirm"
                            ? "Confirm special-category data"
                            : "Record as not applicable"}
                      </Button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
