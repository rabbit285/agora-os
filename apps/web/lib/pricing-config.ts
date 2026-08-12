/** The one place display copy for pricing lives (docs/PUBLIC_SITE_DESIGN.md §5).
 * Plan names and entitlement values are never hardcoded here — both the
 * homepage's PricingPreview and the full /pricing page fetch the real,
 * public GET /api/v1/billing/plans for those. This file only supplies the
 * marketing framing (price, tagline, what each tier is *for*, which
 * entitlements to headline) for each of the four real plan keys.
 *
 * These are list prices, not what the system charges: there is no payment
 * collection in this build (see docs/KNOWN_LIMITATIONS.md and the note on
 * `app.routers.billing.update_current_plan`). Showing a price while the
 * product cannot take one is a deliberate, reversible marketing decision;
 * the number must not be read anywhere as evidence that billing works.
 */

export type PricingPlanCopy = {
  key: "starter" | "growth" | "business" | "enterprise";
  priceLabel: string;
  /** Shown next to the price — "/month", or a qualifier like "from". */
  priceSuffix?: string;
  /** A short badge above the plan name, e.g. the trial offer. */
  badge?: string;
  tagline: string;
  /** What the tier is actually for, in one line. */
  summary: string;
  ctaLabel: string;
  ctaHref: string;
  highlightEntitlements: string[];
  featured?: boolean;
};

export const PRICING_PLAN_COPY: PricingPlanCopy[] = [
  {
    key: "starter",
    priceLabel: "€499",
    priceSuffix: "/month",
    badge: "14-day free trial",
    tagline: "AI Compliance core, with limited users and usage.",
    summary: "Start with a free trial — no card required until it ends.",
    ctaLabel: "Start free trial",
    ctaHref: "/signup",
    highlightEntitlements: ["max_users", "max_documents", "max_storage_gb", "max_frameworks"],
  },
  {
    key: "growth",
    priceLabel: "€999",
    priceSuffix: "/month",
    tagline: "Compliance, Automation, and Security together.",
    summary: "For teams ready to connect SSO and automate their own workflows.",
    ctaLabel: "Start free trial",
    ctaHref: "/signup",
    highlightEntitlements: ["max_users", "sso_enabled", "api_enabled", "max_integrations"],
    featured: true,
  },
  {
    key: "business",
    priceLabel: "€1,999",
    priceSuffix: "/month",
    tagline: "The full platform, with Sales and Support.",
    summary: "Higher limits, every integration, custom frameworks, and SCIM.",
    ctaLabel: "Contact sales",
    ctaHref: "/contact",
    highlightEntitlements: [
      "max_users",
      "scim_enabled",
      "custom_frameworks_enabled",
      "advanced_reporting_enabled",
    ],
  },
  {
    key: "enterprise",
    priceLabel: "€3,500+",
    priceSuffix: "/month",
    tagline: "Custom scale, with an SLA and dedicated support.",
    summary: "Advanced RBAC, custom integrations, data residency, and agency support.",
    ctaLabel: "Contact sales",
    ctaHref: "/contact",
    highlightEntitlements: [
      "data_residency_enabled",
      "trust_center_enabled",
      "sso_enabled",
      "scim_enabled",
    ],
  },
];
