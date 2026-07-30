"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type {
  LeadFinderResult,
  SalesAccount,
  SalesIntelligence,
  SalesLead,
  SalesOpportunity,
} from "@/lib/types";

function IntelligenceSection() {
  const { data: intelligence } = useQuery<SalesIntelligence>({
    queryKey: ["sales", "intelligence"],
    queryFn: () => apiFetch<SalesIntelligence>("/api/v1/sales/intelligence"),
  });
  const queryClient = useQueryClient();

  const findLeads = useMutation({
    mutationFn: () =>
      apiFetch<LeadFinderResult>("/api/v1/sales/leads/find", { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales", "leads"] });
    },
  });

  if (!intelligence) return null;

  const stageEntries = Object.entries(intelligence.pipeline_value_by_stage);

  return (
    <div className="mb-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-neutral-500">
          Sales Intelligence
        </h2>
        <Button size="sm" variant="outline" disabled={findLeads.isPending} onClick={() => findLeads.mutate()}>
          {findLeads.isPending ? "Finding…" : "Run Lead Finder"}
        </Button>
      </div>
      {findLeads.data && (
        <p className="mb-3 text-xs text-neutral-500">
          Considered {findLeads.data.candidates_considered} account(s); created{" "}
          {findLeads.data.created_leads.length} new lead(s).
        </p>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-semibold text-neutral-900">
              {intelligence.win_rate_percent}%
            </div>
            <div className="text-xs text-neutral-500">Win Rate</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-semibold text-neutral-900">
              €{intelligence.average_deal_size.toLocaleString()}
            </div>
            <div className="text-xs text-neutral-500">Avg Deal Size</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-semibold text-neutral-900">
              {intelligence.sequence_completion_rate_percent}%
            </div>
            <div className="text-xs text-neutral-500">Sequence Completion</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-semibold text-neutral-900">
              {intelligence.top_accounts_by_icp_score.length}
            </div>
            <div className="text-xs text-neutral-500">Top ICP Accounts</div>
          </CardContent>
        </Card>
      </div>
      {stageEntries.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {stageEntries.map(([stage, value]) => (
            <Badge key={stage} variant="outline">
              {stage.replace(/_/g, " ")}: €{value.toLocaleString()}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

function AccountsSection() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  const { data: accounts } = useQuery<SalesAccount[]>({
    queryKey: ["sales", "accounts"],
    queryFn: () => apiFetch<SalesAccount[]>("/api/v1/sales/accounts"),
  });

  const createAccount = useMutation({
    mutationFn: (newName: string) =>
      apiFetch<SalesAccount>("/api/v1/sales/accounts", { method: "POST", body: { name: newName } }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: ["sales", "accounts"] });
    },
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Accounts
      </h2>
      <Card className="mb-4">
        <CardContent className="flex gap-2 pt-6">
          <Input
            placeholder="New account name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && name.trim()) createAccount.mutate(name.trim());
            }}
          />
          <Button disabled={!name.trim() || createAccount.isPending} onClick={() => createAccount.mutate(name.trim())}>
            Add account
          </Button>
        </CardContent>
      </Card>
      {accounts?.length === 0 && <p className="text-sm text-neutral-500">No accounts yet.</p>}
      <div className="flex flex-col gap-2">
        {accounts?.map((account) => (
          <Link key={account.id} href={`/sales/accounts/${account.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">{account.name}</div>
                  {account.industry && (
                    <div className="text-xs text-neutral-400">{account.industry}</div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {account.icp_score !== null && (
                    <Badge variant="outline">ICP {account.icp_score}</Badge>
                  )}
                  <StatusBadge status={account.status} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function LeadsSection() {
  const { data: leads } = useQuery<SalesLead[]>({
    queryKey: ["sales", "leads"],
    queryFn: () => apiFetch<SalesLead[]>("/api/v1/sales/leads"),
  });

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Leads
      </h2>
      {leads?.length === 0 && <p className="text-sm text-neutral-500">No leads yet.</p>}
      <div className="flex flex-col gap-2">
        {leads?.map((lead) => (
          <Link key={lead.id} href={`/sales/leads/${lead.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div>
                  <div className="font-medium text-neutral-900">
                    {lead.source ?? "Unknown source"}
                  </div>
                  {lead.score !== null && (
                    <div className="text-xs text-neutral-400">Score: {lead.score}</div>
                  )}
                </div>
                <StatusBadge status={lead.status} />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function PipelineSection() {
  const { data: opportunities } = useQuery<SalesOpportunity[]>({
    queryKey: ["sales", "opportunities"],
    queryFn: () => apiFetch<SalesOpportunity[]>("/api/v1/sales/opportunities"),
  });

  const totalValue = opportunities?.reduce((sum, o) => sum + (o.value ?? 0), 0) ?? 0;

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Pipeline {opportunities && opportunities.length > 0 && `— €${totalValue.toLocaleString()}`}
      </h2>
      {opportunities?.length === 0 && <p className="text-sm text-neutral-500">No opportunities yet.</p>}
      <div className="flex flex-col gap-2">
        {opportunities?.map((opportunity) => (
          <Link key={opportunity.id} href={`/sales/opportunities/${opportunity.id}`}>
            <Card className="transition-colors hover:border-neutral-400">
              <CardContent className="flex items-center justify-between pt-6">
                <div className="font-medium text-neutral-900">{opportunity.title}</div>
                <div className="flex items-center gap-2">
                  {opportunity.value !== null && (
                    <Badge variant="outline">€{opportunity.value.toLocaleString()}</Badge>
                  )}
                  <StatusBadge status={opportunity.stage} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

const SUB_PAGES = [
  { href: "/sales/icp", label: "ICP Builder" },
  { href: "/sales/sequences", label: "Sequences" },
  { href: "/sales/campaigns", label: "Campaigns" },
  { href: "/sales/inbox", label: "Sales Inbox" },
  { href: "/sales/meetings", label: "Meetings" },
];

export default function SalesPage() {
  return (
    <div>
      <PageHeader
        title="Sales"
        description="Accounts, contacts, and pipeline — spec sections 20-29."
        actions={
          <div className="flex flex-wrap gap-2">
            {SUB_PAGES.map((page) => (
              <Link key={page.href} href={page.href}>
                <Button variant="outline" size="sm">
                  {page.label}
                </Button>
              </Link>
            ))}
          </div>
        }
      />
      <IntelligenceSection />
      <AccountsSection />
      <LeadsSection />
      <PipelineSection />
    </div>
  );
}
