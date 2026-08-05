"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type {
  Workflow,
  WorkflowRun,
  WorkflowRunDetail,
  WorkflowStatus,
  WorkflowStep,
  WorkflowVersion,
} from "@/lib/types";

import { StepBuilder } from "./step-builder";

const NEXT_STATUS: Partial<Record<WorkflowStatus, WorkflowStatus>> = {
  draft: "active",
  paused: "active",
  active: "paused",
};

const ACTIVE_RUN_STATUSES = new Set(["running", "awaiting_approval"]);

function RunRow({ run }: { run: WorkflowRun }) {
  const [expanded, setExpanded] = useState(false);
  const { data: detail } = useQuery<WorkflowRunDetail>({
    queryKey: ["automation", "runs", run.id],
    queryFn: () => apiFetch<WorkflowRunDetail>(`/api/v1/automation/runs/${run.id}`),
    enabled: expanded,
    refetchInterval: ACTIVE_RUN_STATUSES.has(run.status) ? 2000 : false,
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
            className="text-sm text-[var(--fg-muted)] hover:underline"
            onClick={() => setExpanded((v) => !v)}
          >
            Run started {new Date(run.started_at).toLocaleString()}
          </button>
          <div className="flex items-center gap-2">
            {run.status === "awaiting_approval" && (
              <>
                <Link href="/approvals" className="text-xs text-[var(--fg-muted)] hover:underline">
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
          <div className="mt-3 flex flex-col gap-1 border-t border-[var(--border-default)] pt-3">
            {detail.step_runs.length === 0 && (
              <p className="text-xs text-[var(--fg-subtle)]">
                Queued for durable execution — no steps have run yet.
              </p>
            )}
            {detail.step_runs.map((stepRun) => (
              <div
                key={stepRun.id}
                className="flex items-center justify-between text-xs text-[var(--fg-muted)]"
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

function VersionHistorySection({ workflowId }: { workflowId: string }) {
  const { data: versions } = useQuery<WorkflowVersion[]>({
    queryKey: ["automation", "workflows", workflowId, "versions"],
    queryFn: () =>
      apiFetch<WorkflowVersion[]>(`/api/v1/automation/workflows/${workflowId}/versions`),
  });

  if (!versions || versions.length === 0) return null;

  return (
    <div className="mb-8">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Version History
      </h2>
      <p className="mb-2 text-xs text-[var(--fg-subtle)]">
        Immutable snapshots (spec §41) — one is recorded every time this workflow is published.
      </p>
      <div className="flex flex-col gap-2">
        {versions.map((version) => (
          <Card key={version.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <span className="text-sm text-[var(--fg-muted)]">v{version.version_number}</span>
              <span className="text-xs text-[var(--fg-subtle)]">
                {version.steps.length} step(s) · published{" "}
                {new Date(version.published_at).toLocaleString()}
              </span>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
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
    refetchInterval: (query) => {
      const list = query.state.data as WorkflowRun[] | undefined;
      return list?.some((r) => ACTIVE_RUN_STATUSES.has(r.status)) ? 2000 : false;
    },
  });

  const setStatus = useMutation({
    mutationFn: (status: WorkflowStatus) =>
      apiFetch(`/api/v1/automation/workflows/${id}/status`, { method: "PATCH", body: { status } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automation", "workflows", id] });
      queryClient.invalidateQueries({ queryKey: ["automation", "workflows", id, "versions"] });
    },
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
    mutationFn: () =>
      apiFetch(`/api/v1/automation/workflows/${id}/run`, { method: "POST", body: {} }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["automation", "runs"] }),
  });

  const saveSteps = useMutation({
    mutationFn: (steps: WorkflowStep[]) =>
      apiFetch(`/api/v1/automation/workflows/${id}/steps`, { method: "PATCH", body: { steps } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["automation", "workflows", id] }),
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
          <Button
            size="sm"
            variant="outline"
            disabled={archive.isPending}
            onClick={() => archive.mutate()}
          >
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
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Steps (v{workflow.version}) — trigger: {workflow.trigger_type.replace(/_/g, " ")}
          {workflow.schedule_cron ? ` (${workflow.schedule_cron})` : ""}
        </h2>
        {workflow.status === "draft" ? (
          <StepBuilder
            key={workflow.version}
            steps={workflow.steps}
            saving={saveSteps.isPending}
            onSave={(steps) => saveSteps.mutate(steps)}
          />
        ) : (
          <div className="flex flex-col gap-2">
            <p className="mb-1 text-xs text-[var(--fg-subtle)]">
              Steps are locked while this workflow isn&rsquo;t in draft status (spec §41).
            </p>
            {workflow.steps.map((step, index) => (
              <Card key={index}>
                <CardContent className="flex items-center justify-between pt-6">
                  <span className="text-sm text-[var(--fg-muted)]">
                    {index + 1}. {step.step_type.replace(/_/g, " ")}
                  </span>
                  <span className="text-xs text-[var(--fg-subtle)]">
                    {"title" in step.config
                      ? String(step.config.title)
                      : String(step.config.action_type ?? "")}
                  </span>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      <VersionHistorySection workflowId={id} />

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Run History
        </h2>
        {workflowRuns.length === 0 && <p className="text-sm text-[var(--fg-muted)]">No runs yet.</p>}
        <div className="flex flex-col gap-2">
          {workflowRuns.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </div>
      </div>
    </div>
  );
}
