"use client";

import Link from "next/link";
import { use, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ChevronDown, FileText, Loader2, Sparkles } from "lucide-react";

import { ImportQuestionnaire } from "@/components/compliance/import-questionnaire";
import { LinkCustomerReview } from "@/components/compliance/link-customer-review";
import { RenameQuestionnaire } from "@/components/compliance/rename-questionnaire";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type {
  AnswerStatus,
  QuestionnaireDetail,
  QuestionnaireQuestionDetail,
} from "@/lib/types";

/** A questionnaire that answers itself, and says what it could not.
 *
 * This page used to be a form builder: an always-open Add Question form,
 * a single-line answer input, and a Suggest answer button to press once
 * per question. A real customer questionnaire is a hundred questions
 * long and the answers already exist — in the control register and in
 * the policies the customer uploaded. Pressing a button a hundred times
 * to fetch them is being the integration.
 *
 * So questions arrive by import and come back mostly answered. What is
 * left on this screen is the part that genuinely needs a person: the
 * answers Veyntra could not stand behind, and why.
 */

const STATUS_VARIANT: Record<AnswerStatus, "success" | "warning" | "secondary" | "outline"> = {
  approved: "success",
  needs_review: "warning",
  draft: "secondary",
  unanswered: "outline",
  rejected: "warning",
};

/** Work first. A page that opens on a wall of approved answers makes the
 * reader hunt for the ones that need them. */
const URGENCY: Record<AnswerStatus, number> = {
  needs_review: 0,
  unanswered: 1,
  rejected: 1,
  draft: 2,
  approved: 3,
};

