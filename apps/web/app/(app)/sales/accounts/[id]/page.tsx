"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { OutreachMessage, SalesAccountDetail } from "@/lib/types";

export default function AccountDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [selectedContactId, setSelectedContactId] = useState<string | null>(null);
  const [messageBody, setMessageBody] = useState("");

  const { data: account } = useQuery<SalesAccountDetail>({
    queryKey: ["sales", "accounts", id],
    queryFn: () => apiFetch<SalesAccountDetail>(`/api/v1/sales/accounts/${id}`),
  });

  const { data: outreach } = useQuery<OutreachMessage[]>({
    queryKey: ["sales", "outreach"],
    queryFn: () => apiFetch<OutreachMessage[]>("/api/v1/sales/outreach"),
  });

  const toggleSuppression = useMutation({
    mutationFn: ({ contactId, doNotContact }: { contactId: string; doNotContact: boolean }) =>
      apiFetch(`/api/v1/sales/contacts/${contactId}`, {
        method: "PATCH",
        body: { do_not_contact: doNotContact },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sales", "accounts", id] }),
  });

  const sendMessage = useMutation({
    mutationFn: async ({ contactId, body }: { contactId: string; body: string }) => {
      const message = await apiFetch<OutreachMessage>("/api/v1/sales/outreach", {
        method: "POST",
        body: { contact_id: contactId, body },
      });
      return apiFetch<OutreachMessage>(`/api/v1/sales/outreach/${message.id}/send`, {
        method: "POST",
      });
    },
    onSuccess: () => {
      setMessageBody("");
      queryClient.invalidateQueries({ queryKey: ["sales", "outreach"] });
    },
  });

  if (!account) return null;

  return (
    <div>
      <PageHeader
        title={account.name}
        description={account.industry ?? undefined}
        actions={<StatusBadge status={account.status} />}
      />

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Contacts
        </h2>
        <div className="flex flex-col gap-2">
          {account.contacts.map((contact) => (
            <Card key={contact.id}>
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{contact.full_name}</div>
                  <div className="text-xs text-neutral-400">{contact.email}</div>
                </div>
                <div className="flex items-center gap-2">
                  {contact.do_not_contact && <Badge variant="destructive">Do not contact</Badge>}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      toggleSuppression.mutate({
                        contactId: contact.id,
                        doNotContact: !contact.do_not_contact,
                      })
                    }
                  >
                    {contact.do_not_contact ? "Remove suppression" : "Suppress"}
                  </Button>
                  <Button
                    size="sm"
                    variant={selectedContactId === contact.id ? "default" : "outline"}
                    onClick={() => setSelectedContactId(contact.id)}
                  >
                    Message
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {selectedContactId && (
        <div className="mb-8">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
            Compose Outreach
          </h2>
          <Card>
            <CardContent className="flex flex-col gap-3 pt-6">
              <Input
                placeholder="Message body"
                value={messageBody}
                onChange={(e) => setMessageBody(e.target.value)}
              />
              <Button
                className="self-start"
                disabled={!messageBody.trim() || sendMessage.isPending}
                onClick={() => sendMessage.mutate({ contactId: selectedContactId, body: messageBody.trim() })}
              >
                Send
              </Button>
              <p className="text-xs text-neutral-400">
                Sending is blocked automatically if the contact is marked do-not-contact
                (spec section 91 — compliance governs outreach).
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Opportunities
        </h2>
        {account.opportunities.length === 0 && (
          <p className="text-sm text-neutral-500">No opportunities yet.</p>
        )}
        <div className="flex flex-col gap-2">
          {account.opportunities.map((opportunity) => (
            <Card key={opportunity.id}>
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{opportunity.title}</div>
                  {opportunity.onboarding_customer_id && (
                    <Link href="/support" className="text-xs text-neutral-500 hover:underline">
                      Onboarded as a Support customer →
                    </Link>
                  )}
                </div>
                <StatusBadge status={opportunity.stage} />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Outreach History
        </h2>
        {outreach?.length === 0 && <p className="text-sm text-neutral-500">No outreach yet.</p>}
        <div className="flex flex-col gap-2">
          {outreach
            ?.filter((m) => account.contacts.some((c) => c.id === m.contact_id))
            .map((message) => (
              <Card key={message.id}>
                <CardContent className="flex items-center justify-between pt-6">
                  <div>
                    <div className="text-sm text-neutral-700">{message.body}</div>
                    {message.blocked_reason && (
                      <div className="text-xs text-red-600">{message.blocked_reason}</div>
                    )}
                  </div>
                  <StatusBadge status={message.status} />
                </CardContent>
              </Card>
            ))}
        </div>
      </div>
    </div>
  );
}
