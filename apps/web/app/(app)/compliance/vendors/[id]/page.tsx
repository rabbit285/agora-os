"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { SeverityBadge } from "@/components/severity-badge";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { Severity, VendorDetail, VendorStatus } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400";

export default function VendorDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");
  const [riskConclusion, setRiskConclusion] = useState<Severity>("low");

  const { data: vendor } = useQuery<VendorDetail>({
    queryKey: ["compliance", "vendors", id],
    queryFn: () => apiFetch<VendorDetail>(`/api/v1/compliance/vendors/${id}`),
  });

  const updateStatus = useMutation({
    mutationFn: (status: VendorStatus) =>
      apiFetch(`/api/v1/compliance/vendors/${id}/status`, { method: "PATCH", body: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance", "vendors", id] }),
  });

  const updateDpaStatus = useMutation({
    mutationFn: (dpa_status: VendorDetail["dpa_status"]) =>
      apiFetch(`/api/v1/compliance/vendors/${id}/dpa-status`, {
        method: "PATCH",
        body: { dpa_status },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance", "vendors", id] }),
  });

  const recordAssessment = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/vendors/${id}/assessments`, {
        method: "POST",
        body: { risk_conclusion: riskConclusion, notes: notes.trim() || null },
      }),
    onSuccess: () => {
      setNotes("");
      setRiskConclusion("low");
      queryClient.invalidateQueries({ queryKey: ["compliance", "vendors", id] });
      queryClient.invalidateQueries({ queryKey: ["compliance", "risks"] });
    },
  });

  if (!vendor) return null;

  return (
    <div>
      <PageHeader
        title={vendor.name}
        description={vendor.description ?? undefined}
        actions={<SeverityBadge severity={vendor.risk_tier} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        {vendor.website && (
          <a
            href={vendor.website}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-neutral-500 hover:underline"
          >
            {vendor.website}
          </a>
        )}
        <span className="text-sm text-neutral-500">Status:</span>
        <StatusBadge status={vendor.status} />
        <select
          className={selectClassName}
          value={vendor.status}
          onChange={(e) => updateStatus.mutate(e.target.value as VendorStatus)}
        >
          <option value="active">Active</option>
          <option value="under_review">Under review</option>
          <option value="offboarded">Offboarded</option>
        </select>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <span className="text-sm text-neutral-500">DPA review:</span>
        <StatusBadge status={vendor.dpa_status} />
        <select
          className={selectClassName}
          value={vendor.dpa_status}
          onChange={(e) =>
            updateDpaStatus.mutate(e.target.value as VendorDetail["dpa_status"])
          }
        >
          <option value="pending">Pending</option>
          <option value="signed">Signed</option>
          <option value="not_required">Not required</option>
        </select>
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Record Risk Assessment
        </h2>
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <div className="flex gap-2">
              <select
                className={selectClassName}
                value={riskConclusion}
                onChange={(e) => setRiskConclusion(e.target.value as Severity)}
              >
                <option value="low">Low risk</option>
                <option value="medium">Medium risk</option>
                <option value="high">High risk</option>
                <option value="critical">Critical risk</option>
              </select>
              <Input
                placeholder="Notes (optional)"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="flex-1"
              />
              <Button disabled={recordAssessment.isPending} onClick={() => recordAssessment.mutate()}>
                Record assessment
              </Button>
            </div>
            <p className="text-xs text-neutral-400">
              A high or critical conclusion automatically creates a linked Risk in the Risk
              Register.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Assessment History
        </h2>
        {vendor.assessments.length === 0 && (
          <p className="text-sm text-neutral-500">No assessments recorded yet.</p>
        )}
        <div className="flex flex-col gap-2">
          {vendor.assessments.map((assessment) => (
            <Card key={assessment.id}>
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  {assessment.notes && (
                    <div className="text-sm text-neutral-700">{assessment.notes}</div>
                  )}
                  <div className="text-xs text-neutral-400">
                    {new Date(assessment.created_at).toLocaleString()}
                  </div>
                </div>
                <SeverityBadge severity={assessment.risk_conclusion} />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Evidence
        </h2>
        {vendor.evidence.length === 0 && (
          <p className="text-sm text-neutral-500">No evidence attached.</p>
        )}
        <div className="flex flex-col gap-2">
          {vendor.evidence.map((item) => (
            <Card key={item.id}>
              <CardContent className="pt-6 text-sm text-neutral-700">{item.title}</CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
