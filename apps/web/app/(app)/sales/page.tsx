"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Sales Intelligence
        </h2>
        <Button size="sm" variant="outline" disabled={findLeads.isPending} onClick={() => findLeads.mutate()}>
          {findLeads.isPending ? "Finding…" : "Run Lead Finder"}
        </Button>
      </div>
      {findLeads.data && (
        <p className="mb-3 text-xs text-[var(--fg-muted)]">
          Considered {findLeads.data.candidates_considered} account(s); created{" "}
          {findLeads.data.created_leads.length} new lead(s).
        </p>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricCard label="Win Rate" value={`${intelligence.win_rate_percent}%`} />
        <MetricCard
          label="Avg Deal Size"
          value={`€${intelligence.average_deal_size.toLocaleString()}`}
        />
        <MetricCard
          label="Sequence Completion"
          value={`${intelligence.sequence_completion_rate_percent}%`}
        />
        <MetricCard
          label="Top ICP Accounts"
          value={String(intelligence.top_accounts_by_icp_score.length)}
        />
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
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  const { data: accounts, isLoading, error, refetch } = useQuery<SalesAccount[]>({
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

  const columns: DataTableColumn<SalesAccount>[] = [
    {
      key: "name",
      header: "Account",
      render: (account) => (
        <div className="flex flex-col">
          <span className="font-medium">{account.name}</span>
          {account.industry && (
            <span className="text-xs text-[var(--fg-subtle)]">{account.industry}</span>
          )}
        </div>
      ),
      sortValue: (account) => account.name.toLowerCase(),
    },
    {
      key: "icp_score",
      header: "ICP Score",
      render: (account) =>
        account.icp_score !== null ? <Badge variant="outline">ICP {account.icp_score}</Badge> : "—",
      sortValue: (account) => account.icp_score ?? -1,
    },
    {
      key: "status",
      header: "Status",
      render: (account) => <StatusBadge status={account.status} />,
    },
  ];

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Accounts
      </h2>
      <div className="mb-4 flex gap-2">
        <Input
          placeholder="New account name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && name.trim()) createAccount.mutate(name.trim());
          }}
          className="max-w-sm"
        />
        <Button disabled={!name.trim() || createAccount.isPending} onClick={() => createAccount.mutate(name.trim())}>
          Add account
        </Button>
      </div>
      <DataTable
        columns={columns}
        data={accounts}
        getRowId={(account) => account.id}
        onRowClick={(account) => router.push(`/sales/accounts/${account.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No accounts yet"
      />
    </div>
  );
}

function LeadsSection() {
  const router = useRouter();
  const { data: leads, isLoading, error, refetch } = useQuery<SalesLead[]>({
    queryKey: ["sales", "leads"],
    queryFn: () => apiFetch<SalesLead[]>("/api/v1/sales/leads"),
  });

  const columns: DataTableColumn<SalesLead>[] = [
    {
      key: "source",
      header: "Lead",
      render: (lead) => <span className="font-medium">{lead.source ?? "Unknown source"}</span>,
      sortValue: (lead) => lead.source ?? "",
    },
    {
      key: "score",
      header: "Score",
      render: (lead) => (lead.score !== null ? lead.score : "—"),
      sortValue: (lead) => lead.score ?? -1,
    },
    {
      key: "status",
      header: "Status",
      render: (lead) => <StatusBadge status={lead.status} />,
    },
  ];

  return (
    <div className="mb-8">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Leads
      </h2>
      <DataTable
        columns={columns}
        data={leads}
        getRowId={(lead) => lead.id}
        onRowClick={(lead) => router.push(`/sales/leads/${lead.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No leads yet"
      />
    </div>
  );
}

function PipelineSection() {
  const router = useRouter();
  const { data: opportunities, isLoading, error, refetch } = useQuery<SalesOpportunity[]>({
    queryKey: ["sales", "opportunities"],
    queryFn: () => apiFetch<SalesOpportunity[]>("/api/v1/sales/opportunities"),
  });

  const totalValue = opportunities?.reduce((sum, o) => sum + (o.value ?? 0), 0) ?? 0;

  const columns: DataTableColumn<SalesOpportunity>[] = [
    {
      key: "title",
      header: "Opportunity",
      render: (opportunity) => <span className="font-medium">{opportunity.title}</span>,
      sortValue: (opportunity) => opportunity.title.toLowerCase(),
    },
    {
      key: "value",
      header: "Value",
      render: (opportunity) =>
        opportunity.value !== null ? `€${opportunity.value.toLocaleString()}` : "—",
      sortValue: (opportunity) => opportunity.value ?? 0,
    },
    {
      key: "stage",
      header: "Stage",
      render: (opportunity) => <StatusBadge status={opportunity.stage} />,
    },
  ];

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
        Pipeline {opportunities && opportunities.length > 0 && `— €${totalValue.toLocaleString()}`}
      </h2>
      <DataTable
        columns={columns}
        data={opportunities}
        getRowId={(opportunity) => opportunity.id}
        onRowClick={(opportunity) => router.push(`/sales/opportunities/${opportunity.id}`)}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No opportunities yet"
      />
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
        description="Accounts, contacts, and pipeline."
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
