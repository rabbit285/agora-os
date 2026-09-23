"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Circle, Search, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  DsarDiscoveredItem,
  DsarDiscoveryPlan,
  DsarReviewDecision,
  DsarSearchState,
} from "@/lib/types";

/** The five states, and how each one reads.
 *
 * The distinction the whole panel exists for: "searched — no records" is
 * evidence, "not searched" and "manual follow-up" are the absence of it.
 * A single count collapsed those into one number, and somebody signing a
 * response could not tell them apart.
 */
const STATES: Record<DsarSearchState, { label: string; tone: string; evidence: boolean }> = {
  searched_found: {
    label: "Searched — records found",
    tone: "text-[var(--fg-default)]",
    evidence: true,
  },
  searched_none: {
    label: "Searched — no records found",
    tone: "text-[var(--success-700)]",
    evidence: true,
  },
  not_searched: { label: "Not searched", tone: "text-[var(--fg-subtle)]", evidence: false },
  search_failed: { label: "Search failed", tone: "text-[var(--critical-600)]", evidence: false },
  manual_follow_up: {
    label: "Manual follow-up required",
    tone: "text-[var(--warning-600)]",
    evidence: false,
  },
  // A processor holds it; asking them is the only route.
  processor_follow_up: {
    label: "Processor follow-up required",
    tone: "text-[var(--warning-600)]",
    evidence: false,
  },
  // No integration exists. Distinct from manual follow-up: this one is
  // fixable by connecting the system.
  not_connected: {
    label: "Not connected — not searched",
    tone: "text-[var(--fg-subtle)]",
    evidence: false,
  },
};

const DECISIONS: { value: DsarReviewDecision; label: string }[] = [
  { value: "include", label: "Include" },
  { value: "exclude", label: "Exclude" },
  { value: "redact", label: "Redact" },
  { value: "needs_review", label: "Needs review" },
];

/** Discovery, and the review of what it found.
 *
 * Two rules are visible in the markup. The search button stays disabled
 * until the scope is confirmed, because discovery obeys the scope
 * exactly. And a source Veyntra could not reach is rendered under its
 * own state with its own explanation, never as a zero — a case worker
 * reading "0" signs a response saying nothing was found, for a system
 * nobody looked in.
 */
