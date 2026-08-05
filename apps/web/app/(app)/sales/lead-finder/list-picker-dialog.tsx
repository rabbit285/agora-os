"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type { SalesListOut } from "@/lib/types";

/** Picks an existing list or creates a new one, then hands the chosen
 * list id back to the caller — the caller is responsible for saving each
 * selected result as an Account/Contact first (if not already) and then
 * adding it as a list item, since a raw search result can't be a list
 * item on its own (see app.sales.list_service). */
export function ListPickerDialog({
  open,
  onOpenChange,
  listType,
  onConfirm,
  isSubmitting,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  listType: "company" | "person";
  onConfirm: (listId: string) => void;
  isSubmitting: boolean;
}) {
  const queryClient = useQueryClient();
  const [selectedListId, setSelectedListId] = useState<string>("");
  const [newListName, setNewListName] = useState("");

  const { data: lists } = useQuery<SalesListOut[]>({
    queryKey: ["sales", "lead-finder", "lists", listType],
    queryFn: () => apiFetch<SalesListOut[]>(`/api/v1/sales/lead-finder/lists?list_type=${listType}`),
    enabled: open,
  });

  const createList = useMutation({
    mutationFn: (name: string) =>
      apiFetch<SalesListOut>("/api/v1/sales/lead-finder/lists", {
        method: "POST",
        body: { name, list_type: listType },
      }),
    onSuccess: (list) => {
      queryClient.invalidateQueries({ queryKey: ["sales", "lead-finder", "lists", listType] });
      setNewListName("");
      setSelectedListId(list.id);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add to list</DialogTitle>
          <DialogDescription>
            Choose an existing {listType} list or create a new one. Selected results that aren&apos;t
            already saved will be saved first.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--fg-default)]">
              Existing list
            </label>
            <Select value={selectedListId} onChange={(e) => setSelectedListId(e.target.value)}>
              <option value="">Select a list…</option>
              {(lists ?? []).map((list) => (
                <option key={list.id} value={list.id}>
                  {list.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-[var(--fg-default)]">
                Or create a new list
              </label>
              <Input
                value={newListName}
                onChange={(e) => setNewListName(e.target.value)}
                placeholder="New list name"
              />
            </div>
            <Button
              variant="outline"
              disabled={!newListName.trim() || createList.isPending}
              onClick={() => createList.mutate(newListName.trim())}
            >
              Create
            </Button>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={!selectedListId || isSubmitting}
            onClick={() => onConfirm(selectedListId)}
          >
            {isSubmitting ? "Adding…" : "Add to list"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
