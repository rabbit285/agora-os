"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  type Edge,
  MiniMap,
  type Node,
  type NodeChange,
  ReactFlow,
  applyNodeChanges,
} from "@xyflow/react";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { WorkflowStep, WorkflowStepType } from "@/lib/types";
import { WORKFLOW_STEP_TYPES } from "@/lib/types";

const NODE_WIDTH = 260;
const NODE_HEIGHT = 70;
const V_GAP = 110;

const selectClassName =
  "flex h-9 w-full rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

function stepsToNodes(steps: WorkflowStep[]): Node[] {
  return steps.map((step, index) => ({
    id: String(index),
    position: { x: 40, y: index * V_GAP },
    data: { label: `${index + 1}. ${step.step_type.replace(/_/g, " ")}` },
    style: {
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontSize: 13,
      textAlign: "center" as const,
      borderRadius: 8,
    },
  }));
}

function stepsToEdges(steps: WorkflowStep[]): Edge[] {
  const edges: Edge[] = [];
  for (let i = 0; i < steps.length - 1; i++) {
    edges.push({ id: `e${i}-${i + 1}`, source: String(i), target: String(i + 1) });
  }
  return edges;
}

/** Real, genuinely-configurable fields for the steps a user most commonly
 * builds with; every other step type falls back to a raw JSON config
 * editor rather than a bespoke form for all 26 types. */
function StepConfigForm({
  step,
  onChange,
}: {
  step: WorkflowStep;
  onChange: (config: Record<string, unknown>) => void;
}) {
  const config = step.config;
  switch (step.step_type) {
    case "create_task":
      return (
        <Input
          placeholder="Task title"
          value={(config.title as string) ?? ""}
          onChange={(e) => onChange({ ...config, title: e.target.value })}
        />
      );
    case "send_notification":
      return (
        <div className="flex flex-col gap-2">
          <Input
            placeholder="Title"
            value={(config.title as string) ?? ""}
            onChange={(e) => onChange({ ...config, title: e.target.value })}
          />
          <Input
            placeholder="Body"
            value={(config.body as string) ?? ""}
            onChange={(e) => onChange({ ...config, body: e.target.value })}
          />
        </div>
      );
    case "human_approval":
      return (
        <div className="flex flex-col gap-2">
          <Input
            placeholder="What needs approval?"
            value={(config.action_type as string) ?? ""}
            onChange={(e) => onChange({ ...config, action_type: e.target.value })}
          />
          <select
            className={selectClassName}
            value={(config.risk_class as string) ?? "moderate"}
            onChange={(e) => onChange({ ...config, risk_class: e.target.value })}
          >
            <option value="low">Low risk</option>
            <option value="moderate">Moderate risk</option>
            <option value="high">High risk</option>
            <option value="critical">Critical risk</option>
          </select>
        </div>
      );
    case "delay":
      return (
        <Input
          type="number"
          placeholder="Seconds to wait"
          value={(config.seconds as number) ?? 0}
          onChange={(e) => onChange({ ...config, seconds: Number(e.target.value) })}
        />
      );
    case "condition":
      return (
        <div className="flex flex-col gap-2">
          <Input
            placeholder="Trigger payload field name"
            value={(config.field as string) ?? ""}
            onChange={(e) => onChange({ ...config, field: e.target.value })}
          />
          <select
            className={selectClassName}
            value={(config.operator as string) ?? "equals"}
            onChange={(e) => onChange({ ...config, operator: e.target.value })}
          >
            <option value="equals">equals</option>
            <option value="not_equals">not equals</option>
            <option value="contains">contains</option>
          </select>
          <Input
            placeholder="Expected value"
            value={(config.value as string) ?? ""}
            onChange={(e) => onChange({ ...config, value: e.target.value })}
          />
        </div>
      );
    case "call_api":
    case "webhook":
      return (
        <div className="flex flex-col gap-2">
          <Input
            placeholder="URL"
            value={(config.url as string) ?? ""}
            onChange={(e) => onChange({ ...config, url: e.target.value })}
          />
          {step.step_type === "call_api" && (
            <select
              className={selectClassName}
              value={(config.method as string) ?? "GET"}
              onChange={(e) => onChange({ ...config, method: e.target.value })}
            >
              <option value="GET">GET</option>
              <option value="POST">POST</option>
              <option value="PUT">PUT</option>
              <option value="PATCH">PATCH</option>
            </select>
          )}
        </div>
      );
    default:
      return (
        <div>
          <p className="mb-1 text-xs text-[var(--fg-subtle)]">
            Raw JSON config (no dedicated form for this step type yet)
          </p>
          <Textarea
            value={JSON.stringify(config, null, 2)}
            onChange={(e) => {
              try {
                onChange(JSON.parse(e.target.value || "{}"));
              } catch {
                // Ignore invalid JSON while the user is still typing —
                // the last valid parse stays in effect.
              }
            }}
            className="font-mono text-xs"
            rows={6}
          />
        </div>
      );
  }
}

