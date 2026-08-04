"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Recommendation } from "@/lib/types";

const RISK_VARIANT: Record<string, "default" | "outline" | "destructive"> = {
  low: "outline",
  medium: "default",
  high: "destructive",
};

// Each category's suggested action deep-links into the module that
// already owns real creation for it, rather than a second miniature
// action-executor living on this page.
const CATEGORY_LINK: Record<string, string> = {
  compliance: "/compliance",
  security: "/security",
  sales: "/sales",
  support: "/support",
  automation: "/automation",
};

function RecommendationCard({ recommendation }: { recommendation: Recommendation }) {
  const queryClient = useQueryClient();

  const dismiss = useMutation({
    mutationFn: () =>
      apiFetch<Recommendation>(`/api/v1/recommendations/${recommendation.id}/dismiss`, {
        method: "POST",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recommendations"] }),
  });

  const action = useMutation({
    mutationFn: () =>
      apiFetch<Recommendation>(`/api/v1/recommendations/${recommendation.id}/action`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      const href = CATEGORY_LINK[recommendation.category];
      if (href) window.location.href = href;
    },
  });

  return (
    <Card className="border-[var(--ai-100)] bg-[var(--ai-50)]">
      <CardContent className="flex flex-col gap-3 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Sparkles className="h-3.5 w-3.5 text-[var(--ai-600)]" aria-hidden="true" />
              <Badge variant="outline" className="capitalize">
                {recommendation.category}
              </Badge>
              <Badge variant={RISK_VARIANT[recommendation.risk] ?? "outline"}>
                {recommendation.risk} risk
              </Badge>
              <span className="text-xs text-[var(--fg-subtle)]">
                {recommendation.confidence} confidence
              </span>
            </div>
            <h3 className="mt-1 text-sm font-medium text-[var(--fg-default)]">{recommendation.title}</h3>
          </div>
        </div>
        <p className="text-sm text-[var(--fg-muted)]">{recommendation.business_impact}</p>
        <p className="text-xs text-[var(--fg-subtle)]">{recommendation.reason}</p>
        {recommendation.estimated_value && (
          <p className="text-xs font-medium text-[var(--fg-default)]">
            Estimated value: {recommendation.estimated_value}
          </p>
        )}
        <p className="text-xs text-[var(--fg-subtle)]">
          {recommendation.sources.length} source{recommendation.sources.length === 1 ? "" : "s"}
        </p>
        <div className="flex items-center justify-between gap-3">
          <span className="rounded-[var(--radius-sm)] bg-white/60 px-2.5 py-1.5 text-xs text-[var(--fg-default)]">
            {recommendation.suggested_action}
          </span>
          <div className="flex shrink-0 gap-2">
            <Button size="sm" variant="ghost" disabled={dismiss.isPending} onClick={() => dismiss.mutate()}>
              Dismiss
            </Button>
            <Button size="sm" variant="ai" disabled={action.isPending} onClick={() => action.mutate()}>
              Act on this
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function RecommendationsPage() {
  const {
    data: recommendations,
    isLoading,
    error,
    refetch,
  } = useQuery<Recommendation[]>({
    queryKey: ["recommendations"],
    queryFn: () => apiFetch<Recommendation[]>("/api/v1/recommendations"),
  });

  return (
    <div>
      <PageHeader
        title="Recommendations"
        description="Real recommendations computed from your own compliance, security, sales, support, and automation data. Each one names the exact records it came from."
      />

      {isLoading && <LoadingSkeleton rows={3} />}
      {error && <ErrorState onRetry={() => refetch()} />}
      {!isLoading && !error && recommendations && recommendations.length === 0 && (
        <EmptyState
          title="No recommendations right now"
          description="Nothing in your data currently crosses a threshold worth flagging."
        />
      )}
      {!isLoading && !error && recommendations && recommendations.length > 0 && (
        <div className="flex flex-col gap-3">
          {recommendations.map((recommendation) => (
            <RecommendationCard key={recommendation.id} recommendation={recommendation} />
          ))}
        </div>
      )}
    </div>
  );
}
