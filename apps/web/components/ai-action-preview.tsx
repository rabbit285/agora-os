import { CheckCircle2, ShieldAlert, Zap } from "lucide-react";

import { RiskBadge } from "@/components/risk-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/** Proposed-action-before-approval card for the Copilot's "Proposed
 * Actions" section — always shows what would happen and whether it needs
 * a human decision first (spec F2: no direct autonomous writes). */
export function AIActionPreview({
  title,
  description,
  riskClass,
  requiresApproval,
  executed,
  auditReference,
  onConfirm,
}: {
  title: string;
  description: string;
  riskClass: "low" | "moderate" | "high" | "critical";
  requiresApproval: boolean;
  executed?: boolean;
  auditReference?: string;
  onConfirm?: () => void;
}) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--ai-100)] bg-white p-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Zap className="h-3.5 w-3.5 text-[var(--ai-600)]" aria-hidden="true" />
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--ai-700)]">
            Proposed action
          </span>
        </div>
        <RiskBadge riskClass={riskClass} />
      </div>
      <p className="text-sm font-medium text-[var(--fg-default)]">{title}</p>
      <p className="mt-0.5 text-xs text-[var(--fg-muted)]">{description}</p>

      {executed ? (
        <div className="mt-2 flex items-center gap-1.5 text-xs text-[var(--success-700)]">
          <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
          Executed{auditReference && ` — audit ref ${auditReference}`}
        </div>
      ) : requiresApproval ? (
        <div className="mt-2 flex items-center gap-1.5">
          <Badge variant="warning" className="gap-1">
            <ShieldAlert className="h-3 w-3" aria-hidden="true" />
            Requires approval
          </Badge>
        </div>
      ) : (
        onConfirm && (
          <Button size="sm" variant="ai" className="mt-2" onClick={onConfirm}>
            Confirm
          </Button>
        )
      )}
    </div>
  );
}
