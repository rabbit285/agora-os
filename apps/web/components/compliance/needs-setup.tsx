"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import type { CustomerLinkResult, Questionnaire } from "@/lib/types";

/** The questionnaires that cannot be shared with anybody yet.
 *
 * A customer-provided questionnaire with no customer on it is not a
 * questionnaire in progress — it is one nobody can finish, because
 * "ready to share" means ready to send back to someone, and there is no
 * someone. Every answer on it could be approved and it would still be
 * stuck.
 *
 * So it is surfaced here, at the top of the section, with the action on
 * it. The alternative — a sentence in an empty state explaining that
 * some questionnaires elsewhere need attention — makes the reader go
 * looking for records the product could simply have listed.
 */
export function NeedsSetupPanel({
  questionnaires,
}: {
  questionnaires: Questionnaire[];
}) {
  const needing = questionnaires.filter((row) => row.readiness?.needs_setup);
  if (needing.length === 0) return null;

  return (
    <Card className="mb-4 border-[var(--warning-300)] bg-[var(--warning-50)]">
      <CardContent className="pt-6">
        <div className="flex items-start gap-3">
          <TriangleAlert
            className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-700)]"
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-[var(--fg-default)]">
              {needing.length} questionnaire
              {needing.length === 1 ? "" : "s"} need
              {needing.length === 1 ? "s" : ""} setup
            </h3>
            <p className="mt-1 text-sm text-[var(--fg-muted)]">
              These came from a customer, but no customer is recorded on
              them — so they have no security review to belong to and
              cannot be shared, however many answers are approved.
            </p>

            <ul className="mt-4 flex flex-col gap-2">
              {needing.map((questionnaire) => (
                <li
                  key={questionnaire.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[var(--border-default)] bg-[var(--bg-default)] px-4 py-3"
                >
                  <div className="min-w-0">
                    <div className="truncate font-medium text-[var(--fg-default)]">
                      {questionnaire.title}
                    </div>
                    <div className="text-xs text-[var(--fg-subtle)]">
                      {/* The server's words, so this and the API refusal
                          say the same thing. */}
                      {questionnaire.readiness?.blockers?.[0]?.message ??
                        "Customer required."}
                    </div>
                  </div>
                  <SetCustomerButton questionnaire={questionnaire} />
                </li>
              ))}
            </ul>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/** Naming the customer, from wherever the questionnaire is listed. */
export function SetCustomerButton({
  questionnaire,
}: {
  questionnaire: Questionnaire;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [customer, setCustomer] = useState("");
  const [error, setError] = useState<string | null>(null);

  const link = useMutation<CustomerLinkResult, unknown, string>({
    mutationFn: (name) =>
      apiFetch<CustomerLinkResult>(
        `/api/v1/compliance/questionnaires/${questionnaire.id}/customer`,
        { method: "POST", body: { customer_name: name } },
      ),
    onMutate: () => setError(null),
    onSuccess: async () => {
      setOpen(false);
      setCustomer("");
      // The questionnaire's status, the engagement list and the counts
      // all move together — naming the customer is what unblocks them.
      await queryClient.invalidateQueries({ queryKey: ["compliance"] });
    },
    onError: (cause) =>
      setError(
        cause instanceof ApiError
          ? cause.message
          : "That did not go through. Nothing was changed.",
      ),
  });

  const trimmed = customer.trim();

  return (
    <>
      <Button
        size="sm"
        onClick={() => setOpen(true)}
        aria-label={`Set customer for ${questionnaire.title}`}
      >
        Set customer
      </Button>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) setError(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Who sent this questionnaire?</DialogTitle>
            <DialogDescription>
              <span className="mb-2 block font-medium text-[var(--fg-default)]">
                {questionnaire.title}
              </span>
              Veyntra will open this customer&rsquo;s security review, or add
              the questionnaire to the one they already have.
            </DialogDescription>
          </DialogHeader>

          <form
            id={`set-customer-${questionnaire.id}`}
            onSubmit={(event) => {
              event.preventDefault();
              if (trimmed) link.mutate(trimmed);
            }}
          >
            <label
              htmlFor={`set-customer-name-${questionnaire.id}`}
              className="mb-1.5 block text-xs font-medium text-[var(--fg-muted)]"
            >
              Customer
            </label>
            <Input
              id={`set-customer-name-${questionnaire.id}`}
              value={customer}
              onChange={(event) => setCustomer(event.target.value)}
              placeholder="The company that sent this questionnaire"
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
              disabled={link.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              form={`set-customer-${questionnaire.id}`}
              disabled={!trimmed || link.isPending}
            >
              {link.isPending ? "Linking…" : "Set customer and create review"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
