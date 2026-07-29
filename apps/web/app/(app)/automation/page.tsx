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
import type { Workflow, WorkflowStep, WorkflowStepType } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400";

function emptyStep(): WorkflowStep {
  return { step_type: "create_task", config: { title: "" } };
}

function StepEditor({
  step,
  onChange,
  onRemove,
}: {
  step: WorkflowStep;
  onChange: (step: WorkflowStep) => void;
  onRemove: () => void;
}) {
  const setType = (step_type: WorkflowStepType) => {
    if (step_type === "create_task") onChange({ step_type, config: { title: "" } });
    else if (step_type === "send_notification") onChange({ step_type, config: { title: "", body: "" } });
    else onChange({ step_type, config: { action_type: "", risk_class: "moderate" } });
  };

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-neutral-200 p-2">
      <select
        className={selectClassName}
        value={step.step_type}
        onChange={(e) => setType(e.target.value as WorkflowStepType)}
      >
        <option value="create_task">Create task</option>
        <option value="send_notification">Send notification</option>
        <option value="human_approval">Human approval</option>
      </select>
      {step.step_type === "create_task" && (
        <Input
          placeholder="Task title"
          value={(step.config.title as string) ?? ""}
          onChange={(e) => onChange({ ...step, config: { ...step.config, title: e.target.value } })}
          className="min-w-[200px] flex-1"
        />
      )}
      {step.step_type === "send_notification" && (
        <>
          <Input
            placeholder="Title"
            value={(step.config.title as string) ?? ""}
            onChange={(e) => onChange({ ...step, config: { ...step.config, title: e.target.value } })}
            className="min-w-[160px] flex-1"
          />
          <Input
            placeholder="Body"
            value={(step.config.body as string) ?? ""}
            onChange={(e) => onChange({ ...step, config: { ...step.config, body: e.target.value } })}
            className="min-w-[160px] flex-1"
          />
        </>
      )}
      {step.step_type === "human_approval" && (
        <>
          <Input
            placeholder="What needs approval?"
            value={(step.config.action_type as string) ?? ""}
            onChange={(e) =>
              onChange({ ...step, config: { ...step.config, action_type: e.target.value } })
            }
            className="min-w-[200px] flex-1"
          />
          <select
            className={selectClassName}
            value={(step.config.risk_class as string) ?? "moderate"}
            onChange={(e) =>
              onChange({ ...step, config: { ...step.config, risk_class: e.target.value } })
            }
          >
            <option value="low">Low risk</option>
            <option value="moderate">Moderate risk</option>
            <option value="high">High risk</option>
            <option value="critical">Critical risk</option>
          </select>
        </>
      )}
      <Button variant="outline" size="sm" onClick={onRemove}>
        Remove
      </Button>
    </div>
  );
}

function WorkflowsSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [steps, setSteps] = useState<WorkflowStep[]>([emptyStep()]);

  const { data: workflows } = useQuery<Workflow[]>({
    queryKey: ["automation", "workflows"],
    queryFn: () => apiFetch<Workflow[]>("/api/v1/automation/workflows"),
  });

  const createWorkflow = useMutation({
    mutationFn: () =>
      apiFetch<Workflow>("/api/v1/automation/workflows", {
        method: "POST",
        body: { name, steps },
      }),
    onSuccess: () => {
      setName("");
      setSteps([emptyStep()]);
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
          <Input placeholder="Workflow name" value={name} onChange={(e) => setName(e.target.value)} />
          <div className="flex flex-col gap-2">
            {steps.map((step, index) => (
              <StepEditor
                key={index}
                step={step}
                onChange={(updated) =>
                  setSteps((prev) => prev.map((s, i) => (i === index ? updated : s)))
                }
                onRemove={() => setSteps((prev) => prev.filter((_, i) => i !== index))}
              />
            ))}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setSteps((prev) => [...prev, emptyStep()])}>
              Add step
            </Button>
            <Button
              disabled={!name.trim() || steps.length === 0 || createWorkflow.isPending}
              onClick={() => createWorkflow.mutate()}
            >
              Create workflow (draft)
            </Button>
          </div>
          <p className="text-xs text-neutral-400">
            New workflows start as drafts. Steps can only be edited while a workflow is in draft
            status — publishing to active locks the steps (spec section 41).
          </p>
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
                    {workflow.version}
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

export default function AutomationPage() {
  return (
    <div>
      <PageHeader
        title="Business Automation"
        description="Workflow builder, runs, and the Human Approval hook — spec sections 36-43."
      />
      <WorkflowsSection />
    </div>
  );
}
