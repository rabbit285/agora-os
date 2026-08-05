"use client";

import Link from "next/link";
import { use, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import type {
  QAScore,
  SalesLead,
  SecurityAlert,
  SupportTicketDetail,
  TicketMessage,
  TicketStatus,
} from "@/lib/types";

const WORKFLOW: TicketStatus[] = ["open", "pending", "resolved", "closed"];

function QAScoreSection({ ticketId }: { ticketId: string }) {
  const queryClient = useQueryClient();
  const [score, setScore] = useState(5);
  const [notes, setNotes] = useState("");

  const { data: qaScores } = useQuery<QAScore[]>({
    queryKey: ["support", "tickets", ticketId, "qa-scores"],
    queryFn: () => apiFetch<QAScore[]>(`/api/v1/support/tickets/${ticketId}/qa-scores`),
  });

  const addScore = useMutation({
    mutationFn: () =>
      apiFetch<QAScore>(`/api/v1/support/tickets/${ticketId}/qa-score`, {
        method: "POST",
        body: { score, notes: notes || null },
      }),
    onSuccess: () => {
      setNotes("");
      queryClient.invalidateQueries({
        queryKey: ["support", "tickets", ticketId, "qa-scores"],
      });
    },
  });

  return (
    <div className="mb-6">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        QA Review
      </h2>
      <Card className="mb-3">
        <CardContent className="flex flex-col gap-2 pt-6">
          <div className="flex items-center gap-2">
            <label className="text-sm text-[var(--fg-muted)]">Score (1-5):</label>
            <Input
              type="number"
              min={1}
              max={5}
              className="w-20"
              value={score}
              onChange={(e) => setScore(Number(e.target.value))}
            />
          </div>
          <Textarea
            placeholder="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
          <Button
            size="sm"
            className="self-start"
            disabled={addScore.isPending}
            onClick={() => addScore.mutate()}
          >
            Submit QA score
          </Button>
        </CardContent>
      </Card>
      {qaScores?.map((qa) => (
        <Card key={qa.id} className="mb-2">
          <CardContent className="pt-6">
            <div className="text-sm text-[var(--fg-default)]">Score: {qa.score}/5</div>
            {qa.notes && <p className="text-xs text-[var(--fg-muted)]">{qa.notes}</p>}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

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

  const draftReply = useMutation({
    mutationFn: () =>
      apiFetch<TicketMessage>(`/api/v1/support/tickets/${id}/draft-reply`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["support", "tickets", id] }),
  });

  const sendDraft = useMutation({
    mutationFn: (messageId: string) =>
      apiFetch(`/api/v1/support/tickets/${id}/messages/${messageId}/send`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["support", "tickets", id] }),
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
        <span className="text-sm text-[var(--fg-muted)]">Status:</span>
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
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
              Linked Security Alert
            </h2>
            <p className="mb-2 text-xs text-[var(--fg-subtle)]">
              This ticket was categorized &ldquo;security&rdquo;, which automatically notified
              Security by creating an alert in their triage queue (spec section 35).
            </p>
            {linkedAlert ? (
              <div className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
                {linkedAlert.title}
                <StatusBadge status={linkedAlert.status} />
              </div>
            ) : (
              <span className="text-sm text-[var(--fg-subtle)]">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}

      {ticket.upsell_lead_id && (
        <Card className="mb-6">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
              Linked Sales Lead
            </h2>
            <p className="mb-2 text-xs text-[var(--fg-subtle)]">
              This ticket was flagged as an upsell signal, which automatically created a lead for
              Sales and notified the account owner (spec section 69 — Support Upsell Signal).
            </p>
            {linkedLead ? (
              <div className="flex items-center gap-2 text-sm text-[var(--fg-muted)]">
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
              <span className="text-sm text-[var(--fg-subtle)]">Loading…</span>
            )}
          </CardContent>
        </Card>
      )}

      <QAScoreSection ticketId={id} />

      <div>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Conversation
        </h2>
        <div className="mb-4 flex flex-col gap-2">
          {ticket.messages.length === 0 && (
            <p className="text-sm text-[var(--fg-muted)]">No messages yet.</p>
          )}
          {ticket.messages.map((message) => (
            <Card key={message.id}>
              <CardContent className="pt-6">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-xs uppercase tracking-wide text-[var(--fg-subtle)]">
                    {message.sender_type}
                  </span>
                  {message.status === "draft" && (
                    <div className="flex items-center gap-2">
                      <StatusBadge status="draft" />
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={sendDraft.isPending}
                        onClick={() => sendDraft.mutate(message.id)}
                      >
                        Send
                      </Button>
                    </div>
                  )}
                </div>
                <div className="text-sm text-[var(--fg-muted)]">{message.body}</div>
              </CardContent>
            </Card>
          ))}
        </div>
        <Card className="mb-3">
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
        <Button
          variant="outline"
          size="sm"
          disabled={draftReply.isPending}
          onClick={() => draftReply.mutate()}
        >
          {draftReply.isPending ? "Drafting…" : "Draft AI Reply"}
        </Button>
        <p className="mt-2 text-xs text-[var(--fg-subtle)]">
          AI-drafted replies are retrieval-grounded (spec §32) and land as a pending draft
          requiring agent approval, unless the org&rsquo;s AI Agent is configured to auto-send
          grounded replies.
        </p>
      </div>
    </div>
  );
}
