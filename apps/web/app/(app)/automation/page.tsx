"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type {
  Workflow,
  WorkflowAnalytics,
  WorkflowStep,
  WorkflowTriggerType,
} from "@/lib/types";
import { UNWIRED_TRIGGER_TYPES, WORKFLOW_TRIGGER_TYPES } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400";

function AnalyticsSection() {
  const { data: analytics } = useQuery<WorkflowAnalytics>({
    queryKey: ["automation", "analytics"],
    queryFn: () => apiFetch<WorkflowAnalytics>("/api/v1/automation/analytics"),
  });

  if (!analytics) return null;

  return (
    <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Card>
        <CardContent className="pt-6">
          <div className="text-2xl font-semibold text-neutral-900">
            {analytics.active_workflows}
          </div>
          <div className="text-xs text-neutral-500">Active Workflows</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="text-2xl font-semibold text-neutral-900">{analytics.total_runs}</div>
          <div className="text-xs text-neutral-500">Total Runs</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="text-2xl font-semibold text-neutral-900">
            {analytics.success_rate_percent}%
          </div>
          <div className="text-xs text-neutral-500">Success Rate</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="text-2xl font-semibold text-neutral-900">
            {analytics.awaiting_approval_count}
          </div>
          <div className="text-xs text-neutral-500">Awaiting Approval</div>
        </CardContent>
      </Card>
    </div>
  );
}

function emptyStep(): WorkflowStep {
  return { step_type: "create_task", config: { title: "" } };
}

function WorkflowsSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState<WorkflowTriggerType>("manual");
  const [scheduleCron, setScheduleCron] = useState("");
  const [steps] = useState<WorkflowStep[]>([emptyStep()]);

  const { data: workflows } = useQuery<Workflow[]>({
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

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Workflows
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-3 pt-6">
          <Input
            placeholder="Workflow name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <select
              className={selectClassName}
              value={triggerType}
              onChange={(e) => setTriggerType(e.target.value as WorkflowTriggerType)}
            >
              {WORKFLOW_TRIGGER_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type.replace(/_/g, " ")}
                  {UNWIRED_TRIGGER_TYPES.includes(type) ? " (not yet wired)" : ""}
                </option>
              ))}
            </select>
            {triggerType === "schedule" && (
              <Input
                placeholder="Cron expression (e.g. 0 9 * * 1)"
                value={scheduleCron}
                onChange={(e) => setScheduleCron(e.target.value)}
                className="min-w-[200px] flex-1"
              />
            )}
          </div>
          <p className="text-xs text-neutral-400">
            New workflows start as a single &ldquo;Create task&rdquo; draft step — use the
            visual Step Builder on the workflow&rsquo;s own page to add and configure more
            steps before publishing (spec §41: steps lock once active).
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
      {workflows?.length === 0 && <p className="text-sm text-neutral-500">No workflows yet.</p>}
      <div className="flex flex-col gap-2">
        {workflows?.map((workflow) => (
          <Link key={workflow.id} href={`/automation/workflows/${workflow.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{workflow.name}</div>
                  <div className="text-xs text-neutral-400">
                    {workflow.steps.length} step{workflow.steps.length === 1 ? "" : "s"} · v
                    {workflow.version} · {workflow.trigger_type.replace(/_/g, " ")}
                  </div>
                </div>
                <StatusBadge status={workflow.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
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
        description="Workflow builder, runs, and the Human Approval hook — spec sections 36-43."
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
