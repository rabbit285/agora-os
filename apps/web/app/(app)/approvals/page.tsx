"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApprovalPanel } from "@/components/approval-panel";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { FilterBar } from "@/components/filter-bar";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { PageHeader } from "@/components/page-header";
import { Select } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type { Approval } from "@/lib/types";

export default function ApprovalsPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState("pending");

  const {
    data: approvals,
    isLoading,
    error,
    refetch,
  } = useQuery<Approval[]>({
    queryKey: ["approvals"],
    queryFn: () => apiFetch<Approval[]>("/api/v1/approvals"),
  });

  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: string; approve: boolean }) =>
      apiFetch<Approval>(`/api/v1/approvals/${id}/decide`, { method: "POST", body: { approve } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["approvals"] }),
  });

  const filtered = useMemo(
    () => (approvals ?? []).filter((a) => statusFilter === "all" || a.status === statusFilter),
    [approvals, statusFilter],
  );

  return (
    <div>
      <PageHeader
        title="Approval Center"
        description="High-risk and critical AI/automation actions land here until a human decides."
      />

      <FilterBar>
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-40">
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="expired">Expired</option>
          <option value="all">All</option>
        </Select>
      </FilterBar>

      {isLoading && <LoadingSkeleton rows={4} />}
      {error && <ErrorState onRetry={() => refetch()} />}
      {!isLoading && !error && filtered.length === 0 && (
        <EmptyState
          title={statusFilter === "pending" ? "No approvals pending" : "No approvals found"}
          description={statusFilter === "pending" ? "You're all caught up." : undefined}
        />
      )}
      {!isLoading && !error && filtered.length > 0 && (
        <div className="flex flex-col gap-2">
          {filtered.map((approval) => (
            <ApprovalPanel
              key={approval.id}
              approval={approval}
              isDeciding={decide.isPending}
              onApprove={() => decide.mutate({ id: approval.id, approve: true })}
              onReject={() => decide.mutate({ id: approval.id, approve: false })}
            />
          ))}
        </div>
      )}
    </div>
  );
}
