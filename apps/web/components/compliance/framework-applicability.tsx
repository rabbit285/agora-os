"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Scale } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { FrameworkRecommendations } from "@/lib/types";

/** Which frameworks apply to this organization, and why.
 *
 * The question a 60-person software company cannot answer on its own,
 * and the reason the reasons matter more than the verdict: every
 * recommendation restates a fact the customer declared, so disagreeing
 * with one means changing a fact rather than arguing with a model.
 *
 * Deliberately never says "you are compliant" or "this does not apply to
 * you" as a settled conclusion — applicability is scope, not compliance,
 * and where the answer turns on something the product does not hold it
 * is flagged for legal review instead of guessed.
 */

const FACTS: { key: string; label: string; hint?: string }[] = [
  { key: "sells_to_eu_customers", label: "We have customers in the EU" },
  { key: "operates_in_eu", label: "We have an entity or staff in the EU" },
  { key: "processes_personal_data", label: "We process personal data" },
  {
    key: "processes_special_category_data",
    label: "Including special category data",
    hint: "Health, biometrics, religion, political opinions, sexual orientation",
  },
  { key: "uses_third_party_ai", label: "We use third-party AI (OpenAI, Claude, Copilot…)" },
  { key: "builds_ai_features", label: "We build AI features into our product" },
  {
    key: "is_data_processor",
    label: "We process data on behalf of our customers",
    hint: "True for most B2B SaaS",
  },
  { key: "sells_to_enterprise", label: "We sell to enterprise customers" },
];

const APPLICABILITY_LABEL: Record<string, string> = {
  required: "Likely applicable",
  likely: "Likely applicable — requires review",
  recommended: "Recommended",
  not_indicated: "Not currently indicated",
};

const APPLICABILITY_VARIANT: Record<string, "success" | "outline" | "secondary"> = {
  required: "success",
  likely: "outline",
  recommended: "outline",
  not_indicated: "secondary",
};

export function FrameworkApplicability() {
  const queryClient = useQueryClient();
  const [facts, setFacts] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState(false);

  const { data } = useQuery<FrameworkRecommendations>({
    queryKey: ["compliance", "framework-recommendations"],
    queryFn: () =>
      apiFetch<FrameworkRecommendations>("/api/v1/compliance/framework-recommendations"),
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["compliance", "framework-recommendations"] });
    void queryClient.invalidateQueries({ queryKey: ["compliance", "overview"] });
    void queryClient.invalidateQueries({ queryKey: ["compliance", "controls"] });
    void queryClient.invalidateQueries({ queryKey: ["compliance", "frameworks", "activations"] });
  };

  const declare = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/compliance/company-facts", { method: "PUT", body: facts }),
    onSuccess: () => {
      setExpanded(false);
      refresh();
    },
  });

  const adopt = useMutation({
    mutationFn: (keys: string[]) =>
      apiFetch("/api/v1/compliance/frameworks/adopt-recommended", {
        method: "POST",
        body: { framework_keys: keys },
      }),
    onSuccess: refresh,
  });

  const error = declare.error ?? adopt.error;
  const indicated = (data?.recommendations ?? []).filter(
    (r) => r.applicability !== "not_indicated",
  );
  const adoptable = indicated.filter((r) => !r.already_active).map((r) => r.framework_key);

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        What applies to us
      </h2>

      {/* Before anything is declared this must read as "we have not asked
          yet", never as "nothing applies to you" — the one wrong answer. */}
      {!data?.facts_declared && !expanded && (
        <Card className="mb-4">
          <CardContent className="pt-6">
            <p className="mb-3 text-sm leading-relaxed text-[var(--fg-muted)]">
              Tell Veyntra a few things about your company and it will work out which
              frameworks you are held to, and explain why. Nothing is adopted until you say so.
            </p>
            <Button size="sm" onClick={() => setExpanded(true)}>
              Answer eight questions
            </Button>
          </CardContent>
        </Card>
      )}

      {(expanded || (data?.facts_declared && expanded)) && (
        <Card className="mb-4">
          <CardContent className="flex flex-col gap-3 pt-6">
            {FACTS.map((fact) => (
              <label key={fact.key} className="flex items-start gap-2.5 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={facts[fact.key] ?? false}
                  onChange={(e) => setFacts({ ...facts, [fact.key]: e.target.checked })}
                />
                <span>
                  <span className="text-[var(--fg-default)]">{fact.label}</span>
                  {fact.hint && (
                    <span className="block text-xs text-[var(--fg-subtle)]">{fact.hint}</span>
                  )}
                </span>
              </label>
            ))}
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={declare.isPending}
                onClick={() => declare.mutate()}
              >
                {declare.isPending ? "Working it out…" : "Show what applies"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setExpanded(false)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {error && (
        <p className="mb-3 text-sm text-[var(--critical-600)]">
          {error instanceof ApiError ? error.message : (error as Error).message}
        </p>
      )}

      {data?.facts_declared && (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            {adoptable.length > 0 && (
              <Button size="sm" disabled={adopt.isPending} onClick={() => adopt.mutate(adoptable)}>
                <Check className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                Adopt {adoptable.length} framework{adoptable.length === 1 ? "" : "s"}
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setExpanded(true)}>
              Change my answers
            </Button>
          </div>

          <div className="flex flex-col gap-3">
            {indicated.map((recommendation) => (
              <Card key={recommendation.framework_key}>
                <CardContent className="pt-6">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium text-[var(--fg-default)]">
                      {recommendation.framework_name ?? recommendation.framework_key}
                    </span>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {recommendation.already_active && (
                        <Badge variant="secondary">Adopted</Badge>
                      )}
                      <Badge variant={APPLICABILITY_VARIANT[recommendation.applicability]}>
                        {APPLICABILITY_LABEL[recommendation.applicability]}
                      </Badge>
                    </div>
                  </div>

                  {/* The reasons are the product here. A verdict without
                      them cannot be argued with, and applicability is
                      exactly the kind of call a customer must be able to
                      disagree with. */}
                  <ul className="flex flex-col gap-1">
                    {recommendation.reasons.map((reason) => (
                      <li
                        key={reason}
                        className="flex items-start gap-2 text-sm leading-relaxed text-[var(--fg-muted)]"
                      >
                        <Check
                          className="mt-1 h-3 w-3 shrink-0 text-[var(--success-600)]"
                          aria-hidden="true"
                        />
                        {reason}
                      </li>
                    ))}
                  </ul>

                  {recommendation.uncertainties.length > 0 && (
                    <div className="mt-3 flex items-start gap-2 rounded-[var(--radius-md)] bg-[var(--bg-app)] p-3">
                      <AlertTriangle
                        className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--warning-700)]"
                        aria-hidden="true"
                      />
                      <div className="text-sm leading-relaxed text-[var(--fg-muted)]">
                        {recommendation.uncertainties.map((note) => (
                          <p key={note}>{note}</p>
                        ))}
                      </div>
                    </div>
                  )}

                  {recommendation.requires_legal_review && (
                    <p className="mt-2 flex items-center gap-1.5 text-xs text-[var(--fg-subtle)]">
                      <Scale className="h-3 w-3" aria-hidden="true" />
                      Confirm with counsel before treating this as settled.
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>

          <p className="mt-3 text-xs leading-relaxed text-[var(--fg-subtle)]">
            Applicability is computed from the facts you declared, not by a language model.
            It says a framework is in scope — not that you meet it, which is what the
            assessment measures from your evidence.
          </p>
        </>
      )}
    </div>
  );
}
