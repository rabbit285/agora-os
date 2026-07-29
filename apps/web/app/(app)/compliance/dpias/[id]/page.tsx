"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { Approval, DPIA, DPIAStatus } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400";

export default function DPIADetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [findings, setFindings] = useState("");

  const { data: dpia } = useQuery<DPIA>({
    queryKey: ["compliance", "dpias", id],
    queryFn: () => apiFetch<DPIA>(`/api/v1/compliance/dpias/${id}`),
  });

  const { data: approvals } = useQuery<Approval[]>({
    queryKey: ["approvals"],
    queryFn: () => apiFetch<Approval[]>("/api/v1/approvals"),
    enabled: !!dpia?.approval_id,
  });

  const updateStatus = useMutation({
    mutationFn: (status: DPIAStatus) =>
      apiFetch(`/api/v1/compliance/dpias/${id}/status`, {
        method: "PATCH",
        body: { status, findings: findings || undefined },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance", "dpias", id] }),
  });

  if (!dpia) return null;

  const linkedApproval = approvals?.find((a) => a.id === dpia.approval_id);

  return (
    <div>
      <PageHeader
        title={dpia.title}
        description="Data Protection Impact Assessment — GDPR Article 35."
        actions={<StatusBadge status={dpia.risk_level} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {dpia.ai_system_id && (
          <Link
            href={`/compliance/ai-systems/${dpia.ai_system_id}`}
            className="text-sm text-neutral-500 hover:underline"
          >
            View linked AI system →
          </Link>
        )}
        <span className="text-sm text-neutral-500">Status:</span>
        <StatusBadge status={dpia.status} />
        <select
          className={selectClassName}
          value={dpia.status}
          onChange={(e) => updateStatus.mutate(e.target.value as DPIAStatus)}
        >
          <option value="draft">Draft</option>
          <option value="in_review">In review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        {updateStatus.isError && (
          <span className="text-xs text-red-600">{(updateStatus.error as Error).message}</span>
        )}
      </div>

      {dpia.approval_id && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Required Approval
            </h2>
            <p className="mb-2 text-xs text-neutral-400">
              This DPIA&apos;s high risk level automatically requires sign-off before it can be
              marked approved (GDPR Article 35).
            </p>
            {linkedApproval ? (
              <div className="flex items-center gap-2 text-sm text-neutral-700">
                <Link href="/approvals" className="hover:underline">
                  {linkedApproval.action_type}
                </Link>
                <StatusBadge status={linkedApproval.status} />
              </div>
            ) : (
              <span className="text-sm text-neutral-400">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Findings
        </h2>
        <Card>
          <CardContent className="flex flex-col gap-2 pt-6">
            {dpia.findings && <p className="text-sm text-neutral-700">{dpia.findings}</p>}
            <Input
              placeholder="Record findings (saved with the next status change)"
              value={findings}
              onChange={(e) => setFindings(e.target.value)}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
