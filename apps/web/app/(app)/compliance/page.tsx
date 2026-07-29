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
import type { Control, Framework, Risk } from "@/lib/types";

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
      <FrameworksSection />
    </div>
  );
}
