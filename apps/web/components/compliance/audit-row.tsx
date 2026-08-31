"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ExternalLink } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import type { AuditDecision, AuditDecisionResult, AuditItem } from "@/lib/types";

/** One scoped requirement, and the auditor's decision on it.
 *
 * Everything needed to decide is here: the requirement, the control
 * answering it, what Veyntra found, what is missing, and the evidence
 * behind it. The auditor should not open four screens to understand one
 * row — that was the old workflow, and what it produced was findings
 * typed from memory.
 *
 * The decision buttons are the primary path to a finding. Choosing one
 * carries the requirement, control and evidence into it, so nothing is
 * retyped and the finding says what it was based on.
 */
const DECISIONS: { key: AuditDecision; label: string; needsNote: boolean }[] = [
  { key: "no_finding", label: "No finding", needsNote: false },
  { key: "observation", label: "Observation", needsNote: false },
  { key: "minor", label: "Minor finding", needsNote: true },
  { key: "major", label: "Major finding", needsNote: true },
  { key: "critical", label: "Critical finding", needsNote: true },
  { key: "needs_evidence", label: "Request more evidence", needsNote: true },
];

export function AuditItemRow({
  auditId,
  item,
  readOnly = false,
}: {
  auditId: string;
  item: AuditItem;
  /** A completed audit is a record. Its decisions are not re-editable
   * from the review screen. */
  readOnly?: boolean;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<AuditDecision | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const decide = useMutation<
    AuditDecisionResult,
    unknown,
    { decision: AuditDecision; note: string | null }
  >({
    mutationFn: (body) =>
      apiFetch<AuditDecisionResult>(
        `/api/v1/compliance/audits/${auditId}/items/${item.id}/decision`,
        { method: "POST", body },
      ),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setPending(null);
      setNote("");
      await queryClient.invalidateQueries({ queryKey: ["compliance", "audits"] });
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was recorded.",
      ),
  });

  const chosen = DECISIONS.find((entry) => entry.key === pending);
  const evidence = [...item.evidence_snapshot, ...item.new_evidence];

  return (
    <Card className="mb-2">
      <CardContent className="pt-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="text-xs font-medium text-[var(--fg-subtle)]">
              {item.framework_key ? `${item.framework_key} ` : ""}
              {item.reference_code}
            </div>
            <div className="font-medium text-[var(--fg-default)]">
              {item.requirement_title}
            </div>
            {item.control_title ? (
              <div className="mt-1 text-sm text-[var(--fg-muted)]">
                Control: {item.control_title}
              </div>
            ) : (
              <div className="mt-1 text-sm text-[var(--fg-muted)]">
                No control mapped to this requirement.
              </div>
            )}
          </div>
          {/* Two claims by two parties, each said out loud. Veyntra
              reports what the evidence shows; the auditor records what
              they concluded about it. Rendered as adjacent bare badges,
              a reader had no way to tell which was which — or that
              "No evidence" is not itself a finding. */}
          <div className="flex shrink-0 flex-col items-end gap-2">
            <div className="text-right">
              <div className="text-[10px] font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
                Evidence state
              </div>
              <StatusBadge
                status={item.prepared_status}
                label={item.prepared_status_label}
              />
            </div>
            {item.decision_label && (
              <div className="text-right">
                <div className="text-[10px] font-medium uppercase tracking-wide text-[var(--fg-subtle)]">
                  Auditor conclusion
                </div>
                <span className="inline-block rounded-full border border-[var(--border-strong)] px-2.5 py-0.5 text-xs font-medium text-[var(--fg-default)]">
                  {item.decision_label}
                </span>
              </div>
            )}
          </div>
        </div>

        {item.prepared_why && (
          <p className="mt-3 text-sm text-[var(--fg-muted)]">{item.prepared_why}</p>
        )}
        {item.prepared_missing && (
          <p className="mt-1 text-sm text-[var(--warning-700)]">
            Missing: {item.prepared_missing}
          </p>
        )}

        {evidence.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen((was) => !was)}
            className="mt-3 flex items-center gap-1 text-xs font-medium text-[var(--brand-primary)] hover:underline"
            aria-expanded={open}
          >
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
            {evidence.length} evidence item{evidence.length === 1 ? "" : "s"}
            {item.new_evidence.length > 0 &&
              ` · ${item.new_evidence.length} new since this audit was prepared`}
          </button>
        )}

        {open && (
          <ul className="mt-2 flex flex-col gap-1.5">
            {evidence.map((entry, index) => (
              <li
                key={`${entry.evidence_id ?? entry.title}-${index}`}
                className="rounded-md border border-[var(--border-default)] px-3 py-2 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-[var(--fg-default)]">
                    {entry.title}
                  </span>
                  {entry.evidence_type && (
                    <span className="text-xs text-[var(--fg-subtle)]">
                      {entry.evidence_type.replace(/_/g, " ")}
                    </span>
                  )}
                  {entry.document_href && (
                    <a
                      href={entry.document_href}
                      className="inline-flex items-center gap-1 text-xs text-[var(--brand-primary)] hover:underline"
                    >
                      <ExternalLink className="h-3 w-3" aria-hidden="true" />
                      Open document
                    </a>
                  )}
                </div>
                {entry.source_location && (
                  <div className="mt-0.5 text-xs text-[var(--fg-subtle)]">
                    {entry.source_location}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        {item.decision_note && (
          <p className="mt-3 border-l-2 border-[var(--border-strong)] pl-3 text-sm text-[var(--fg-muted)]">
            {item.decision_note}
          </p>
        )}

        {(item.finding_status_label || item.current_status_label) && (
          <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1">
            {item.finding_status_label && (
              <div className="flex items-baseline gap-1.5">
                <dt className="text-xs text-[var(--fg-subtle)]">Remediation</dt>
                <dd className="text-sm text-[var(--fg-default)]">
                  {item.finding_status_label}
                </dd>
              </div>
            )}
            {/* §14: what the auditor assessed, and where it stands now.
                Shown together so a completed audit can display
                improvement without rewriting its own conclusions. */}
            {item.current_status_label && (
              <div className="flex items-baseline gap-1.5">
                <dt className="text-xs text-[var(--fg-subtle)]">
                  Current state
                </dt>
                <dd className="text-sm text-[var(--success-700)]">
                  {item.current_status_label}
                  <span className="ml-1 text-xs text-[var(--fg-subtle)]">
                    (changed since this audit)
                  </span>
                </dd>
              </div>
            )}
          </dl>
        )}

        {!readOnly && (
          <div className="mt-4">
            {pending === null ? (
              <div className="flex flex-wrap gap-2">
                {DECISIONS.map((entry) => (
                  <Button
                    key={entry.key}
                    variant={entry.key === "no_finding" ? "outline" : "ghost"}
                    size="sm"
                    disabled={decide.isPending}
                    onClick={() => {
                      if (entry.needsNote) {
                        setPending(entry.key);
                        return;
                      }
                      decide.mutate({ decision: entry.key, note: null });
                    }}
                  >
                    {item.decision === entry.key ? `✓ ${entry.label}` : entry.label}
                  </Button>
                ))}
              </div>
            ) : (
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  if (note.trim()) {
                    decide.mutate({ decision: pending, note: note.trim() });
                  }
                }}
              >
                <label
                  htmlFor={`decision-note-${item.id}`}
                  className="mb-1.5 block text-xs font-medium text-[var(--fg-muted)]"
                >
                  {chosen?.label} — reason
                </label>
                {/* Required, and the server refuses without it. A finding
                    against somebody's control that does not say what is
                    wrong is not something they can act on. */}
                <Textarea
                  id={`decision-note-${item.id}`}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  rows={3}
                  placeholder="What is wrong, and what you looked at."
                  autoFocus
                />
                <div className="mt-2 flex gap-2">
                  <Button type="submit" size="sm" disabled={!note.trim() || decide.isPending}>
                    {decide.isPending ? "Recording…" : `Record ${chosen?.label.toLowerCase()}`}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setPending(null);
                      setNote("");
                      setError(null);
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </form>
            )}
          </div>
        )}

        {error && (
          <p role="alert" className="mt-2 text-sm text-[var(--fg-danger)]">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
