"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { Approval, AISystemDetail, AISystemStatus } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

export default function AISystemDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [assessmentStatus, setAssessmentStatus] = useState<
    "pass" | "fail" | "partial" | "not_assessed"
  >("pass");
  const [assessmentNotes, setAssessmentNotes] = useState("");

  const { data: system } = useQuery<AISystemDetail>({
    queryKey: ["compliance", "ai-systems", id],
    queryFn: () => apiFetch<AISystemDetail>(`/api/v1/compliance/ai-systems/${id}`),
  });

  const { data: approvals } = useQuery<Approval[]>({
    queryKey: ["approvals"],
    queryFn: () => apiFetch<Approval[]>("/api/v1/approvals"),
    enabled: !!system?.approval_id,
  });

  const updateStatus = useMutation({
    mutationFn: (status: AISystemStatus) =>
      apiFetch(`/api/v1/compliance/ai-systems/${id}/status`, { method: "PATCH", body: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance", "ai-systems", id] }),
  });

  const addAssessment = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/ai-systems/${id}/assessments`, {
        method: "POST",
        body: { status: assessmentStatus, notes: assessmentNotes || null },
      }),
    onSuccess: () => {
      setAssessmentNotes("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "ai-systems", id] });
    },
  });

  if (!system) return null;

  const linkedApproval = approvals?.find((a) => a.id === system.approval_id);

  return (
    <div>
      <PageHeader
        title={system.name}
        description={system.purpose}
        actions={<StatusBadge status={system.risk_classification} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {system.vendor && (
          <span className="text-sm text-[var(--fg-muted)]">Vendor: {system.vendor}</span>
        )}
        <span className="text-sm text-[var(--fg-muted)]">Status:</span>
        <StatusBadge status={system.status} />
        <select
          className={selectClassName}
          value={system.status}
          onChange={(e) => updateStatus.mutate(e.target.value as AISystemStatus)}
        >
          <option value="in_review">In review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="retired">Retired</option>
        </select>
        {updateStatus.isError && (
          <span className="text-xs text-[var(--critical-600)]">
            {(updateStatus.error as Error).message}
          </span>
        )}
      </div>

      {system.approval_id && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
              Required Approval
            </h2>
            <p className="mb-2 text-xs text-[var(--fg-subtle)]">
              This system&apos;s risk classification automatically required sign-off before it can
              be marked approved (spec section 69 — New AI Tool Adoption).
            </p>
            {linkedApproval ? (
              <div className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
                <Link href="/approvals" className="hover:underline">
                  {linkedApproval.action_type}
                </Link>
                <StatusBadge status={linkedApproval.status} />
              </div>
            ) : (
              <span className="text-sm text-[var(--fg-subtle)]">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Assessments
        </h2>
        <div className="mb-4 flex flex-col gap-2">
          {system.assessments.length === 0 && (
            <p className="text-sm text-[var(--fg-muted)]">No assessments yet.</p>
          )}
          {system.assessments.map((assessment) => (
            <Card key={assessment.id}>
              <CardContent className="flex items-center justify-between pt-6">
                <div className="text-sm text-[var(--fg-muted)]">{assessment.notes ?? "—"}</div>
                <StatusBadge status={assessment.status} />
              </CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardContent className="flex flex-wrap gap-2 pt-6">
            <select
              className={selectClassName}
              value={assessmentStatus}
              onChange={(e) =>
                setAssessmentStatus(
                  e.target.value as "pass" | "fail" | "partial" | "not_assessed",
                )
              }
            >
              <option value="pass">Pass</option>
              <option value="fail">Fail</option>
              <option value="partial">Partial</option>
              <option value="not_assessed">Not assessed</option>
            </select>
            <Input
              placeholder="Notes"
              value={assessmentNotes}
              onChange={(e) => setAssessmentNotes(e.target.value)}
              className="min-w-[200px] flex-1"
            />
            <Button disabled={addAssessment.isPending} onClick={() => addAssessment.mutate()}>
              Record assessment
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
