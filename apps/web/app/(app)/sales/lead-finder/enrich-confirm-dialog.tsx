"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { CreditEstimatePreviewOut } from "@/lib/types";

/** Required before any bulk enrichment can run (spec: "credit estimate
 * preview required before any bulk enrichment") — shows the provider's
 * own estimate, never a number invented by the frontend. */
export function EnrichConfirmDialog({
  open,
  onOpenChange,
  estimate,
  isEstimating,
  onConfirm,
  isEnriching,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  estimate: CreditEstimatePreviewOut | null;
  isEstimating: boolean;
  onConfirm: () => void;
  isEnriching: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm enrichment</DialogTitle>
          <DialogDescription>
            This will spend provider credits to fill in missing fields on the saved records.
          </DialogDescription>
        </DialogHeader>
        {isEstimating ? (
          <p className="text-sm text-[var(--fg-muted)]">Estimating credit usage…</p>
        ) : estimate ? (
          <div className="rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-sunken)] p-3 text-sm">
            <p>
              <span className="font-semibold">{estimate.estimated_credits}</span> estimated credit
              {estimate.estimated_credits === 1 ? "" : "s"} for {estimate.record_count} record
              {estimate.record_count === 1 ? "" : "s"} via {estimate.provider}.
            </p>
            <p className="mt-1 text-xs text-[var(--fg-muted)]">
              This is an estimate — the actual amount charged may differ and is recorded after the
              job completes.
            </p>
          </div>
        ) : (
          <p className="text-sm text-[var(--fg-muted)]">Unable to load a credit estimate.</p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!estimate || isEnriching} onClick={onConfirm}>
            {isEnriching ? "Starting…" : "Confirm enrichment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
