import { Sparkles } from "lucide-react";

import { RiskBadge } from "@/components/risk-badge";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { Approval } from "@/lib/types";

/** Risk/requester/decide UI for a single Approval — reused on the
 * Approval Center list and wherever an Approval is shown inline on an
 * entity detail page (AI System, DPIA, Security review, ...). */
export function ApprovalPanel({
  approval,
  onApprove,
  onReject,
  isDeciding,
}: {
  approval: Approval;
  onApprove?: () => void;
  onReject?: () => void;
  isDeciding?: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-5">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-[var(--fg-default)]">
              {approval.action_type}
            </span>
            {approval.module && <Badge variant="outline">{approval.module}</Badge>}
            <RiskBadge riskClass={approval.risk_class} />
            <StatusBadge status={approval.status} />
            {approval.ai_generated && (
              <Badge variant="ai" className="gap-1">
                <Sparkles className="h-3 w-3" aria-hidden="true" />
                AI-generated
              </Badge>
            )}
          </div>
          {approval.due_at && (
            <p className="mt-1 text-xs text-[var(--fg-subtle)]">
              Due {new Date(approval.due_at).toLocaleDateString()}
            </p>
          )}
        </div>
        {approval.status === "pending" && (onApprove || onReject) && (
          <div className="flex gap-2">
            {onReject && (
              <Button variant="outline" size="sm" disabled={isDeciding} onClick={onReject}>
                Reject
              </Button>
            )}
            {onApprove && (
              <Button size="sm" disabled={isDeciding} onClick={onApprove}>
                Approve
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
