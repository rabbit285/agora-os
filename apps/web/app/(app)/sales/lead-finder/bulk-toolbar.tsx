"use client";

import { Layers, Save, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Contextual bulk-selection toolbar — only rendered once at least one row
 * is selected (spec: "contextual bulk-selection toolbar"). Enrichment is
 * a separate, explicit action from Save so a credit estimate can always
 * be shown before it runs (see enrich-confirm-dialog.tsx) — selecting
 * rows never spends credits by itself. */
export function BulkToolbar({
  count,
  onClear,
  onSave,
  savePending,
  onAddToList,
  onEnrich,
  enrichDisabled,
}: {
  count: number;
  onClear: () => void;
  onSave: () => void;
  savePending: boolean;
  onAddToList: () => void;
  onEnrich: () => void;
  enrichDisabled?: boolean;
}) {
  if (count === 0) return null;
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-sunken)] px-3 py-2">
      <span className="text-xs font-medium text-[var(--fg-default)]">{count} selected</span>
      <Button size="sm" variant="outline" disabled={savePending} onClick={onSave}>
        <Save className="h-3.5 w-3.5" />
        {savePending ? "Saving…" : "Save"}
      </Button>
      <Button size="sm" variant="outline" onClick={onAddToList}>
        <Layers className="h-3.5 w-3.5" />
        Add to list
      </Button>
      <Button size="sm" variant="outline" disabled={enrichDisabled} onClick={onEnrich}>
        <Sparkles className="h-3.5 w-3.5" />
        Save &amp; enrich
      </Button>
      <Button size="sm" variant="ghost" onClick={onClear} className="ml-auto">
        <X className="h-3.5 w-3.5" />
        Clear selection
      </Button>
    </div>
  );
}
