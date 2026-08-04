"use client";

import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Approval, Control, SecurityOverview, Task } from "@/lib/types";

function MetricCard({ title, value, description }: { title: string; value: string; description?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl">{value}</CardTitle>
      </CardHeader>
      {description && <CardContent className="text-sm text-neutral-500">{description}</CardContent>}
    </Card>
  );
}

export default function DashboardPage() {
  const { data: tasks } = useQuery<Task[]>({
    queryKey: ["tasks"],
    queryFn: () => apiFetch<Task[]>("/api/v1/tasks"),
  });
  const { data: approvals } = useQuery<Approval[]>({
    queryKey: ["approvals"],
    queryFn: () => apiFetch<Approval[]>("/api/v1/approvals"),
  });
  const { data: controls } = useQuery<Control[]>({
    queryKey: ["compliance", "controls"],
    queryFn: () => apiFetch<Control[]>("/api/v1/compliance/controls"),
  });
  const { data: securityOverview } = useQuery<SecurityOverview>({
    queryKey: ["security", "overview"],
    queryFn: () => apiFetch<SecurityOverview>("/api/v1/security/overview"),
  });

  const openTasks = tasks?.filter((t) => t.status === "open" || t.status === "in_progress").length;
  const pendingApprovals = approvals?.filter((a) => a.status === "pending").length;

  // Same implemented/total formula as the Onboarding readiness score's
  // Compliance dimension (app.onboarding.service._compliance_percent) —
  // one real number, not a second independently-drifting one.
  const complianceHealth =
    controls && controls.length > 0
      ? `${Math.round((100 * controls.filter((c) => c.status === "implemented").length) / controls.length)}%`
      : controls
        ? "No controls yet"
        : undefined;

  return (
    <div>
      <PageHeader
        title="Business Overview"
        description="Compliance, Security, Sales, and Support metrics appear here as each module ships (see docs/IMPLEMENTATION_PLAN.md)."
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard title="Open Tasks" value={openTasks !== undefined ? String(openTasks) : "—"} />
        <MetricCard
          title="Pending Approvals"
          value={pendingApprovals !== undefined ? String(pendingApprovals) : "—"}
        />
        <MetricCard title="Compliance Health" value={complianceHealth ?? "—"} />
        <MetricCard
          title="Security Posture"
          value={
            securityOverview !== undefined ? `${securityOverview.security_score}/100` : "—"
          }
        />
      </div>
    </div>
  );
}
