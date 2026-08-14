"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import type { DPIA, Risk } from "@/lib/types";

/** Article 35(7)'s required content, one field per section.
 *
 * Rendered as named sections rather than a single notes box so a DPO can
 * see at a glance which parts were never addressed. "Not yet completed"
 * is shown explicitly for the same reason the privacy assessment lists
 * its unanswered questions: an empty section that renders as nothing
 * looks like a section that did not apply.
 */
const SECTIONS: { key: keyof DPIA; label: string; help: string }[] = [
  {
    key: "processing_description",
    label: "Description of the processing",
    help: "The nature, scope, context and purposes of the processing.",
  },
  {
    key: "necessity_assessment",
    label: "Necessity",
    help: "Why the processing is necessary for the purpose, and why no less intrusive means suffices.",
  },
  {
    key: "proportionality_assessment",
    label: "Proportionality",
    help: "Whether the processing is proportionate to the purpose, and the safeguards applied.",
  },
  {
    key: "consultation_notes",
    label: "Consultation",
    help: "DPO advice, and where relevant the views of data subjects or their representatives.",
  },
];

const RESIDUAL_VARIANT: Record<string, "success" | "secondary" | "destructive"> = {
  low: "success",
  medium: "secondary",
  high: "destructive",
};

export function DpiaSections({ dpia }: { dpia: DPIA }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});

  const { data: risks } = useQuery<Risk[]>({
    queryKey: ["compliance", "risks"],
    queryFn: () => apiFetch<Risk[]>("/api/v1/compliance/risks"),
  });

  const save = useMutation({
    mutationFn: () =>
      apiFetch<DPIA>(`/api/v1/compliance/dpias/${dpia.id}/sections`, {
        method: "PATCH",
        body: draft,
      }),
    onSuccess: () => {
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["compliance", "dpias", dpia.id] });
    },
  });

  const recalculate = useMutation({
    mutationFn: () =>
      apiFetch<DPIA>(`/api/v1/compliance/dpias/${dpia.id}/recalculate-residual`, {
        method: "POST",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["compliance", "dpias", dpia.id] }),
  });

  const linkedRisks = (risks ?? []).filter((r) => r.dpia_id === dpia.id);
  const unassessed = linkedRisks.filter((r) => !(r.residual_likelihood && r.residual_impact));

  return (
    <>
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-medium text-[var(--fg-default)]">
              Assessment (Article 35(7))
            </h2>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                if (!editing) {
                  setDraft(
                    Object.fromEntries(
                      SECTIONS.map((s) => [s.key, (dpia[s.key] as string | null) ?? ""]),
                    ),
                  );
                }
                setEditing(!editing);
              }}
            >
              {editing ? "Cancel" : "Edit assessment"}
            </Button>
          </div>

          <div className="flex flex-col gap-5">
            {SECTIONS.map((section) => {
              const value = dpia[section.key] as string | null;
              return (
                <div key={section.key}>
                  <p className="text-sm font-medium text-[var(--fg-default)]">{section.label}</p>
                  <p className="mb-1 text-xs text-[var(--fg-subtle)]">{section.help}</p>
                  {editing ? (
                    <textarea
                      rows={3}
                      className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 text-sm text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                      value={draft[section.key] ?? ""}
                      onChange={(e) =>
                        setDraft((prev) => ({ ...prev, [section.key]: e.target.value }))
                      }
                    />
                  ) : value ? (
                    <p className="text-sm leading-relaxed text-[var(--fg-muted)]">{value}</p>
                  ) : (
                    <p className="text-sm italic text-[var(--warning-700)]">Not yet completed</p>
                  )}
                </div>
              );
            })}
          </div>

          {save.error && (
            <p className="mt-3 text-sm text-[var(--critical-600)]">
              {save.error instanceof ApiError ? save.error.message : "Could not save."}
            </p>
          )}

          {editing && (
            <div className="mt-4">
              <Button disabled={save.isPending} onClick={() => save.mutate()}>
                {save.isPending ? "Saving…" : "Save assessment"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-medium text-[var(--fg-default)]">Risk after mitigation</h2>
            <Button
              size="sm"
              variant="outline"
              disabled={recalculate.isPending}
              onClick={() => recalculate.mutate()}
            >
              {recalculate.isPending ? "Recalculating…" : "Recalculate residual risk"}
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-6">
            <div>
              <p className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">Inherent</p>
              <Badge variant={RESIDUAL_VARIANT[dpia.risk_level] ?? "secondary"}>
                {dpia.risk_level}
              </Badge>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">Residual</p>
              {dpia.residual_risk_level ? (
                <Badge variant={RESIDUAL_VARIANT[dpia.residual_risk_level] ?? "secondary"}>
                  {dpia.residual_risk_level}
                </Badge>
              ) : (
                <span className="text-sm text-[var(--fg-subtle)]">Not yet calculated</span>
              )}
            </div>
            <p className="text-xs text-[var(--fg-subtle)]">
              {linkedRisks.length} risk{linkedRisks.length === 1 ? "" : "s"} raised against this
              DPIA
            </p>
          </div>

          {unassessed.length > 0 && (
            <p className="mt-4 flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-3 text-sm text-[var(--warning-700)]">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              {unassessed.length} risk{unassessed.length === 1 ? " has" : "s have"} no residual
              rating yet, so {unassessed.length === 1 ? "it counts" : "they count"} at the
              inherent level. The residual figure cannot improve just because a risk has not been
              reassessed.
            </p>
          )}

          {linkedRisks.length === 0 && (
            <p className="mt-4 flex items-start gap-2 text-sm text-[var(--fg-muted)]">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              No risks have been raised against this DPIA yet. A DPIA with no identified risks has
              not assessed anything.
            </p>
          )}
        </CardContent>
      </Card>
    </>
  );
}