export function StepBuilder({
  steps,
  onSave,
  saving,
}: {
  steps: WorkflowStep[];
  onSave: (steps: WorkflowStep[]) => void;
  saving: boolean;
}) {
  const [localSteps, setLocalSteps] = useState<WorkflowStep[]>(steps);
  const [nodes, setNodes] = useState<Node[]>(() => stepsToNodes(steps));
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  const edges = useMemo(() => stepsToEdges(localSteps), [localSteps]);

  const onNodesChange = (changes: NodeChange[]) => {
    setNodes((current) => applyNodeChanges(changes, current));
  };

  const onNodeDragStop = () => {
    // Real drag-and-drop reordering: whichever node ended up highest (by
    // y position) becomes step 1, and so on — then snap every node back
    // onto the standard vertical grid at its new index.
    const order = [...nodes].sort((a, b) => a.position.y - b.position.y).map((n) => Number(n.id));
    const reordered = order.map((i) => localSteps[i]);
    setLocalSteps(reordered);
    setNodes(stepsToNodes(reordered));
    setSelectedIndex(null);
  };

  const addStep = () => {
    const next = [...localSteps, { step_type: "create_task" as WorkflowStepType, config: {} }];
    setLocalSteps(next);
    setNodes(stepsToNodes(next));
  };

  const removeStep = (index: number) => {
    const next = localSteps.filter((_, i) => i !== index);
    setLocalSteps(next);
    setNodes(stepsToNodes(next));
    setSelectedIndex(null);
  };

  const updateStep = (index: number, updated: WorkflowStep) => {
    const next = localSteps.map((s, i) => (i === index ? updated : s));
    setLocalSteps(next);
    setNodes(stepsToNodes(next));
  };

  return (
    <div className="flex flex-col gap-3">
      <div style={{ height: 400 }} className="rounded-md border border-[var(--border-default)]">
        <ReactFlow
          nodes={nodes.map((n) => ({
            ...n,
            selected: Number(n.id) === selectedIndex,
          }))}
          edges={edges}
          onNodesChange={onNodesChange}
          onNodeDragStop={onNodeDragStop}
          onNodeClick={(_, node) => setSelectedIndex(Number(node.id))}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={addStep}>
          Add step
        </Button>
        <Button
          size="sm"
          disabled={localSteps.length === 0 || saving}
          onClick={() => onSave(localSteps)}
        >
          Save steps
        </Button>
      </div>
      {selectedIndex !== null && localSteps[selectedIndex] && (
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <div className="flex items-center justify-between">
              <Badge variant="outline">Step {selectedIndex + 1}</Badge>
              <Button size="sm" variant="ghost" onClick={() => removeStep(selectedIndex)}>
                Remove step
              </Button>
            </div>
            <select
              className={selectClassName}
              value={localSteps[selectedIndex].step_type}
              onChange={(e) =>
                updateStep(selectedIndex, {
                  step_type: e.target.value as WorkflowStepType,
                  config: {},
                })
              }
            >
              {WORKFLOW_STEP_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type.replace(/_/g, " ")}
                </option>
              ))}
            </select>
            <StepConfigForm
              step={localSteps[selectedIndex]}
              onChange={(config) =>
                updateStep(selectedIndex, { ...localSteps[selectedIndex], config })
              }
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
