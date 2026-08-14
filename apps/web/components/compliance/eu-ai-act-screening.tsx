"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Ban, Info, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { AIAssessmentDetail, IndicatorCatalog } from "@/lib/types";

/** How each tier is presented. "Unacceptable" is deliberately not styled
 * as the top of a risk scale — Article 5 is a prohibition, and showing it
 * in the same visual language as "high" invites someone to try to
 * mitigate it. */
const TIER: Record<
  string,
  { label: string; variant: "success" | "secondary" | "destructive"; icon: typeof Info }
> = {
  minimal: { label: "Minimal risk", variant: "success", icon: ShieldCheck },
  limited: { label: "Limited risk — transparency duties", variant: "secondary", icon: Info },
  high: { label: "High risk (Annex III)", variant: "destructive", icon: AlertTriangle },
  unacceptable: { label: "Prohibited practice (Article 5)", variant: "destructive", icon: Ban },
};

const GROUP_LABEL: Record<string, string> = {
  prohibited: "Prohibited practices (Article 5)",
  high_risk: "High-risk uses (Annex III)",
  transparency: "Transparency triggers (Chapter IV)",
};

export function EuAiActScreening({
  aiSystemId,
  latest,
}: {
  aiSystemId: string;
  latest: AIAssessmentDetail | undefined;
}) {
  const queryClient = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const [open, setOpen] = useState(false);

  const { data: catalog } = useQuery<IndicatorCatalog>({
    queryKey: ["compliance", "indicator-catalog"],
    queryFn: () => apiFetch<IndicatorCatalog>("/api/v1/compliance/ai-systems/indicator-catalog"),
  });

  const screen = useMutation({
    mutationFn: () =>
      apiFetch<AIAssessmentDetail>(
        `/api/v1/compliance/ai-systems/${aiSystemId}/eu-ai-act-screening`,
        { method: "POST", body: { indicators: answers } },
      ),
    onSuccess: () => {
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["compliance", "ai-systems", aiSystemId] });
    },
  });

  const findings = latest?.findings;
  const tier = findings?.classification ? TIER[findings.classification] : null;
  const answeredCount = Object.keys(answers).length;
  const totalIndicators = catalog
    ? Object.keys(catalog.prohibited).length +
      Object.keys(catalog.high_risk).length +
      Object.keys(catalog.transparency).length
    : 0;

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-medium text-[var(--fg-default)]">EU AI Act screening</h2>
          <Button size="sm" variant={latest ? "outline" : "default"} onClick={() => setOpen(!open)}>
            {open ? "Cancel" : latest ? "Re-screen" : "Assess applicability"}
          </Button>
        </div>

        {!latest && !open && (
          <p className="text-sm text-[var(--fg-muted)]">
            This system has not been screened. The classification comes from the Act&rsquo;s own
            indicators — what the system does — not from an inference about it.
          </p>
        )}

        {latest && findings && (
          <div className="mb-4">
            {tier && (
              <Badge variant={tier.variant} className="gap-1">
                <tier.icon className="h-3 w-3" aria-hidden="true" />
                {tier.label}
              </Badge>
            )}
            <p className="mt-3 text-sm leading-relaxed text-[var(--fg-muted)]">
              {findings.rationale}
            </p>

            {findings.facts_relied_on && findings.facts_relied_on.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-[var(--fg-subtle)]">
                  Facts relied on
                </p>
                <ul className="mt-1 list-disc pl-5 text-sm text-[var(--fg-muted)]">
                  {findings.facts_relied_on.map((fact) => (
                    <li key={fact}>{fact}</li>
                  ))}
                </ul>
              </div>
            )}

            {findings.uncertainties && findings.uncertainties.length > 0 && (
              <div className="mt-3 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-[var(--warning-700)]">
                  Uncertainty
                </p>
                {findings.uncertainties.map((note) => (
                  <p key={note} className="mt-1 text-sm leading-relaxed text-[var(--warning-700)]">
                    {note}
                  </p>
                ))}
              </div>
            )}

            {findings.requires_human_review && (
              <p className="mt-3 flex items-start gap-2 text-sm text-[var(--fg-muted)]">
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-700)]"
                  aria-hidden="true"
                />
                Classifying a system under the EU AI Act is a legal judgement. This screening
                prepares that judgement — it does not replace it. Have legal or your DPO confirm
                before relying on it.
              </p>
            )}

            <p className="mt-3 text-xs text-[var(--fg-subtle)]">
              Screened {new Date(latest.created_at).toLocaleString()}
              {findings.indicators_unanswered && findings.indicators_unanswered.length > 0 && (
                <> · {findings.indicators_unanswered.length} indicator(s) unanswered</>
              )}
            </p>
          </div>
        )}

        {open && catalog && (
          <div className="mt-4 border-t border-[var(--border-default)] pt-4">
            <p className="mb-4 text-sm text-[var(--fg-muted)]">
              Answer what this system does. Anything left blank is reported as unanswered rather
              than assumed to be &ldquo;no&rdquo;.
            </p>

            {(["prohibited", "high_risk", "transparency"] as const).map((group) => (
              <fieldset key={group} className="mb-5">
                <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--fg-subtle)]">
                  {GROUP_LABEL[group]}
                </legend>
                <div className="flex flex-col gap-2">
                  {Object.entries(catalog[group]).map(([key, label]) => (
                    <label key={key} className="flex items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={answers[key] === true}
                        onChange={(e) =>
                          setAnswers((prev) => ({ ...prev, [key]: e.target.checked }))
                        }
                      />
                      <span className="text-[var(--fg-muted)]">{label}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
            ))}

            {screen.error && (
              <p className="mb-3 text-sm text-[var(--critical-600)]">
                {screen.error instanceof ApiError ? screen.error.message : "Screening failed."}
              </p>
            )}

            <div className="flex items-center gap-3">
              <Button disabled={screen.isPending} onClick={() => screen.mutate()}>
                {screen.isPending ? "Screening…" : "Run screening"}
              </Button>
              <span className="text-xs text-[var(--fg-subtle)]">
                {answeredCount} of {totalIndicators} indicators answered
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
