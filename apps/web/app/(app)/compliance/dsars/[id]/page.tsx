"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DsarDiscoveryPanel } from "@/components/compliance/dsar-discovery";
import { DsarNextAction } from "@/components/compliance/dsar-next-action";
import { DsarResponsePackagePanel } from "@/components/compliance/dsar-response-package";
import { DsarScopeReview } from "@/components/compliance/dsar-scope-review";
import { DsarWorkflow } from "@/components/compliance/dsar-workflow";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { DSAR, DSARStatus, DsarWorkflowState } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

export default function DSARDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");

  const { data: dsar } = useQuery<DSAR>({
    queryKey: ["compliance", "dsars", id],
    queryFn: () => apiFetch<DSAR>(`/api/v1/compliance/dsars/${id}`),
  });

  // Where the request is and what it needs, derived server-side from the
  // record. Nothing on this page lets somebody set it directly.
  const { data: workflow } = useQuery<DsarWorkflowState>({
    queryKey: ["compliance", "dsars", id, "workflow"],
    queryFn: () => apiFetch<DsarWorkflowState>(`/api/v1/compliance/dsars/${id}/workflow`),
  });

  const updateStatus = useMutation({
    mutationFn: (status: DSARStatus) =>
      apiFetch(`/api/v1/compliance/dsars/${id}/status`, {
        method: "PATCH",
        body: { status, notes: notes || undefined },
      }),
    onSuccess: () => {
      setNotes("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "dsars", id] });
    },
  });

  if (!dsar) return null;

  return (
    <div>
      <PageHeader
        title={dsar.requester_name}
        description={`${dsar.requester_email} — ${dsar.request_type} request`}
        actions={
          <StatusBadge
            status={workflow?.phase ?? dsar.status}
            label={workflow?.phase_label}
          />
        }
      />

      {workflow && (
        <DsarNextAction
          workflow={workflow}
          dueAt={dsar.due_at}
          daysRemaining={dsar.days_remaining}
          overdue={dsar.overdue}
        />
      )}

      {/* Identity first: everything below either discloses data or acts
          on a record, and both are wrong if the requester is not who
          they say they are. */}
      <DsarWorkflow dsar={dsar} />

      <DsarScopeReview dsarId={id} confirmed={dsar.scope_confirmed_at !== null} />

      <DsarDiscoveryPanel
        dsarId={id}
        canSearch={
          dsar.verification_status === "verified" && dsar.scope_confirmed_at !== null
        }
        blockedReason={
          dsar.verification_status !== "verified"
            ? "Verify the requester's identity before searching. Looking a person up on an unverified request is the same disclosure risk as answering it."
            : dsar.scope_confirmed_at === null
              ? "Confirm the search scope first — discovery searches exactly what you confirm."
              : null
        }
      />

      {dsar.discovery_run_at && (
        <DsarResponsePackagePanel dsarId={id} workflow={workflow} />
      )}

      <Card className="mb-6">
        <CardContent className="flex flex-col gap-3 pt-6">
          <div className="flex items-center gap-2">
            <span className="text-sm text-[var(--fg-muted)]">Status:</span>
            <select
              className={selectClassName}
              value={dsar.status}
              onChange={(e) => updateStatus.mutate(e.target.value as DSARStatus)}
            >
              <option value="received">Received</option>
              <option value="in_progress">In progress</option>
              <option value="fulfilled">Fulfilled</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          {dsar.notes && <p className="text-sm text-[var(--fg-muted)]">Notes: {dsar.notes}</p>}
          <div className="flex gap-2">
            <Input
              placeholder="Add notes (saved with the next status change)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="flex-1"
            />
          </div>
          {updateStatus.isError && (
            <span className="text-xs text-[var(--critical-600)]">{(updateStatus.error as Error).message}</span>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
