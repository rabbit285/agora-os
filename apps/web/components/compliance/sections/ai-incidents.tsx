"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { CreatePanel } from "@/components/create-panel";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CARD_LINK_FOCUS } from "@/lib/focus";
import { apiFetch } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import type {
  AIIncident,
  AISystem,
  Severity,
} from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm text-[var(--fg-default)] shadow-[var(--shadow-token-sm)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

/* AI incidents, shown with the systems they happened to.
 *
 * Previously on the Compliance page beside a second AI system inventory
 * that duplicated /ai-systems outright. */

export function AIIncidentsSection() {
  const queryClient = useQueryClient();
  const [aiSystemId, setAiSystemId] = useState("");
  const [title, setTitle] = useState("");
  const [severity, setSeverity] = useState<Severity>("low");

  const { data: aiSystems } = useQuery<AISystem[]>({
    queryKey: ["compliance", "ai-systems"],
    queryFn: () => apiFetch<AISystem[]>("/api/v1/compliance/ai-systems"),
  });

  const { data: incidents } = useQuery<AIIncident[]>({
    queryKey: ["compliance", "ai-incidents"],
    queryFn: () => apiFetch<AIIncident[]>("/api/v1/compliance/ai-incidents"),
  });

  const createIncident = useMutation({
    mutationFn: () =>
      apiFetch<AIIncident>("/api/v1/compliance/ai-incidents", {
        method: "POST",
        body: { ai_system_id: aiSystemId, title, severity },
      }),
    onSuccess: () => {
      setTitle("");
      setSeverity("low");
      queryClient.invalidateQueries({ queryKey: ["compliance", "ai-incidents"] });
    },
  });

  const aiSystemNames = new Map((aiSystems ?? []).map((s) => [s.id, s.name]));

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        AI Incidents
      </h2>
      <CreatePanel label="Log incident">
        <div className="flex flex-wrap gap-2">
          <select
            className={selectClassName}
            value={aiSystemId}
            onChange={(e) => setAiSystemId(e.target.value)}
          >
            <option value="">Select AI system…</option>
            {aiSystems?.map((system) => (
              <option key={system.id} value={system.id}>
                {system.name}
              </option>
            ))}
          </select>
          <Input
            placeholder="Incident title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="min-w-[200px] flex-1"
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
            disabled={!aiSystemId || !title.trim() || createIncident.isPending}
            onClick={() => createIncident.mutate()}
          >
            Log incident
          </Button>
        </div>
        <div className="pt-0 pb-4">
          <p className="text-xs text-[var(--fg-subtle)]">
            A critical incident automatically creates a linked Risk and response Task, and
            notifies the incident owner (EU AI Act Article 73 serious-incident obligations).
          </p>
        </div>
      </CreatePanel>
      {incidents?.length === 0 && (
        <EmptyState
          title="No AI incidents logged"
          description={"Log an incident when an AI system behaves in a way that caused, or could have caused, harm. Serious incidents carry reporting obligations under the EU AI Act."}
        />
      )}
      <div className="flex flex-col gap-2">
        {incidents?.map((incident) => (
          <Link key={incident.id} href={`/compliance/ai-incidents/${incident.id}`} className={CARD_LINK_FOCUS}>
            <Card className="transition-colors hover:border-[var(--border-strong)]">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-[var(--fg-default)]">{incident.title}</div>
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {aiSystemNames.get(incident.ai_system_id) ?? "Unknown system"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={incident.severity} />
                  <StatusBadge status={incident.status} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
