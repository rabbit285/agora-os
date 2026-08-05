"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { ENTITLEMENT_LABELS, type OrganizationPlan, type Plan } from "@/lib/types";

function formatEntitlement(value: number | boolean | null): string {
  if (typeof value === "boolean") return value ? "Included" : "Not included";
  if (value === null) return "Unlimited";
  return String(value);
}

export default function BillingSettingsPage() {
  const queryClient = useQueryClient();

  const { data: plans, isLoading: plansLoading } = useQuery<Plan[]>({
    queryKey: ["billing", "plans"],
    queryFn: () => apiFetch<Plan[]>("/api/v1/billing/plans"),
  });

  const { data: current, isLoading: currentLoading } = useQuery<OrganizationPlan>({
    queryKey: ["billing", "current"],
    queryFn: () => apiFetch<OrganizationPlan>("/api/v1/billing/current"),
  });

  const setPlan = useMutation({
    mutationFn: (plan_key: string) =>
      apiFetch<OrganizationPlan>("/api/v1/billing/current", {
        method: "PUT",
        body: { plan_key },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["billing", "current"] }),
  });

  return (
    <div>
      <PageHeader
        title="Billing & Plans"
        description="spec §64 — real plans and real entitlement enforcement across the product. No payment
          collection exists in this build (disclosed in docs/KNOWN_LIMITATIONS.md): changing your plan
          here is immediate and free, a direct self-service action rather than a checkout flow."
      />

      {(plansLoading || currentLoading) && <p className="text-sm text-[var(--fg-muted)]">Loading…</p>}

      {current && (
        <Card className="mb-6 max-w-md">
          <CardContent className="pt-6">
            <p className="text-sm text-[var(--fg-muted)]">
              Current plan: <span className="font-medium text-[var(--fg-default)]">{current.plan_key}</span>
            </p>
            <p className="text-xs text-[var(--fg-subtle)]">
              {current.current_users} user{current.current_users === 1 ? "" : "s"} active
            </p>
          </CardContent>
        </Card>
      )}

      {setPlan.isError && (
        <p className="mb-4 text-sm text-[var(--critical-600)]">
          {setPlan.error instanceof ApiError ? setPlan.error.message : "Could not change plan."}
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {plans?.map((plan) => {
          const isCurrent = current?.plan_key === plan.key;
          return (
            <Card key={plan.key} className={isCurrent ? "border-[var(--brand-primary)]" : undefined}>
              <CardContent className="flex flex-col gap-3 pt-6">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium text-[var(--fg-default)]">{plan.name}</h3>
                  {isCurrent && <Badge>Current</Badge>}
                </div>
                <ul className="flex flex-col gap-1 text-xs text-[var(--fg-muted)]">
                  {Object.entries(plan.entitlements).map(([key, value]) => (
                    <li key={key} className="flex justify-between gap-2">
                      <span>{ENTITLEMENT_LABELS[key] ?? key}</span>
                      <span className="font-mono text-[var(--fg-default)]">{formatEntitlement(value)}</span>
                    </li>
                  ))}
                </ul>
                {!isCurrent && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={setPlan.isPending}
                    onClick={() => setPlan.mutate(plan.key)}
                  >
                    Switch to {plan.name}
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
