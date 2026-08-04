"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { RiskBadge } from "@/components/risk-badge";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Approval } from "@/lib/types";

export default function ApprovalsPage() {
  const queryClient = useQueryClient();

  const { data: approvals, isLoading } = useQuery<Approval[]>({
    queryKey: ["approvals"],
    queryFn: () => apiFetch<Approval[]>("/api/v1/approvals"),
  });

  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      apiFetch<Approval>(`/api/v1/approvals/${id}/decide`, { method: "POST", body: { approve } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["approvals"] }),
  });

  return (
    <div>
      <PageHeader
        title="Approval Center"
        description="High-risk and critical AI/automation actions land here until a human decides (spec sections B7, 45)."
      />
      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {approvals && approvals.length === 0 && (
        <p className="text-sm text-neutral-500">No approvals pending.</p>
      )}
      <div className="flex flex-col gap-2">
        {approvals?.map((approval) => (
          <Card key={approval.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-neutral-900">{approval.action_type}</div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  {approval.module && <Badge variant="outline">{approval.module}</Badge>}
                  <RiskBadge riskClass={approval.risk_class} />
                  <StatusBadge status={approval.status} />
                  {approval.ai_generated && <Badge variant="secondary">AI-generated</Badge>}
                  {approval.due_at && (
                    <span className="text-xs text-neutral-400">
                      Due {new Date(approval.due_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
              {approval.status === "pending" && (
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => decide.mutate({ id: approval.id, approve: false })}
                  >
                    Reject
                  </Button>
                  <Button size="sm" onClick={() => decide.mutate({ id: approval.id, approve: true })}>
                    Approve
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
