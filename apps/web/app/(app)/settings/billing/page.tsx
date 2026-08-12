"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, Info, Lock } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, apiFetch } from "@/lib/api";
import { PRICING_PLAN_COPY } from "@/lib/pricing-config";
import { ENTITLEMENT_LABELS, type OrganizationPlan, type Plan } from "@/lib/types";

function formatEntitlement(value: number | boolean | null): string {
  if (typeof value === "boolean") return value ? "Included" : "Not included";
  if (value === null) return "Unlimited";
  return String(value);
}

/** Which plans a customer can buy without talking to sales. Mirrors
 * `SELF_SERVE_PAID_PLANS` on the API, which enforces it — this copy only
 * decides which button to draw. */
const SELF_SERVE_PAID = new Set(["growth", "business"]);

export default function BillingSettingsPage() {
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const checkoutResult = searchParams.get("checkout");

  const { data: plans, isLoading: plansLoading } = useQuery<Plan[]>({
    queryKey: ["billing", "plans"],
    queryFn: () => apiFetch<Plan[]>("/api/v1/billing/plans"),
  });

  const { data: current, isLoading: currentLoading } = useQuery<OrganizationPlan>({
    queryKey: ["billing", "current"],
    queryFn: () => apiFetch<OrganizationPlan>("/api/v1/billing/current"),
  });

  // Stripe redirects back here the moment the customer finishes paying,
  // but the plan is granted by the webhook — which may land a beat later.
  // Refetching on return avoids showing a stale "Starter" to someone who
  // just paid.
  useEffect(() => {
    if (checkoutResult === "success") {
      void queryClient.invalidateQueries({ queryKey: ["billing", "current"] });
    }
  }, [checkoutResult, queryClient]);

  const startCheckout = useMutation({
    mutationFn: (plan_key: string) =>
      apiFetch<{ checkout_url: string }>("/api/v1/billing/checkout", {
        method: "POST",
        body: { plan_key },
      }),
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
  });

  const openPortal = useMutation({
    mutationFn: () =>
      apiFetch<{ portal_url: string }>("/api/v1/billing/portal", { method: "POST" }),
    onSuccess: (data) => {
      window.location.href = data.portal_url;
    },
  });

  const downgrade = useMutation({
    mutationFn: () =>
      apiFetch<OrganizationPlan>("/api/v1/billing/current", {
        method: "PUT",
        body: { plan_key: "starter" },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["billing", "current"] }),
  });

  const subscription = current?.subscription ?? null;
  const isLocked = subscription?.access_state === "locked";
  const paymentsConfigured = subscription?.payments_configured ?? false;
  const actionError = startCheckout.error ?? openPortal.error ?? downgrade.error;

  return (
    <div>
      <PageHeader
        title="Billing & Plans"
        description="Your plan, what it includes, and how it is paid for. Card details are handled by Stripe and never touch Agora Origin."
      />

      {(plansLoading || currentLoading) && (
        <p className="text-sm text-[var(--fg-muted)]">Loading…</p>
      )}

      {checkoutResult === "cancelled" && (
        <div className="mb-6 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <p className="text-sm text-[var(--fg-muted)]">
            Checkout was cancelled — no payment was taken and your plan has not changed.
          </p>
        </div>
      )}

      {/* The upgrade screen a lapsed trial lands on. Deliberately loud:
          the account still works for reading and exporting, so without
          this the customer would just find things quietly failing. */}
      {isLocked && (
        <div className="mb-6 rounded-[var(--radius-lg)] border border-[var(--critical-500)]/35 bg-[var(--critical-50)] p-6">
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--critical-700)]">
            <Lock className="h-4 w-4 shrink-0" aria-hidden="true" />
            {subscription?.status === "canceled"
              ? "Your subscription has ended"
              : "Your free trial has ended"}
          </p>
          <p className="mt-2 text-sm leading-relaxed text-[var(--critical-700)]">
            Your organization and everything in it has been kept exactly as you left it, and you can
            still sign in, read, and export your data. Creating new work and premium features are
            paused until you choose a plan.
          </p>
        </div>
      )}

      {subscription?.access_state === "trialing" && (
        <div className="mb-6 rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-5">
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--fg-default)]">
            <Info className="h-4 w-4 shrink-0 text-[var(--brand-primary)]" aria-hidden="true" />
            {subscription.trial_days_remaining === 0
              ? "Your trial ends today"
              : `${subscription.trial_days_remaining} days left in your free trial`}
          </p>
          <p className="mt-2 text-sm leading-relaxed text-[var(--fg-muted)]">
            No card is on file. When the trial ends, your data stays put — premium functionality
            pauses until you pick a plan.
          </p>
        </div>
      )}

      {subscription?.access_state === "past_due" && (
        <div className="mb-6 rounded-[var(--radius-lg)] border border-[var(--warning-500)]/35 bg-[var(--warning-50)] p-5">
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--warning-700)]">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            We could not take your last payment
          </p>
          <p className="mt-2 text-sm leading-relaxed text-[var(--warning-700)]">
            Your plan is still active while we retry. Updating your card now avoids any
            interruption.
          </p>
          <Button className="mt-4" size="sm" onClick={() => openPortal.mutate()}>
            Update payment method
          </Button>
        </div>
      )}

      {current && (
        <Card className="mb-6 max-w-md">
          <CardContent className="flex flex-col gap-1 pt-6">
            <p className="text-sm text-[var(--fg-muted)]">
              Current plan:{" "}
              <span className="font-medium text-[var(--fg-default)]">
                {plans?.find((p) => p.key === current.plan_key)?.name ?? current.plan_key}
              </span>
            </p>
            <p className="text-xs text-[var(--fg-subtle)]">
              {current.current_users} user{current.current_users === 1 ? "" : "s"} active
            </p>
            {subscription?.cancel_at_period_end && subscription.current_period_end && (
              <p className="mt-1 text-xs text-[var(--warning-700)]">
                Cancels on {new Date(subscription.current_period_end).toLocaleDateString()} — you
                keep everything until then.
              </p>
            )}
            {subscription?.tax_id && (
              <p className="mt-1 text-xs text-[var(--fg-subtle)]">VAT {subscription.tax_id}</p>
            )}
            {subscription?.has_payment_method && (
              <Button
                className="mt-3 self-start"
                size="sm"
                variant="outline"
                disabled={openPortal.isPending}
                onClick={() => openPortal.mutate()}
              >
                Manage payment & invoices
                <ExternalLink className="ml-1.5 h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Never let an upgrade button lead somewhere that cannot take a
          payment — say so instead. */}
      {current && !paymentsConfigured && (
        <div className="mb-6 max-w-2xl rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
          <p className="text-sm text-[var(--fg-muted)]">
            Online payment is not configured on this deployment, so upgrades cannot be completed
            here yet. <Link href="/contact" className="underline">Contact us</Link> to arrange a
            plan.
          </p>
        </div>
      )}

      {actionError && (
        <p className="mb-4 text-sm text-[var(--critical-600)]">
          {actionError instanceof ApiError ? actionError.message : "Something went wrong."}
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {plans?.map((plan) => {
          const isCurrent = current?.plan_key === plan.key;
          const copy = PRICING_PLAN_COPY.find((c) => c.key === plan.key);
          const isPaid = SELF_SERVE_PAID.has(plan.key);
          const isEnterprise = plan.key === "enterprise";
          return (
            <Card
              key={plan.key}
              className={isCurrent ? "border-[var(--brand-primary)]" : undefined}
            >
              <CardContent className="flex h-full flex-col gap-3 pt-6">
                <div className="flex items-center justify-between">
                  <h3 className="font-medium text-[var(--fg-default)]">{plan.name}</h3>
                  {isCurrent && <Badge>Current</Badge>}
                </div>
                {copy && (
                  <p className="flex items-baseline gap-1">
                    <span className="text-2xl font-semibold tracking-tight text-[var(--fg-default)]">
                      {copy.priceLabel}
                    </span>
                    <span className="text-xs text-[var(--fg-muted)]">{copy.priceSuffix}</span>
                  </p>
                )}
                <ul className="flex flex-1 flex-col gap-1 text-xs text-[var(--fg-muted)]">
                  {Object.entries(plan.entitlements).map(([key, value]) => (
                    <li key={key} className="flex justify-between gap-2">
                      <span>{ENTITLEMENT_LABELS[key] ?? key}</span>
                      <span className="font-mono text-[var(--fg-default)]">
                        {formatEntitlement(value)}
                      </span>
                    </li>
                  ))}
                </ul>
                {!isCurrent && isEnterprise && (
                  <Button size="sm" variant="outline" asChild>
                    <Link href="/contact">Contact sales</Link>
                  </Button>
                )}
                {!isCurrent && isPaid && (
                  <Button
                    size="sm"
                    disabled={startCheckout.isPending || !paymentsConfigured}
                    onClick={() => startCheckout.mutate(plan.key)}
                  >
                    {startCheckout.isPending ? "Redirecting…" : `Upgrade to ${plan.name}`}
                  </Button>
                )}
                {!isCurrent && plan.key === "starter" && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={downgrade.isPending}
                    onClick={() => downgrade.mutate()}
                  >
                    Downgrade to Starter
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <p className="mt-6 max-w-2xl text-xs leading-relaxed text-[var(--fg-subtle)]">
        Prices exclude VAT. Stripe calculates the VAT for your location at checkout, and applies
        B2B reverse charge where your VAT number makes it applicable.
      </p>
    </div>
  );
}
