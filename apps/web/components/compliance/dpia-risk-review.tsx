"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Lightbulb, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { DpiaSuggestedRisk, DpiaWorkflow } from "@/lib/types";

/** Risks Veyntra proposes, and the decision each is waiting on.
 *
 * The boundary this screen exists to hold: a suggestion is not a risk.
 * Nothing here counts toward the inherent or residual rating. Approving
 * one is what creates the risk — with a likelihood and an impact the
 * reviewer chooses, because a rating Veyntra supplied would flow
 * straight into a risk level nobody decided.
 */
const LEVELS = ["low", "medium", "high"] as const;
type Level = (typeof LEVELS)[number];

const SELECT_CLASS =
  "h-8 rounded-md border border-[var(--border-strong)] bg-[var(--bg-default)] px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

function Proposal({
  dpiaId,
  suggestion,
}: {
  dpiaId: string;
  suggestion: DpiaSuggestedRisk;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState<"approve" | "dismiss" | null>(null);
  const [likelihood, setLikelihood] = useState<Level>("medium");
  const [impact, setImpact] = useState<Level>("medium");
  const [title, setTitle] = useState(suggestion.title);
  const [subjects, setSubjects] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["compliance"] });

  const decide = useMutation({
    mutationFn: (action: "approve" | "dismiss") =>
      apiFetch(
        `/api/v1/compliance/dpias/${dpiaId}/risk-suggestions/${suggestion.id}/${action}`,
        {
          method: "POST",
          body:
            action === "approve"
              ? {
                  likelihood,
                  impact,
                  title: title.trim() || undefined,
                  affected_data_subjects: subjects.trim() || undefined,
                }
              : { reason },
        },
      ),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setOpen(null);
      await refresh();
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was recorded.",
      ),
  });

  const settled = suggestion.status !== "suggested";

  return (
    <li className="rounded-[var(--radius-md)] border border-[var(--border-default)] p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm font-medium text-[var(--fg-default)]">
          {suggestion.title}
        </p>
        <Badge
          variant={
            suggestion.status === "approved"
              ? "success"
              : suggestion.status === "dismissed"
                ? "secondary"
                : "warning"
          }
        >
          {suggestion.status === "suggested"
            ? "Needs review"
            : suggestion.status}
        </Badge>
      </div>
      <p className="mt-1 text-sm leading-relaxed text-[var(--fg-muted)]">
        {suggestion.description}
      </p>
      {/* The fact it was read from, so a reviewer can check rather than
          trust. */}
      <p className="mt-1 text-xs text-[var(--fg-subtle)]">
        Why Veyntra raised this: {suggestion.reason}
      </p>
      {suggestion.suggested_safeguards && !settled && (
        <p className="mt-1 text-xs text-[var(--fg-subtle)]">
          {suggestion.suggested_safeguards}
        </p>
      )}

      {!settled && open === null && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => setOpen("approve")}>
            <Check className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            Approve as a risk
          </Button>
          <Button size="sm" variant="outline" onClick={() => setOpen("dismiss")}>
            <X className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            Dismiss
          </Button>
        </div>
      )}

      {open === "approve" && (
        <div className="mt-3 flex flex-col gap-2 rounded-[var(--radius-md)] bg-[var(--bg-subtle)] p-3">
          <label className="text-xs text-[var(--fg-muted)]" htmlFor={`t-${suggestion.id}`}>
            Risk (edit if the wording is not right)
          </label>
          <Input
            id={`t-${suggestion.id}`}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <label className="text-xs text-[var(--fg-muted)]" htmlFor={`s-${suggestion.id}`}>
            Who it affects
          </label>
          <Input
            id={`s-${suggestion.id}`}
            placeholder="e.g. Customers contacting support"
            value={subjects}
            onChange={(e) => setSubjects(e.target.value)}
          />
          {/* No default that means anything. This is the moment the DPIA
              acquires a risk position, and there is no honest value to
              fall back on. */}
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-xs text-[var(--fg-muted)]">
              Likelihood{" "}
              <select
                aria-label="Likelihood"
                className={SELECT_CLASS}
                value={likelihood}
                onChange={(e) => setLikelihood(e.target.value as Level)}
              >
                {LEVELS.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-[var(--fg-muted)]">
              Impact{" "}
              <select
                aria-label="Impact"
                className={SELECT_CLASS}
                value={impact}
                onChange={(e) => setImpact(e.target.value as Level)}
              >
                {LEVELS.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={decide.isPending}
              onClick={() => decide.mutate("approve")}
            >
              {decide.isPending ? "Recording…" : "Add to the risk register"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {open === "dismiss" && (
        <div className="mt-3 flex flex-col gap-2 rounded-[var(--radius-md)] bg-[var(--bg-subtle)] p-3">
          <label className="text-xs text-[var(--fg-muted)]" htmlFor={`d-${suggestion.id}`}>
            {/* Required for the same reason "DPIA not required" needs
                one: an unexplained dismissal is indistinguishable from
                nobody having looked. */}
            Why this is not a risk here (required)
          </label>
          <Input
            id={`d-${suggestion.id}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!reason.trim() || decide.isPending}
              onClick={() => decide.mutate("dismiss")}
            >
              {decide.isPending ? "Recording…" : "Dismiss with this reason"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-2 text-xs text-[var(--fg-danger)]">
          {error}
        </p>
      )}
    </li>
  );
}

export function DpiaRiskReview({ workflow }: { workflow: DpiaWorkflow }) {
  const proposals = workflow.suggested_risks;
  if (proposals.length === 0) return null;

  const pending = proposals.filter((row) => row.status === "suggested");
  const approved = proposals.filter((row) => row.status === "approved").length;
  const dismissed = proposals.filter((row) => row.status === "dismissed").length;

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 font-medium text-[var(--fg-default)]">
            <Lightbulb className="h-4 w-4" aria-hidden="true" />
            Risks Veyntra suggests
          </h2>
          <span className="text-xs text-[var(--fg-subtle)]">
            {pending.length} need review · {approved} approved · {dismissed}{" "}
            dismissed
          </span>
        </div>
        <p className="mb-3 text-xs leading-relaxed text-[var(--fg-subtle)]">
          Read from what your records already say. None of these counts
          toward the risk rating until you approve it — a suggestion is a
          proposal, and the risk register is your statement of what
          threatens data subjects.
        </p>
        <ul className="flex flex-col gap-2">
          {proposals.map((suggestion) => (
            <Proposal
              key={suggestion.id ?? suggestion.title}
              dpiaId={workflow.id}
              suggestion={suggestion}
            />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
