"use client";

import Link from "next/link";
import { use } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { SalesLeadDetail } from "@/lib/types";

const WORKFLOW = ["new", "qualified", "contacted", "converted"] as const;

export default function LeadDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const queryClient = useQueryClient();

  const { data: lead } = useQuery<SalesLeadDetail>({
    queryKey: ["sales", "leads", id],
    queryFn: () => apiFetch<SalesLeadDetail>(`/api/v1/sales/leads/${id}`),
  });

  const advanceStatus = useMutation({
    mutationFn: (status: string) =>
      apiFetch(`/api/v1/sales/leads/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sales", "leads", id] }),
  });

  if (!lead) return null;

  const currentIndex = WORKFLOW.indexOf(lead.status as (typeof WORKFLOW)[number]);
  const nextStatus = WORKFLOW[currentIndex + 1];

  return (
    <div>
      <PageHeader
        title={`Lead — ${lead.source ?? "Unknown source"}`}
        description={lead.score !== null ? `Score: ${lead.score}` : undefined}
        actions={<StatusBadge status={lead.status} />}
      />
      <div className="mb-6 flex items-center gap-3">
        {nextStatus && (
          <Button
            size="sm"
            variant="outline"
            disabled={advanceStatus.isPending}
            onClick={() => advanceStatus.mutate(nextStatus)}
          >
            Advance to {nextStatus}
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          disabled={advanceStatus.isPending}
          onClick={() => advanceStatus.mutate("disqualified")}
        >
          Disqualify
        </Button>
      </div>
      {lead.account && (
        <Card className="mb-4">
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Account
            </h2>
            <Link href={`/sales/accounts/${lead.account.id}`} className="text-sm text-neutral-700 hover:underline">
              {lead.account.name}
            </Link>
          </CardContent>
        </Card>
      )}
      {lead.contact && (
        <Card>
          <CardContent className="pt-6">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
              Contact
            </h2>
            <Link href={`/sales/contacts/${lead.contact.id}`} className="text-sm text-neutral-700 hover:underline">
              {lead.contact.full_name}
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
