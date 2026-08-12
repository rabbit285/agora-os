"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";

import { apiFetch } from "@/lib/api";
import type { OrganizationPlan } from "@/lib/types";

/** A locked organization can still sign in, read, and export — that is
 * deliberate (see LOCKED_ENTITLEMENTS on the API). The cost of that
 * choice is that failures would otherwise be silent: buttons would just
 * start returning 402 with no explanation anywhere on screen. This banner
 * is what makes the locked state legible from wherever the user happens
 * to be.
 *
 * Shown only for a lapsed trial or ended subscription, and only outside
 * the billing page itself, which already renders the full upgrade screen.
 * A trial that is merely running does not get a banner on every page —
 * that is nagging, and the billing page already counts the days down.
 */
export function BillingStatusBanner() {
  const pathname = usePathname();

  const { data } = useQuery<OrganizationPlan>({
    queryKey: ["billing", "current"],
    queryFn: () => apiFetch<OrganizationPlan>("/api/v1/billing/current"),
    // Never let a billing lookup failure take down the page it sits on.
    retry: false,
  });

  const subscription = data?.subscription;
  if (!subscription || subscription.access_state !== "locked") return null;
  if (pathname?.startsWith("/settings/billing")) return null;

  const ended = subscription.status === "canceled";

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-[var(--critical-500)]/35 bg-[var(--critical-50)] px-4 py-2.5 sm:px-6"
    >
      <Lock className="h-4 w-4 shrink-0 text-[var(--critical-700)]" aria-hidden="true" />
      <p className="text-sm text-[var(--critical-700)]">
        <span className="font-semibold">
          {ended ? "Your subscription has ended." : "Your free trial has ended."}
        </span>{" "}
        Your data is safe and still readable — creating new work is paused until you choose a plan.
      </p>
      <Link
        href="/settings/billing"
        className="ml-auto shrink-0 text-sm font-semibold text-[var(--critical-700)] underline underline-offset-2"
      >
        Choose a plan
      </Link>
    </div>
  );
}
