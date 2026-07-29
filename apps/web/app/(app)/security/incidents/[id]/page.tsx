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
import type { Risk, SecurityIncident, SecurityIncidentStatus } from "@/lib/types";

const WORKFLOW: SecurityIncidentStatus[] = [
  "detected",
  "triage",
  "investigation",
  "containment",
  "eradication",
  "recovery",
  "postmortem",
  "closed",
];

export default function IncidentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: incident } = useQuery<SecurityIncident>({
    queryKey: ["security", "incidents", id],
    queryFn: () => apiFetch<SecurityIncident>(`/api/v1/security/incidents/${id}`),
  });

  const { data: risks } = useQuery<Risk[]>({
    queryKey: ["compliance", "risks"],
    queryFn: () => apiFetch<Risk[]>("/api/v1/compliance/risks"),
    enabled: !!incident?.related_risk_id,
  });

  const advanceStatus = useMutation({
    mutationFn: (status: SecurityIncidentStatus) =>
      apiFetch(`/api/v1/security/incidents/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["security", "incidents", id] }),
  });

  if (!incident) return null;

  const linkedRisk = risks?.find((r) => r.id === incident.related_risk_id);
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
        <Card>
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Linked Compliance Risk
            </h2>
            <p className="text-xs text-neutral-400 mb-2">
              Critical security incidents automatically create a linked risk so GDPR breach
              notification obligations are tracked (spec section 19).
            </p>
            {linkedRisk ? (
              <Link
                href="/compliance"
                className="text-sm text-neutral-700 hover:underline"
              >
                {linkedRisk.title}
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
