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
import type { SecurityFinding } from "@/lib/types";

type AlertDetail = {
  id: string;
  title: string;
  description: string | null;
  severity: "low" | "medium" | "high" | "critical";
  status: "new" | "investigating" | "contained" | "resolved" | "false_positive";
  finding_id: string | null;
  created_at: string;
  finding: SecurityFinding | null;
};

const WORKFLOW = ["new", "investigating", "contained", "resolved"] as const;

export default function AlertDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: alert, isLoading } = useQuery<AlertDetail>({
    queryKey: ["security", "alerts", id],
    queryFn: () => apiFetch<AlertDetail>(`/api/v1/security/alerts/${id}`),
  });

  const advanceStatus = useMutation({
    mutationFn: (status: string) =>
      apiFetch(`/api/v1/security/alerts/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security", "alerts", id] });
      queryClient.invalidateQueries({ queryKey: ["security", "alerts"] });
      queryClient.invalidateQueries({ queryKey: ["security", "overview"] });
    },
  });

  if (isLoading) return <p className="text-sm text-neutral-500">Loading alert…</p>;
  if (!alert) return <p className="text-sm text-neutral-500">Alert not found.</p>;

  const currentIndex = WORKFLOW.indexOf(alert.status as (typeof WORKFLOW)[number]);
  const nextStatus = WORKFLOW[currentIndex + 1];

  return (
    <div>
      <PageHeader
        title={alert.title}
        description={alert.description ?? undefined}
        actions={<SeverityBadge severity={alert.severity} />}
      />

      <div className="mb-6 flex items-center gap-3">
        <span className="text-sm text-neutral-500">Status:</span>
        <StatusBadge status={alert.status} />
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
        {alert.status !== "false_positive" && alert.status !== "resolved" && (
          <Button
            size="sm"
            variant="ghost"
            disabled={advanceStatus.isPending}
            onClick={() => advanceStatus.mutate("false_positive")}
          >
            Mark false positive
          </Button>
        )}
      </div>

      {alert.finding && (
        <Card>
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Related Finding
            </h2>
            <Link
              href="/security"
              className="text-sm text-neutral-700 hover:underline"
            >
              {alert.finding.title}
            </Link>
            <div className="mt-2 flex gap-2">
              <SeverityBadge severity={alert.finding.severity} />
              <StatusBadge status={alert.finding.status} />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
