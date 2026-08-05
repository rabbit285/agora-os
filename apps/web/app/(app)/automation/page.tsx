"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type {
  Workflow,
  WorkflowAnalytics,
  WorkflowStep,
  WorkflowTriggerType,
} from "@/lib/types";
import { UNWIRED_TRIGGER_TYPES, WORKFLOW_TRIGGER_TYPES } from "@/lib/types";

function AnalyticsSection() {
  const { data: analytics } = useQuery<WorkflowAnalytics>({
    queryKey: ["automation", "analytics"],
    queryFn: () => apiFetch<WorkflowAnalytics>("/api/v1/automation/analytics"),
  });

  if (!analytics) return null;

  return (
    <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <MetricCard label="Active Workflows" value={String(analytics.active_workflows)} />
      <MetricCard label="Total Runs" value={String(analytics.total_runs)} />
      <MetricCard
        label="Success Rate"
        value={`${analytics.success_rate_percent}%`}
        status={
          analytics.success_rate_percent >= 80
            ? "success"
            : analytics.success_rate_percent >= 50
              ? "warning"
              : "critical"
        }
      />
      <MetricCard
        label="Awaiting Approval"
        value={String(analytics.awaiting_approval_count)}
        status={analytics.awaiting_approval_count > 0 ? "warning" : "success"}
      />
    </div>
  );
}

function emptyStep(): WorkflowStep {
  return { step_type: "create_task", config: { title: "" } };
}

function WorkflowsSection() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState<WorkflowTriggerType>("manual");
  const [scheduleCron, setScheduleCron] = useState("");
  const [steps] = useState<WorkflowStep[]>([emptyStep()]);

  const { data: workflows, isLoading, error, refetch } = useQuery<Workflow[]>({
    queryKey: ["automation", "workflows"],
    queryFn: () => apiFetch<Workflow[]>("/api/v1/automation/workflows"),
  });

  const createWorkflow = useMutation({
    mutationFn: () =>
      apiFetch<Workflow>("/api/v1/automation/workflows", {
        method: "POST",
        body: {
          name,
          trigger_type: triggerType,
          schedule_cron: triggerType === "schedule" ? scheduleCron : null,
          steps,
        },
      }),
    onSuccess: () => {
      setName("");
      setTriggerType("manual");
      setScheduleCron("");
      queryClient.invalidateQueries({ queryKey: ["automation", "workflows"] });
    },
  });

  const columns: DataTableColumn<Workflow>[] = [
    {
      key: "name",
      header: "Workflow",
      render: (workflow) => (
        <div className="flex flex-col">
          <span className="font-medium">{workflow.name}</span>
          <span className="text-xs text-[var(--fg-subtle)]">
            {workflow.steps.length} step{workflow.steps.length === 1 ? "" : "s"} · v
            {workflow.version} · {workflow.trigger_type.replace(/_/g, " ")}
          </span>
        </div>
      ),
      sortValue: (workflow) => workflow.name.toLowerCase(),
    },
    {
      key: "status",
      header: "Status",
      render: (workflow) => <StatusBadge status={workflow.status} />,
    },
  ];

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Workflows
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-3 pt-5">
          <Input
            placeholder="Workflow name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Select
              value={triggerType}
              onChange={(e) => setTriggerType(e.target.value as WorkflowTriggerType)}
              className="w-56"
            >
              {WORKFLOW_TRIGGER_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type.replace(/_/g, " ")}
                  {UNWIRED_TRIGGER_TYPES.includes(type) ? " (not yet wired)" : ""}
                </option>
              ))}
            </Select>
            {triggerType === "schedule" && (
              <Input
                placeholder="Cron expression (e.g. 0 9 * * 1)"
                value={scheduleCron}
                onChange={(e) => setScheduleCron(e.target.value)}
                className="min-w-[200px] flex-1"
              />
            )}
          </div>
          <p className="text-xs text-[var(--fg-subtle)]">
            New workflows start as a single &ldquo;Create task&rdquo; draft step — use the
            visual Step Builder on the workflow&rsquo;s own page to add and configure more
            steps before publishing (steps lock once active).
          </p>
          <Button
            disabled={!name.trim() || createWorkflow.isPending}
            onClick={() => createWorkflow.mutate()}
            className="self-start"
          >
            Create workflow (draft)
          </Button>
        </CardContent>
      </Card>
      <DataTable
        columns={columns}
        data={workflows}
        getRowId={(workflow) => workflow.id}
        onRowClick={(workflow) => router.push(`/automation/workflows/${workflow.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No workflows yet"
      />
    </div>
  );
}

const SUB_PAGES = [
  { href: "/automation/templates", label: "Templates" },
  { href: "/automation/connections", label: "Connections" },
];

export default function AutomationPage() {
  return (
    <div>
      <PageHeader
        title="Business Automation"
        description="Workflow builder, runs, and the Human Approval hook."
        actions={
          <div className="flex flex-wrap gap-2">
            {SUB_PAGES.map((page) => (
              <Link key={page.href} href={page.href}>
                <Button variant="outline" size="sm">
                  {page.label}
                </Button>
              </Link>
            ))}
          </div>
        }
      />
      <AnalyticsSection />
      <WorkflowsSection />
    </div>
  );
}
