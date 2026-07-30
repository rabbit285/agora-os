"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { Campaign, SalesContact, Sequence } from "@/lib/types";

export default function CampaignsPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [sequenceId, setSequenceId] = useState("");
  const [selectedContactIds, setSelectedContactIds] = useState<string[]>([]);

  const { data: campaigns } = useQuery<Campaign[]>({
    queryKey: ["sales", "campaigns"],
    queryFn: () => apiFetch<Campaign[]>("/api/v1/sales/campaigns"),
  });
  const { data: sequences } = useQuery<Sequence[]>({
    queryKey: ["sales", "sequences"],
    queryFn: () => apiFetch<Sequence[]>("/api/v1/sales/sequences"),
  });
  const { data: contacts } = useQuery<SalesContact[]>({
    queryKey: ["sales", "contacts"],
    queryFn: () => apiFetch<SalesContact[]>("/api/v1/sales/contacts"),
  });

  const createCampaign = useMutation({
    mutationFn: () =>
      apiFetch<Campaign>("/api/v1/sales/campaigns", {
        method: "POST",
        body: { name, sequence_id: sequenceId, contact_ids: selectedContactIds },
      }),
    onSuccess: () => {
      setName("");
      setSequenceId("");
      setSelectedContactIds([]);
      queryClient.invalidateQueries({ queryKey: ["sales", "campaigns"] });
    },
  });

  return (
    <div>
      <PageHeader
        title="Campaigns"
        description="A named, tracked bulk-enrollment into one Sequence (spec §23)."
      />
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-3 pt-6">
          <Input
            placeholder="Campaign name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select
            className="h-9 rounded-md border border-neutral-300 bg-white px-3 text-sm"
            value={sequenceId}
            onChange={(e) => setSequenceId(e.target.value)}
          >
            <option value="">Select a sequence…</option>
            {sequences?.map((sequence) => (
              <option key={sequence.id} value={sequence.id}>
                {sequence.name}
              </option>
            ))}
          </select>
          <select
            multiple
            className="h-24 rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm"
            value={selectedContactIds}
            onChange={(e) =>
              setSelectedContactIds(Array.from(e.target.selectedOptions, (o) => o.value))
            }
          >
            {contacts?.map((contact) => (
              <option key={contact.id} value={contact.id}>
                {contact.full_name}
              </option>
            ))}
          </select>
          <Button
            disabled={!name.trim() || !sequenceId || createCampaign.isPending}
            onClick={() => createCampaign.mutate()}
            className="self-start"
          >
            Launch campaign
          </Button>
        </CardContent>
      </Card>
      {campaigns?.length === 0 && <p className="text-sm text-neutral-500">No campaigns yet.</p>}
      <div className="flex flex-col gap-2">
        {campaigns?.map((campaign) => (
          <Link key={campaign.id} href={`/sales/campaigns/${campaign.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div className="font-medium text-neutral-900">{campaign.name}</div>
                <StatusBadge status={campaign.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
