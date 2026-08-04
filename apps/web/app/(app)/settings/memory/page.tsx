"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, apiFetch } from "@/lib/api";
import { MEMORY_ENTRY_TYPES, type MemoryEntry } from "@/lib/types";

function AddMemoryForm() {
  const queryClient = useQueryClient();
  const [entryType, setEntryType] = useState<string>(MEMORY_ENTRY_TYPES[0]);
  const [content, setContent] = useState("");

  const create = useMutation({
    mutationFn: () =>
      apiFetch<MemoryEntry>("/api/v1/memory", {
        method: "POST",
        body: { entry_type: entryType, content },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["memory"] });
      setContent("");
    },
  });

  return (
    <Card className="mb-6 max-w-2xl">
      <CardContent className="flex flex-col gap-3 pt-6">
        <h2 className="text-sm font-semibold text-neutral-900">Add a memory entry</h2>
        <Select value={entryType} onChange={(e) => setEntryType(e.target.value)}>
          {MEMORY_ENTRY_TYPES.map((type) => (
            <option key={type} value={type}>
              {type.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
        <Textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="e.g. Refunds over €500 require Finance approval."
        />
        {create.isError && (
          <p className="text-sm text-red-600">
            {create.error instanceof ApiError ? create.error.message : "Could not save entry."}
          </p>
        )}
        <div>
          <Button
            size="sm"
            disabled={!content.trim() || create.isPending}
            onClick={() => create.mutate()}
          >
            Save
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function MemoryEntryRow({ entry, canManage }: { entry: MemoryEntry; canManage: boolean }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entry.content);

  const correct = useMutation({
    mutationFn: () =>
      apiFetch<MemoryEntry>(`/api/v1/memory/${entry.id}`, { method: "PATCH", body: { content: draft } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["memory"] });
      setEditing(false);
    },
  });

  const remove = useMutation({
    mutationFn: () => apiFetch<MemoryEntry>(`/api/v1/memory/${entry.id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["memory"] }),
  });

  return (
    <Card>
      <CardContent className="flex flex-col gap-2 pt-6">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="capitalize">
            {entry.entry_type.replace(/_/g, " ")}
          </Badge>
          {entry.provenance_type === "policy" && <Badge>From published policy</Badge>}
        </div>
        {editing ? (
          <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} />
        ) : (
          <p className="text-sm text-neutral-800">{entry.content}</p>
        )}
        {canManage && (
          <div className="flex gap-2">
            {editing ? (
              <>
                <Button size="sm" disabled={correct.isPending} onClick={() => correct.mutate()}>
                  Save correction
                </Button>
                <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              </>
            ) : (
              <>
                <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                  Correct
                </Button>
                <Button size="sm" variant="outline" disabled={remove.isPending} onClick={() => remove.mutate()}>
                  Delete
                </Button>
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function BusinessMemoryPage() {
  const { data: entries, isLoading } = useQuery<MemoryEntry[]>({
    queryKey: ["memory"],
    queryFn: () => apiFetch<MemoryEntry[]>("/api/v1/memory"),
  });

  // Every org member can view memory; write access is permission-gated
  // server-side (business_memory.manage). The add/correct/delete controls
  // are hidden here for anyone without that permission, but the server is
  // the real enforcement point regardless.
  const { data: permissions } = useQuery<string[]>({
    queryKey: ["organizations", "current", "my-permissions"],
    queryFn: () => apiFetch<string[]>("/api/v1/organizations/current/my-permissions"),
  });
  const canManage = permissions?.includes("business_memory.manage") ?? false;

  return (
    <div>
      <PageHeader
        title="Business Memory"
        description="spec §89 — structured organization memory: approved facts, approved answers, policies,
          business rules, preferences, past decisions, and workflow outcomes. Every entry names its real
          source; administrators can correct or delete any entry."
      />

      {canManage && <AddMemoryForm />}

      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {entries && entries.length === 0 && (
        <p className="text-sm text-neutral-500">No memory entries yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {entries?.map((entry) => (
          <MemoryEntryRow key={entry.id} entry={entry} canManage={canManage} />
        ))}
      </div>
    </div>
  );
}
