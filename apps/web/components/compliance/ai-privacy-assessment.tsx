"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { AIAssessmentDetail, IndicatorCatalog } from "@/lib/types";

/** The privacy side of an AI system review.
 *
 * Unanswered questions are shown rather than hidden. "No transfer takes
 * place" and "nobody has checked whether a transfer takes place" are
 * different answers, and an assessment that quietly omits the second
 * reads as complete when it is not — which is precisely the thing a DPO
 * is relying on this screen to tell them.
 */
export function AiPrivacyAssessment({
  aiSystemId,
  latest,
}: {
  aiSystemId: string;
  latest: AIAssessmentDetail | undefined;
}) {
  const queryClient = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [open, setOpen] = useState(false);

  const { data: catalog } = useQuery<IndicatorCatalog>({
    queryKey: ["compliance", "indicator-catalog"],
    queryFn: () => apiFetch<IndicatorCatalog>("/api/v1/compliance/ai-systems/indicator-catalog"),
  });

  const assess = useMutation({
    mutationFn: () =>
      apiFetch<AIAssessmentDetail>(
        `/api/v1/compliance/ai-systems/${aiSystemId}/privacy-assessment`,
        { method: "POST", body: { answers } },
      ),
    onSuccess: () => {
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["compliance", "ai-systems", aiSystemId] });
    },
  });

  const findings = latest?.findings;
  const questions = catalog?.privacy_questions ?? {};

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-medium text-[var(--fg-default)]">Privacy assessment</h2>
          <Button size="sm" variant={latest ? "outline" : "default"} onClick={() => setOpen(!open)}>
            {open ? "Cancel" : latest ? "Reassess" : "Run privacy assessment"}
          </Button>
        </div>

        {!latest && !open && (
          <p className="text-sm text-[var(--fg-muted)]">
            No privacy assessment has been recorded for this system.
          </p>
        )}

        {latest && findings && (
          <div className="mb-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={findings.unanswered?.length ? "secondary" : "success"}>
                {findings.unanswered?.length
                  ? `${findings.unanswered.length} question(s) unanswered`
                  : "All questions answered"}
              </Badge>
              {findings.dpia_indicated && <Badge variant="destructive">DPIA indicated</Badge>}
            </div>

            {findings.answers && Object.keys(findings.answers).length > 0 && (
              <dl className="mt-4 flex flex-col gap-3">
                {Object.entries(findings.answers).map(([key, answer]) => (
                  <div key={key}>
                    <dt className="text-xs font-medium text-[var(--fg-subtle)]">
                      {questions[key] ?? key}
                    </dt>
                    <dd className="text-sm text-[var(--fg-muted)]">{answer}</dd>
                  </div>
                ))}
              </dl>
            )}

            {findings.unanswered && findings.unanswered.length > 0 && (
              <div className="mt-4 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-3">
                <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--warning-700)]">
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                  Not yet answered
                </p>
                <ul className="mt-1 list-disc pl-5 text-sm text-[var(--warning-700)]">
                  {findings.unanswered.map((key) => (
                    <li key={key}>{questions[key] ?? key}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {open && catalog && (
          <div className="mt-4 flex flex-col gap-3 border-t border-[var(--border-default)] pt-4">
            {Object.entries(questions).map(([key, question]) => (
              <label key={key} className="flex flex-col gap-1">
                <span className="text-sm text-[var(--fg-default)]">{question}</span>
                <textarea
                  rows={2}
                  className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 text-sm text-[var(--fg-default)] placeholder:text-[var(--fg-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                  placeholder="Leave blank if not yet established"
                  value={answers[key] ?? ""}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [key]: e.target.value }))}
                />
              </label>
            ))}

            {assess.error && (
              <p className="text-sm text-[var(--critical-600)]">
                {assess.error instanceof ApiError ? assess.error.message : "Assessment failed."}
              </p>
            )}

            <div>
              <Button disabled={assess.isPending} onClick={() => assess.mutate()}>
                {assess.isPending ? "Saving…" : "Save assessment"}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
