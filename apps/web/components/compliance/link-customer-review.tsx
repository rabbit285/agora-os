"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link2, TriangleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, apiFetch } from "@/lib/api";
import type { CustomerLinkResult } from "@/lib/types";

/** Naming the customer a questionnaire came from.
 *
 * This is the one thing the product will not decide on its own. A
 * customer-provided questionnaire belongs in that customer's security
 * review, but plenty of them carry no customer at all — they were made
 * before there was a field to put one in, and their titles are all
 * anybody has to go on.
 *
 * A title is not identity. "Agora Origin cusotmer" is almost certainly a
 * customer called Agora Origin; "Do you encrypt customer data at rest?"
 * is a question somebody pasted into the wrong box. Guessing right most
 * of the time is not good enough when the output is a customer's name in
 * a compliance record, so the server suggests and a person decides.
 *
 * Which is why this is a field with a value in it, not a button that
 * says "Link". The suggestion is visible and editable before it is
 * agreed to, and the reasoning is shown underneath so nobody has to
 * wonder where the name came from.
 */
export function LinkCustomerReview({
  questionnaireId,
  suggestedCustomer,
  suggestionReason,
}: {
  questionnaireId: string;
  suggestedCustomer: string | null;
  suggestionReason: string | null;
}) {
  const queryClient = useQueryClient();
  const [customer, setCustomer] = useState(suggestedCustomer ?? "");
  const [error, setError] = useState<string | null>(null);

  const link = useMutation<CustomerLinkResult, unknown, string>({
    mutationFn: (name) =>
      apiFetch<CustomerLinkResult>(
        `/api/v1/compliance/questionnaires/${questionnaireId}/customer`,
        { method: "POST", body: { customer_name: name } },
      ),
    onMutate: () => setError(null),
    onSuccess: async () => {
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
    <div className="mb-5 rounded-lg border border-[var(--warning-300)] bg-[var(--warning-50)] p-5">
      <div className="flex items-start gap-3">
        <TriangleAlert
          className="mt-0.5 h-4 w-4 shrink-0 text-[var(--warning-700)]"
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-[var(--fg-default)]">
            Not linked to a customer security review
          </h2>
          <p className="mt-1 text-sm text-[var(--fg-muted)]">
            This questionnaire came from a customer, but no customer is
            recorded on it — so there is no security review for it to
            belong to. Name the customer and Veyntra will open their
            review, or add this questionnaire to the one they already
            have.
          </p>

          <form
            className="mt-4 flex flex-wrap items-end gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              if (trimmed) link.mutate(trimmed);
            }}
          >
            <div className="min-w-[16rem] flex-1">
              <label
                htmlFor="customer-name"
                className="mb-1.5 block text-xs font-medium text-[var(--fg-muted)]"
              >
                Customer
              </label>
              <Input
                id="customer-name"
                value={customer}
                onChange={(event) => setCustomer(event.target.value)}
                placeholder="The company that sent this questionnaire"
                aria-describedby={
                  suggestionReason ? "customer-name-reason" : undefined
                }
              />
            </div>
            <Button type="submit" disabled={!trimmed || link.isPending}>
              <Link2 className="mr-2 h-4 w-4" aria-hidden="true" />
              {link.isPending ? "Linking…" : "Set customer and create review"}
            </Button>
          </form>

          {/* Where the name in the box came from. Shown rather than
              implied, because a filled-in field otherwise reads as
              something the product already knew. */}
          {suggestionReason && (
            <p
              id="customer-name-reason"
              className="mt-2 text-xs text-[var(--fg-subtle)]"
            >
              {suggestionReason} Check it before saving.
            </p>
          )}
          {!suggestedCustomer && (
            <p className="mt-2 text-xs text-[var(--fg-subtle)]">
              Nothing in the title identifies a customer, so there is
              nothing to suggest.
            </p>
          )}

          {error && (
            <p role="alert" className="mt-3 text-sm text-[var(--fg-danger)]">
              {error}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
