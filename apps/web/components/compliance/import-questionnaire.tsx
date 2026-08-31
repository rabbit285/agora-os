"use client";

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  CopyCheck,
  FileUp,
  Loader2,
  Upload,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { uploadFile } from "@/lib/upload";
import type { ImportAnalysis, ImportResult } from "@/lib/types";

/** Getting a customer's questionnaire into Veyntra.
 *
 * The workflow is input → analyse → preview → confirm, and the preview
 * is the point. Creating a hundred questions the moment somebody pastes
 * something is fast and unsafe: they cannot see what was found, what was
 * thrown away or what already existed, and by the time they can it is a
 * hundred rows to unpick by hand.
 *
 * Two ways in, because customers send both. A file — the spreadsheet or
 * PDF that arrived by email — or text pasted straight out of that email.
 * The formats named here are the ones the parser genuinely reads; the
 * modal used to list them beside no file picker at all, which promised
 * something the screen could not do.
 */

/** Content types the API accepts, paired with what a person calls them. */
const ACCEPTED = ".csv,.txt,.md,.xlsx,.docx,.pdf";

type Step = "input" | "preview" | "done";

export function ImportQuestionnaire({
  questionnaireId,
  formats,
  onDone,
}: {
  questionnaireId: string;
  formats: string[];
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>("input");
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<ImportAnalysis | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<string>("");
  const fileInput = useRef<HTMLInputElement>(null);

  const reset = () => {
    setStep("input");
    setText("");
    setFileName(null);
    setAnalysis(null);
    setResult(null);
    setSkipped(new Set());
    setError(null);
    setStage("");
  };

  const analyze = useMutation({
    mutationFn: async (file: File | null) => {
      setError(null);
      let body: Record<string, unknown>;
      if (file) {
        setStage("Uploading the file…");
        const fileId = await uploadFile(file, { classification: "confidential" });
        setStage("Reading the questionnaire…");
        body = { file_id: fileId };
      } else {
        setStage("Reading the questions…");
        body = { questions_text: text };
      }
      return apiFetch<ImportAnalysis>(
        `/api/v1/compliance/questionnaires/${questionnaireId}/import/analyze`,
        { method: "POST", body },
      );
    },
    onSuccess: (data) => {
      setAnalysis(data);
      setStage("");
      setStep("preview");
    },
    onError: (cause) => {
      setStage("");
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Those questions could not be read. Nothing was imported.",
      );
    },
  });

  const confirm = useMutation({
    mutationFn: () => {
      const chosen = (analysis?.lines ?? [])
        .filter((line) => line.importable && !skipped.has(line.text))
        .map((line) => line.text);
      return apiFetch<ImportResult>(
        `/api/v1/compliance/questionnaires/${questionnaireId}/import/confirm`,
        {
          method: "POST",
          body: {
            questions: chosen,
            draft_answers: true,
            source_filename: fileName,
          },
        },
      );
    },
    onSuccess: (data) => {
      setResult(data);
      setStep("done");
      onDone();
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Those questions could not be imported. Nothing was created.",
      ),
  });

  const importable = (analysis?.lines ?? []).filter(
    (line) => line.importable && !skipped.has(line.text),
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm">
          <Upload className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
          Import questionnaire
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto p-6 sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import customer questionnaire</DialogTitle>
        </DialogHeader>

        {step === "input" && (
          <InputStep
            text={text}
            setText={setText}
            fileName={fileName}
            formats={formats}
            fileInput={fileInput}
            onFile={(file) => {
              setFileName(file.name);
              analyze.mutate(file);
            }}
          />
        )}

        {step === "preview" && analysis && (
          <PreviewStep
            analysis={analysis}
            skipped={skipped}
            onToggleSkip={(lineText) =>
              setSkipped((current) => {
                const next = new Set(current);
                if (next.has(lineText)) next.delete(lineText);
                else next.add(lineText);
                return next;
              })
            }
          />
        )}

        {step === "done" && result && <ResultStep result={result} />}

        {stage && (
          <p className="mt-4 flex items-center gap-2 text-sm text-[var(--fg-muted)]">
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            {stage}
          </p>
        )}

        {error && (
          <p role="alert" className="mt-4 text-sm text-[var(--fg-danger)]">
            {error}
          </p>
        )}

        <DialogFooter className="mt-6 flex-wrap border-t border-[var(--border-default)] pt-4">
          {step === "input" && (
            <>
              <Button variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button
                disabled={!text.trim() || analyze.isPending}
                onClick={() => analyze.mutate(null)}
              >
                {analyze.isPending && (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                )}
                Analyze questions
              </Button>
            </>
          )}

          {step === "preview" && (
            <>
              <Button variant="outline" onClick={() => setStep("input")}>
                Back
              </Button>
              <Button
                disabled={importable.length === 0 || confirm.isPending}
                onClick={() => confirm.mutate()}
              >
                {confirm.isPending && (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                )}
                {importable.length === 0
                  ? "Nothing to import"
                  : `Import ${importable.length} question${importable.length === 1 ? "" : "s"}`}
              </Button>
            </>
          )}

          {step === "done" && (
            <Button onClick={() => setOpen(false)}>Done</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */

function InputStep({
  text,
  setText,
  fileName,
  formats,
  fileInput,
  onFile,
}: {
  text: string;
  setText: (value: string) => void;
  fileName: string | null;
  formats: string[];
  fileInput: React.RefObject<HTMLInputElement | null>;
  onFile: (file: File) => void;
}) {
  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm leading-relaxed text-[var(--fg-muted)]">
        Veyntra will extract the questions, draft answers from your existing compliance
        records and documents, and flag uncertain answers for review. Nothing is created
        until you have seen what it found.
      </p>

      <div>
        <h3 className="text-sm font-medium text-[var(--fg-default)]">Upload file</h3>
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPTED}
          className="sr-only"
          aria-label="Questionnaire file"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) onFile(file);
          }}
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => fileInput.current?.click()}>
            <FileUp className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
            Choose file
          </Button>
          {fileName && (
            <span className="truncate text-sm text-[var(--fg-muted)]">{fileName}</span>
          )}
        </div>
        {/* Named because the picker behind them genuinely reads them.
            This list used to appear beside no picker at all. */}
        {formats.length > 0 && (
          <p className="mt-1.5 text-xs text-[var(--fg-subtle)]">
            Supported: {formats.join(", ")}
          </p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="h-px flex-1 bg-[var(--border-default)]" aria-hidden="true" />
        <span className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">or</span>
        <span className="h-px flex-1 bg-[var(--border-default)]" aria-hidden="true" />
      </div>

      <div>
        <label
          htmlFor="paste-questions"
          className="text-sm font-medium text-[var(--fg-default)]"
        >
          Paste questions
        </label>
        <Textarea
          id="paste-questions"
          value={text}
          onChange={(event) => setText(event.target.value)}
          rows={8}
          className="mt-2"
          // Placeholder, not a value. The old dialog's example read as
          // real entered data, so people deleted it before typing.
          placeholder={
            "Paste questions here, one per line or copied from a spreadsheet…\n\nFor example:\nDo you have an information security policy?\nDo you encrypt customer data at rest?"
          }
        />
      </div>
    </div>
  );
}

