"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus } from "lucide-react";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { FilterBar } from "@/components/filter-bar";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type { Task } from "@/lib/types";

const PRIORITY_ORDER: Record<Task["priority"], number> = { urgent: 0, high: 1, normal: 2, low: 3 };

export default function TasksPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const { data: tasks, isLoading, error, refetch } = useQuery<Task[]>({
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

  const filtered = useMemo(() => {
    return (tasks ?? []).filter((task) => {
      if (statusFilter !== "all" && task.status !== statusFilter) return false;
      if (search && !task.title.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [tasks, statusFilter, search]);

  const columns: DataTableColumn<Task>[] = [
    {
      key: "title",
      header: "Task",
      render: (task) => <span className="font-medium">{task.title}</span>,
      sortValue: (task) => task.title.toLowerCase(),
    },
    {
      key: "module",
      header: "Module",
      render: (task) => <span className="capitalize text-[var(--fg-muted)]">{task.module}</span>,
      sortValue: (task) => task.module,
    },
    {
      key: "priority",
      header: "Priority",
      render: (task) => <span className="capitalize">{task.priority}</span>,
      sortValue: (task) => PRIORITY_ORDER[task.priority],
    },
    {
      key: "status",
      header: "Status",
      render: (task) => <StatusBadge status={task.status} />,
      sortValue: (task) => task.status,
    },
    {
      key: "due_at",
      header: "Due",
      render: (task) => (task.due_at ? new Date(task.due_at).toLocaleDateString() : "—"),
      sortValue: (task) => task.due_at ?? "",
    },
  ];

  return (
    <div>
      <PageHeader title="Tasks" description="Shared across every module." />

      <div className="mb-4 flex gap-2">
        <Input
          placeholder="New task title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && title.trim()) createTask.mutate(title.trim());
          }}
          className="max-w-sm"
        />
        <Button
          disabled={!title.trim() || createTask.isPending}
          onClick={() => createTask.mutate(title.trim())}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add task
        </Button>
      </div>

      <FilterBar searchValue={search} onSearchChange={setSearch} searchPlaceholder="Search tasks…">
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-40">
          <option value="all">All statuses</option>
          <option value="open">Open</option>
          <option value="in_progress">In progress</option>
          <option value="done">Done</option>
          <option value="cancelled">Cancelled</option>
        </Select>
      </FilterBar>

      <DataTable
        columns={columns}
        data={filtered}
        getRowId={(task) => task.id}
        onRowClick={(task) => router.push(`/tasks/${task.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No tasks yet"
        emptyDescription="Tasks created across every module will show up here."
        rowActions={(task) =>
          task.status !== "done" ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" aria-label={`Actions for ${task.title}`}>
                  •••
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => updateStatus.mutate({ id: task.id, status: "done" })}>
                  <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  Mark done
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : undefined
        }
      />
    </div>
  );
}
