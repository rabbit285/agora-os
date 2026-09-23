"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ClipboardCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  AISystem,
  DpiaContext,
  DpiaWorkflow,
  ProcessingActivity,
} from "@/lib/types";

/** Starting a DPIA by screening, not by guessing.
 *
 * The old flow was a title, a risk dropdown and "Start DPIA" — which
 * asks somebody to classify the risk *before* the screening that exists
 * to establish it, and then to retype facts already sitting in the
 * record they are assessing.
 *
 * So: name what is being assessed, read back what Veyntra already knows
 * about it, answer the criteria, and get a recommendation. The DPIA is
 * created only after a person says a DPIA is required — the screening
 * counts criteria, it does not conclude anything, and a product that
 * created the assessment automatically would have made that call for
 * them.
 */
const SELECT_CLASS =
  "flex h-9 w-full rounded-md border border-[var(--border-strong)] bg-[var(--bg-default)] px-3 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

type Criteria = { mandatory: Record<string, string>; edpb: Record<string, string> };

const OUTCOME_COPY: Record<string, { label: string; tone: string }> = {
  required: {
    label: "A DPIA appears to be required",
    tone: "text-[var(--warning-800)]",
  },
  recommended: {
    label: "A DPIA may be required",
    tone: "text-[var(--warning-700)]",
  },
  not_indicated: {
    label: "A DPIA does not currently appear necessary",
    tone: "text-[var(--fg-muted)]",
  },
};

function Fact({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="flex gap-3">
      <span className="w-36 shrink-0 text-xs text-[var(--fg-muted)]">{label}</span>
      <span className="text-sm text-[var(--fg-default)]">{value}</span>
    </div>
  );
}

