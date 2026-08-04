"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { Task } from "@/lib/types";

export default function TasksPage() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");

  const { data: tasks, isLoading } = useQuery<Task[]>({
    queryKey: ["tasks"],
    queryFn: () => apiFetch<Task[]>("/api/v1/tasks"),
  });

  const createTask = useMutation({
    mutationFn: (newTitle: string) =>
      apiFetch<Task>("/api/v1/tasks", { method: "POST", body: { title: newTitle } }),
    onSuccess: () => {
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });

  const updateStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiFetch<Task>(`/api/v1/tasks/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["tasks"] }),
  });

  return (
    <div>
      <PageHeader title="Tasks" description="Shared across every module (spec section 44)." />
      <Card className="mb-6">
        <CardContent className="flex gap-2 pt-6">
          <Input
            placeholder="New task title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && title.trim()) createTask.mutate(title.trim());
            }}
          />
          <Button
            disabled={!title.trim() || createTask.isPending}
            onClick={() => createTask.mutate(title.trim())}
          >
            Add task
          </Button>
        </CardContent>
      </Card>

      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {tasks && tasks.length === 0 && <p className="text-sm text-neutral-500">No tasks yet.</p>}
      <div className="flex flex-col gap-2">
        {tasks?.map((task) => (
          <Card key={task.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div>
                <Link
                  href={`/tasks/${task.id}`}
                  className="font-medium text-neutral-900 hover:underline"
                >
                  {task.title}
                </Link>
                <div className="text-xs text-neutral-400">Priority: {task.priority}</div>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge status={task.status} />
                {task.status !== "done" && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => updateStatus.mutate({ id: task.id, status: "done" })}
                  >
                    Mark done
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