const OUTCOME = {
  new: {
    icon: Check,
    label: "New",
    tone: "text-[var(--fg-success)]",
  },
  duplicate: {
    icon: CopyCheck,
    label: "Already here",
    tone: "text-[var(--fg-subtle)]",
  },
  possible_duplicate: {
    icon: CopyCheck,
    label: "Possible duplicate",
    tone: "text-[var(--warning-700)]",
  },
  unparsed: {
    icon: AlertTriangle,
    label: "Not recognised",
    tone: "text-[var(--warning-700)]",
  },
} as const;

function PreviewStep({
  analysis,
  skipped,
  onToggleSkip,
}: {
  analysis: ImportAnalysis;
  skipped: Set<string>;
  onToggleSkip: (text: string) => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm font-medium text-[var(--fg-default)]">{analysis.headline}</p>
      <p className="text-xs text-[var(--fg-subtle)]">
        Nothing has been created yet.
      </p>

      <ul className="mt-1 flex max-h-72 flex-col gap-2 overflow-y-auto pr-2">
        {analysis.lines.map((line, index) => {
          const tone = OUTCOME[line.outcome] ?? OUTCOME.unparsed;
          const Icon = tone.icon;
          const isSkipped = skipped.has(line.text);
          return (
            <li
              key={`${line.outcome}-${index}`}
              className="rounded-[var(--radius-md)] border border-[var(--border-default)] px-3.5 py-2.5"
            >
              <div className="flex items-start gap-2">
                <Icon
                  className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${tone.tone}`}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <p
                    className={`text-sm ${
                      isSkipped
                        ? "text-[var(--fg-subtle)] line-through"
                        : "text-[var(--fg-default)]"
                    }`}
                  >
                    {line.text}
                  </p>
                  <p className="text-xs text-[var(--fg-subtle)]">
                    {tone.label}
                    {line.matches && ` · matches "${line.matches}"`}
                  </p>
                  {line.reason && (
                    <p className="mt-0.5 text-xs text-[var(--fg-muted)]">{line.reason}</p>
                  )}
                </div>
                {/* A possible duplicate is the reader's call — which is
                    the whole reason it is flagged rather than merged. */}
                {line.outcome === "possible_duplicate" && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="shrink-0"
                    onClick={() => onToggleSkip(line.text)}
                  >
                    {isSkipped ? "Import anyway" : "Skip"}
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ResultStep({ result }: { result: ImportResult }) {
  return (
    <div className="flex flex-col gap-2.5">
      <p className="text-sm font-medium text-[var(--fg-default)]">
        {result.created === 0
          ? "Nothing new to import — every question was already here."
          : `${result.created} question${result.created === 1 ? "" : "s"} imported.`}
      </p>

      {result.duplicates_skipped > 0 && (
        <p className="text-sm text-[var(--fg-muted)]">
          {result.duplicates_skipped} already existed and {result.duplicates_skipped === 1 ? "was" : "were"} not
          created again.
        </p>
      )}

      {result.drafting && (
        <p className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          Answers are being drafted. Statuses update as each one finishes.
        </p>
      )}

      {/* Importing unresolved questions into something marked finished
          has to move it back, and saying so beats letting somebody
          notice later that it stopped being ready to share. */}
      {result.status_before !== result.status_after && (
        <p className="text-sm text-[var(--fg-muted)]">
          This questionnaire is no longer marked complete — there are new questions to
          answer.
        </p>
      )}
    </div>
  );
}
