"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { DpiaSections } from "@/components/compliance/dpia-sections";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { Approval, DPIA, DPIAStatus } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

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
            className="text-sm text-[var(--fg-muted)] hover:underline"
          >
            View linked AI system →
          </Link>
        )}
        <span className="text-sm text-[var(--fg-muted)]">Status:</span>
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
          <span className="text-xs text-[var(--critical-600)]">{(updateStatus.error as Error).message}</span>
        )}
      </div>

      <DpiaSections dpia={dpia} />

      {dpia.approval_id && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
              Required Approval
            </h2>
            <p className="mb-2 text-xs text-[var(--fg-subtle)]">
              This DPIA&apos;s high risk level automatically requires sign-off before it can be
              marked approved (GDPR Article 35).
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
          Findings
        </h2>
        <Card>
          <CardContent className="flex flex-col gap-2 pt-6">
            {dpia.findings && <p className="text-sm text-[var(--fg-muted)]">{dpia.findings}</p>}
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
