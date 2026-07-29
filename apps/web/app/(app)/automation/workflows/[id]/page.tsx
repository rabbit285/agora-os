"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Workflow, WorkflowRun, WorkflowRunDetail, WorkflowStatus } from "@/lib/types";

const NEXT_STATUS: Partial<Record<WorkflowStatus, WorkflowStatus>> = {
  draft: "active",
  paused: "active",
  active: "paused",
};

function RunRow({ run }: { run: WorkflowRun }) {
  const [expanded, setExpanded] = useState(false);
  const { data: detail } = useQuery<WorkflowRunDetail>({
    queryKey: ["automation", "runs", run.id],
    queryFn: () => apiFetch<WorkflowRunDetail>(`/api/v1/automation/runs/${run.id}`),
    enabled: expanded,
  });

  const queryClient = useQueryClient();
  const resumeRun = useMutation({
    mutationFn: () => apiFetch(`/api/v1/automation/runs/${run.id}/resume`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation", "runs"] });
      queryClient.invalidateQueries({ queryKey: ["automation", "runs", run.id] });
    },
  });

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <button
            className="text-sm text-neutral-700 hover:underline"
            onClick={() => setExpanded((v) => !v)}
          >
            Run started {new Date(run.started_at).toLocaleString()}
          </button>
          <div className="flex items-center gap-2">
            {run.status === "awaiting_approval" && (
              <>
                <Link href="/approvals" className="text-xs text-neutral-500 hover:underline">
                  Decide in Approvals
                </Link>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={resumeRun.isPending}
                  onClick={() => resumeRun.mutate()}
                >
                  Check for decision
                </Button>
              </>
            )}
            <StatusBadge status={run.status} />
          </div>
        </div>
        {expanded && detail && (
          <div className="mt-3 flex flex-col gap-1 border-t border-neutral-100 pt-3">
            {detail.step_runs.map((stepRun) => (
              <div
                key={stepRun.id}
                className="flex items-center justify-between text-xs text-neutral-600"
              >
                <span>
                  {stepRun.step_index + 1}. {stepRun.step_type.replace(/_/g, " ")}
                </span>
                <StatusBadge status={stepRun.status} />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function WorkflowDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: workflow } = useQuery<Workflow>({
    queryKey: ["automation", "workflows", id],
    queryFn: () => apiFetch<Workflow>(`/api/v1/automation/workflows/${id}`),
  });

  const { data: runs } = useQuery<WorkflowRun[]>({
    queryKey: ["automation", "runs"],
    queryFn: () => apiFetch<WorkflowRun[]>("/api/v1/automation/runs"),
  });

  const setStatus = useMutation({
    mutationFn: (status: WorkflowStatus) =>
      apiFetch(`/api/v1/automation/workflows/${id}/status`, { method: "PATCH", body: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["automation", "workflows", id] }),
  });

  const archive = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/automation/workflows/${id}/status`, {
        method: "PATCH",
        body: { status: "archived" },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["automation", "workflows", id] }),
  });

  const runNow = useMutation({
    mutationFn: () => apiFetch(`/api/v1/automation/workflows/${id}/run`, { method: "POST", body: {} }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["automation", "runs"] }),
  });

  if (!workflow) return null;

  const workflowRuns = runs?.filter((r) => r.workflow_id === workflow.id) ?? [];
  const nextStatus = NEXT_STATUS[workflow.status];

  return (
    <div>
      <PageHeader
        title={workflow.name}
        description={workflow.description ?? undefined}
        actions={<StatusBadge status={workflow.status} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {nextStatus && (
          <Button
            size="sm"
            variant="outline"
            disabled={setStatus.isPending}
            onClick={() => setStatus.mutate(nextStatus)}
          >
            {nextStatus === "active" ? "Publish" : "Pause"}
          </Button>
        )}
        {workflow.status !== "archived" && (
          <Button size="sm" variant="outline" disabled={archive.isPending} onClick={() => archive.mutate()}>
            Archive
          </Button>
        )}
        {workflow.status === "active" && (
          <Button size="sm" disabled={runNow.isPending} onClick={() => runNow.mutate()}>
            Run now
          </Button>
        )}
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Steps (v{workflow.version})
        </h2>
        <div className="flex flex-col gap-2">
          {workflow.steps.map((step, index) => (
            <Card key={index}>
              <CardContent className="flex items-center justify-between pt-6">
                <span className="text-sm text-neutral-700">
                  {index + 1}. {step.step_type.replace(/_/g, " ")}
                </span>
                <span className="text-xs text-neutral-400">
                  {"title" in step.config ? String(step.config.title) : String(step.config.action_type ?? "")}
                </span>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Run History
        </h2>
        {workflowRuns.length === 0 && <p className="text-sm text-neutral-500">No runs yet.</p>}
        <div className="flex flex-col gap-2">
          {workflowRuns.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </div>
      </div>
    </div>
  );
}
