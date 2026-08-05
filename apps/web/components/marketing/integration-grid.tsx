import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

type IntegrationStatus = "available" | "coming-soon" | "requires-configuration";

type Integration = { name: string; category: string; status: IntegrationStatus };

/** All nine listed here have real, complete OAuth/REST adapter code in the
 * backend (docs/PUBLIC_SITE_AUDIT.md §8) — none is a stub or vaporware, so
 * all are honestly "Available." None is marked "Coming soon," since that
 * would undersell real, finished work; "requires-configuration" is used
 * only where connecting genuinely needs an admin step first (true of every
 * OAuth connector here, which is normal integration UX, not a deficiency
 * — shown as a status label rather than omitted so it isn't misread as
 * "already connected"). */
const INTEGRATIONS: Integration[] = [
  { name: "HubSpot", category: "CRM", status: "requires-configuration" },
  { name: "Salesforce", category: "CRM", status: "requires-configuration" },
  { name: "Pipedrive", category: "CRM", status: "requires-configuration" },
  { name: "Google", category: "Calendar, mail, drive", status: "requires-configuration" },
  { name: "Microsoft", category: "Calendar, mail", status: "requires-configuration" },
  { name: "GitHub", category: "Engineering", status: "requires-configuration" },
  { name: "Slack", category: "Communication", status: "requires-configuration" },
  { name: "Intercom", category: "Customer support", status: "requires-configuration" },
  { name: "Apollo", category: "Sales data", status: "requires-configuration" },
];

const STATUS_LABEL: Record<IntegrationStatus, string> = {
  available: "Available",
  "coming-soon": "Coming soon",
  "requires-configuration": "Requires configuration",
};

const STATUS_VARIANT: Record<IntegrationStatus, "success" | "secondary" | "info"> = {
  available: "success",
  "coming-soon": "secondary",
  "requires-configuration": "info",
};

export function IntegrationGrid() {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {INTEGRATIONS.map((integration) => (
        <Card key={integration.name} className="flex flex-col gap-2 p-4">
          <span className="text-sm font-semibold text-[var(--fg-default)]">{integration.name}</span>
          <span className="text-xs text-[var(--fg-muted)]">{integration.category}</span>
          <Badge variant={STATUS_VARIANT[integration.status]} className="w-fit">
            {STATUS_LABEL[integration.status]}
          </Badge>
        </Card>
      ))}
    </div>
  );
}
