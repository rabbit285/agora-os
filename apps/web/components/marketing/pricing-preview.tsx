"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";

import { InteractiveCard } from "@/components/marketing/interactive-card";
import { Button } from "@/components/ui/button";
import { CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import { PRICING_PLAN_COPY } from "@/lib/pricing-config";
import { ENTITLEMENT_LABELS, type Plan } from "@/lib/types";

function formatEntitlement(value: number | boolean | null): string {
  if (typeof value === "boolean") return value ? "Included" : "—";
  if (value === null) return "Unlimited";
  return String(value);
}

/** Real plan names and entitlement values come from the same, already-
 * public GET /api/v1/billing/plans the authenticated billing settings
 * page uses — never hardcoded here. Only the price label and which
 * entitlements to headline come from pricing-config.ts (see
 * docs/PUBLIC_SITE_DESIGN.md §5). */
export function PricingPreview() {
  const { data: plans } = useQuery<Plan[]>({
    queryKey: ["billing", "plans", "public"],
    queryFn: () => apiFetch<Plan[]>("/api/v1/billing/plans"),
  });

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {PRICING_PLAN_COPY.map((copy) => {
        const plan = plans?.find((p) => p.key === copy.key);
        return (
          <InteractiveCard key={copy.key} selected={copy.featured} className="flex flex-col">
            <CardHeader>
              <span className="text-sm font-semibold text-[var(--fg-default)]">
                {plan?.name ?? copy.key}
              </span>
              <span className="text-2xl font-semibold text-[var(--fg-default)]">{copy.priceLabel}</span>
              <p className="text-xs text-[var(--fg-muted)]">{copy.tagline}</p>
            </CardHeader>
            <CardContent className="flex-1 pt-0">
              <ul className="flex flex-col gap-2">
                {copy.highlightEntitlements.map((key) => {
                  const value = plan?.entitlements[key] ?? null;
                  return (
                    <li key={key} className="flex items-center gap-2 text-xs text-[var(--fg-muted)]">
                      <Check className="h-3.5 w-3.5 shrink-0 text-[var(--success-600)]" aria-hidden="true" />
                      <span>
                        {ENTITLEMENT_LABELS[key] ?? key}: {formatEntitlement(value)}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </CardContent>
            <CardFooter>
              <Button asChild className="w-full" variant={copy.featured ? "default" : "outline"}>
                <Link href={copy.ctaHref}>{copy.ctaLabel}</Link>
              </Button>
            </CardFooter>
          </InteractiveCard>
        );
      })}
    </div>
  );
}
