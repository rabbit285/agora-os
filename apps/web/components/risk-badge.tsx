import { Badge } from "@/components/ui/badge";

const RISK_VARIANTS: Record<string, "secondary" | "success" | "warning" | "destructive"> = {
  read_only: "success",
  low: "secondary",
  moderate: "warning",
  high: "destructive",
  critical: "destructive",
};

const RISK_LABELS: Record<string, string> = {
  read_only: "Read Only",
  low: "Low Risk",
  moderate: "Moderate Risk",
  high: "High Risk",
  critical: "Critical",
};

export function RiskBadge({ riskClass }: { riskClass: string }) {
  return (
    <Badge variant={RISK_VARIANTS[riskClass] ?? "secondary"}>
      {RISK_LABELS[riskClass] ?? riskClass}
    </Badge>
  );
}