const FILTERS = [
  { key: "all", label: "All" },
  { key: "attention", label: "Needs attention" },
  { key: "needs_review", label: "Needs review" },
  { key: "unanswered", label: "Unanswered" },
  { key: "approved", label: "Approved" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

function statusOf(question: QuestionnaireQuestionDetail): AnswerStatus {
  return (question.answer?.status as AnswerStatus) ?? "unanswered";
}

function matches(question: QuestionnaireQuestionDetail, filter: FilterKey): boolean {
  const status = statusOf(question);
  if (filter === "all") return true;
  if (filter === "attention") return status === "needs_review" || status === "unanswered";
  return status === filter;
}

export default function QuestionnaireDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<FilterKey>("all");

  const { data: questionnaire } = useQuery<QuestionnaireDetail>({
    queryKey: ["compliance", "questionnaires", id],
    queryFn: () => apiFetch<QuestionnaireDetail>(`/api/v1/compliance/questionnaires/${id}`),
    // Drafting runs in the background after an import; the page fills in
    // rather than making the user refresh to find out whether it worked.
    refetchInterval: (query) =>
      (query.state.data?.questions ?? []).some((q) => statusOf(q) === "unanswered")
        ? 5000
        : false,
    // Kept polling when the tab is not in front. Drafting a hundred
    // questions takes minutes and nobody watches it happen — without
    // this the answers land in the database and the page goes on
    // showing "unanswered" until the reader thinks to reload.
    refetchIntervalInBackground: true,
  });

  const refresh = () =>
    void queryClient.invalidateQueries({ queryKey: ["compliance", "questionnaires", id] });

  const draftAll = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/questionnaires/${id}/draft-answers`, { method: "POST" }),
    onSuccess: refresh,
  });

  const sorted = useMemo(() => {
    return [...(questionnaire?.questions ?? [])].sort((a, b) => {
      const byUrgency = URGENCY[statusOf(a)] - URGENCY[statusOf(b)];
      return byUrgency !== 0 ? byUrgency : a.order_index - b.order_index;
    });
  }, [questionnaire]);

  if (!questionnaire) return null;

  const visible = sorted.filter((question) => matches(question, filter));
  const { progress } = questionnaire;

  return (
    <div>
      <PageHeader
        title={questionnaire.title}
        description={
          questionnaire.customer_name
            ? `Security questionnaire from ${questionnaire.customer_name}`
            : "Security questionnaire"
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {progress.unanswered > 0 && (
              <Button
                size="sm"
                variant="ai"
                disabled={draftAll.isPending}
                onClick={() => draftAll.mutate()}
              >
                {draftAll.isPending ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <Sparkles className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
                )}
                Draft {progress.unanswered} remaining
              </Button>
            )}
            {/* One way in. The import dialog already takes a file or
                pasted text, and pasting a single question is the same
                action as pasting forty — a second button for that was
                two paths to one outcome. */}
            <ImportQuestionnaire
              questionnaireId={id}
              formats={questionnaire.supported_import_formats}
              onDone={refresh}
            />
          </div>
        }
      />

      {/* Flagged, not fixed: the product can see the title reads like a
          question, but only a person knows what it should say. */}
      {questionnaire.title_looks_like_a_question && (
        <RenameQuestionnaire
          questionnaireId={questionnaire.id}
          currentTitle={questionnaire.title}
          suggestedCustomer={questionnaire.customer_name}
        />
      )}

      {/* Only ever set for a customer questionnaire with no customer on
          it. An internal assessment is not missing anything. */}
      {questionnaire.needs_customer && (
        <LinkCustomerReview
          questionnaireId={questionnaire.id}
          suggestedCustomer={questionnaire.suggested_customer}
          suggestionReason={questionnaire.suggested_customer_reason}
        />
      )}

      <QuestionnaireSummary questionnaire={questionnaire} />

      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter questions">
        {FILTERS.map((option) => (
          <Button
            key={option.key}
            size="sm"
            variant={filter === option.key ? "default" : "outline"}
            aria-pressed={filter === option.key}
            onClick={() => setFilter(option.key)}
          >
            {option.label}
          </Button>
        ))}
      </div>

      {questionnaire.questions.length === 0 ? (
        <EmptyState
          title="No questions yet"
          description={
            "Import the customer's questionnaire — a spreadsheet, a document, or the " +
            "questions pasted from their email — and Veyntra drafts the answers from " +
            "your compliance records and uploaded documents."
          }
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {visible.map((question) => (
            <QuestionCard
              key={question.id}
              questionnaireId={id}
              question={question}
              onSaved={refresh}
            />
          ))}
        </ul>
      )}

      {questionnaire.questions.length > 0 && visible.length === 0 && (
        <p className="py-6 text-sm text-[var(--fg-muted)]">
          Nothing in this questionnaire matches that filter.
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */

/** Who is asking, by when, and what is left. */
function QuestionnaireSummary({ questionnaire }: { questionnaire: QuestionnaireDetail }) {
  const { progress } = questionnaire;
  const facts = [
    questionnaire.customer_name ? { label: "Customer", value: questionnaire.customer_name } : null,
    {
      label: "Source",
      value: questionnaire.source === "customer_provided" ? "Customer-provided" : "Internal",
    },
    questionnaire.due_at
      ? {
          label: "Due",
          value: new Date(questionnaire.due_at).toLocaleDateString(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
          }),
        }
      : null,
  ].filter(Boolean) as { label: string; value: string }[];

  return (
    <Card className="mb-5">
      <CardContent className="py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <dl className="flex flex-wrap gap-x-6 gap-y-1">
            {facts.map((fact) => (
              <div key={fact.label} className="flex items-baseline gap-1.5">
                <dt className="text-xs text-[var(--fg-subtle)]">{fact.label}</dt>
                <dd className="text-sm text-[var(--fg-default)]">{fact.value}</dd>
              </div>
            ))}
            {/* Where this questionnaire belongs. A customer sends a
                security questionnaire, then a privacy one; they are one
                engagement, and the reader should be able to get to it. */}
            {questionnaire.security_review_href && (
              <>
                <div className="flex items-baseline gap-1.5">
                  <dt className="text-xs text-[var(--fg-subtle)]">Security review</dt>
                  <dd className="text-sm">
                    <Link
                      href={questionnaire.security_review_href}
                      className="text-[var(--brand-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
                    >
                      {questionnaire.security_review_title}
                    </Link>
                  </dd>
                </div>
                {/* How far the engagement got, and whether it is still
                    open. Two separate facts: a review can be ready to
                    share and archived at once, and reading either one as
                    the other is the confusion this splits apart. */}
                {questionnaire.security_review_status_label && (
                  <div className="flex items-baseline gap-1.5">
                    <dt className="text-xs text-[var(--fg-subtle)]">Review status</dt>
                    <dd className="text-sm text-[var(--fg-default)]">
                      {questionnaire.security_review_status_label}
                    </dd>
                  </div>
                )}
                <div className="flex items-baseline gap-1.5">
                  <dt className="text-xs text-[var(--fg-subtle)]">Review lifecycle</dt>
                  <dd className="text-sm text-[var(--fg-default)]">
                    {questionnaire.security_review_archived_at
                      ? `Archived ${new Date(
                          questionnaire.security_review_archived_at,
                        ).toLocaleDateString(undefined, {
                          year: "numeric",
                          month: "short",
                          day: "numeric",
                        })}`
                      : "Active"}
                  </dd>
                </div>
              </>
            )}
          </dl>
          {/* The status the server derived from the answers — the same
              value the list renders. This badge used to compute its own
              opinion from `progress`, which is how the detail page could
              say "Ready to share" over a record stored as draft. */}
          <div className="flex shrink-0 items-center gap-2">
            {questionnaire.archived_at && (
              <Badge variant="secondary" className="gap-1">
                <Archive className="h-3 w-3" aria-hidden="true" />
                Archived
              </Badge>
            )}
            <StatusBadge status={questionnaire.status} />
          </div>
        </div>

        <div className="mt-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm text-[var(--fg-muted)]">
              <span className="text-lg font-semibold text-[var(--fg-default)]">
                {progress.approved}
              </span>{" "}
              of {progress.total} approved
            </p>
            <p className="text-sm font-medium text-[var(--fg-default)]">
              {progress.percent_complete}% complete
            </p>
          </div>
          <div
            className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-[var(--gray-200)]"
            role="progressbar"
            aria-valuenow={progress.percent_complete}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${progress.percent_complete}% of questions approved`}
          >
            <div
              className="h-full rounded-full bg-[var(--brand-primary)]"
              style={{ width: `${progress.percent_complete}%` }}
            />
          </div>
          <p className="mt-2 flex flex-wrap gap-x-4 text-xs text-[var(--fg-subtle)]">
            <span>{progress.needs_review} need review</span>
            <span>{progress.draft} drafted</span>
            <span>{progress.unanswered} unanswered</span>
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */

function QuestionCard({
  questionnaireId,
  question,
  onSaved,
}: {
  questionnaireId: string;
  question: QuestionnaireQuestionDetail;
  onSaved: () => void;
}) {
  const answer = question.answer;
  const status = statusOf(question);
  const [draft, setDraft] = useState(answer?.answer_text ?? "");
  const [editing, setEditing] = useState(false);

  const save = useMutation({
    mutationFn: (next: { answer_text: string; status: AnswerStatus }) =>
      apiFetch(
        `/api/v1/compliance/questionnaires/${questionnaireId}/questions/${question.id}/answer`,
        { method: "PATCH", body: next }
      ),
    onSuccess: () => {
      setEditing(false);
      onSaved();
    },
  });

  const text = editing ? draft : (answer?.answer_text ?? "");
  const canApprove = editing ? draft.trim().length > 0 : (answer?.can_approve ?? false);

  return (
    <li>
      <Card>
        <CardContent className="py-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="min-w-0 font-medium text-[var(--fg-default)]">{question.text}</p>
            <Badge variant={STATUS_VARIANT[status]}>
              {answer?.status_label ?? "Unanswered"}
            </Badge>
          </div>

          {status === "unanswered" && !editing ? (
            <p className="mt-2 text-sm text-[var(--fg-muted)]">
              {answer?.review_reason ??
                "Veyntra has not drafted an answer for this question yet."}
            </p>
          ) : (
            <div className="mt-3">
              <p className="mb-1 text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                {answer?.source_type === "manual" ? "Answer" : "Suggested answer"}
              </p>
              {editing ? (
                // Security questionnaire answers run to several
                // sentences; the single-line input this replaces made
                // that painful enough to discourage editing at all.
                <Textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={6}
                  className="max-h-72"
                  aria-label={`Answer to: ${question.text}`}
                />
              ) : (
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--fg-default)]">
                  {text || "—"}
                </p>
              )}
            </div>
          )}

          {answer?.review_reason && status === "needs_review" && (
            <p className="mt-2 border-l-2 border-[var(--warning-600)]/40 pl-2 text-sm leading-relaxed text-[var(--fg-muted)]">
              <span className="text-[var(--fg-subtle)]">Why review is needed: </span>
              {answer.review_reason}
            </p>
          )}

          <AnswerSources answer={answer} />

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {editing ? (
                <>
                  <Button
                    size="sm"
                    disabled={save.isPending}
                    onClick={() => save.mutate({ answer_text: draft, status: "draft" })}
                  >
                    Save draft
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
                    Cancel
                  </Button>
                </>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setDraft(answer?.answer_text ?? "");
                    setEditing(true);
                  }}
                >
                  Edit
                </Button>
              )}

              <Button
                size="sm"
                disabled={!canApprove || save.isPending}
                title={
                  !canApprove ? (answer?.approval_blocked_reason ?? undefined) : undefined
                }
                onClick={() => save.mutate({ answer_text: text, status: "approved" })}
              >
                Approve
              </Button>

              {/* An empty answer cannot be approved, and the button says
                  why rather than being silently dead. */}
              {!canApprove && answer?.approval_blocked_reason && (
                <span className="text-xs text-[var(--fg-subtle)]">
                  {answer.approval_blocked_reason}
                </span>
              )}
            </div>

            {answer?.confidence !== null && answer?.confidence !== undefined && (
              <span className="text-xs text-[var(--fg-subtle)]">
                Veyntra&apos;s confidence: {Math.round(answer.confidence * 100)}%
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </li>
  );
}

