"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, FileText, Quote, Sparkles } from "lucide-react";

import {
  AssessmentBadge,
  EvidenceCoverage,
} from "@/components/compliance/assessment-badge";
import { AttachEvidence } from "@/components/compliance/attach-evidence";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { ControlAssessment, ControlDetail } from "@/lib/types";

/** One control: what the evidence supports, and what it does not.
 *
 * This page used to open on an empty pass/fail form, which is the
 * workflow the product exists to remove — by the time someone opens a
 * control, document intelligence has usually already found evidence for
 * it. So the assessment leads, the evidence behind it is shown with the
 * section it came from, and recording a verdict by hand is still
 * available but secondary.
 *
 * A human verdict is never overwritten by the derived one. Where both
 * exist they are shown together, because "the software concluded X and a
 * person concluded Y" is information, not a conflict to resolve silently.
 */

const OVERRIDE_STATUSES: { value: ControlAssessment["status"]; label: string }[] = [
  { value: "pass", label: "Passed" },
  { value: "partial", label: "Partially implemented" },
  { value: "fail", label: "Failed" },
  { value: "not_assessed", label: "Needs review" },
];

/** Applicability and coverage, per requirement.
 *
 * Only `not_applicable` leaves the denominator; `likely_applicable` and
 * `needs_review` still count, because "we cannot tell yet" must not
 * quietly improve the score. */
const REQUIREMENT_LABEL: Record<string, string> = {
  applicable: "Applicable",
  likely_applicable: "Likely applicable",
  needs_review: "Needs review",
  not_applicable: "Not applicable",
};

const REQUIREMENT_VARIANT: Record<string, "success" | "secondary" | "outline"> = {
  applicable: "secondary",
  likely_applicable: "secondary",
  needs_review: "secondary",
  not_applicable: "outline",
};

const COVERAGE_LABEL: Record<string, string> = {
  satisfied: "Evidenced",
  deficient: "Gap",
  uncertain: "Awaiting review",
  no_evidence: "No evidence",
};

