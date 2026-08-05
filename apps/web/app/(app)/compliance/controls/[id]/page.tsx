"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { ControlAssessment, ControlDetail, Evidence } from "@/lib/types";

const ASSESSMENT_STATUSES: ControlAssessment["status"][] = ["pass", "fail", "partial", "not_assessed"];

export default function ControlDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");

  const { data: control } = useQuery<ControlDetail>({
    queryKey: ["compliance", "controls", id],
    queryFn: () => apiFetch<ControlDetail>(`/api/v1/compliance/controls/${id}`),
  });

  const { data: evidence } = useQuery<Evidence[]>({
    queryKey: ["compliance", "evidence"],
    queryFn: () => apiFetch<Evidence[]>("/api/v1/compliance/evidence"),
  });

  const recordAssessment = useMutation({
    mutationFn: (status: ControlAssessment["status"]) =>
      apiFetch(`/api/v1/compliance/controls/${id}/assessments`, {
        method: "POST",
        body: { status, notes: notes.trim() || null },
      }),
    onSuccess: () => {
      setNotes("");
      queryClient.invalidateQueries({ queryKey: ["compliance", "controls", id] });
      queryClient.invalidateQueries({ queryKey: ["compliance", "controls"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  if (!control) return null;

  const controlEvidence = evidence?.filter((e) => e.control_id === control.id) ?? [];

  return (
    <div>
      <PageHeader
        title={control.title}
        description={control.description ?? undefined}
        actions={<StatusBadge status={control.status} />}
      />

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Mapped Requirements
        </h2>
        {control.requirements.length === 0 && (
          <p className="text-sm text-[var(--fg-muted)]">Not mapped to any framework requirement.</p>
        )}
        <div className="flex flex-wrap gap-2">
          {control.requirements.map((req) => (
            <Badge key={req.id} variant="outline">
              {req.reference_code} — {req.title}
            </Badge>
          ))}
        </div>
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Record Assessment
        </h2>
        <Card>
          <CardContent className="flex flex-col gap-3 pt-6">
            <Input
              placeholder="Notes (optional)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
            <div className="flex gap-2">
              {ASSESSMENT_STATUSES.map((status) => (
                <Button
                  key={status}
                  variant="outline"
                  size="sm"
                  disabled={recordAssessment.isPending}
                  onClick={() => recordAssessment.mutate(status)}
                >
                  {status.replace(/_/g, " ")}
                </Button>
              ))}
            </div>
            <p className="text-xs text-[var(--fg-subtle)]">
              A &quot;fail&quot; assessment automatically creates a remediation task.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Assessment History
        </h2>
        {control.assessments.length === 0 && (
          <p className="text-sm text-[var(--fg-muted)]">No assessments recorded yet.</p>
        )}
        <div className="flex flex-col gap-2">
          {control.assessments.map((assessment) => (
            <Card key={assessment.id}>
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  {assessment.notes && (
                    <div className="text-sm text-[var(--fg-muted)]">{assessment.notes}</div>
                  )}
                  <div className="text-xs text-[var(--fg-subtle)]">
                    {new Date(assessment.created_at).toLocaleString()}
                  </div>
                </div>
                <StatusBadge status={assessment.status} />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Evidence
        </h2>
        {controlEvidence.length === 0 && (
          <p className="text-sm text-[var(--fg-muted)]">No evidence attached.</p>
        )}
        <div className="flex flex-col gap-2">
          {controlEvidence.map((item) => (
            <Card key={item.id}>
              <CardContent className="pt-6 text-sm text-[var(--fg-muted)]">{item.title}</CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
