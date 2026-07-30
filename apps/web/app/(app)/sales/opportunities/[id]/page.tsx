"use client";

import Link from "next/link";
import { use } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { OpportunityStage, SalesOpportunityDetail } from "@/lib/types";

const STAGES: OpportunityStage[] = [
  "prospecting",
  "qualification",
  "proposal",
  "security_review",
  "negotiation",
  "closed_won",
];

export default function OpportunityDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: opportunity } = useQuery<SalesOpportunityDetail>({
    queryKey: ["sales", "opportunities", id],
    queryFn: () => apiFetch<SalesOpportunityDetail>(`/api/v1/sales/opportunities/${id}`),
  });

  const advanceStage = useMutation({
    mutationFn: (stage: OpportunityStage) =>
      apiFetch(`/api/v1/sales/opportunities/${id}`, { method: "PATCH", body: { stage } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales", "opportunities", id] });
      queryClient.invalidateQueries({ queryKey: ["sales", "intelligence"] });
    },
  });

  if (!opportunity) return null;

  const currentIndex = STAGES.indexOf(opportunity.stage);
  const nextStage = opportunity.stage === "closed_won" ? undefined : STAGES[currentIndex + 1];

  return (
    <div>
      <PageHeader
        title={opportunity.title}
        description={
          opportunity.value !== null ? `€${opportunity.value.toLocaleString()}` : undefined
        }
        actions={<StatusBadge status={opportunity.stage} />}
      />
      <div className="mb-6 flex items-center gap-3">
        {nextStage && (
          <Button
            size="sm"
            variant="outline"
            disabled={advanceStage.isPending}
            onClick={() => advanceStage.mutate(nextStage)}
          >
            Advance to {nextStage.replace(/_/g, " ")}
          </Button>
        )}
        {opportunity.stage !== "closed_lost" && opportunity.stage !== "closed_won" && (
          <Button
            size="sm"
            variant="ghost"
            disabled={advanceStage.isPending}
            onClick={() => advanceStage.mutate("closed_lost")}
          >
            Mark closed lost
          </Button>
        )}
      </div>
      <Card className="mb-4">
        <CardContent className="pt-6">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Account
          </h2>
          <Link
            href={`/sales/accounts/${opportunity.account.id}`}
            className="text-sm text-neutral-700 hover:underline"
          >
            {opportunity.account.name}
          </Link>
        </CardContent>
      </Card>
      {opportunity.onboarding_customer_id && (
        <Card>
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Onboarded as Support Customer
            </h2>
            <Badge variant="outline">Customer created</Badge>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
