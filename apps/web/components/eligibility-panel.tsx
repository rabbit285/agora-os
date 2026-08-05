"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { EligibilityCheckOut } from "@/lib/types";
import { cn } from "@/lib/utils";

const STATUS_META: Record<
  EligibilityCheckOut["status"],
  { label: string; icon: typeof CheckCircle2; className: string }
> = {
  eligible: { label: "Eligible for outreach", icon: CheckCircle2, className: "text-[var(--success-700)]" },
  requires_review: {
    label: "Requires review before outreach",
    icon: AlertTriangle,
    className: "text-[var(--warning-700)]",
  },
  blocked: { label: "Blocked — do not contact", icon: XCircle, className: "text-[var(--critical-700)]" },
  unknown: { label: "Unknown — not enough information", icon: HelpCircle, className: "text-[var(--fg-muted)]" },
};

/** Preview of app.compliance.governance.evaluate_outreach_eligibility for
 * a saved Contact (spec §23: eligible/requires_review/blocked/unknown
 * with reasons). This is a preview only — the authoritative block still
 * happens at send time (app.sales.service.send_outreach_message), so a
 * "requires_review" contact can still be manually messaged; this panel
 * just makes the real reason visible before that happens. */
export function EligibilityPanel({ contactId }: { contactId: string }) {
  const { data, isLoading } = useQuery<EligibilityCheckOut>({
    queryKey: ["sales", "lead-finder", "eligibility", "contact", contactId],
    queryFn: () =>
      apiFetch<EligibilityCheckOut>("/api/v1/sales/lead-finder/eligibility/check", {
        method: "POST",
        body: { contact_id: contactId },
      }),
  });

  if (isLoading || !data) return null;

  const meta = STATUS_META[data.status];
  const Icon = meta.icon;

  return (
    <Card className="mb-6">
      <CardContent className="pt-6">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--fg-muted)]">
          Outreach Eligibility
        </h2>
        <div className={cn("mb-1 flex items-center gap-1.5 text-sm font-medium", meta.className)}>
          <Icon className="h-4 w-4" aria-hidden="true" />
          {meta.label}
        </div>
        {data.reasons.length > 0 && (
          <ul className="mt-1 list-disc pl-5 text-xs text-[var(--fg-muted)]">
            {data.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
