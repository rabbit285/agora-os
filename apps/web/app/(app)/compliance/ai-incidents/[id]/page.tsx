"use client";

import Link from "next/link";
import { use } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { AIIncident, AIIncidentStatus, AISystem, Risk, Task } from "@/lib/types";

const WORKFLOW: AIIncidentStatus[] = ["open", "investigating", "resolved", "closed"];

export default function AIIncidentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: incident } = useQuery<AIIncident>({
    queryKey: ["compliance", "ai-incidents", id],
    queryFn: () => apiFetch<AIIncident>(`/api/v1/compliance/ai-incidents/${id}`),
  });

  const { data: aiSystem } = useQuery<AISystem>({
    queryKey: ["compliance", "ai-systems", incident?.ai_system_id],
    queryFn: () => apiFetch<AISystem>(`/api/v1/compliance/ai-systems/${incident?.ai_system_id}`),
    enabled: !!incident?.ai_system_id,
  });

  const { data: risks } = useQuery<Risk[]>({
    queryKey: ["compliance", "risks"],
    queryFn: () => apiFetch<Risk[]>("/api/v1/compliance/risks"),
    enabled: !!incident?.related_risk_id,
  });

  const { data: tasks } = useQuery<Task[]>({
    queryKey: ["tasks"],
    queryFn: () => apiFetch<Task[]>("/api/v1/tasks"),
    enabled: !!incident?.related_task_id,
  });

  const advanceStatus = useMutation({
    mutationFn: (status: AIIncidentStatus) =>
      apiFetch(`/api/v1/compliance/ai-incidents/${id}/status`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["compliance", "ai-incidents", id] }),
  });

  if (!incident) return null;

  const linkedRisk = risks?.find((r) => r.id === incident.related_risk_id);
  const linkedTask = tasks?.find((t) => t.id === incident.related_task_id);
  const currentIndex = WORKFLOW.indexOf(incident.status);
  const nextStatus = WORKFLOW[currentIndex + 1];

  return (
    <div>
      <PageHeader
        title={incident.title}
        description={incident.description ?? undefined}
        actions={<SeverityBadge severity={incident.severity} />}
      />

      <div className="mb-6 flex items-center gap-3">
        {aiSystem && (
          <Link
            href={`/compliance/ai-systems/${aiSystem.id}`}
            className="text-sm text-neutral-500 hover:underline"
          >
            {aiSystem.name} →
          </Link>
        )}
        <span className="text-sm text-neutral-500">Status:</span>
        <StatusBadge status={incident.status} />
        {nextStatus && (
          <Button
            size="sm"
            variant="outline"
            disabled={advanceStatus.isPending}
            onClick={() => advanceStatus.mutate(nextStatus)}
          >
            Advance to {nextStatus.replace(/_/g, " ")}
          </Button>
        )}
      </div>

      {incident.related_risk_id && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Linked Compliance Risk
            </h2>
            <p className="mb-2 text-xs text-neutral-400">
              Critical AI incidents automatically create a linked risk so EU AI Act Article 73
              serious-incident obligations are tracked.
            </p>
            {linkedRisk ? (
              <Link href="/compliance" className="text-sm text-neutral-700 hover:underline">
                {linkedRisk.title}
              </Link>
            ) : (
              <span className="text-sm text-neutral-400">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}

      {incident.related_task_id && (
        <Card>
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Response Task
            </h2>
            <p className="mb-2 text-xs text-neutral-400">
              Critical incidents automatically create a response task, and notify the incident
              owner directly if one is assigned.
            </p>
            {linkedTask ? (
              <Link href="/tasks" className="text-sm text-neutral-700 hover:underline">
                {linkedTask.title}
              </Link>
            ) : (
              <span className="text-sm text-neutral-400">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
