"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Policy } from "@/lib/types";

export default function SecurityPoliciesPage() {
  const { data: policies, isLoading } = useQuery<Policy[]>({
    queryKey: ["compliance", "policies"],
    queryFn: () => apiFetch<Policy[]>("/api/v1/compliance/policies"),
  });

  return (
    <div>
      <PageHeader
        title="Security Policies"
        description="Published and draft policies — the same policy library maintained in Compliance (spec §12/§13), viewed here in a security context."
      />
      {isLoading && <p className="text-sm text-[var(--fg-muted)]">Loading policies…</p>}
      {policies?.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">
          No policies yet.{" "}
          <Link href="/compliance" className="underline">
            Create one in Compliance
          </Link>
          .
        </p>
      )}
      <div className="flex flex-col gap-2">
        {policies?.map((policy) => (
          <Card key={policy.id}>
            <CardContent className="flex items-center justify-between pt-6">
              <div className="font-medium text-[var(--fg-default)]">{policy.title}</div>
              <StatusBadge status={policy.status} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
