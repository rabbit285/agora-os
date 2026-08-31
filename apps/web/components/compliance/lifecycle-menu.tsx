"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ExternalLink,
  MoreHorizontal,
  RotateCcw,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ApiError, apiFetch } from "@/lib/api";

/** Tidying up, without being able to destroy the record of what happened.
 *
 * Two actions that look adjacent in a menu and are nothing alike.
 * Archiving takes a record off the working list and keeps every answer,
 * approval and citation on it. Deleting destroys it, and is only ever
 * offered for records nothing has happened to — a test questionnaire, a
 * duplicate, an audit scheduled against the wrong framework.
 *
 * Which one a row gets is the server's answer, not this component's:
 * `canDelete` comes from what actually happened to the record, and the
 * endpoint checks again regardless. So a stale list cannot talk somebody
 * into destroying an approved answer — the worst it can do is offer a
 * Delete that comes back refused, with the reason.
 *
 * Neither action fires from the menu. Destructive styling appears once,
 * on the final confirmation, and never on the row itself.
 */
export type LifecycleKind = "questionnaire" | "audit" | "security_review";

const PATHS = {
  questionnaire: "questionnaires",
  audit: "audits",
  security_review: "security-reviews",
} as const;

const COPY = {
  questionnaire: {
    noun: "questionnaire",
    deleteBody:
      "This will permanently remove this draft questionnaire and its draft questions and answers.",
    archiveBody:
      "This questionnaire will be removed from active work. Its answers, approvals, source citations and audit history are all preserved.",
  },
  audit: {
    noun: "audit",
    deleteBody: "This will permanently remove this planned audit.",
    archiveBody:
      "This audit will be removed from active work. Its findings, remediation and audit history are all preserved.",
  },
  security_review: {
    noun: "security review",
    // Never offered. A review is the record of a conversation with a
    // customer, and `canDelete` is hard-coded false at every call site.
    deleteBody: "",
    archiveBody:
      "This engagement will be removed from active work. The questionnaires in it stay linked, stay exactly as they are, and keep their own lifecycle — closing a review says the conversation is over, not that the evidence should go anywhere.",
  },
} as const;

export function LifecycleMenu({
  kind,
  id,
  title,
  canDelete,
  deleteBlockedReason,
  archived = false,
  openHref,
}: {
  kind: LifecycleKind;
  id: string;
  title: string;
  canDelete: boolean;
  deleteBlockedReason?: string | null;
  archived?: boolean;
  /** Where the record opens. The row is already a link; this puts the
   * same destination in the menu for anybody who got here by keyboard. */
  openHref?: string;
}) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState<"delete" | "archive" | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const copy = COPY[kind];
  const base = `/api/v1/compliance/${PATHS[kind]}`;

  const act = useMutation({
    mutationFn: (action: "delete" | "archive" | "restore") =>
      action === "delete"
        ? apiFetch(`${base}/${id}`, { method: "DELETE" })
        : apiFetch(`${base}/${id}/${action}`, { method: "POST" }),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setConfirming(null);
      await queryClient.invalidateQueries({ queryKey: ["compliance"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was changed.",
      ),
  });

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Actions for ${title}`}
            // The row is a link. Without this the menu click opens the
            // record instead of the menu.
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
          >
            <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {openHref && (
            <>
              <DropdownMenuItem asChild>
                <Link href={openHref}>
                  <ExternalLink className="mr-2 h-4 w-4" aria-hidden="true" />
                  Open
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
            </>
          )}

          {archived ? (
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault();
                act.mutate("restore");
              }}
            >
              <RotateCcw className="mr-2 h-4 w-4" aria-hidden="true" />
              Restore
            </DropdownMenuItem>
          ) : (
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault();
                setConfirming("archive");
              }}
            >
              <Archive className="mr-2 h-4 w-4" aria-hidden="true" />
              Archive
            </DropdownMenuItem>
          )}

          {/* Offered only for active records that nothing has happened
              to. An archived record is one somebody chose to keep, so
              destroying it takes restoring it first rather than one
              click from a tidy-up menu. Where delete is not offered on
              an active row, the menu says why rather than leaving a
              reader to wonder where the option went. */}
          {archived ? null : canDelete ? (
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault();
                setConfirming("delete");
              }}
            >
              <Trash2 className="mr-2 h-4 w-4" aria-hidden="true" />
              Delete {archived ? copy.noun : "draft"}
            </DropdownMenuItem>
          ) : (
            <p className="px-2 py-1.5 text-xs text-[var(--fg-subtle)]">
              {deleteBlockedReason ??
                `This ${copy.noun} has history that has to be kept.`}
            </p>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog
        open={confirming !== null}
        onOpenChange={(open) => {
          if (!open) {
            setConfirming(null);
            setError(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {confirming === "delete" ? "Delete" : "Archive"} {copy.noun}?
            </DialogTitle>
            <DialogDescription>
              <span className="mb-2 block font-medium text-[var(--fg-default)]">
                {title}
              </span>
              {confirming === "delete" ? copy.deleteBody : copy.archiveBody}
              {confirming === "delete" && (
                <span className="mt-2 block">
                  This action cannot be undone.
                </span>
              )}
            </DialogDescription>
          </DialogHeader>

          {error && (
            <p role="alert" className="text-sm text-[var(--fg-danger)]">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirming(null)}
              disabled={act.isPending}
            >
              Cancel
            </Button>
            {/* The only destructive styling anywhere in this flow. */}
            <Button
              variant={confirming === "delete" ? "destructive" : "default"}
              onClick={() =>
                act.mutate(confirming === "delete" ? "delete" : "archive")
              }
              disabled={act.isPending}
            >
              {act.isPending
                ? "Working…"
                : confirming === "delete"
                  ? `Delete ${archived ? copy.noun : "draft"}`
                  : "Archive"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
