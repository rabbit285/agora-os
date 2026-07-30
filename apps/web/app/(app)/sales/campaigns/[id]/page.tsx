"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { CampaignDetail } from "@/lib/types";

export default function CampaignDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const { data: campaign } = useQuery<CampaignDetail>({
    queryKey: ["sales", "campaigns", id],
    queryFn: () => apiFetch<CampaignDetail>(`/api/v1/sales/campaigns/${id}`),
  });

  if (!campaign) return null;

  return (
    <div>
      <PageHeader
        title={campaign.name}
        description="Campaign performance — real counts over the sequence enrollments it launched."
        actions={<StatusBadge status={campaign.status} />}
      />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-semibold text-neutral-900">
              {campaign.stats.enrolled}
            </div>
            <div className="text-xs text-neutral-500">Enrolled</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-semibold text-neutral-900">
              {campaign.stats.messages_sent}
            </div>
            <div className="text-xs text-neutral-500">Messages Sent</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-semibold text-neutral-900">
              {campaign.stats.messages_blocked}
            </div>
            <div className="text-xs text-neutral-500">Messages Blocked</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-semibold text-neutral-900">
              {campaign.stats.completed}
            </div>
            <div className="text-xs text-neutral-500">Completed</div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
