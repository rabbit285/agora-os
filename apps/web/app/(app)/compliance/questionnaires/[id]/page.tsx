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
import type {
  AnswerStatus,
  QuestionCategory,
  QuestionnaireDetail,
  QuestionnaireQuestionDetail,
  QuestionnaireStatus,
} from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-neutral-300 bg-white px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400";

function QuestionRow({
  questionnaireId,
  question,
}: {
  questionnaireId: string;
  question: QuestionnaireQuestionDetail;
}) {
  const queryClient = useQueryClient();
  const [answerText, setAnswerText] = useState(question.answer?.answer_text ?? "");

  const invalidate = () =>
    queryClient.invalidateQueries({
      queryKey: ["compliance", "questionnaires", questionnaireId],
    });

  const suggestAnswer = useMutation({
    mutationFn: () =>
      apiFetch(
        `/api/v1/compliance/questionnaires/${questionnaireId}/questions/${question.id}/suggest-answer`,
        { method: "POST" },
      ),
    onSuccess: (data) => {
      setAnswerText((data as { answer_text: string | null }).answer_text ?? "");
      invalidate();
    },
  });

  const saveAnswer = useMutation({
    mutationFn: (status: AnswerStatus) =>
      apiFetch(
        `/api/v1/compliance/questionnaires/${questionnaireId}/questions/${question.id}/answer`,
        { method: "PATCH", body: { answer_text: answerText || null, status } },
      ),
    onSuccess: invalidate,
  });

  const status = question.answer?.status ?? "missing";
  const sourceType = question.answer?.source_type;

  return (
    <Card>
      <CardContent className="flex flex-col gap-2 pt-6">
        <div className="flex items-center justify-between">
          <div className="font-medium text-neutral-900">{question.text}</div>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{question.category}</Badge>
            <StatusBadge status={status} />
          </div>
        </div>
        {sourceType && (
          <div className="text-xs text-neutral-400">source: {sourceType.replace(/_/g, " ")}</div>
        )}
        <Input
          placeholder="Answer text"
          value={answerText}
          onChange={(e) => setAnswerText(e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={suggestAnswer.isPending}
            onClick={() => suggestAnswer.mutate()}
          >
            Suggest answer
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={saveAnswer.isPending}
            onClick={() => saveAnswer.mutate("draft")}
          >
            Save as draft
          </Button>
          <Button
            size="sm"
            disabled={saveAnswer.isPending || !answerText.trim()}
            onClick={() => saveAnswer.mutate("approved")}
          >
            Approve
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function QuestionnaireDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [questionText, setQuestionText] = useState("");
  const [category, setCategory] = useState<QuestionCategory>("compliance");

  const { data: questionnaire } = useQuery<QuestionnaireDetail>({
    queryKey: ["compliance", "questionnaires", id],
    queryFn: () => apiFetch<QuestionnaireDetail>(`/api/v1/compliance/questionnaires/${id}`),
  });

  const updateStatus = useMutation({
    mutationFn: (status: QuestionnaireStatus) =>
      apiFetch(`/api/v1/compliance/questionnaires/${id}/status`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["compliance", "questionnaires", id] }),
  });

  const addQuestion = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/questionnaires/${id}/questions`, {
        method: "POST",
        body: { text: questionText, category },
      }),
    onSuccess: () => {
      setQuestionText("");
      setCategory("compliance");
      queryClient.invalidateQueries({ queryKey: ["compliance", "questionnaires", id] });
    },
  });

  if (!questionnaire) return null;

  const missingCount = questionnaire.questions.filter(
    (q) => (q.answer?.status ?? "missing") === "missing",
  ).length;

  return (
    <div>
      <PageHeader
        title={questionnaire.title}
        description={`${questionnaire.source.replace(/_/g, " ")} questionnaire`}
        actions={<StatusBadge status={questionnaire.status} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <span className="text-sm text-neutral-500">Status:</span>
        <select
          className={selectClassName}
          value={questionnaire.status}
          onChange={(e) => updateStatus.mutate(e.target.value as QuestionnaireStatus)}
        >
          <option value="draft">Draft</option>
          <option value="in_progress">In progress</option>
          <option value="completed">Completed</option>
        </select>
        {missingCount > 0 && (
          <span className="text-xs text-red-600">
            {missingCount} question{missingCount === 1 ? "" : "s"} missing an answer
          </span>
        )}
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Add Question
        </h2>
        <Card>
          <CardContent className="flex flex-wrap gap-2 pt-6">
            <Input
              placeholder="Question text"
              value={questionText}
              onChange={(e) => setQuestionText(e.target.value)}
              className="min-w-[220px] flex-1"
            />
            <select
              className={selectClassName}
              value={category}
              onChange={(e) => setCategory(e.target.value as QuestionCategory)}
            >
              <option value="compliance">Compliance</option>
              <option value="security">Security</option>
            </select>
            <Button
              disabled={!questionText.trim() || addQuestion.isPending}
              onClick={() => addQuestion.mutate()}
            >
              Add question
            </Button>
          </CardContent>
        </Card>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Questions
        </h2>
        {questionnaire.questions.length === 0 && (
          <p className="text-sm text-neutral-500">No questions added yet.</p>
        )}
        <div className="flex flex-col gap-3">
          {questionnaire.questions.map((question) => (
            <QuestionRow key={question.id} questionnaireId={id} question={question} />
          ))}
        </div>
      </div>
    </div>
  );
}
