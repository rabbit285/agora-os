"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { CardSkeleton } from "@/components/loading-skeleton";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type {
  CloudScanResult,
  SecurityAlert,
  SecurityAsset,
  SecurityFinding,
  SecurityIncident,
  SecurityOverview,
} from "@/lib/types";

function metricStatus(value: number, kind: "lower-is-better" | "higher-is-better") {
  if (kind === "higher-is-better") {
    return value >= 80 ? "success" : value >= 50 ? "warning" : "critical";
  }
  return value === 0 ? "success" : value > 5 ? "critical" : "warning";
}

function OverviewSection() {
  const { data: overview, isLoading } = useQuery<SecurityOverview>({
    queryKey: ["security", "overview"],
    queryFn: () => apiFetch<SecurityOverview>("/api/v1/security/overview"),
  });

  const queryClient = useQueryClient();
  const runScan = useMutation({
    mutationFn: () => apiFetch<CloudScanResult>("/api/v1/security/cloud-scan", { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["security"] });
    },
  });

  return (
    <div className="mb-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Security Overview
        </h2>
        <Button
          size="sm"
          variant="outline"
          disabled={runScan.isPending}
          onClick={() => runScan.mutate()}
        >
          {runScan.isPending ? "Scanning…" : "Run cloud scan"}
        </Button>
      </div>
      {runScan.data && (
        <p className="mb-3 text-xs text-[var(--fg-muted)]">
          {runScan.data.configured
            ? `Scan complete: ${runScan.data.checks_run.length} checks run, ${runScan.data.findings_created} finding(s) created.`
            : "AWS credentials are not configured for this organization — cloud scanning is unavailable until AWS_SECURITY_SCAN_ACCESS_KEY_ID/SECRET are set."}
        </p>
      )}
      {isLoading && <CardSkeleton />}
      {overview && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <MetricCard
            label="Security Score"
            value={`${overview.security_score}/100`}
            status={metricStatus(overview.security_score, "higher-is-better")}
          />
          <MetricCard
            label="Critical Alerts"
            value={String(overview.critical_alerts)}
            status={metricStatus(overview.critical_alerts, "lower-is-better")}
          />
          <MetricCard
            label="High Risks"
            value={String(overview.high_risks)}
            status={metricStatus(overview.high_risks, "lower-is-better")}
          />
          <MetricCard label="Assets Monitored" value={String(overview.assets_monitored)} />
          <MetricCard
            label="Vulnerabilities"
            value={String(overview.vulnerabilities_open)}
            status={metricStatus(overview.vulnerabilities_open, "lower-is-better")}
          />
          <MetricCard
            label="Identity Issues"
            value={String(overview.identity_issues_open)}
            status={metricStatus(overview.identity_issues_open, "lower-is-better")}
          />
          <MetricCard
            label="Cloud Misconfigurations"
            value={String(overview.cloud_misconfigurations_open)}
            status={metricStatus(overview.cloud_misconfigurations_open, "lower-is-better")}
          />
          <MetricCard
            label="Open Incidents"
            value={String(overview.open_incidents)}
            status={metricStatus(overview.open_incidents, "lower-is-better")}
          />
          <MetricCard
            label="Evidence Coverage"
            value={`${overview.evidence_coverage_percent}%`}
            status={metricStatus(overview.evidence_coverage_percent, "higher-is-better")}
          />
        </div>
      )}
    </div>
  );
}

