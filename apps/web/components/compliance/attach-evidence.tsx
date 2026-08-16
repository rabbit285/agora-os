"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Paperclip } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import { uploadFile } from "@/lib/upload";
import type { Evidence } from "@/lib/types";

/** Attach a document to a control as evidence.
 *
 * This is the step that turns a mapped control into a satisfied
 * requirement, and it had no entry point anywhere in the interface — the
 * API accepted evidence, but the only way to send it was by hand. A
 * compliance tool where evidence can only be attached via curl is a
 * compliance tool nobody will put evidence into.
 *
 * Attaching does not itself change the requirement's status. Evidence is
 * a fact; whether it *satisfies* the requirement is a judgement someone
 * records as an assessment, and the framework screen recalculates on
 * reassessment. The copy says so, because the alternative — a green tick
 * appearing the moment a file lands — is how these systems end up
 * asserting things nobody checked.
 */
export function AttachEvidence({
  controlId,
  onAttached,
  compact = false,
  label = "Attach evidence",
}: {
  controlId: string;
  onAttached?: () => void;
  compact?: boolean;
  label?: string;
}) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");

  const attach = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a document first.");
      const fileId = await uploadFile(file, { classification: "internal" });
      return apiFetch<Evidence>("/api/v1/compliance/evidence", {
        method: "POST",
        body: {
          file_id: fileId,
          title: title.trim() || file.name,
          control_id: controlId,
        },
      });
    },
    onSuccess: () => {
      setOpen(false);
      setFile(null);
      setTitle("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      void queryClient.invalidateQueries({ queryKey: ["compliance", "evidence"] });
      void queryClient.invalidateQueries({ queryKey: ["compliance", "controls", controlId] });
      onAttached?.();
    },
  });

  if (!open) {
    return (
      <Button
        size="sm"
        variant={compact ? "outline" : "default"}
        onClick={() => setOpen(true)}
      >
        <Paperclip className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
        {label}
      </Button>
    );
  }

  return (
    <div className="w-full rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--bg-app)] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-[var(--fg-default)]">Attach evidence</p>
        <Button size="sm" variant="outline" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>

      <div className="flex flex-col gap-2">
        <input
          ref={fileInputRef}
          type="file"
          className="text-sm text-[var(--fg-muted)] file:mr-3 file:rounded-[var(--radius-md)] file:border file:border-[var(--border-default)] file:bg-[var(--bg-surface)] file:px-3 file:py-1.5 file:text-sm file:text-[var(--fg-default)]"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <Input
          placeholder="What this document demonstrates (defaults to the filename)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />

        {attach.error && (
          <p className="text-sm text-[var(--critical-600)]">
            {attach.error instanceof ApiError
              ? attach.error.message
              : (attach.error as Error).message}
          </p>
        )}

        <p className="text-xs leading-relaxed text-[var(--fg-subtle)]">
          Attaching a document records that it exists. It does not mark the requirement
          satisfied — run the framework assessment afterwards, and record an assessment against
          the control, so the status reflects a judgement someone made rather than a file
          appearing.
        </p>

        <div>
          <Button size="sm" disabled={!file || attach.isPending} onClick={() => attach.mutate()}>
            {attach.isPending ? "Uploading…" : "Upload and attach"}
          </Button>
        </div>
      </div>
    </div>
  );
}
