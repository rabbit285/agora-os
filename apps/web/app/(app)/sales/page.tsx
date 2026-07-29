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
import type { SalesAccount, SalesOpportunity } from "@/lib/types";

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
          <Card key={opportunity.id}>
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
        ))}
      </div>
    </div>
  );
}

export default function SalesPage() {
  return (
    <div>
      <PageHeader
        title="Sales"
        description="Accounts, contacts, and pipeline — spec sections 20-29."
      />
      <AccountsSection />
      <PipelineSection />
    </div>
  );
}
