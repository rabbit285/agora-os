"use client";

import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { OutreachMessage } from "@/lib/types";

export default function SalesInboxPage() {
  const { data: messages } = useQuery<OutreachMessage[]>({
    queryKey: ["sales", "inbox"],
    queryFn: () => apiFetch<OutreachMessage[]>("/api/v1/sales/inbox"),
  });

  return (
    <div>
      <PageHeader
        title="Sales Inbox"
        description="Every outreach message sent or attempted, across all contacts and channels — outbound status only, no inbound reply tracking yet (spec §24)."
      />
      {messages?.length === 0 && (
        <p className="text-sm text-neutral-500">No outreach messages yet.</p>
      )}
      <div className="flex flex-col gap-2">
        {messages?.map((message) => (
          <Card key={message.id}>
            <CardContent className="pt-6">
              <div className="mb-1 flex items-center justify-between">
                <Badge variant="outline">{message.channel}</Badge>
                <StatusBadge status={message.status} />
              </div>
              {message.subject && (
                <div className="font-medium text-neutral-900">{message.subject}</div>
              )}
              <p className="text-sm text-neutral-700">{message.body}</p>
              {message.blocked_reason && (
                <p className="mt-1 text-xs text-red-600">Blocked: {message.blocked_reason}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