function AssetsSection() {
  const router = useRouter();
  const { data: assets, isLoading, error, refetch } = useQuery<SecurityAsset[]>({
    queryKey: ["security", "assets"],
    queryFn: () => apiFetch<SecurityAsset[]>("/api/v1/security/assets"),
  });

  const columns: DataTableColumn<SecurityAsset>[] = [
    {
      key: "name",
      header: "Asset",
      render: (asset) => <span className="font-medium">{asset.name}</span>,
      sortValue: (asset) => asset.name.toLowerCase(),
    },
    {
      key: "type",
      header: "Type",
      render: (asset) => (
        <span className="text-[var(--fg-muted)]">
          {asset.asset_type}
          {asset.provider ? ` · ${asset.provider}` : ""}
          {asset.internet_exposed ? " · internet-exposed" : ""}
        </span>
      ),
    },
    {
      key: "criticality",
      header: "Criticality",
      render: (asset) => <SeverityBadge severity={asset.criticality} />,
    },
    {
      key: "status",
      header: "Status",
      render: (asset) => <StatusBadge status={asset.status} />,
    },
  ];

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Asset Inventory
      </h2>
      <DataTable
        columns={columns}
        data={assets}
        getRowId={(asset) => asset.id}
        onRowClick={(asset) => router.push(`/security/assets/${asset.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No assets tracked yet"
      />
    </div>
  );
}

function FindingsSection() {
  const { data: findings, isLoading, error, refetch } = useQuery<SecurityFinding[]>({
    queryKey: ["security", "findings"],
    queryFn: () => apiFetch<SecurityFinding[]>("/api/v1/security/findings"),
  });

  const columns: DataTableColumn<SecurityFinding>[] = [
    {
      key: "title",
      header: "Finding",
      render: (finding) => (
        <div className="flex flex-col gap-1">
          <span className="font-medium">{finding.title}</span>
          <Badge variant="outline" className="w-fit capitalize">
            {finding.category.replace(/_/g, " ")}
          </Badge>
        </div>
      ),
      sortValue: (finding) => finding.title.toLowerCase(),
    },
    {
      key: "severity",
      header: "Severity",
      render: (finding) => <SeverityBadge severity={finding.severity} />,
    },
    {
      key: "status",
      header: "Status",
      render: (finding) => <StatusBadge status={finding.status} />,
    },
  ];

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Findings
      </h2>
      <DataTable
        columns={columns}
        data={findings}
        getRowId={(finding) => finding.id}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No findings recorded"
      />
    </div>
  );
}

function AlertsSection() {
  const router = useRouter();
  const { data: alerts, isLoading, error, refetch } = useQuery<SecurityAlert[]>({
    queryKey: ["security", "alerts"],
    queryFn: () => apiFetch<SecurityAlert[]>("/api/v1/security/alerts"),
  });

  const columns: DataTableColumn<SecurityAlert>[] = [
    {
      key: "title",
      header: "Alert",
      render: (alert) => <span className="font-medium">{alert.title}</span>,
      sortValue: (alert) => alert.title.toLowerCase(),
    },
    {
      key: "severity",
      header: "Severity",
      render: (alert) => <SeverityBadge severity={alert.severity} />,
    },
    {
      key: "status",
      header: "Status",
      render: (alert) => <StatusBadge status={alert.status} />,
    },
  ];

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Alerts
      </h2>
      <DataTable
        columns={columns}
        data={alerts}
        getRowId={(alert) => alert.id}
        onRowClick={(alert) => router.push(`/security/alerts/${alert.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No alerts"
      />
    </div>
  );
}

function IncidentsSection() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");

  const { data: incidents, isLoading, error, refetch } = useQuery<SecurityIncident[]>({
    queryKey: ["security", "incidents"],
    queryFn: () => apiFetch<SecurityIncident[]>("/api/v1/security/incidents"),
  });

  const createIncident = useMutation({
    mutationFn: (newTitle: string) =>
      apiFetch<SecurityIncident>("/api/v1/security/incidents", {
        method: "POST",
        body: { title: newTitle, severity: "high" },
      }),
    onSuccess: () => {
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["security", "incidents"] });
      queryClient.invalidateQueries({ queryKey: ["compliance", "risks"] });
    },
  });

  const columns: DataTableColumn<SecurityIncident>[] = [
    {
      key: "title",
      header: "Incident",
      render: (incident) => (
        <div className="flex flex-col">
          <span className="font-medium">{incident.title}</span>
          {incident.related_risk_id && (
            <span className="text-xs text-[var(--fg-subtle)]">
              Linked to Compliance risk register
            </span>
          )}
        </div>
      ),
      sortValue: (incident) => incident.title.toLowerCase(),
    },
    {
      key: "severity",
      header: "Severity",
      render: (incident) => <SeverityBadge severity={incident.severity} />,
    },
    {
      key: "status",
      header: "Status",
      render: (incident) => <StatusBadge status={incident.status} />,
    },
  ];

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Incidents
      </h2>
      <Card className="mb-4">
        <CardContent className="flex gap-2 pt-5">
          <Input
            placeholder="New incident title (severity: high)"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && title.trim()) createIncident.mutate(title.trim());
            }}
          />
          <Button
            disabled={!title.trim() || createIncident.isPending}
            onClick={() => createIncident.mutate(title.trim())}
          >
            Open incident
          </Button>
        </CardContent>
      </Card>
      <DataTable
        columns={columns}
        data={incidents}
        getRowId={(incident) => incident.id}
        onRowClick={(incident) => router.push(`/security/incidents/${incident.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No incidents"
      />
    </div>
  );
}

export default function SecurityPage() {
  return (
    <div>
      <PageHeader
        title="Security"
        description="Asset inventory, findings, alerts, and incident response."
        actions={
          <Link href="/security/policies">
            <Button variant="outline" size="sm">
              Security Policies
            </Button>
          </Link>
        }
      />
      <OverviewSection />
      <AssetsSection />
      <FindingsSection />
      <AlertsSection />
      <IncidentsSection />
    </div>
  );
}