export function StartDpiaScreening() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [subject, setSubject] = useState<"activity" | "ai_system">("activity");
  const [subjectId, setSubjectId] = useState("");
  const [context, setContext] = useState<DpiaContext | null>(null);
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const [result, setResult] = useState<DpiaWorkflow | null>(null);
  // Required to decide a DPIA is *not* needed. An unexplained no is not
  // a record anybody can defend later.
  const [rationale, setRationale] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: criteria } = useQuery<Criteria>({
    queryKey: ["compliance", "dpia-screening-criteria"],
    queryFn: () => apiFetch<Criteria>("/api/v1/compliance/dpias/screening-criteria"),
    enabled: open,
  });
  const { data: activities } = useQuery<ProcessingActivity[]>({
    queryKey: ["compliance", "processing-activities"],
    queryFn: () =>
      apiFetch<ProcessingActivity[]>("/api/v1/compliance/processing-activities"),
    enabled: open,
  });
  const { data: systems } = useQuery<AISystem[]>({
    queryKey: ["compliance", "ai-systems"],
    queryFn: () => apiFetch<AISystem[]>("/api/v1/compliance/ai-systems"),
    enabled: open,
  });

  const reset = () => {
    setSubjectId("");
    setContext(null);
    setAnswers({});
    setResult(null);
    setRationale("");
    setError(null);
  };

  const load = useMutation<DpiaContext, unknown, string>({
    mutationFn: (id) =>
      apiFetch<DpiaContext>(
        `/api/v1/compliance/dpias/prefill?${
          subject === "activity"
            ? `processing_activity_id=${id}`
            : `ai_system_id=${id}`
        }`,
      ),
    onMutate: () => setError(null),
    onSuccess: (loaded) => {
      setContext(loaded);
      // Criteria the record already speaks to arrive ticked, each with
      // its reason. Everything else stays blank — silence on a criterion
      // is not a "no".
      setAnswers(
        Object.fromEntries(
          loaded.suggested_answers.map((answer) => [answer.criterion, answer.value]),
        ),
      );
    },
    onError: () => setError("Could not read that record."),
  });

  const screen = useMutation<DpiaWorkflow, unknown, void>({
    mutationFn: () =>
      apiFetch<DpiaWorkflow>("/api/v1/compliance/dpias/screening/start", {
        method: "POST",
        body: {
          answers,
          processing_activity_id: context?.processing_activity_id,
          ai_system_id: context?.processing_activity_id
            ? null
            : context?.ai_system_id,
        },
      }),
    onMutate: () => setError(null),
    onSuccess: setResult,
    onError: (cause) =>
      setError(
        cause instanceof ApiError ? cause.message : "The screening did not run.",
      ),
  });

  const decide = useMutation<DpiaWorkflow, unknown, "required" | "not_required">({
    mutationFn: (decision) =>
      apiFetch<DpiaWorkflow>(
        `/api/v1/compliance/dpias/${result?.id}/screening/decision`,
        {
          method: "POST",
          body: {
            decision,
            rationale: decision === "not_required" ? rationale : null,
          },
        },
      ),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setOpen(false);
      reset();
      await queryClient.invalidateQueries({ queryKey: ["compliance"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was recorded.",
      ),
  });

  const options =
    subject === "activity"
      ? (activities ?? []).map((row) => ({ id: row.id, label: row.name }))
      : (systems ?? []).map((row) => ({ id: row.id, label: row.name }));

  // The screening only runs against a processing activity — it is the
  // record that carries the lawful basis and the data subjects.
  const screenable = Boolean(context?.processing_activity_id);
  const reasons = new Map(
    (context?.suggested_answers ?? []).map((answer) => [
      answer.criterion,
      answer.reason,
    ]),
  );

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <ClipboardCheck className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
        Start DPIA screening
      </Button>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) reset();
        }}
      >
        <DialogContent className="max-h-[86vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Start DPIA screening</DialogTitle>
            <DialogDescription>
              Screening records whether an assessment is needed, and why.
              Veyntra counts the criteria you report; whether a DPIA is
              required is your decision.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-4">
            {/* §4: what is being assessed, before anything else. */}
            <div className="flex flex-col gap-2">
              <p className="text-xs font-medium text-[var(--fg-muted)]">
                What are you assessing?
              </p>
              <div className="flex gap-2">
                {(
                  [
                    ["activity", "Processing activity"],
                    ["ai_system", "AI system"],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={subject === key}
                    onClick={() => {
                      setSubject(key);
                      reset();
                    }}
                    className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                      subject === key
                        ? "border-[var(--border-strong)] bg-[var(--bg-subtle)] font-medium text-[var(--fg-default)]"
                        : "border-[var(--border-default)] text-[var(--fg-muted)]"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <select
                aria-label="Record to assess"
                className={SELECT_CLASS}
                value={subjectId}
                onChange={(event) => {
                  setSubjectId(event.target.value);
                  setResult(null);
                  if (event.target.value) load.mutate(event.target.value);
                }}
              >
                <option value="">Select a record…</option>
                {options.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
              {options.length === 0 && (
                <p className="text-xs text-[var(--fg-subtle)]">
                  {subject === "activity"
                    ? "No processing activities recorded yet."
                    : "No AI systems registered yet."}
                </p>
              )}
            </div>

            {/* §5: what Veyntra already knows, rather than asking again. */}
            {context && (
              <div className="rounded-md border border-[var(--border-default)] px-3 py-3">
                <p className="mb-2 text-xs font-medium text-[var(--fg-default)]">
                  What Veyntra already knows
                </p>
                <div className="flex flex-col gap-1.5">
                  <Fact label="DPIA title" value={context.title} />
                  <Fact label="Purpose" value={context.purpose} />
                  <Fact label="Data subjects" value={context.data_subjects} />
                  <Fact
                    label="Personal data"
                    value={context.data_categories.join(", ") || null}
                  />
                  <Fact
                    label="AI systems"
                    value={
                      context.ai_systems.map((row) => row.label).join(", ") || null
                    }
                  />
                  <Fact
                    label="Processors"
                    value={context.vendors.map((row) => row.label).join(", ") || null}
                  />
                  <Fact
                    label="Transfers"
                    value={
                      context.transfers.map((row) => row.label).join(", ") || null
                    }
                  />
                </div>
              </div>
            )}

            {/* §6: the criteria, with the pre-ticked ones explained. */}
            {context && criteria && (
              <div className="flex flex-col gap-3">
                {(
                  [
                    ["Article 35(3) cases", criteria.mandatory],
                    ["EDPB criteria", criteria.edpb],
                  ] as const
                ).map(([heading, group]) => (
                  <div key={heading}>
                    <p className="mb-1.5 text-xs font-medium text-[var(--fg-muted)]">
                      {heading}
                    </p>
                    <div className="flex flex-col gap-1.5">
                      {Object.entries(group).map(([key, label]) => (
                        <label
                          key={key}
                          className="flex gap-2 text-xs text-[var(--fg-default)]"
                        >
                          <input
                            type="checkbox"
                            className="mt-0.5"
                            checked={Boolean(answers[key])}
                            onChange={(event) => {
                              setAnswers({ ...answers, [key]: event.target.checked });
                              setResult(null);
                            }}
                          />
                          <span>
                            {label}
                            {reasons.has(key) && (
                              <span className="block text-[var(--fg-subtle)]">
                                Suggested: {reasons.get(key)}
                              </span>
                            )}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {result && (
              <div className="rounded-md border border-[var(--border-default)] bg-[var(--bg-subtle)] px-3 py-3">
                {/* §4: screening an activity that already has an
                    assessment continues it rather than opening a second
                    one. */}
                {result.reused_existing && (
                  <p className="mb-2 text-xs text-[var(--fg-muted)]">
                    Continuing the existing assessment:{" "}
                    <span className="font-medium">{result.title}</span>
                  </p>
                )}
                <p
                  className={`text-sm font-semibold ${
                    OUTCOME_COPY[result.screening_outcome ?? ""]?.tone ?? ""
                  }`}
                >
                  {OUTCOME_COPY[result.screening_outcome ?? ""]?.label ??
                    result.screening_outcome}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-[var(--fg-muted)]">
                  {result.screening_rationale_text}
                </p>
                {result.screening_criteria_met.length > 0 && (
                  <ul className="mt-2 flex list-disc flex-col gap-0.5 pl-4">
                    {result.screening_criteria_met.map((criterion) => (
                      <li key={criterion} className="text-xs text-[var(--fg-muted)]">
                        {criterion}
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-2 text-xs text-[var(--fg-subtle)]">
                  This is a recommendation based on what you reported, not a
                  determination. The decision — and the record of it — is yours.
                </p>

                {/* §3: declining needs a reason. */}
                <div className="mt-3">
                  <label
                    htmlFor="dpia-not-required-reason"
                    className="mb-1 block text-xs text-[var(--fg-muted)]"
                  >
                    Reason (required to record that a DPIA is not needed)
                  </label>
                  <Input
                    id="dpia-not-required-reason"
                    placeholder="Why this processing does not need an assessment"
                    value={rationale}
                    onChange={(event) => setRationale(event.target.value)}
                  />
                </div>
              </div>
            )}

            {error && (
              <p role="alert" className="text-sm text-[var(--fg-danger)]">
                {error}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => {
                setOpen(false);
                reset();
              }}
            >
              <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
              Cancel
            </Button>
            {!result ? (
              <Button
                disabled={!screenable || screen.isPending}
                onClick={() => screen.mutate()}
              >
                {screen.isPending ? "Screening…" : "Run screening"}
              </Button>
            ) : (
              <>
                {/* §3: both answers are decisions, and both are recorded.
                    "Not required" is a conclusion somebody reached, not
                    the absence of one. */}
                <Button
                  variant="outline"
                  disabled={!rationale.trim() || decide.isPending}
                  onClick={() => decide.mutate("not_required")}
                >
                  DPIA not required
                </Button>
                <Button
                  disabled={decide.isPending}
                  onClick={() => decide.mutate("required")}
                >
                  {decide.isPending ? "Recording…" : "Confirm DPIA required"}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