export function DsarDiscoveryPanel({
  dsarId,
  canSearch,
  blockedReason,
}: {
  dsarId: string;
  canSearch: boolean;
  blockedReason: string | null;
}) {
  const queryClient = useQueryClient();
  const [reasons, setReasons] = useState<Record<string, string>>({});

  const { data: items } = useQuery<DsarDiscoveredItem[]>({
    queryKey: ["compliance", "dsars", dsarId, "discovered"],
    queryFn: () =>
      apiFetch<DsarDiscoveredItem[]>(`/api/v1/compliance/dsars/${dsarId}/discovered`),
  });

  const { data: plan } = useQuery<DsarDiscoveryPlan>({
    queryKey: ["compliance", "dsars", dsarId, "discovery-plan"],
    queryFn: () =>
      apiFetch<DsarDiscoveryPlan>(`/api/v1/compliance/dsars/${dsarId}/discovery-plan`),
    enabled: canSearch,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["compliance", "dsars", dsarId] });

  const search = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/dsars/${dsarId}/discovery/run`, { method: "POST" }),
    onSuccess: invalidate,
  });

  const review = useMutation({
    mutationFn: ({ itemId, decision }: { itemId: string; decision: DsarReviewDecision }) =>
      apiFetch(`/api/v1/compliance/dsars/${dsarId}/discovered/${itemId}`, {
        method: "PATCH",
        body: { review_decision: decision, review_reason: reasons[itemId] || undefined },
      }),
    onSuccess: invalidate,
  });

  const hasRun = (items?.length ?? 0) > 0;
  const error = search.error ?? review.error;

  return (
    <Card className="mb-6" id="discovery">
      <CardContent className="pt-6">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-medium text-[var(--fg-default)]">Data discovery</h2>
          <Button
            size="sm"
            variant="outline"
            disabled={!canSearch || search.isPending}
            onClick={() => search.mutate()}
          >
            <Search className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            {search.isPending
              ? "Searching…"
              : hasRun
                ? "Search again"
                : "Search confirmed data sources"}
          </Button>
        </div>

        {!canSearch && (
          <p className="mb-3 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] p-3 text-sm text-[var(--fg-muted)]">
            {blockedReason ??
              "Verify the requester's identity and confirm the search scope before searching."}
          </p>
        )}

        {canSearch && plan && !hasRun && (
          <div
            className="mb-3 rounded-[var(--radius-md)] border border-[var(--border-default)] p-3 text-sm"
            data-testid="discovery-plan"
          >
            <p className="font-medium text-[var(--fg-default)]">Discovery plan</p>
            <p className="mt-1 text-[var(--fg-muted)]">
              {plan.total} source(s) in scope · {plan.connected} Veyntra will search ·{" "}
              {plan.manual} need manual follow-up
              {plan.excluded > 0 && ` · ${plan.excluded} excluded`}
            </p>
            {plan.manual_sources.length > 0 && (
              <p className="mt-1 text-xs text-[var(--fg-subtle)]">
                Veyntra cannot search {plan.manual_sources.join(", ")} — it will raise a
                follow-up task rather than reporting them as empty.
              </p>
            )}
          </div>
        )}

        {error && (
          <p className="mb-3 text-sm text-[var(--critical-600)]">
            {error instanceof ApiError ? error.message : "Something went wrong."}
          </p>
        )}

        {!hasRun ? (
          <p className="text-sm text-[var(--fg-muted)]">
            No search has been run for this request yet.
          </p>
        ) : (
          <ul className="space-y-2">
            {items!.map((item) => {
              const state = STATES[item.search_state];
              const needsDecision = item.review_decision === "needs_review";
              return (
                <li
                  key={item.id}
                  className="rounded-[var(--radius-md)] border border-[var(--border-default)] p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    {state.evidence ? (
                      <CheckCircle2
                        className="h-4 w-4 text-[var(--success-600)]"
                        aria-hidden="true"
                      />
                    ) : item.search_state === "search_failed" ? (
                      <XCircle className="h-4 w-4 text-[var(--critical-600)]" aria-hidden="true" />
                    ) : (
                      <Circle className="h-4 w-4 text-[var(--fg-subtle)]" aria-hidden="true" />
                    )}
                    <span className="text-sm font-medium text-[var(--fg-default)]">
                      {item.source_name}
                    </span>
                    <span className={`text-xs ${state.tone}`}>{state.label}</span>
                    {item.search_state === "searched_found" && (
                      <Badge variant="outline">{item.matches} record(s)</Badge>
                    )}
                    {needsDecision && <Badge variant="outline">Needs review</Badge>}
                  </div>

                  {item.state_detail && (
                    <p className="mt-1 text-xs leading-relaxed text-[var(--fg-muted)]">
                      {item.state_detail}
                    </p>
                  )}

                  {item.sensitivity_flags.map((flag) => (
                    <p
                      key={flag}
                      className="mt-1 flex gap-1.5 text-xs leading-relaxed text-[var(--warning-700)]"
                    >
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
                      {flag}
                    </p>
                  ))}

                  {item.review_reason && !needsDecision && (
                    <p className="mt-1 text-xs text-[var(--fg-subtle)]">
                      {DECISIONS.find((d) => d.value === item.review_decision)?.label}:{" "}
                      {item.review_reason}
                    </p>
                  )}

                  {item.search_state !== "not_searched" && (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {DECISIONS.filter((d) => d.value !== "needs_review").map((decision) => (
                        <Button
                          key={decision.value}
                          size="sm"
                          variant={
                            item.review_decision === decision.value ? "default" : "outline"
                          }
                          disabled={review.isPending}
                          onClick={() =>
                            review.mutate({ itemId: item.id, decision: decision.value })
                          }
                        >
                          {decision.label}
                        </Button>
                      ))}
                      <Input
                        className="h-8 max-w-xs"
                        placeholder="Reason (required to exclude or redact)"
                        value={reasons[item.id] ?? ""}
                        onChange={(event) =>
                          setReasons((current) => ({
                            ...current,
                            [item.id]: event.target.value,
                          }))
                        }
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
