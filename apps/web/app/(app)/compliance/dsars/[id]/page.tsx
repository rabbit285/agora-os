"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { DSAR, DSARStatus } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400";

export default function DSARDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");

  const { data: dsar } = useQuery<DSAR>({
    queryKey: ["compliance", "dsars", id],
    queryFn: () => apiFetch<DSAR>(`/api/v1/compliance/dsars/${id}`),
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

  const dueDate = new Date(dsar.due_at);
  const isOverdue = dsar.status !== "fulfilled" && dsar.status !== "rejected" && dueDate < new Date();

  return (
    <div>
      <PageHeader
        title={dsar.requester_name}
        description={`${dsar.requester_email} — ${dsar.request_type} request`}
        actions={<StatusBadge status={dsar.status} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <span className="text-sm text-neutral-500">
          Due {dueDate.toLocaleDateString()}
          {isOverdue && <span className="ml-1 text-red-600">(overdue)</span>}
        </span>
        {dsar.fulfilled_at && (
          <span className="text-sm text-neutral-500">
            · Fulfilled {new Date(dsar.fulfilled_at).toLocaleDateString()}
          </span>
        )}
      </div>

      <Card className="mb-6">
        <CardContent className="flex flex-col gap-3 pt-6">
          <div className="flex items-center gap-2">
            <span className="text-sm text-neutral-500">Status:</span>
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
          {dsar.notes && <p className="text-sm text-neutral-700">Notes: {dsar.notes}</p>}
          <div className="flex gap-2">
            <Input
              placeholder="Add notes (saved with the next status change)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="flex-1"
            />
          </div>
          {updateStatus.isError && (
            <span className="text-xs text-red-600">{(updateStatus.error as Error).message}</span>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
