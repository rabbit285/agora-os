"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { AIRiskClassification, AISystem, Control, Framework, Risk } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400";

function ControlsSection() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");

  const { data: controls } = useQuery<Control[]>({
    queryKey: ["compliance", "controls"],
    queryFn: () => apiFetch<Control[]>("/api/v1/compliance/controls"),
  });

  const createControl = useMutation({
    mutationFn: (newTitle: string) =>
      apiFetch<Control>("/api/v1/compliance/controls", { method: "POST", body: { title: newTitle } }),
    onSuccess: () => {
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "controls"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Controls
      </h2>
      <Card className="mb-4">
        <CardContent className="flex gap-2 pt-6">
          <Input
            placeholder="New control title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && title.trim()) createControl.mutate(title.trim());
            }}
          />
          <Button disabled={!title.trim() || createControl.isPending} onClick={() => createControl.mutate(title.trim())}>
            Add control
          </Button>
        </CardContent>
      </Card>
      {controls?.length === 0 && <p className="text-sm text-neutral-500">No controls yet.</p>}
      <div className="flex flex-col gap-2">
        {controls?.map((control) => (
          <Link key={control.id} href={`/compliance/controls/${control.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div className="font-medium text-neutral-900">{control.title}</div>
                <StatusBadge status={control.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function RisksSection() {
  const { data: risks } = useQuery<Risk[]>({
    queryKey: ["compliance", "risks"],
    queryFn: () => apiFetch<Risk[]>("/api/v1/compliance/risks"),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Risk Register
      </h2>
      {risks?.length === 0 && <p className="text-sm text-neutral-500">No risks recorded.</p>}
      <div className="flex flex-col gap-2">
        {risks?.map((risk) => (
          <Card key={risk.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-neutral-900">{risk.title}</div>
                <div className="mt-1 flex gap-2">
                  <Badge variant="outline">likelihood: {risk.likelihood}</Badge>
                  <Badge variant="outline">impact: {risk.impact}</Badge>
                </div>
              </div>
              <StatusBadge status={risk.status} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function AISystemsSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [riskClassification, setRiskClassification] = useState<AIRiskClassification>("minimal");

  const { data: aiSystems } = useQuery<AISystem[]>({
    queryKey: ["compliance", "ai-systems"],
    queryFn: () => apiFetch<AISystem[]>("/api/v1/compliance/ai-systems"),
  });

  const registerSystem = useMutation({
    mutationFn: () =>
      apiFetch<AISystem>("/api/v1/compliance/ai-systems", {
        method: "POST",
        body: { name, purpose, risk_classification: riskClassification },
      }),
    onSuccess: () => {
      setName("");
      setPurpose("");
      setRiskClassification("minimal");
      queryClient.invalidateQueries({ queryKey: ["compliance", "ai-systems"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        AI System Inventory
      </h2>
      <Card className="mb-4">
        <CardContent className="flex flex-wrap gap-2 pt-6">
          <Input
            placeholder="System name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <Input
            placeholder="Purpose"
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            className="min-w-[200px] flex-1"
          />
          <select
            className={selectClassName}
            value={riskClassification}
            onChange={(e) => setRiskClassification(e.target.value as AIRiskClassification)}
          >
            <option value="minimal">Minimal risk</option>
            <option value="limited">Limited risk</option>
            <option value="high">High risk</option>
            <option value="unacceptable">Unacceptable risk</option>
          </select>
          <Button
            disabled={!name.trim() || !purpose.trim() || registerSystem.isPending}
            onClick={() => registerSystem.mutate()}
          >
            Register AI system
          </Button>
        </CardContent>
        <CardContent className="pt-0 pb-4">
          <p className="text-xs text-neutral-400">
            High or unacceptable-risk systems automatically require an Approval before they can be
            marked approved (spec section 69 — New AI Tool Adoption).
          </p>
        </CardContent>
      </Card>
      {aiSystems?.length === 0 && (
        <p className="text-sm text-neutral-500">No AI systems registered yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {aiSystems?.map((system) => (
          <Link key={system.id} href={`/compliance/ai-systems/${system.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{system.name}</div>
                  {system.vendor && (
                    <div className="text-xs text-neutral-400">{system.vendor}</div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <StatusBadge status={system.risk_classification} />
                  <StatusBadge status={system.status} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function FrameworksSection() {
  const { data: frameworks } = useQuery<Framework[]>({
    queryKey: ["compliance", "frameworks"],
    queryFn: () => apiFetch<Framework[]>("/api/v1/compliance/frameworks"),
  });

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Frameworks
      </h2>
      <div className="flex flex-wrap gap-2">
        {frameworks?.map((framework) => (
          <Badge key={framework.id} variant="secondary">
            {framework.name}
          </Badge>
        ))}
      </div>
    </div>
  );
}

export default function CompliancePage() {
  return (
    <div>
      <PageHeader
        title="Compliance"
        description="Frameworks, controls, evidence, and risk — spec section 12."
      />
      <ControlsSection />
      <RisksSection />
      <AISystemsSection />
      <FrameworksSection />
    </div>
  );
}
