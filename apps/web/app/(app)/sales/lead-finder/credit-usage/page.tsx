"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { DataTable, type DataTableColumn } from "@/components/data-table";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { apiFetch } from "@/lib/api";
import type { CreditUsageSummaryOut, Membership, ProviderStatusOut } from "@/lib/types";

const OPERATIONS = [
  "search_companies",
  "search_people",
  "enrich_company",
  "enrich_person",
  "find_decision_makers",
];

/** Credit-usage dashboard (spec: organization/user/provider/operation/
 * estimate/actual/date filters). Organization scope is the tenant
 * boundary itself, not a selectable filter — every row here is already
 * this organization's own usage; a cross-org selector would be a
 * tenant-isolation bug, not a feature (see
 * app.routers.sales_lead_finder.credit_usage_dashboard). */
export default function CreditUsagePage() {
  const [provider, setProvider] = useState("");
  const [operation, setOperation] = useState("");
  const [userId, setUserId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const { data: providers } = useQuery<ProviderStatusOut[]>({
    queryKey: ["sales", "lead-finder", "providers"],
    queryFn: () => apiFetch<ProviderStatusOut[]>("/api/v1/sales/lead-finder/providers"),
  });

  const { data: members } = useQuery<Membership[]>({
    queryKey: ["organizations", "current", "members"],
    queryFn: () => apiFetch<Membership[]>("/api/v1/organizations/current/members"),
  });

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (provider) params.set("provider", provider);
    if (operation) params.set("operation", operation);
    if (userId) params.set("user_id", userId);
    if (dateFrom) params.set("date_from", new Date(dateFrom).toISOString());
    if (dateTo) params.set("date_to", new Date(dateTo).toISOString());
    return params.toString();
  }, [provider, operation, userId, dateFrom, dateTo]);

  const { data: usage, isLoading, error, refetch } = useQuery<CreditUsageSummaryOut[]>({
    queryKey: ["sales", "lead-finder", "credit-usage", query],
    queryFn: () => apiFetch<CreditUsageSummaryOut[]>(`/api/v1/sales/lead-finder/credit-usage?${query}`),
  });

  const totalEstimated = (usage ?? []).reduce((sum, row) => sum + row.estimated_credits, 0);
  const totalActual = (usage ?? []).reduce((sum, row) => sum + (row.actual_credits ?? 0), 0);
  const hasUnknownActual = (usage ?? []).some((row) => row.actual_credits === null);

  const columns: DataTableColumn<CreditUsageSummaryOut>[] = [
    {
      key: "created_at",
      header: "Date",
      render: (row) => new Date(row.created_at).toLocaleString(),
      sortValue: (row) => row.created_at,
    },
    {
      key: "provider",
      header: "Provider",
      render: (row) => <span className="capitalize">{row.provider}</span>,
      sortValue: (row) => row.provider,
    },
    {
      key: "operation",
      header: "Operation",
      render: (row) => row.operation.replace(/_/g, " "),
      sortValue: (row) => row.operation,
    },
    {
      key: "user",
      header: "User",
      render: (row) =>
        row.requested_by_user_id ? (
          <span className="font-mono text-xs text-[var(--fg-muted)]">{row.requested_by_user_id}</span>
        ) : (
          "—"
        ),
    },
    {
      key: "estimated",
      header: "Estimated",
      render: (row) => row.estimated_credits,
      sortValue: (row) => row.estimated_credits,
      align: "right",
    },
    {
      key: "actual",
      header: "Actual",
      // Never fabricated — a provider that doesn't report actual usage
      // stays "Unknown", not a copy of the estimate.
      render: (row) => (row.actual_credits === null ? "Unknown" : row.actual_credits),
      sortValue: (row) => row.actual_credits ?? -1,
      align: "right",
    },
    {
      key: "succeeded",
      header: "Status",
      render: (row) => <Badge variant={row.succeeded ? "success" : "destructive"}>{row.succeeded ? "Succeeded" : "Failed"}</Badge>,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Credit Usage"
        description="Provider credit spend across your organization — estimated vs. actual, never fabricated."
      />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
        <div>
          <Label htmlFor="credit-filter-provider" className="mb-1 block text-xs">
            Provider
          </Label>
          <Select id="credit-filter-provider" value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="">All providers</option>
            {(providers ?? []).map((p) => (
              <option key={p.provider_key} value={p.provider_key}>
                {p.provider_key}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="credit-filter-operation" className="mb-1 block text-xs">
            Operation
          </Label>
          <Select id="credit-filter-operation" value={operation} onChange={(e) => setOperation(e.target.value)}>
            <option value="">All operations</option>
            {OPERATIONS.map((op) => (
              <option key={op} value={op}>
                {op.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="credit-filter-user" className="mb-1 block text-xs">
            User
          </Label>
          <Select id="credit-filter-user" value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">All users</option>
            {(members ?? []).map((m) => (
              <option key={m.id} value={m.user_id}>
                {m.user_id}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="credit-filter-from" className="mb-1 block text-xs">
            From
          </Label>
          <Input
            id="credit-filter-from"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor="credit-filter-to" className="mb-1 block text-xs">
            To
          </Label>
          <Input id="credit-filter-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
      </div>

      {usage && usage.length > 0 && (
        <p className="mb-3 text-xs text-[var(--fg-muted)]">
          {usage.length} record{usage.length === 1 ? "" : "s"} · {totalEstimated} estimated credit
          {totalEstimated === 1 ? "" : "s"} ·{" "}
          {hasUnknownActual ? `${totalActual}+ actual (some providers don't report actual usage)` : `${totalActual} actual`}
        </p>
      )}

      <DataTable
        columns={columns}
        data={usage}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error}
        onRetry={() => refetch()}
        emptyTitle="No credit usage yet"
        emptyDescription="Selective or bulk enrichment spends provider credits — usage will appear here once you run one."
      />
    </div>
  );
}