export default function ControlDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState("");
  const [overrideOpen, setOverrideOpen] = useState(false);

  const { data: control } = useQuery<ControlDetail>({
    queryKey: ["compliance", "controls", id],
    queryFn: () => apiFetch<ControlDetail>(`/api/v1/compliance/controls/${id}`),
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["compliance", "controls", id] });
    void queryClient.invalidateQueries({ queryKey: ["compliance", "overview"] });
  };

  const recordAssessment = useMutation({
    mutationFn: (status: ControlAssessment["status"]) =>
      apiFetch(`/api/v1/compliance/controls/${id}/assessments`, {
        method: "POST",
        body: { status, notes: notes.trim() || null },
      }),
    onSuccess: () => {
      setNotes("");
      setOverrideOpen(false);
      refresh();
    },
  });

  if (!control) return null;
  const assessment = control.assessment;

  return (
    <div>
      <PageHeader title={control.title} description={control.description ?? undefined} />

      {assessment && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            {/* Four dimensions, each labelled. They used to be one badge
                reading "Needs review · 100%" with the human decision
                mentioned in a footnote — which asked the reader to decode
                an assessment state, an evidence measurement and a review
                decision out of a single line. */}
            <div className="mb-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <p className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                  Status
                </p>
                <div className="mt-1">
                  <AssessmentBadge
                    status={assessment.effective_status}
                    label={assessment.label}
                  />
                </div>
              </div>

              <EvidenceCoverage
                percent={assessment.confidence}
                status={assessment.effective_status}
              />

              <div>
                <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                  <Sparkles
                    className="h-3 w-3 text-[var(--brand-primary)]"
                    aria-hidden="true"
                  />
                  AI assessment
                </p>
                {/* Never overwritten by a human decision — "a person
                    disagreed with the automated assessment" is exactly
                    what an auditor wants to see. */}
                <p className="mt-1 text-sm text-[var(--fg-default)]">
                  {assessment.ai_label}
                </p>
              </div>

              <div>
                <p className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                  Human review
                </p>
                <p className="mt-1 text-sm text-[var(--fg-default)]">
                  {assessment.human_label ?? "Not reviewed yet"}
                </p>
                {assessment.recorded_at && assessment.human_label && (
                  <p className="text-xs text-[var(--fg-subtle)]">
                    {new Date(assessment.recorded_at).toLocaleDateString()}
                  </p>
                )}
              </div>
            </div>

            {assessment.requirement_codes.length > 0 && (
              <p className="mb-2 text-xs text-[var(--fg-subtle)]">
                {assessment.requirement_codes.join(" · ")}
              </p>
            )}

            <p className="text-sm leading-relaxed text-[var(--fg-default)]">{assessment.why}</p>

            {assessment.missing && (
              <p className="mt-2 flex items-start gap-2 text-sm leading-relaxed text-[var(--warning-700)]">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span>
                  <span className="font-medium">Missing: </span>
                  {assessment.missing}
                </span>
              </p>
            )}

            {/* Coverage, not a model's self-reported certainty. Labelled
                so nobody reads it as the latter. */}
            {/* Names the denominator. Requirements that do not bind this
                organization are not in it, and the sentence says so. */}
            <p className="mt-3 text-xs text-[var(--fg-subtle)]">
              Coverage is {assessment.satisfied_count} of {assessment.applicable_count}{" "}
              applicable requirement{assessment.applicable_count === 1 ? "" : "s"}
              {" "}evidenced. Computed from what is on file — not a legal conclusion, and
              not a score a model assigned itself.
            </p>

            {assessment.recorded_status && (
              <p className="mt-3 rounded-[var(--radius-md)] bg-[var(--bg-app)] p-3 text-sm text-[var(--fg-muted)]">
                A person recorded{" "}
                <span className="font-medium text-[var(--fg-default)]">
                  {assessment.recorded_status}
                </span>{" "}
                {assessment.recorded_at
                  ? `on ${new Date(assessment.recorded_at).toLocaleDateString()}`
                  : ""}
                . That decision stands alongside this and is not overwritten by it.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <div className="mb-8">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Evidence
        </h2>

        {assessment && assessment.evidence.length > 0 ? (
          <div className="flex flex-col gap-2">
            {assessment.evidence.map((item) => (
              <Card key={item.evidence_id}>
                <CardContent className="py-4">
                  <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                    <span className="flex items-center gap-2 font-medium text-[var(--fg-default)]">
                      <FileText
                        className="h-4 w-4 text-[var(--fg-subtle)]"
                        aria-hidden="true"
                      />
                      {/* The same Document Detail route the library and a
                          Copilot citation open. No link when the document
                          is not indexed — a filename without one beats a
                          link to a page that does not exist. */}
                      {item.document_href ? (
                        <Link
                          href={item.document_href}
                          className="hover:text-[var(--brand-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                        >
                          {item.filename}
                        </Link>
                      ) : (
                        item.filename
                      )}
                    </span>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {item.source_location && (
                        <Badge variant="outline">{item.source_location}</Badge>
                      )}
                      {item.mapped_by === "auto" && (
                        <Badge variant="secondary" className="gap-1">
                          <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
                          Mapped automatically
                        </Badge>
                      )}
                      {item.mapped_by === "human" && (
                        <Badge variant="success">Approved by a person</Badge>
                      )}
                    </div>
                  </div>

                  {item.quoted_passage && (
                    <blockquote className="mt-2 flex gap-2 border-l-2 border-[var(--brand-primary)] bg-[var(--bg-app)] p-3">
                      <Quote
                        className="mt-0.5 h-3 w-3 shrink-0 text-[var(--fg-subtle)]"
                        aria-hidden="true"
                      />
                      <p className="text-sm italic leading-relaxed text-[var(--fg-default)]">
                        {item.quoted_passage}
                      </p>
                    </blockquote>
                  )}

                  {item.model_confidence !== null && (
                    <p className="mt-1.5 text-xs text-[var(--fg-subtle)]">
                      {item.evidence_type?.replace(/_/g, " ")} · model confidence{" "}
                      {Math.round(item.model_confidence * 100)}%
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm leading-relaxed text-[var(--fg-muted)]">
                Nothing mapped to this control yet. Upload a policy or procedure under
                Documents and Veyntra will propose which controls it evidences — you do not
                need to attach anything by hand.
              </p>
            </CardContent>
          </Card>
        )}

        {/* Secondary on purpose: the normal path is that evidence arrives
            from document intelligence, not from someone hunting for a file. */}
        <div className="mt-3">
          <AttachEvidence controlId={id} label="Attach evidence manually" compact />
        </div>
      </div>

      {control.requirements.length > 0 && (
        <div className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
            Requirements this control serves
          </h2>
          <div className="flex flex-col gap-2">
            {(assessment?.requirements.length
              ? assessment.requirements
              : control.requirements.map((r) => ({
                  requirement_id: r.id,
                  reference_code: r.reference_code,
                  title: r.title,
                  applicability: "applicable" as const,
                  applicability_reason: "",
                  coverage: "no_evidence" as const,
                  missing_conditions: [] as string[],
                }))
            ).map((line) => (
              <Card key={line.requirement_id}>
                <CardContent className="py-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <span className="font-medium text-[var(--fg-default)]">
                        {line.reference_code}
                      </span>
                      <span className="text-[var(--fg-muted)]"> — {line.title}</span>
                    </div>
                    <Badge variant={REQUIREMENT_VARIANT[line.applicability] ?? "outline"}>
                      {REQUIREMENT_LABEL[line.applicability] ?? line.applicability}
                      {line.applicability !== "not_applicable" &&
                        ` · ${COVERAGE_LABEL[line.coverage] ?? line.coverage}`}
                    </Badge>
                  </div>
                  {/* Why a requirement is excluded belongs beside it. A
                      denominator that silently shrinks looks like a bug. */}
                  {line.applicability !== "applicable" && line.applicability_reason && (
                    <p className="mt-1 text-xs leading-relaxed text-[var(--fg-subtle)]">
                      {line.applicability_reason}
                    </p>
                  )}
                  {line.missing_conditions.length > 0 && (
                    <p className="mt-1 text-xs leading-relaxed text-[var(--warning-700)]">
                      Not covered: {line.missing_conditions.join("; ")}
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      <div className="mb-8">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
            Assessment history
          </h2>
          <Button size="sm" variant="outline" onClick={() => setOverrideOpen((v) => !v)}>
            {overrideOpen ? "Cancel" : "Override assessment"}
          </Button>
        </div>

        {overrideOpen && (
          <Card className="mb-3">
            <CardContent className="flex flex-col gap-3 pt-6">
              <p className="text-sm leading-relaxed text-[var(--fg-muted)]">
                Record your own conclusion. It is stored alongside the derived assessment,
                written to the audit log with your name and the time, and never silently
                replaces what was here before.
              </p>
              <Input
                placeholder="Why (recorded in the audit log)"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
              <div className="flex flex-wrap gap-2">
                {OVERRIDE_STATUSES.map((option) => (
                  <Button
                    key={option.value}
                    size="sm"
                    variant="outline"
                    disabled={recordAssessment.isPending}
                    onClick={() => recordAssessment.mutate(option.value)}
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        <h2 className="mb-3 mt-6 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Assessment history
        </h2>
        {control.assessments.length === 0 ? (
          <p className="text-sm text-[var(--fg-muted)]">
            No human assessment recorded. The assessment above is derived from the evidence
            on file.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {control.assessments.map((entry) => (
              <Card key={entry.id}>
                <CardContent className="flex items-center justify-between py-3">
                  <div>
                    <span className="font-medium text-[var(--fg-default)]">{entry.status}</span>
                    {entry.notes && (
                      <span className="text-[var(--fg-muted)]"> — {entry.notes}</span>
                    )}
                  </div>
                  <span className="text-xs text-[var(--fg-subtle)]">
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
