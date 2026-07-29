"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { SalesLead, SecurityAlert, SupportTicketDetail, TicketStatus } from "@/lib/types";

const WORKFLOW: TicketStatus[] = ["open", "pending", "resolved", "closed"];

export default function TicketDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();
  const [messageBody, setMessageBody] = useState("");

  const { data: ticket } = useQuery<SupportTicketDetail>({
    queryKey: ["support", "tickets", id],
    queryFn: () => apiFetch<SupportTicketDetail>(`/api/v1/support/tickets/${id}`),
  });

  const { data: alerts } = useQuery<SecurityAlert[]>({
    queryKey: ["security", "alerts"],
    queryFn: () => apiFetch<SecurityAlert[]>("/api/v1/security/alerts"),
    enabled: !!ticket?.related_alert_id,
  });

  const { data: leads } = useQuery<SalesLead[]>({
    queryKey: ["sales", "leads"],
    queryFn: () => apiFetch<SalesLead[]>("/api/v1/sales/leads"),
    enabled: !!ticket?.upsell_lead_id,
  });

  const advanceStatus = useMutation({
    mutationFn: (status: TicketStatus) =>
      apiFetch(`/api/v1/support/tickets/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["support", "tickets", id] }),
  });

  const flagUpsell = useMutation({
    mutationFn: () => apiFetch(`/api/v1/support/tickets/${id}/flag-upsell`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["support", "tickets", id] });
      queryClient.invalidateQueries({ queryKey: ["sales", "leads"] });
    },
  });

  const sendMessage = useMutation({
    mutationFn: (body: string) =>
      apiFetch(`/api/v1/support/tickets/${id}/messages`, {
        method: "POST",
        body: { sender_type: "agent", body },
      }),
    onSuccess: () => {
      setMessageBody("");
      queryClient.invalidateQueries({ queryKey: ["support", "tickets", id] });
    },
  });

  if (!ticket) return null;

  const linkedAlert = alerts?.find((a) => a.id === ticket.related_alert_id);
  const linkedLead = leads?.find((l) => l.id === ticket.upsell_lead_id);
  const currentIndex = WORKFLOW.indexOf(ticket.status);
  const nextStatus = WORKFLOW[currentIndex + 1];

  return (
    <div>
      <PageHeader
        title={ticket.subject}
        description={ticket.description ?? undefined}
        actions={<StatusBadge status={ticket.priority} />}
      />

      <div className="mb-6 flex items-center gap-3">
        <StatusBadge status={ticket.category} />
        <span className="text-sm text-neutral-500">Status:</span>
        <StatusBadge status={ticket.status} />
        {nextStatus && (
          <Button
            size="sm"
            variant="outline"
            disabled={advanceStatus.isPending}
            onClick={() => advanceStatus.mutate(nextStatus)}
          >
            Advance to {nextStatus.replace(/_/g, " ")}
          </Button>
        )}
        {!ticket.upsell_lead_id && (
          <Button
            size="sm"
            variant="outline"
            disabled={flagUpsell.isPending}
            onClick={() => flagUpsell.mutate()}
          >
            Flag as upsell signal
          </Button>
        )}
      </div>

      {ticket.related_alert_id && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Linked Security Alert
            </h2>
            <p className="mb-2 text-xs text-neutral-400">
              This ticket was categorized &ldquo;security&rdquo;, which automatically notified
              Security by creating an alert in their triage queue (spec section 35).
            </p>
            {linkedAlert ? (
              <div className="flex items-center gap-2 text-sm text-neutral-700">
                {linkedAlert.title}
                <StatusBadge status={linkedAlert.status} />
              </div>
            ) : (
              <span className="text-sm text-neutral-400">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}

      {ticket.upsell_lead_id && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Linked Sales Lead
            </h2>
            <p className="mb-2 text-xs text-neutral-400">
              This ticket was flagged as an upsell signal, which automatically created a lead for
              Sales and notified the account owner (spec section 69 — Support Upsell Signal).
            </p>
            {linkedLead ? (
              <div className="flex items-center gap-2 text-sm text-neutral-700">
                {linkedLead.account_id ? (
                  <Link href={`/sales/accounts/${linkedLead.account_id}`} className="hover:underline">
                    View linked account
                  </Link>
                ) : (
                  <span>Lead created (no linked account)</span>
                )}
                <StatusBadge status={linkedLead.status} />
              </div>
            ) : (
              <span className="text-sm text-neutral-400">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Conversation
        </h2>
        <div className="mb-4 flex flex-col gap-2">
          {ticket.messages.length === 0 && (
            <p className="text-sm text-neutral-500">No messages yet.</p>
          )}
          {ticket.messages.map((message) => (
            <Card key={message.id}>
              <CardContent className="pt-6">
                <div className="mb-1 text-xs uppercase tracking-wide text-neutral-400">
                  {message.sender_type}
                </div>
                <div className="text-sm text-neutral-700">{message.body}</div>
              </CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardContent className="flex gap-2 pt-6">
            <Input
              placeholder="Reply as agent…"
              value={messageBody}
              onChange={(e) => setMessageBody(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && messageBody.trim()) sendMessage.mutate(messageBody.trim());
              }}
            />
            <Button
              disabled={!messageBody.trim() || sendMessage.isPending}
              onClick={() => sendMessage.mutate(messageBody.trim())}
            >
              Reply
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
