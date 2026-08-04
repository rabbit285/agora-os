"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { AuditDetail, AuditStatus, Severity } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

export default function AuditDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [findingTitle, setFindingTitle] = useState("");
  const [findingDescription, setFindingDescription] = useState("");
  const [severity, setSeverity] = useState<Severity>("low");

  const { data: audit } = useQuery<AuditDetail>({
    queryKey: ["compliance", "audits", id],
    queryFn: () => apiFetch<AuditDetail>(`/api/v1/compliance/audits/${id}`),
  });

  const updateStatus = useMutation({
    mutationFn: (status: AuditStatus) =>
      apiFetch(`/api/v1/compliance/audits/${id}/status`, { method: "PATCH", body: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance", "audits", id] }),
  });

  const createFinding = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/audits/${id}/findings`, {
        method: "POST",
        body: {
          title: findingTitle,
          description: findingDescription.trim() || null,
          severity,
        },
      }),
    onSuccess: () => {
      setFindingTitle("");
      setFindingDescription("");
      setSeverity("low");
      queryClient.invalidateQueries({ queryKey: ["compliance", "audits", id] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  const remediateFinding = useMutation({
    mutationFn: (findingId: string) =>
      apiFetch(`/api/v1/compliance/audits/${id}/findings/${findingId}/status`, {
        method: "PATCH",
        body: { status: "remediated" },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance", "audits", id] }),
  });

  if (!audit) return null;

  return (
    <div>
      <PageHeader
        title={audit.title}
        description={audit.auditor_name ?? undefined}
        actions={<StatusBadge status={audit.status} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <span className="text-sm text-[var(--fg-muted)]">Status:</span>
        <select
          className={selectClassName}
          value={audit.status}
          onChange={(e) => updateStatus.mutate(e.target.value as AuditStatus)}
        >
          <option value="planned">Planned</option>
          <option value="in_progress">In progress</option>
          <option value="completed">Completed</option>
        </select>
        {audit.completed_at && (
          <span className="text-xs text-[var(--fg-subtle)]">
            Completed {new Date(audit.completed_at).toLocaleString()}
          </span>
        )}
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Add Finding
        </h2>
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <div className="flex flex-wrap gap-2">
              <Input
                placeholder="Finding title"
                value={findingTitle}
                onChange={(e) => setFindingTitle(e.target.value)}
                className="min-w-[220px] flex-1"
              />
              <select
                className={selectClassName}
                value={severity}
                onChange={(e) => setSeverity(e.target.value as Severity)}
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
              <Button
                disabled={!findingTitle.trim() || createFinding.isPending}
                onClick={() => createFinding.mutate()}
              >
                Add finding
              </Button>
            </div>
            <Input
              placeholder="Description (optional)"
              value={findingDescription}
              onChange={(e) => setFindingDescription(e.target.value)}
            />
            <p className="text-xs text-[var(--fg-subtle)]">
              A high or critical finding automatically creates a remediation task.
            </p>
          </CardContent>
        </Card>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Findings
        </h2>
        {audit.findings.length === 0 && (
          <p className="text-sm text-[var(--fg-muted)]">No findings recorded yet.</p>
        )}
        <div className="flex flex-col gap-2">
          {audit.findings.map((finding) => (
            <Card key={finding.id}>
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{finding.title}</div>
                  {finding.description && (
                    <div className="text-sm text-[var(--fg-muted)]">{finding.description}</div>
                  )}
                  {finding.related_task_id && (
                    <div className="text-xs text-[var(--fg-subtle)]">Remediation task created</div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={finding.severity} />
                  <StatusBadge status={finding.status} />
                  {finding.status === "open" && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={remediateFinding.isPending}
                      onClick={() => remediateFinding.mutate(finding.id)}
                    >
                      Mark remediated
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
