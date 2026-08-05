"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { SupportTicket, SupportTicketDetail } from "@/lib/types";

function ConversationThread({ ticket }: { ticket: SupportTicket }) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");

  const { data: detail } = useQuery<SupportTicketDetail>({
    queryKey: ["support", "tickets", ticket.id],
    queryFn: () => apiFetch<SupportTicketDetail>(`/api/v1/support/tickets/${ticket.id}`),
  });

  const reply = useMutation({
    mutationFn: () =>
      apiFetch(`/api/v1/support/tickets/${ticket.id}/messages`, {
        method: "POST",
        body: { sender_type: "agent", body },
      }),
    onSuccess: () => {
      setBody("");
      queryClient.invalidateQueries({ queryKey: ["support", "tickets", ticket.id] });
    },
  });

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="mb-2 flex items-center justify-between">
          <div className="font-medium text-[var(--fg-default)]">{ticket.subject}</div>
          <div className="flex items-center gap-2">
            <StatusBadge status={ticket.channel} />
            <StatusBadge status={ticket.status} />
          </div>
        </div>
        <div className="mb-3 flex flex-col gap-1">
          {detail?.messages.map((message) => (
            <div key={message.id} className="text-sm">
              <span className="font-medium text-[var(--fg-muted)]">{message.sender_type}:</span>{" "}
              <span className="text-[var(--fg-muted)]">{message.body}</span>
            </div>
          ))}
          {detail?.messages.length === 0 && (
            <p className="text-xs text-[var(--fg-subtle)]">No messages yet.</p>
          )}
        </div>
        <div className="flex gap-2">
          <Input
            placeholder="Reply…"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && body.trim()) reply.mutate();
            }}
          />
          <Button size="sm" disabled={!body.trim() || reply.isPending} onClick={() => reply.mutate()}>
            Send
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ConversationsPage() {
  const { data: tickets } = useQuery<SupportTicket[]>({
    queryKey: ["support", "tickets"],
    queryFn: () => apiFetch<SupportTicket[]>("/api/v1/support/tickets"),
  });

  const conversations = tickets?.filter((t) => t.channel === "email" || t.channel === "chat");

  return (
    <div>
      <PageHeader
        title="Conversations"
        description="A thread-first view over the same Tickets data, filtered to the conversational channels (email/chat) — spec §32."
      />
      {conversations?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">No conversations yet.</p>
      )}
      <div className="flex flex-col gap-3">
        {conversations?.map((ticket) => (
          <ConversationThread key={ticket.id} ticket={ticket} />
        ))}
      </div>
    </div>
  );
}
