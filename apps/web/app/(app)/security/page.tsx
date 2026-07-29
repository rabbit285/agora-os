"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type {
  SecurityAlert,
  SecurityAsset,
  SecurityFinding,
  SecurityIncident,
} from "@/lib/types";

function AssetsSection() {
  const { data: assets } = useQuery<SecurityAsset[]>({
    queryKey: ["security", "assets"],
    queryFn: () => apiFetch<SecurityAsset[]>("/api/v1/security/assets"),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Asset Inventory
      </h2>
      {assets?.length === 0 && <p className="text-sm text-neutral-500">No assets tracked yet.</p>}
      <div className="flex flex-col gap-2">
        {assets?.map((asset) => (
          <Card key={asset.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-neutral-900">{asset.name}</div>
                <div className="text-xs text-neutral-400">
                  {asset.asset_type} {asset.provider ? `· ${asset.provider}` : ""}
                  {asset.internet_exposed ? " · internet-exposed" : ""}
                </div>
              </div>
              <div className="flex gap-2">
                <SeverityBadge severity={asset.criticality} />
                <StatusBadge status={asset.status} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function FindingsSection() {
  const { data: findings } = useQuery<SecurityFinding[]>({
    queryKey: ["security", "findings"],
    queryFn: () => apiFetch<SecurityFinding[]>("/api/v1/security/findings"),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Findings
      </h2>
      {findings?.length === 0 && <p className="text-sm text-neutral-500">No findings recorded.</p>}
      <div className="flex flex-col gap-2">
        {findings?.map((finding) => (
          <Card key={finding.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <div className="font-medium text-neutral-900">{finding.title}</div>
                <Badge variant="outline">{finding.category.replace(/_/g, " ")}</Badge>
              </div>
              <div className="flex gap-2">
                <SeverityBadge severity={finding.severity} />
                <StatusBadge status={finding.status} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function AlertsSection() {
  const { data: alerts } = useQuery<SecurityAlert[]>({
    queryKey: ["security", "alerts"],
    queryFn: () => apiFetch<SecurityAlert[]>("/api/v1/security/alerts"),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Alerts
      </h2>
      {alerts?.length === 0 && <p className="text-sm text-neutral-500">No alerts.</p>}
      <div className="flex flex-col gap-2">
        {alerts?.map((alert) => (
          <Card key={alert.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div className="font-medium text-neutral-900">{alert.title}</div>
              <div className="flex gap-2">
                <SeverityBadge severity={alert.severity} />
                <StatusBadge status={alert.status} />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function IncidentsSection() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");

  const { data: incidents } = useQuery<SecurityIncident[]>({
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

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Incidents
      </h2>
      <Card className="mb-4">
        <CardContent className="flex gap-2 pt-6">
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
      {incidents?.length === 0 && <p className="text-sm text-neutral-500">No incidents.</p>}
      <div className="flex flex-col gap-2">
        {incidents?.map((incident) => (
          <Link key={incident.id} href={`/security/incidents/${incident.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{incident.title}</div>
                  {incident.related_risk_id && (
                    <div className="text-xs text-neutral-400">
                      Linked to Compliance risk register
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
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

export default function SecurityPage() {
  return (
    <div>
      <PageHeader
        title="Security"
        description="Asset inventory, findings, alerts, and incident response — spec sections 13-19."
      />
      <AssetsSection />
      <FindingsSection />
      <AlertsSection />
      <IncidentsSection />
    </div>
  );
}
