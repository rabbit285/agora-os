"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
// already owns real creation for it (spec §72's Global Create pattern),
// rather than a second miniature action-executor living on this page.
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
    <Card>
      <CardContent className="flex flex-col gap-3 pt-6">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="capitalize">
                {recommendation.category}
              </Badge>
              <Badge variant={RISK_VARIANT[recommendation.risk] ?? "outline"}>
                {recommendation.risk} risk
              </Badge>
              <span className="text-xs text-neutral-400">
                {recommendation.confidence} confidence
              </span>
            </div>
            <h3 className="mt-1 font-medium text-neutral-900">{recommendation.title}</h3>
          </div>
        </div>
        <p className="text-sm text-neutral-600">{recommendation.business_impact}</p>
        <p className="text-xs text-neutral-500">{recommendation.reason}</p>
        {recommendation.estimated_value && (
          <p className="text-xs font-medium text-neutral-700">
            Estimated value: {recommendation.estimated_value}
          </p>
        )}
        <p className="text-xs text-neutral-500">
          {recommendation.sources.length} source{recommendation.sources.length === 1 ? "" : "s"}
        </p>
        <div className="flex items-center justify-between">
          <span className="text-sm text-neutral-800">{recommendation.suggested_action}</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={dismiss.isPending} onClick={() => dismiss.mutate()}>
              Dismiss
            </Button>
            <Button size="sm" disabled={action.isPending} onClick={() => action.mutate()}>
              Act on this
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function RecommendationsPage() {
  const { data: recommendations, isLoading } = useQuery<Recommendation[]>({
    queryKey: ["recommendations"],
    queryFn: () => apiFetch<Recommendation[]>("/api/v1/recommendations"),
  });

  return (
    <div>
      <PageHeader
        title="Recommendations"
        description="spec §87 — real recommendations computed from your own compliance, security, sales,
          support, and automation data, refreshed on every visit. Each one names the exact records it
          came from."
      />

      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {recommendations && recommendations.length === 0 && (
        <p className="text-sm text-neutral-500">
          No recommendations right now — nothing in your data currently crosses a threshold worth
          flagging.
        </p>
      )}
      <div className="flex flex-col gap-3">
        {recommendations?.map((recommendation) => (
          <RecommendationCard key={recommendation.id} recommendation={recommendation} />
        ))}
      </div>
    </div>
  );
}
