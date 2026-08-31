"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowUpRight, FileText } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type {
  ChecklistItem,
  ComplianceGap,
  FileRecord,
  Task,
  TaskActivity,
  TaskComment,
  TaskEvidence,
} from "@/lib/types";

const PRIORITY_LABEL: Record<string, string> = {
  urgent: "Urgent",
  high: "High priority",
  normal: "Normal priority",
  low: "Low priority",
};

/** A person reads "Related gap: AI literacy training evidence incomplete",
 * not `linked to compliance_gap: 8f3a…`. Anything we cannot phrase is not
 * shown at all rather than shown as its internal name. */
const ENTITY_LABEL: Record<string, string> = {
  compliance_gap: "Related gap",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        {title}
      </h2>
      {children}
    </div>
  );
}

export default function TaskDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [newChecklistItem, setNewChecklistItem] = useState("");
  const [commentBody, setCommentBody] = useState("");

  const {
    data: task,
    isLoading,
    error,
  } = useQuery<Task>({
    queryKey: ["tasks", id],
    queryFn: () => apiFetch<Task>(`/api/v1/tasks/${id}`),
    retry: false,
  });

  const gapId = task?.entity_type === "compliance_gap" ? task.entity_id : null;

  // The gap carries the remediation plan. Fetched rather than duplicated
  // onto the task so the task can never show a plan the gap has since
  // regenerated against newer evidence.
  const { data: gap } = useQuery<ComplianceGap>({
    queryKey: ["compliance", "gaps", gapId],
    queryFn: () => apiFetch<ComplianceGap>(`/api/v1/compliance/gaps/${gapId}`),
    enabled: !!gapId,
  });

  const { data: comments } = useQuery<TaskComment[]>({
    queryKey: ["tasks", id, "comments"],
    queryFn: () => apiFetch<TaskComment[]>(`/api/v1/tasks/${id}/comments`),
    enabled: !!task,
  });

  const { data: evidence } = useQuery<TaskEvidence[]>({
    queryKey: ["tasks", id, "evidence"],
    queryFn: () => apiFetch<TaskEvidence[]>(`/api/v1/tasks/${id}/evidence`),
    enabled: !!task,
  });

  const { data: activity } = useQuery<TaskActivity[]>({
    queryKey: ["tasks", id, "activity"],
    queryFn: () => apiFetch<TaskActivity[]>(`/api/v1/tasks/${id}/activity`),
    enabled: !!task,
  });

  const updateChecklist = useMutation({
    mutationFn: (checklist: ChecklistItem[]) =>
      apiFetch<Task>(`/api/v1/tasks/${id}`, { method: "PATCH", body: { checklist } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks", id] });
      queryClient.invalidateQueries({ queryKey: ["tasks", id, "activity"] });
    },
  });

  const addComment = useMutation({
    mutationFn: () =>
      apiFetch<TaskComment>(`/api/v1/tasks/${id}/comments`, {
        method: "POST",
        body: { body: commentBody },
      }),
    onSuccess: () => {
      setCommentBody("");
      queryClient.invalidateQueries({ queryKey: ["tasks", id, "comments"] });
    },
  });

  if (isLoading) return <p className="text-sm text-[var(--fg-muted)]">Loading…</p>;

  if (error) {
    const status = error instanceof ApiError ? error.status : null;
    return (
      <p className="text-sm text-[var(--fg-muted)]">
        {status === 404 || status === 403
          ? "Task not found."
          : "Could not load this task. Please try again."}
      </p>
    );
  }

  if (!task) return null;

  const checklist = task.checklist;
  const plan = gap?.remediation_plan ?? null;
  const entityLabel = task.entity_type ? ENTITY_LABEL[task.entity_type] : undefined;

  return (
    <div>
      <PageHeader
        title={task.title}
        // The plan is rendered below as sections. Repeating it here as one
        // wall of text would be the same information twice, worse.
        description={plan ? undefined : (task.description ?? undefined)}
        actions={<StatusBadge status={task.status} />}
      />

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Badge variant="outline">{PRIORITY_LABEL[task.priority] ?? "Normal priority"}</Badge>
        {task.due_at && (
          <Badge variant="outline">
            Due {new Date(task.due_at).toLocaleDateString()}
          </Badge>
        )}
        {plan && <Badge variant="outline">Suggested owner: {plan.owner}</Badge>}
      </div>

      {entityLabel && gap && (
        <Link
          href={`/compliance/frameworks/${gap.framework_id}`}
          className="mb-6 flex items-start gap-2 rounded-[var(--radius-md)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-3 text-sm text-[var(--warning-700)] hover:border-[var(--warning-500)]/60"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-semibold">{entityLabel}:</span> {gap.summary}
          </span>
          <ArrowUpRight className="ml-auto mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        </Link>
      )}

      {plan && (
        <>
          <Section title="Problem">
            <p className="text-sm text-[var(--fg-muted)]">{plan.problem}</p>
          </Section>

          <Section title="Why this is open">
            <p className="text-sm text-[var(--fg-muted)]">{plan.why}</p>
            {plan.evidence_reviewed.length > 0 && (
              <p className="mt-2 text-sm text-[var(--fg-subtle)]">
                Already reviewed: {plan.evidence_reviewed.join(", ")}
              </p>
            )}
            {plan.affected_ai_systems.length > 0 && (
              <p className="mt-1 text-sm text-[var(--fg-subtle)]">
                Affected AI systems: {plan.affected_ai_systems.join(", ")}
              </p>
            )}
          </Section>

          <Section title="What to do">
            <p className="text-sm text-[var(--fg-muted)]">{plan.action}</p>
          </Section>

          <Section title="Evidence that would close this">
            <ul className="flex flex-col gap-1">
              {plan.required_evidence.map((item) => (
                <li
                  key={item}
                  className="flex items-start gap-2 text-sm text-[var(--fg-muted)]"
                >
                  <FileText className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-sm text-[var(--fg-subtle)]">
              Upload these on the Documents page — Veyntra reads them, maps them to this
              control and reassesses on its own. You do not need to attach them by hand.
            </p>
          </Section>
        </>
      )}

      <Section title="Checklist">
        {checklist.length === 0 && (
          <p className="mb-2 text-sm text-[var(--fg-muted)]">No checklist items yet.</p>
        )}
        <div className="mb-3 flex flex-col gap-2">
          {checklist.map((item, index) => (
            <label key={index} className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
              <input
                type="checkbox"
                checked={item.done}
                disabled={updateChecklist.isPending}
                onChange={() => {
                  const next = checklist.map((entry, i) =>
                    i === index ? { ...entry, done: !entry.done } : entry
                  );
                  updateChecklist.mutate(next);
                }}
              />
              <span className={item.done ? "line-through text-[var(--fg-subtle)]" : undefined}>
                {item.text}
              </span>
            </label>
          ))}
        </div>
        <div className="flex gap-2">
          <Input
            placeholder="New checklist item"
            value={newChecklistItem}
            onChange={(e) => setNewChecklistItem(e.target.value)}
            className="max-w-sm"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!newChecklistItem.trim() || updateChecklist.isPending}
            onClick={() => {
              updateChecklist.mutate([...checklist, { text: newChecklistItem.trim(), done: false }]);
              setNewChecklistItem("");
            }}
          >
            Add item
          </Button>
        </div>
      </Section>

      <Section title="Evidence">
        {evidence && evidence.length === 0 && (
          <p className="text-sm text-[var(--fg-muted)]">
            {plan
              ? "Nothing attached to this task yet. Evidence Veyntra maps to the control is counted whether or not it is attached here."
              : "No evidence attached."}
          </p>
        )}
        <div className="flex flex-col gap-2">
          {evidence?.map((item) => (
            <TaskEvidenceRow key={item.id} fileId={item.file_id} />
          ))}
        </div>
      </Section>

      <Section title="Comments">
        {comments && comments.length === 0 && (
          <p className="mb-2 text-sm text-[var(--fg-muted)]">No comments yet.</p>
        )}
        <div className="mb-3 flex flex-col gap-2">
          {comments?.map((comment) => (
            <Card key={comment.id}>
              <CardContent className="pt-6">
                <p className="text-sm text-[var(--fg-muted)]">{comment.body}</p>
                <p className="mt-1 text-xs text-[var(--fg-subtle)]">
                  {new Date(comment.created_at).toLocaleString()}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
        {addComment.isError && (
          <p className="mb-2 text-sm text-[var(--critical-600)]">
            {addComment.error instanceof ApiError ? addComment.error.message : "Could not post comment."}
          </p>
        )}
        <div className="flex gap-2">
          <Input
            placeholder="Add a comment"
            value={commentBody}
            onChange={(e) => setCommentBody(e.target.value)}
          />
          <Button
            size="sm"
            disabled={!commentBody.trim() || addComment.isPending}
            onClick={() => addComment.mutate()}
          >
            Comment
          </Button>
        </div>
      </Section>

      <Section title="Activity">
        {activity && activity.length === 0 && (
          <p className="text-sm text-[var(--fg-muted)]">No activity recorded yet.</p>
        )}
        <ol className="flex flex-col gap-2">
          {activity?.map((event, index) => (
            <li key={index} className="flex flex-wrap items-baseline gap-x-2 text-sm">
              <span className="text-[var(--fg-default)]">{event.label}</span>
              <span className="text-xs text-[var(--fg-subtle)]">
                {new Date(event.created_at).toLocaleString()}
              </span>
            </li>
          ))}
        </ol>
      </Section>
    </div>
  );
}

/** Attached evidence, by filename. The raw file id told the reader
 * nothing and was the same class of leak as the entity id above it. */
function TaskEvidenceRow({ fileId }: { fileId: string }) {
  const { data: file } = useQuery<FileRecord>({
    queryKey: ["files", fileId],
    queryFn: () => apiFetch<FileRecord>(`/api/v1/files/${fileId}`),
  });

  return (
    <Card>
      <CardContent className="flex items-center gap-2 pt-6 text-sm text-[var(--fg-muted)]">
        <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
        {file?.original_filename ?? "Attached document"}
      </CardContent>
    </Card>
  );
}
