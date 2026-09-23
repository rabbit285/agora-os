"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { DpiaWorkflow } from "@/lib/types";

/** Article 35(2), as one record in one place.
 *
 * This renders *inside* the Article 35(7) assessment rather than as a
 * card of its own. It used to be both — a summary in the assessment and
 * a separate card that owned the decision — and while the two agreed
 * after the state was unified, showing one fact twice invites them to
 * drift again and makes the reader check whether they match.
 *
 * Veyntra never drafts any of it. Whether a DPO advised is a fact about
 * an event that happened or did not, and writing plausible advice would
 * be fabricating a compliance record.
 *
 * "No consultation was carried out" is an answer, and it needs a reason.
 * Not deciding is the absence of one. Only the first can be defended
 * later, which is why they are stored and shown differently.
 */
export function DpiaConsultation({
  workflow,
  readOnly,
}: {
  workflow: DpiaWorkflow;
  readOnly: boolean;
}) {
  const queryClient = useQueryClient();
  const resolved = workflow.consultation_state !== "not_decided";
  const [editing, setEditing] = useState(false);
  const [performed, setPerformed] = useState<boolean | null>(
    workflow.consultation_performed,
  );
  const [party, setParty] = useState("");
  const [role, setRole] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/dpias/${workflow.id}/consultation`, {
        method: "POST",
        body: {
          performed,
          party: party.trim() || null,
          role: role.trim() || null,
          notes: notes.trim() || null,
        },
      }),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setEditing(false);
      await queryClient.invalidateQueries({ queryKey: ["compliance"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was recorded.",
      ),
  });

  const start = (value: boolean) => {
    setPerformed(value);
    setParty(workflow.consulted_party ?? "");
    setRole(workflow.consulted_role ?? "");
    setNotes(workflow.consultation_notes ?? "");
    setError(null);
    setEditing(true);
  };

  const recordedBy = workflow.consultation_recorded_by_name;
  const recordedAt = workflow.consultation_recorded_at
    ? new Date(workflow.consultation_recorded_at).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : null;

  return (
    <div id="consultation">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm font-medium text-[var(--fg-default)]">Consultation</p>
        {/* One badge, from the one field that holds the state. */}
        {resolved ? (
          <Badge variant="success">Resolved</Badge>
        ) : (
          <Badge variant="warning">Needs decision</Badge>
        )}
      </div>
      <p className="mb-1 text-xs text-[var(--fg-subtle)]">
        DPO advice, and where relevant the views of data subjects or their
        representatives.
      </p>

      {resolved && !editing ? (
        <div className="flex flex-col gap-1 text-sm text-[var(--fg-muted)]">
          <p className="text-[var(--fg-default)]">
            {workflow.consultation_performed
              ? [workflow.consulted_party, workflow.consulted_role]
                  .filter(Boolean)
                  .join(" — ")
              : "No consultation performed"}
            {workflow.consultation_performed && workflow.consulted_at && (
              <span className="text-[var(--fg-subtle)]">
                {" "}
                · {new Date(workflow.consulted_at).toLocaleDateString()}
              </span>
            )}
          </p>
          {workflow.consultation_notes && (
            <p>
              <span className="text-[var(--fg-subtle)]">
                {workflow.consultation_performed ? "Outcome: " : "Reason: "}
              </span>
              {workflow.consultation_notes}
            </p>
          )}
          <p className="text-xs text-[var(--fg-subtle)]">
            Recorded{recordedBy && ` by ${recordedBy}`}
            {recordedAt && ` on ${recordedAt}`}.
          </p>
          {!readOnly && (
            <div className="mt-1">
              <Button
                size="sm"
                variant="outline"
                onClick={() => start(workflow.consultation_performed ?? false)}
              >
                View / Change
              </Button>
            </div>
          )}
        </div>
      ) : readOnly ? (
        <p className="text-sm italic text-[var(--warning-700)]">
          No consultation is recorded against this assessment.
        </p>
      ) : !editing ? (
        <div className="flex flex-col gap-2">
          <p className="text-xs leading-relaxed text-[var(--fg-subtle)]">
            Record whether Privacy/DPO or data-subject consultation was carried
            out, and any relevant outcome. Veyntra has no record of either and
            will not draft one — both answers are decisions, and deciding none
            was needed is one of them.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => start(true)}>
              Record consultation
            </Button>
            <Button size="sm" variant="outline" onClick={() => start(false)}>
              No consultation performed
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-2 flex flex-col gap-3 rounded-[var(--radius-md)] bg-[var(--bg-subtle)] p-3">
          <div className="flex gap-2">
            {(
              [
                [true, "Consultation performed"],
                [false, "No consultation performed"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={label}
                type="button"
                aria-pressed={performed === value}
                onClick={() => setPerformed(value)}
                className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                  performed === value
                    ? "border-[var(--border-strong)] bg-[var(--bg-default)] font-medium text-[var(--fg-default)]"
                    : "border-[var(--border-default)] text-[var(--fg-muted)]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {performed === true && (
            <div className="flex flex-col gap-2">
              <label className="text-xs text-[var(--fg-muted)]" htmlFor="consulted-party">
                Who was consulted (required)
              </label>
              <Input
                id="consulted-party"
                value={party}
                onChange={(e) => setParty(e.target.value)}
              />
              <label className="text-xs text-[var(--fg-muted)]" htmlFor="consulted-role">
                Their role
              </label>
              <Input
                id="consulted-role"
                placeholder="e.g. Data Protection Officer"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              />
            </div>
          )}

          <label className="text-xs text-[var(--fg-muted)]" htmlFor="consultation-notes">
            {performed === false
              ? "Why no consultation was needed (required)"
              : "The advice or outcome"}
          </label>
          <textarea
            id="consultation-notes"
            rows={3}
            className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 text-sm text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />

          {error && (
            <p role="alert" className="text-xs text-[var(--fg-danger)]">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={
                performed === null ||
                save.isPending ||
                (performed === false && !notes.trim()) ||
                (performed === true && !party.trim())
              }
              onClick={() => save.mutate()}
            >
              {save.isPending ? "Recording…" : "Record consultation"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
