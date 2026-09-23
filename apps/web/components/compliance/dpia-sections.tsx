"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ClipboardCheck, ShieldAlert } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DpiaConsultation } from "@/components/compliance/dpia-consultation";
import { ApiError, apiFetch } from "@/lib/api";
import type { DpiaWorkflow } from "@/lib/types";

/** Article 35(7)'s required content, one field per section.
 *
 * Rendered as named sections rather than a single notes box so a DPO can
 * see at a glance which parts were never addressed. "Not yet completed"
 * is shown explicitly for the same reason the privacy assessment lists
 * its unanswered questions: an empty section that renders as nothing
 * looks like a section that did not apply.
 *
 * Each section carries its own sign-off. Review is recorded, not
 * inferred from whether the text still begins with Veyntra's draft
 * marker — under that rule, deleting one word counted as having read it,
 * and a reviewer who agreed with the draft verbatim had no way to say so
 * without editing it first.
 */
type SectionKey =
  | "processing_description"
  | "necessity_assessment"
  | "proportionality_assessment";

const SECTIONS: { key: SectionKey; label: string; help: string }[] = [
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
];


const RESIDUAL_VARIANT: Record<string, "success" | "secondary" | "destructive"> = {
  low: "success",
  medium: "secondary",
  high: "destructive",
};

const DRAFT_MARKER = "[Veyntra draft";
const MARKER_PATTERN = /^\[Veyntra draft[^\]]*\]\s*/;

/** The prose as it should read to the person looking at it.
 *
 * The marker lives in the stored text, which is what makes the
 * provenance survive an export and a database dump. On screen it is the
 * "whose words are these" signal — and once somebody has approved the
 * section, the badge says that instead, so leaving the marker inline
 * puts "Approved" and "review required" on the same paragraph.
 *
 * Stripping it on approval would edit the text a person signed off, so
 * nothing is written back. This only changes what is rendered. */
function displayText(value: string | null, approved: boolean): string | null {
  if (!value) return value;
  return approved ? value.replace(MARKER_PATTERN, "") : value;
}

