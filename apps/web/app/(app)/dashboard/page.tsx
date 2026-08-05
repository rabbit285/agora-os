"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Briefcase,
  CheckCircle2,
  ClipboardCheck,
  Headset,
  ScrollText,
  ShieldAlert,
  Workflow as WorkflowIcon,
} from "lucide-react";

import { ActivityTimeline, type ActivityEntry } from "@/components/activity-timeline";
import { EmptyState } from "@/components/empty-state";
import { InsightCard } from "@/components/insight-card";
import { CardSkeleton } from "@/components/loading-skeleton";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { RiskBadge } from "@/components/risk-badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type {
  Approval,
  Briefing,
  Control,
  Recommendation,
  SalesIntelligence,
  SecurityOverview,
  SupportAnalytics,
  Task,
  WorkflowAnalytics,
} from "@/lib/types";

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
  const { data: salesIntelligence } = useQuery<SalesIntelligence>({
    queryKey: ["sales", "intelligence"],
    queryFn: () => apiFetch<SalesIntelligence>("/api/v1/sales/intelligence"),
  });
  const { data: supportAnalytics } = useQuery<SupportAnalytics>({
    queryKey: ["support", "analytics"],
    queryFn: () => apiFetch<SupportAnalytics>("/api/v1/support/analytics"),
  });
  const { data: workflowAnalytics } = useQuery<WorkflowAnalytics>({
    queryKey: ["automation", "analytics"],
    queryFn: () => apiFetch<WorkflowAnalytics>("/api/v1/automation/analytics"),
  });
  const { data: briefing, isLoading: briefingLoading } = useQuery<Briefing>({
    queryKey: ["briefing"],
    queryFn: () => apiFetch<Briefing>("/api/v1/briefing"),
  });
  const { data: recommendations, isLoading: recommendationsLoading } = useQuery<Recommendation[]>({
    queryKey: ["recommendations"],
    queryFn: () => apiFetch<Recommendation[]>("/api/v1/recommendations"),
  });

  const openTasks = tasks?.filter((t) => t.status === "open" || t.status === "in_progress");
  const urgentTasks = openTasks?.filter((t) => t.priority === "urgent" || t.priority === "high");
  const pendingApprovals = approvals?.filter((a) => a.status === "pending");

  const complianceHealth =
    controls && controls.length > 0
      ? Math.round((100 * controls.filter((c) => c.status === "implemented").length) / controls.length)
      : undefined;

  const openRecommendations = recommendations?.filter((r) => r.status === "pending");

  const totalPipelineValue = salesIntelligence
    ? Object.values(salesIntelligence.pipeline_value_by_stage).reduce((sum, v) => sum + v, 0)
    : undefined;

  const activityEntries: ActivityEntry[] = [
    ...(tasks ?? []).slice(0, 5).map(
      (t): ActivityEntry => ({
        id: `task-${t.id}`,
        label: `Task created: ${t.title}`,
        description: t.module,
        timestamp: t.created_at,
      }),
    ),
    ...(approvals ?? [])
      .filter((a) => a.decided_at)
      .slice(0, 5)
      .map(
        (a): ActivityEntry => ({
          id: `approval-${a.id}`,
          label: `${a.action_type.replace(/_/g, " ")} — ${a.status}`,
          description: a.module ?? undefined,
          timestamp: a.decided_at!,
        }),
      ),
  ]
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    .slice(0, 6);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Command Center"
        description="Your organization's compliance, security, sales, support, and automation posture in one view."
      />

      {briefingLoading ? (
        <CardSkeleton />
      ) : (
        briefing?.ai_suggestion && (
          <InsightCard title="Today's AI briefing" reason={briefing.ai_suggestion} />
        )
      )}
      {briefing && (
        <Link
          href="/briefing"
          className="-mt-4 self-start text-xs text-[var(--brand-primary)] hover:underline"
        >
          View full daily briefing →
        </Link>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <MetricCard
          label="Open Tasks"
          value={openTasks !== undefined ? String(openTasks.length) : "—"}
          status={urgentTasks && urgentTasks.length > 0 ? "warning" : "neutral"}
          description={urgentTasks && urgentTasks.length > 0 ? `${urgentTasks.length} high priority` : undefined}
          icon={ClipboardCheck}
          href="/tasks"
        />
        <MetricCard
          label="Pending Approvals"
          value={pendingApprovals !== undefined ? String(pendingApprovals.length) : "—"}
          status={pendingApprovals && pendingApprovals.length > 0 ? "warning" : "success"}
          icon={ShieldAlert}
          href="/approvals"
        />
        <MetricCard
          label="Compliance Health"
          value={
            complianceHealth !== undefined ? `${complianceHealth}%` : controls ? "No controls yet" : "—"
          }
          status={
            complianceHealth === undefined
              ? "neutral"
              : complianceHealth >= 80
                ? "success"
                : complianceHealth >= 50
                  ? "warning"
                  : "critical"
          }
          icon={ScrollText}
          href="/compliance"
        />
        <MetricCard
          label="Security Posture"
          value={securityOverview !== undefined ? `${securityOverview.security_score}/100` : "—"}
          status={
            securityOverview === undefined
              ? "neutral"
              : securityOverview.security_score >= 80
                ? "success"
                : securityOverview.security_score >= 50
                  ? "warning"
                  : "critical"
          }
          description={
            securityOverview && securityOverview.critical_alerts > 0
              ? `${securityOverview.critical_alerts} critical alerts`
              : undefined
          }
          icon={ShieldAlert}
          href="/security"
        />
        <MetricCard
          label="Sales Pipeline"
          value={totalPipelineValue !== undefined ? `€${Math.round(totalPipelineValue).toLocaleString()}` : "—"}
          description={
            salesIntelligence ? `${salesIntelligence.win_rate_percent}% win rate` : undefined
          }
          icon={Briefcase}
          href="/sales"
        />
        <MetricCard
          label="Open Tickets"
          value={supportAnalytics !== undefined ? String(supportAnalytics.open_tickets) : "—"}
          status={
            supportAnalytics === undefined
              ? "neutral"
              : supportAnalytics.open_tickets === 0
                ? "success"
                : "neutral"
          }
          description={
            supportAnalytics ? `${supportAnalytics.average_resolution_hours}h avg resolution` : undefined
          }
          icon={Headset}
          href="/support"
        />
        <MetricCard
          label="Active Workflows"
          value={workflowAnalytics !== undefined ? String(workflowAnalytics.active_workflows) : "—"}
          icon={WorkflowIcon}
          href="/automation"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-[var(--fg-default)]">Pending approvals</h2>
            <Link href="/approvals" className="text-xs text-[var(--brand-primary)] hover:underline">
              View all
            </Link>
          </div>
          {!approvals ? (
            <CardSkeleton />
          ) : pendingApprovals && pendingApprovals.length > 0 ? (
            <Card>
              <CardContent className="flex flex-col divide-y divide-[var(--border-default)] pt-5 [&>*:not(:first-child)]:pt-3 [&>*:not(:last-child)]:pb-3">
                {pendingApprovals.slice(0, 5).map((approval) => (
                  <Link
                    key={approval.id}
                    href="/approvals"
                    className="flex items-center justify-between gap-3 rounded-[var(--radius-sm)] transition-colors hover:bg-[var(--bg-surface-hover)]"
                  >
                    <div className="flex flex-col">
                      <span className="text-sm text-[var(--fg-default)]">
                        {approval.action_type.replace(/_/g, " ")}
                      </span>
                      {approval.module && (
                        <span className="text-xs capitalize text-[var(--fg-subtle)]">{approval.module}</span>
                      )}
                    </div>
                    <RiskBadge riskClass={approval.risk_class} />
                  </Link>
                ))}
              </CardContent>
            </Card>
          ) : (
            <EmptyState icon={ClipboardCheck} title="No pending approvals" description="You're all caught up." />
          )}
        </div>

        <div className="flex flex-col gap-3">
          <h2 className="text-sm font-semibold text-[var(--fg-default)]">Recent activity</h2>
          {!tasks && !approvals ? (
            <CardSkeleton />
          ) : (
            <Card>
              <CardContent className="pt-5">
                <ActivityTimeline entries={activityEntries} />
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[var(--fg-default)]">AI recommendations</h2>
          <Link href="/recommendations" className="text-xs text-[var(--brand-primary)] hover:underline">
            View all
          </Link>
        </div>
        {recommendationsLoading ? (
          <CardSkeleton />
        ) : openRecommendations && openRecommendations.length > 0 ? (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {openRecommendations.slice(0, 4).map((rec) => (
              <InsightCard
                key={rec.id}
                title={rec.title}
                reason={rec.reason}
                sources={rec.sources}
                confidence={
                  rec.confidence === "low" || rec.confidence === "medium" || rec.confidence === "high"
                    ? rec.confidence
                    : undefined
                }
                suggestedAction={rec.suggested_action}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            title="No open recommendations"
            description="New AI recommendations will appear here as they're generated."
          />
        )}
      </div>

      {pendingApprovals && pendingApprovals.length === 0 && openRecommendations?.length === 0 && (
        <div className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-4 py-3 text-xs text-[var(--fg-subtle)]">
          <CheckCircle2 className="h-3.5 w-3.5 text-[var(--success-600)]" aria-hidden="true" />
          Nothing needs your attention right now.
        </div>
      )}
    </div>
  );
}
