"use client";

import Link from "next/link";
import { use } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { SalesContactDetail } from "@/lib/types";

export default function ContactDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: contact } = useQuery<SalesContactDetail>({
    queryKey: ["sales", "contacts", id],
    queryFn: () => apiFetch<SalesContactDetail>(`/api/v1/sales/contacts/${id}`),
  });

  const toggleSuppress = useMutation({
    mutationFn: (do_not_contact: boolean) =>
      apiFetch(`/api/v1/sales/contacts/${id}`, { method: "PATCH", body: { do_not_contact } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sales", "contacts", id] }),
  });

  if (!contact) return null;

  return (
    <div>
      <PageHeader
        title={contact.full_name}
        description={contact.job_title ?? contact.email}
        actions={
          <Button
            size="sm"
            variant={contact.do_not_contact ? "default" : "outline"}
            disabled={toggleSuppress.isPending}
            onClick={() => toggleSuppress.mutate(!contact.do_not_contact)}
          >
            {contact.do_not_contact ? "Suppressed — Unblock" : "Suppress"}
          </Button>
        }
      />
      {contact.account && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Account
            </h2>
            <Link
              href={`/sales/accounts/${contact.account.id}`}
              className="text-sm text-neutral-700 hover:underline"
            >
              {contact.account.name}
            </Link>
          </CardContent>
        </Card>
      )}
      <div>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Outreach History
        </h2>
        {contact.outreach.length === 0 && (
          <p className="text-sm text-neutral-500">No outreach sent to this contact yet.</p>
        )}
        <div className="flex flex-col gap-2">
          {contact.outreach.map((message) => (
            <Card key={message.id}>
              <CardContent className="pt-6">
                <div className="mb-1 flex items-center justify-between">
                  <Badge variant="outline">{message.channel}</Badge>
                  <StatusBadge status={message.status} />
                </div>
                <p className="text-sm text-neutral-700">{message.body}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