export function DpiaSections({ workflow }: { workflow: DpiaWorkflow }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [concluding, setConcluding] = useState(false);
  const [approving, setApproving] = useState<SectionKey | null>(null);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [rationale, setRationale] = useState("");

  const readOnly = workflow.status === "completed";
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["compliance"] });

  const save = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/dpias/${workflow.id}/sections`, {
        method: "PATCH",
        body: draft,
      }),
    onSuccess: async () => {
      setEditing(false);
      await refresh();
    },
  });

  const approve = useMutation({
    mutationFn: (section: SectionKey) =>
      apiFetch(`/api/v1/compliance/dpias/${workflow.id}/sections/approve`, {
        method: "POST",
        body: { section },
      }),
    onSuccess: () => {
      setApproveError(null);
      return refresh();
    },
    onError: (cause) =>
      setApproveError(
        cause instanceof ApiError
          ? cause.message
          : "That section could not be approved.",
      ),
  });

  // §9: a reviewer who read every candidate and judged none material
  // can say so. Completion used to require a risk on the register, so
  // the only way to finish was to write down one they did not believe.
  const conclude = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/dpias/${workflow.id}/risk-conclusion`, {
        method: "POST",
        body: { rationale },
      }),
    onSuccess: async () => {
      setConcluding(false);
      setRationale("");
      await refresh();
    },
  });

  const recalculate = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/dpias/${workflow.id}/recalculate-residual`, {
        method: "POST",
      }),
    onSuccess: refresh,
  });

  const reviewed = new Set(workflow.section_reviews.map((row) => row.section));
  const stale = new Set(workflow.stale_sections);

  // Residual risk is what remains after mitigation, so it needs a risk
  // that somebody has actually reassessed. Offering the calculation with
  // nothing behind it implies a number exists to be found.
  const canRecalculate = workflow.can_calculate_residual;
  const recalculateBlockedReason = workflow.risk_blocked_reason;
  const unassessed = workflow.risk_count - workflow.mitigated_count;
  const concluded = workflow.risk_conclusion === "no_material_risks";
  const reviewed_risks = workflow.risk_conclusion === "risks_identified";

  // §9: what became of everything Veyntra proposed. Shown so the record
  // can demonstrate the suggestions were reviewed rather than ignored.
  const suggested = {
    total: workflow.suggested_risks.length,
    accepted: workflow.suggested_risks.filter((r) => r.status === "approved").length,
    dismissed: workflow.suggested_risks.filter((r) => r.status === "dismissed").length,
    reviewed: workflow.suggested_risks.filter((r) => r.status !== "suggested").length,
  };

  return (
    <>
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-medium text-[var(--fg-default)]">
              Assessment (Article 35(7))
            </h2>
            {!readOnly && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (!editing) {
                    setDraft(
                      Object.fromEntries(
                        SECTIONS.map((s) => [s.key, workflow[s.key] ?? ""]),
                      ),
                    );
                  }
                  setEditing(!editing);
                }}
              >
                {editing ? "Cancel" : "Edit assessment"}
              </Button>
            )}
          </div>

          <div className="flex flex-col gap-5">
            {SECTIONS.map((section) => {
              const value = workflow[section.key];
              const signedOff = reviewed.has(section.key);
              const isDraft = Boolean(value?.startsWith(DRAFT_MARKER));
              return (
                <div key={section.key}>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-[var(--fg-default)]">
                      {section.label}
                    </p>
                    {/* Whose words these are, before anybody reads them. */}
                    {signedOff && stale.has(section.key) ? (
                      <Badge variant="warning">Needs review — facts changed</Badge>
                    ) : signedOff ? (
                      <Badge variant="success">Approved</Badge>
                    ) : isDraft ? (
                      <Badge variant="warning">Veyntra draft — review required</Badge>
                    ) : value ? (
                      <Badge variant="secondary">Not approved</Badge>
                    ) : null}
                  </div>
                  <p className="mb-1 text-xs text-[var(--fg-subtle)]">
                    {workflow.section_guidance[section.key] ?? section.help}
                  </p>
                  {editing ? (
                    <textarea
                      rows={3}
                      aria-label={section.label}
                      className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 text-sm text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                      value={draft[section.key] ?? ""}
                      onChange={(e) =>
                        setDraft((prev) => ({ ...prev, [section.key]: e.target.value }))
                      }
                    />
                  ) : value ? (
                    <p className="text-sm leading-relaxed text-[var(--fg-muted)]">
                      {displayText(value, signedOff)}
                    </p>
                  ) : (
                    <p className="text-sm italic text-[var(--warning-700)]">Not yet completed</p>
                  )}

                  {!editing && !readOnly && value && (!signedOff || stale.has(section.key)) && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-2"
                      disabled={approve.isPending}
                      onClick={() => {
                        setApproveError(null);
                        setApproving(section.key);
                        approve.mutate(section.key);
                      }}
                    >
                      <Check className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                      {stale.has(section.key)
                        ? "Re-approve this section"
                        : "Approve this section"}
                    </Button>
                  )}
                  {/* The refusal that says guidance is not an assessment
                      has to land next to the button that was pressed. */}
                  {approveError && approving === section.key && (
                    <p
                      role="alert"
                      className="mt-2 text-sm text-[var(--fg-danger)]"
                    >
                      {approveError}
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          {/* Article 35(7)(d)'s section, rendered by the component that
              owns the decision. One record, one place — a summary here
              and an editor elsewhere is how two states drift apart. */}
          <div className="mt-5 border-t border-[var(--border-default)] pt-4">
            <DpiaConsultation workflow={workflow} readOnly={readOnly} />
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
              {/* Editing withdraws the sign-off, because an approval is a
                  statement about particular words. */}
              <p className="mt-2 text-xs text-[var(--fg-subtle)]">
                Saving withdraws the approval on any section you change — an
                approval is a statement about the words that were approved.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            {/* Not "Risk after mitigation": with no accepted risks and no
                mitigations, that heading describes a calculation nobody
                has any input for. */}
            <h2 className="flex flex-wrap items-center gap-2 font-medium text-[var(--fg-default)]">
              Risk assessment
              {concluded ? (
                <Badge variant="success">Reviewed</Badge>
              ) : reviewed_risks ? (
                <Badge variant="secondary">Risks identified</Badge>
              ) : (
                <Badge variant="warning">Not reviewed</Badge>
              )}
            </h2>
            {!readOnly && !concluded && workflow.risk_count > 0 && (
              <Button
                size="sm"
                variant="outline"
                disabled={recalculate.isPending || !canRecalculate}
                title={canRecalculate ? undefined : recalculateBlockedReason ?? undefined}
                onClick={() => recalculate.mutate()}
              >
                {recalculate.isPending ? "Recalculating…" : "Recalculate residual risk"}
              </Button>
            )}
          </div>

          {/* §9: proof the suggestions were actually reviewed, not
              ignored. Shown whenever Veyntra proposed anything. */}
          {suggested.total > 0 && (
            <dl className="mb-4 flex flex-wrap gap-x-6 gap-y-1 text-xs">
              {(
                [
                  ["Suggested risks", String(suggested.total)],
                  ["Reviewed", `${suggested.reviewed} / ${suggested.total}`],
                  ["Accepted", String(suggested.accepted)],
                  ["Dismissed", String(suggested.dismissed)],
                ] as const
              ).map(([label, value]) => (
                <div key={label}>
                  <dt className="uppercase tracking-wide text-[var(--fg-subtle)]">
                    {label}
                  </dt>
                  <dd className="text-[var(--fg-default)]">{value}</dd>
                </div>
              ))}
            </dl>
          )}

          {!canRecalculate && !concluded && recalculateBlockedReason && (
            <p className="mb-3 text-xs text-[var(--fg-subtle)]">
              {recalculateBlockedReason}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-6">
            <div>
              <p className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">Inherent</p>
              {workflow.inherent_risk ? (
                <Badge variant={RESIDUAL_VARIANT[workflow.inherent_risk] ?? "secondary"}>
                  {workflow.inherent_risk}
                </Badge>
              ) : concluded ? (
                // §12: somebody completed the review. "Not assessed"
                // would read as though nobody had looked.
                <span className="text-sm text-[var(--fg-default)]">
                  No material risks identified
                </span>
              ) : (
                // A level nobody derived, printed on the document whose
                // purpose is to record that somebody derived one, is the
                // most misleading thing this page can say.
                <span className="text-sm text-[var(--fg-subtle)]">Not assessed</span>
              )}
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                {workflow.risk_count > 0 ? "Residual after mitigation" : "Residual"}
              </p>
              {workflow.residual_risk ? (
                <Badge variant={RESIDUAL_VARIANT[workflow.residual_risk] ?? "secondary"}>
                  {workflow.residual_risk}
                </Badge>
              ) : concluded ? (
                <span className="text-sm text-[var(--fg-subtle)]">Not applicable</span>
              ) : (
                <span className="text-sm text-[var(--fg-subtle)]">Not yet calculated</span>
              )}
            </div>
            <p className="text-xs text-[var(--fg-subtle)]">
              {workflow.risk_count} risk{workflow.risk_count === 1 ? "" : "s"} raised against
              this DPIA
            </p>
          </div>

          {unassessed > 0 && (
            <p className="mt-4 flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-3 text-sm text-[var(--warning-700)]">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              {unassessed} risk{unassessed === 1 ? " has" : "s have"} no residual rating yet, so{" "}
              {unassessed === 1 ? "it counts" : "they count"} at the inherent level. The residual
              figure cannot improve just because a risk has not been reassessed.
            </p>
          )}

          {workflow.risk_count === 0 && (
            <div className="mt-4 flex flex-col gap-2">
              {concluded ? (
                <div className="flex items-start gap-2 rounded-[var(--radius-md)] bg-[var(--bg-subtle)] p-3">
                  <ClipboardCheck
                    className="mt-0.5 h-4 w-4 shrink-0 text-[var(--fg-muted)]"
                    aria-hidden="true"
                  />
                  <dl className="flex flex-col gap-1.5 text-sm">
                    <div>
                      <dt className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                        Conclusion
                      </dt>
                      <dd className="font-medium text-[var(--fg-default)]">
                        No material privacy risks identified
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                        Rationale
                      </dt>
                      <dd className="leading-relaxed text-[var(--fg-muted)]">
                        {workflow.risk_conclusion_rationale}
                      </dd>
                    </div>
                    <div className="flex flex-wrap gap-x-6">
                      {workflow.risk_reviewed_by_name && (
                        <div>
                          <dt className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                            Reviewed by
                          </dt>
                          <dd className="text-[var(--fg-muted)]">
                            {workflow.risk_reviewed_by_name}
                          </dd>
                        </div>
                      )}
                      {workflow.risk_reviewed_at && (
                        <div>
                          <dt className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                            Reviewed
                          </dt>
                          <dd className="text-[var(--fg-muted)]">
                            {new Date(workflow.risk_reviewed_at).toLocaleDateString(
                              undefined,
                              { year: "numeric", month: "short", day: "numeric" },
                            )}
                          </dd>
                        </div>
                      )}
                    </div>
                  </dl>
                </div>
              ) : (
                <>
                  {/* §11: "nobody has reviewed" is not "there are none". */}
                  <p className="flex items-start gap-2 text-sm text-[var(--fg-muted)]">
                    <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                    {suggested.total === 0
                      ? "No candidate risks were generated from this processing. Human review is still required — add the risks it carries, or record that none are material and why."
                      : "No risks have been accepted onto this DPIA's register. Human review is still required — add the risks this processing carries, or record that none are material and why."}
                  </p>
                  {!readOnly && !concluding && (
                    <div>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!workflow.can_conclude_no_material_risks}
                        title={
                          workflow.can_conclude_no_material_risks
                            ? undefined
                            : "Every suggested risk has to be approved or dismissed first — concluding that nothing is material means having looked at everything proposed."
                        }
                        onClick={() => setConcluding(true)}
                      >
                        Confirm no material risks identified
                      </Button>
                    </div>
                  )}
                  {concluding && (
                    <div className="flex flex-col gap-2 rounded-[var(--radius-md)] bg-[var(--bg-subtle)] p-3">
                      <p className="text-sm font-medium text-[var(--fg-default)]">
                        Confirm no material privacy risks identified
                      </p>
                      <label
                        className="text-xs leading-relaxed text-[var(--fg-muted)]"
                        htmlFor="risk-conclusion-rationale"
                      >
                        {/* An auditor asks to see the reasoning behind
                            exactly this conclusion, so the field says what
                            the reasoning has to account for. */}
                        Record why the reviewed processing does not present
                        material privacy risks requiring entry in this
                        DPIA&apos;s risk register. (required)
                      </label>
                      <textarea
                        id="risk-conclusion-rationale"
                        rows={3}
                        className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] px-3 py-2 text-sm text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                        value={rationale}
                        onChange={(e) => setRationale(e.target.value)}
                      />
                      {conclude.error && (
                        <p role="alert" className="text-xs text-[var(--fg-danger)]">
                          {conclude.error instanceof ApiError
                            ? conclude.error.message
                            : "Could not record that conclusion."}
                        </p>
                      )}
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setConcluding(false)}
                        >
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          disabled={!rationale.trim() || conclude.isPending}
                          onClick={() => conclude.mutate()}
                        >
                          {conclude.isPending ? "Recording…" : "Confirm conclusion"}
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
