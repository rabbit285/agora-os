"use client";

import Link from "next/link";
import { use } from "react";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { SecurityFinding, SecurityIncident } from "@/lib/types";

type AssetDetail = {
  id: string;
  name: string;
  asset_type: string;
  environment: string;
  provider: string | null;
  criticality: "low" | "medium" | "high" | "critical";
  data_classification: string;
  internet_exposed: boolean;
  status: "healthy" | "at_risk" | "compromised";
  owner_id: string | null;
  last_observed_at: string | null;
  created_at: string;
  findings: SecurityFinding[];
  incidents: SecurityIncident[];
};

export default function AssetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const { data: asset, isLoading } = useQuery<AssetDetail>({
    queryKey: ["security", "assets", id],
    queryFn: () => apiFetch<AssetDetail>(`/api/v1/security/assets/${id}`),
  });

  if (isLoading) return <p className="text-sm text-neutral-500">Loading asset…</p>;
  if (!asset) return <p className="text-sm text-neutral-500">Asset not found.</p>;

  return (
    <div>
      <PageHeader
        title={asset.name}
        description={`${asset.asset_type} · ${asset.environment}${asset.provider ? ` · ${asset.provider}` : ""}`}
        actions={
          <div className="flex gap-2">
            <SeverityBadge severity={asset.criticality} />
            <StatusBadge status={asset.status} />
          </div>
        }
      />

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-xs text-neutral-500">Data Classification</div>
            <div className="font-medium text-neutral-900">{asset.data_classification}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-xs text-neutral-500">Internet Exposed</div>
            <div className="font-medium text-neutral-900">
              {asset.internet_exposed ? "Yes" : "No"}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-xs text-neutral-500">Last Observed</div>
            <div className="font-medium text-neutral-900">
              {asset.last_observed_at ? new Date(asset.last_observed_at).toLocaleString() : "—"}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Findings on this asset
        </h2>
        {asset.findings.length === 0 && (
          <p className="text-sm text-neutral-500">No findings recorded for this asset.</p>
        )}
        <div className="flex flex-col gap-2">
          {asset.findings.map((finding) => (
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

      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Incidents affecting this asset
        </h2>
        {asset.incidents.length === 0 && (
          <p className="text-sm text-neutral-500">No incidents reference this asset.</p>
        )}
        <div className="flex flex-col gap-2">
          {asset.incidents.map((incident) => (
            <Link key={incident.id} href={`/security/incidents/${incident.id}`}>
              <Card className="transition-colors hover:border-neutral-400">
                <CardContent className="flex items-center justify-between pt-6">
                  <div className="font-medium text-neutral-900">{incident.title}</div>
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
    </div>
  );
}
