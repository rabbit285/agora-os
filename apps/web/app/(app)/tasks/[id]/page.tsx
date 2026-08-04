"use client";

import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { ChecklistItem, Task, TaskActivity, TaskComment, TaskEvidence } from "@/lib/types";

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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks", id] }),
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

  return (
    <div>
      <PageHeader
        title={task.title}
        description={task.description ?? undefined}
        actions={<StatusBadge status={task.status} />}
      />

      <div className="mb-6 flex flex-wrap gap-2">
        <Badge variant="outline">{task.module}</Badge>
        <Badge variant="outline">priority: {task.priority}</Badge>
        {task.entity_type && (
          <Badge variant="outline">
            linked to {task.entity_type}: {task.entity_id}
          </Badge>
        )}
        {task.due_at && (
          <Badge variant="outline">due {new Date(task.due_at).toLocaleDateString()}</Badge>
        )}
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Checklist
        </h2>
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
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Evidence
        </h2>
        {evidence && evidence.length === 0 && (
          <p className="text-sm text-[var(--fg-muted)]">No evidence attached.</p>
        )}
        <div className="flex flex-col gap-2">
          {evidence?.map((item) => (
            <Card key={item.id}>
              <CardContent className="pt-6 text-sm text-[var(--fg-muted)]">
                File {item.file_id}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Comments
        </h2>
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
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Activity
        </h2>
        {activity && activity.length === 0 && (
          <p className="text-sm text-[var(--fg-muted)]">No activity recorded yet.</p>
        )}
        <div className="flex flex-col gap-2">
          {activity?.map((event, index) => (
            <div key={index} className="text-xs text-[var(--fg-muted)]">
              <span className="font-medium text-[var(--fg-muted)]">{event.action}</span>{" "}
              {new Date(event.created_at).toLocaleString()}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
