"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { Control, Membership } from "@/lib/types";

const selectClassName =
  "flex h-9 rounded-md border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]";

/** Attach a control to a requirement, either by reusing one that already
 * exists or by writing a new one.
 *
 * "Map existing" is offered first and deliberately: one control usually
 * answers several requirements — a breach procedure covers GDPR Article
 * 33 and most of a security framework at once — and a tool that only
 * offers "create" quietly teaches people to duplicate, which then
 * duplicates the evidence and the assessments behind it.
 */
export function MapControl({
  requirementId,
  requirementCode,
  frameworkId,
  mappedControlIds,
}: {
  requirementId: string;
  requirementCode: string;
  frameworkId: string;
  mappedControlIds: string[];
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"existing" | "new">("existing");

  const [search, setSearch] = useState("");
  const [selectedControlId, setSelectedControlId] = useState("");

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("high");
  const [ownerId, setOwnerId] = useState("");

  const { data: controls } = useQuery<Control[]>({
    queryKey: ["compliance", "controls"],
    queryFn: () => apiFetch<Control[]>("/api/v1/compliance/controls"),
    enabled: open,
  });

  const { data: members } = useQuery<Membership[]>({
    queryKey: ["organization", "members"],
    queryFn: () => apiFetch<Membership[]>("/api/v1/organizations/current/members"),
    enabled: open,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({
      queryKey: ["compliance", "frameworks", frameworkId, "dashboard"],
    });
    void queryClient.invalidateQueries({ queryKey: ["compliance", "controls"] });
  };

  const mapExisting = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/compliance/controls/${selectedControlId}/requirements`, {
        method: "POST",
        body: { requirement_ids: [requirementId] },
      }),
    onSuccess: () => {
      setOpen(false);
      setSelectedControlId("");
      refresh();
    },
  });

  const createNew = useMutation({
    mutationFn: () =>
      apiFetch<Control>("/api/v1/compliance/controls", {
        method: "POST",
        body: {
          title,
          description: description.trim() || null,
          category: category.trim() || null,
          priority,
          owner_id: ownerId || null,
          requirement_ids: [requirementId],
        },
      }),
    onSuccess: () => {
      setOpen(false);
      setTitle("");
      setDescription("");
      setCategory("");
      setOwnerId("");
      refresh();
    },
  });

  // Controls already mapped here are filtered out rather than shown and
  // rejected — offering an option that does nothing is worse than not
  // offering it.
  const candidates = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (controls ?? [])
      .filter((c) => !mappedControlIds.includes(c.id))
      .filter((c) => !term || c.title.toLowerCase().includes(term));
  }, [controls, mappedControlIds, search]);

  const error = mapExisting.error ?? createNew.error;

  if (!open) {
    return (
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        <Link2 className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
        Map control
      </Button>
    );
  }

  return (
    <div className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-[var(--fg-default)]">
          Map a control to {requirementCode}
        </p>
        <Button size="sm" variant="outline" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>

      <div className="mb-3 flex gap-2">
        <button
          type="button"
          onClick={() => setMode("existing")}
          className={
            mode === "existing"
              ? "rounded-full bg-[var(--brand-primary)] px-3 py-1 text-xs font-medium text-[var(--fg-on-primary)]"
              : "rounded-full border border-[var(--border-default)] px-3 py-1 text-xs text-[var(--fg-muted)]"
          }
        >
          Map existing control
        </button>
        <button
          type="button"
          onClick={() => setMode("new")}
          className={
            mode === "new"
              ? "rounded-full bg-[var(--brand-primary)] px-3 py-1 text-xs font-medium text-[var(--fg-on-primary)]"
              : "rounded-full border border-[var(--border-default)] px-3 py-1 text-xs text-[var(--fg-muted)]"
          }
        >
          Create new control
        </button>
      </div>

      {mode === "existing" ? (
        <div className="flex flex-col gap-2">
          <Input
            placeholder="Search your existing controls"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {candidates.length === 0 ? (
            <p className="text-sm text-[var(--fg-muted)]">
              {controls?.length
                ? "No unmapped control matches that search."
                : "You have not created any controls yet."}
            </p>
          ) : (
            <select
              className={selectClassName}
              value={selectedControlId}
              onChange={(e) => setSelectedControlId(e.target.value)}
            >
              <option value="">Select a control…</option>
              {candidates.map((control) => (
                <option key={control.id} value={control.id}>
                  {control.title}
                </option>
              ))}
            </select>
          )}
          <div>
            <Button
              size="sm"
              disabled={!selectedControlId || mapExisting.isPending}
              onClick={() => mapExisting.mutate()}
            >
              {mapExisting.isPending ? "Mapping…" : "Map control"}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <Input
            placeholder="Control name"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <textarea
            rows={3}
            className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--fg-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--border-focus)]"
            placeholder="What the organization actually does to meet this requirement"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <div className="flex flex-wrap gap-2">
            <Input
              placeholder="Category (e.g. Privacy / Data Governance)"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="min-w-[220px] flex-1"
            />
            <select
              className={selectClassName}
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
            >
              <option value="high">High priority</option>
              <option value="medium">Medium priority</option>
              <option value="low">Low priority</option>
            </select>
            <select
              className={selectClassName}
              value={ownerId}
              onChange={(e) => setOwnerId(e.target.value)}
            >
              <option value="">Unassigned</option>
              {(members ?? []).map((member) => (
                <option key={member.id} value={member.user_id}>
                  {member.roles.join(", ") || "Member"}
                </option>
              ))}
            </select>
          </div>
          {/* New controls start unassessed on purpose. Whether the
              control is evidenced is derived from what is attached to it,
              so letting someone declare "implemented" at creation would
              put a claim on the record that nothing supports. */}
          <p className="text-xs text-[var(--fg-subtle)]">
            Saved as <strong>Not assessed</strong>. Its status changes when evidence is attached
            and an assessment is recorded — it is never something you assert here.
          </p>
          <div>
            <Button
              size="sm"
              disabled={!title.trim() || createNew.isPending}
              onClick={() => createNew.mutate()}
            >
              {createNew.isPending ? "Creating…" : "Create and map"}
            </Button>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-2 text-sm text-[var(--critical-600)]">
          {error instanceof ApiError ? error.message : "Something went wrong."}
        </p>
      )}

      {mode === "new" && (
        <p className="mt-3 flex items-start gap-1.5 text-xs text-[var(--fg-subtle)]">
          <Plus className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
          If a control you already have covers this requirement, map it instead of creating a
          second one — duplicates split the evidence and assessments between them.
        </p>
      )}
    </div>
  );
}
