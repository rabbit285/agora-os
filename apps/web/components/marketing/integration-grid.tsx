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
// CRM, helpdesk and sales-data connectors are deliberately absent: they
// fed the sales and support modules, which are no longer part of the
// product. Listing a connector for a module a customer cannot reach
// would be advertising a capability that does not exist.
const INTEGRATIONS: Integration[] = [
  { name: "Google", category: "Drive, mail, calendar", status: "requires-configuration" },
  { name: "Microsoft", category: "SharePoint, mail, calendar", status: "requires-configuration" },
  { name: "GitHub", category: "Engineering evidence", status: "requires-configuration" },
  { name: "Slack", category: "Notifications", status: "requires-configuration" },
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
