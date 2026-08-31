"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";
import { uploadFileWithOutcome } from "@/lib/upload";

/** Replace a document with a newer copy of itself.
 *
 * The escape hatch for the case detection is deliberately bad at: a
 * rewrite so thorough that the new version shares little wording with
 * the old one. Nothing here is a guess — the person picked this
 * document and this file, so the version is linked as soon as the
 * analysis finishes rather than proposed back to them.
 *
 * The same bytes are still the same bytes. Re-uploading an identical
 * file says so and links nothing, because a document is not a new
 * version of itself.
 */
export function UploadNewVersion({
  supersedesFileId,
  documentTitle,
  onUploaded,
}: {
  supersedesFileId: string;
  documentTitle: string;
  onUploaded?: () => void;
}) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const outcome = await uploadFileWithOutcome(file, {
        classification: "confidential",
      });
      // The same bytes, or an upload of them already in flight. Either
      // way a second pipeline would produce a second set of evidence for
      // one real policy.
      if (outcome.status === "duplicate" || outcome.status === "processing") {
        return { duplicate: true as const, status: outcome.status };
      }
      await apiFetch("/api/v1/compliance/documents/process", {
        method: "POST",
        body: { file_id: outcome.fileId, supersedes_file_id: supersedesFileId },
      });
      return { duplicate: false as const, status: outcome.status };
    },
    onMutate: () => {
      setFailed(false);
      setMessage(null);
    },
    onSuccess: async (result) => {
      setFailed(false);
      setMessage(
        result.duplicate
          ? result.status === "processing"
            ? "That file is already being read. Nothing was started twice."
            : "That is the same file you already have, so nothing changed."
          : `Reading it now. It becomes the current version of ${documentTitle} once Veyntra has finished.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["compliance"] });
      onUploaded?.();
    },
    onError: (cause) => {
      setFailed(true);
      setMessage(
        cause instanceof ApiError
          ? cause.message
          : "That upload did not go through. Nothing was changed.",
      );
    },
  });

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        className="sr-only"
        aria-label={`Upload a new version of ${documentTitle}`}
        onChange={(event) => {
          const file = event.target.files?.[0];
          // Cleared straight away, so picking the same file twice after
          // a failure still fires a change event.
          event.target.value = "";
          if (file) upload.mutate(file);
        }}
      />
      <Button
        variant="outline"
        onClick={() => inputRef.current?.click()}
        disabled={upload.isPending}
        className="gap-1.5"
      >
        <Upload className="h-4 w-4" aria-hidden="true" />
        {upload.isPending ? "Uploading…" : "Upload new version"}
      </Button>

      {message && (
        <p
          role={failed ? "alert" : "status"}
          className={`mt-2 text-sm ${
            failed ? "text-[var(--fg-danger)]" : "text-[var(--fg-muted)]"
          }`}
        >
          {message}
        </p>
      )}
    </div>
  );
}