/** Where the answer came from, as references a person can open. */
function AnswerSources({
  answer,
}: {
  answer: QuestionnaireQuestionDetail["answer"];
}) {
  const citations = answer?.citations ?? [];
  if (citations.length === 0) return null;

  return (
    <details className="group mt-3 rounded-[var(--radius-md)] border border-[var(--border-default)]">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-[var(--radius-md)] px-3 py-2 text-xs font-medium text-[var(--fg-muted)] hover:text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]">
        <ChevronDown
          className="h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-180"
          aria-hidden="true"
        />
        Sources ({citations.length})
      </summary>
      <ul className="flex flex-col gap-2 px-3 pb-3">
        {citations.map((citation, index) => (
          <li key={`${citation.document_id}-${index}`}>
            {citation.href ? (
              <Link
                href={citation.href}
                className="inline-flex items-center gap-1.5 rounded-sm text-xs font-medium text-[var(--fg-default)] hover:text-[var(--brand-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
              >
                <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {citation.reference}
              </Link>
            ) : (
              <span className="text-xs font-medium text-[var(--fg-default)]">
                {citation.reference}
              </span>
            )}
            {citation.passage && (
              <blockquote className="mt-1 border-l-2 border-[var(--border-default)] pl-2 text-xs leading-relaxed text-[var(--fg-muted)]">
                {citation.passage}
              </blockquote>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
