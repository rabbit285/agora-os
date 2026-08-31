"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PencilLine } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { Questionnaire } from "@/lib/types";

/** Giving a questionnaire a name that describes it.
 *
 * Records exist whose title is one of their own questions — "Do you
 * encrypt customer data at rest?" as the name of the document that
 * contains it. It reads as a single question in every list, and the
 * customer's security review ends up named after it.
 *
 * The product can see that and says so. It does not fix it: a
 * replacement title is a guess about what somebody meant, and this is
 * their record. So the flag comes with a box, not a correction.
 */
export function RenameQuestionnaire({
  questionnaireId,
  currentTitle,
  suggestedCustomer,
}: {
  questionnaireId: string;
  currentTitle: string;
  /** Used only to offer an example. Never submitted on its own. */
  suggestedCustomer?: string | null;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);

  const rename = useMutation<Questionnaire, unknown, string>({
    mutationFn: (next) =>
      apiFetch<Questionnaire>(
        `/api/v1/compliance/questionnaires/${questionnaireId}/title`,
        { method: "PATCH", body: { title: next } },
      ),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["compliance"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. The title is unchanged.",
      ),
  });

  const trimmed = title.trim();
  const example = `${suggestedCustomer || "Acme Corp"} Security Questionnaire`;

  return (
    <div className="mb-5 rounded-lg border border-[var(--border-default)] bg-[var(--bg-subtle)] px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-[var(--fg-default)]">
            This title looks like one of the questions
          </p>
          <p className="mt-0.5 text-sm text-[var(--fg-muted)]">
            A questionnaire is the document; a question is a line inside
            it. Something like &ldquo;{example}&rdquo; reads better in the
            list and in the customer&rsquo;s security review.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setTitle(currentTitle);
            setOpen(true);
          }}
        >
          <PencilLine className="mr-2 h-4 w-4" aria-hidden="true" />
          Rename
        </Button>
      </div>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setError(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename questionnaire</DialogTitle>
            <DialogDescription>
              Only the name changes. The questions, answers, customer and
              security review stay exactly as they are.
            </DialogDescription>
          </DialogHeader>

          <form
            id="rename-questionnaire"
            onSubmit={(event) => {
              event.preventDefault();
              if (trimmed) rename.mutate(trimmed);
            }}
          >
            <label
              htmlFor="rename-questionnaire-title"
              className="mb-1.5 block text-xs font-medium text-[var(--fg-muted)]"
            >
              Questionnaire title
            </label>
            <Input
              id="rename-questionnaire-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              autoFocus
            />
          </form>

          {error && (
            <p role="alert" className="text-sm text-[var(--fg-danger)]">
              {error}
            </p>
          )}

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={rename.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              form="rename-questionnaire"
              disabled={
                !trimmed || trimmed === currentTitle || rename.isPending
              }
            >
              {rename.isPending ? "Renaming…" : "Rename"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
