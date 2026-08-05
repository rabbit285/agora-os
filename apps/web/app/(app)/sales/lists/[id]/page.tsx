"use client";

import { useParams, useRouter } from "next/navigation";
import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import { Breadcrumbs } from "@/components/breadcrumbs";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { LoadingSkeleton } from "@/components/loading-skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { SalesAccount, SalesContact, SalesListItemOut, SalesListOut } from "@/lib/types";

export default function SalesListDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const listId = params.id;

  // No single-list GET endpoint exists on the backend — find it in the
  // collection instead of fabricating one.
  const {
    data: lists,
    isLoading: listLoading,
    error: listError,
  } = useQuery<SalesListOut[]>({
    queryKey: ["sales", "lead-finder", "lists", "all"],
    queryFn: () => apiFetch<SalesListOut[]>("/api/v1/sales/lead-finder/lists"),
  });
  const resolvedList = lists?.find((l) => l.id === listId);

  const {
    data: items,
    isLoading: itemsLoading,
    error: itemsError,
    refetch: refetchItems,
  } = useQuery<SalesListItemOut[]>({
    queryKey: ["sales", "lead-finder", "lists", listId, "items"],
    queryFn: () => apiFetch<SalesListItemOut[]>(`/api/v1/sales/lead-finder/lists/${listId}/items`),
  });

  const accountDetails = useQueries({
    queries: (items ?? [])
      .filter((item) => item.account_id)
      .map((item) => ({
        queryKey: ["sales", "accounts", item.account_id],
        queryFn: () => apiFetch<SalesAccount>(`/api/v1/sales/accounts/${item.account_id}`),
      })),
  });
  const contactDetails = useQueries({
    queries: (items ?? [])
      .filter((item) => item.contact_id)
      .map((item) => ({
        queryKey: ["sales", "contacts", item.contact_id],
        queryFn: () => apiFetch<SalesContact>(`/api/v1/sales/contacts/${item.contact_id}`),
      })),
  });

  const removeItem = useMutation({
    mutationFn: (itemId: string) =>
      apiFetch(`/api/v1/sales/lead-finder/lists/${listId}/items/${itemId}`, { method: "DELETE" }),
    onSuccess: () => refetchItems(),
  });

  if (listLoading || itemsLoading) return <LoadingSkeleton rows={5} />;
  if (listError) return <ErrorState />;
  if (itemsError) return <ErrorState onRetry={() => refetchItems()} />;
  if (!resolvedList) return <ErrorState title="List not found" />;

  const accountItems = (items ?? []).filter((item) => item.account_id);
  const contactItems = (items ?? []).filter((item) => item.contact_id);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Lists", href: "/sales/lists" }, { label: resolvedList.name }]} />
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-[var(--fg-default)]">{resolvedList.name}</h1>
          <p className="mt-1 text-xs text-[var(--fg-muted)]">
            <Badge variant="outline">{resolvedList.list_type}</Badge>{" "}
            {resolvedList.is_shared && <Badge variant="secondary">Shared</Badge>}
          </p>
        </div>
      </div>

      {(items ?? []).length === 0 ? (
        <EmptyState
          title="This list is empty"
          description="Add companies or people to this list from the Lead Finder's bulk toolbar."
        />
      ) : (
        <div className="flex flex-col gap-2">
          {accountItems.map((item, index) => {
            const account = accountDetails[index]?.data;
            return (
              <div
                key={item.id}
                className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--border-default)] px-3 py-2"
              >
                <button
                  type="button"
                  className="text-left"
                  onClick={() => account && router.push(`/sales/accounts/${account.id}`)}
                >
                  <p className="text-sm font-medium">{account?.name ?? "Loading…"}</p>
                  {account?.industry && <p className="text-xs text-[var(--fg-subtle)]">{account.industry}</p>}
                </button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => removeItem.mutate(item.id)}
                  aria-label="Remove from list"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            );
          })}
          {contactItems.map((item, index) => {
            const contact = contactDetails[index]?.data;
            return (
              <div
                key={item.id}
                className="flex items-center justify-between rounded-[var(--radius-md)] border border-[var(--border-default)] px-3 py-2"
              >
                <button
                  type="button"
                  className="text-left"
                  onClick={() => contact && router.push(`/sales/contacts/${contact.id}`)}
                >
                  <p className="text-sm font-medium">{contact?.full_name ?? "Loading…"}</p>
                  {contact?.job_title && <p className="text-xs text-[var(--fg-subtle)]">{contact.job_title}</p>}
                </button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => removeItem.mutate(item.id)}
                  aria-label="Remove from list"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
