/** The one place display copy for pricing lives (docs/PUBLIC_SITE_DESIGN.md §5).
 * Plan names and entitlement values are never hardcoded here — both the
 * homepage's PricingPreview and the full /pricing page fetch the real,
 * public GET /api/v1/billing/plans for those. This file only supplies the
 * marketing framing (price, tagline, what each tier is *for*, which
 * entitlements to headline) for each of the four real plan keys.
 *
 * These prices are real: Growth and Business are charged through Stripe
 * Checkout (see docs/BILLING_ARCHITECTURE.md). Keep the CTA labels honest
 * about which plans include a trial — only Starter does. Promising a free
 * trial on a plan whose checkout asks for a card immediately is the kind
 * of mismatch that gets a signup abandoned at the payment form.
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
    summary: "Try it for 14 days with no card. Your data stays if you don't continue.",
    ctaLabel: "Start free trial",
    ctaHref: "/signup",
    highlightEntitlements: ["max_users", "max_documents", "max_storage_gb", "max_frameworks"],
  },
  {
    key: "growth",
    priceLabel: "€999",
    priceSuffix: "/month",
    tagline: "More frameworks, more documents, SSO.",
    summary: "For teams running several frameworks at once and connecting SSO.",
    ctaLabel: "Get started",
    ctaHref: "/signup",
    highlightEntitlements: ["max_users", "sso_enabled", "api_enabled", "max_integrations"],
    featured: true,
  },
  {
    key: "business",
    priceLabel: "€1,999",
    priceSuffix: "/month",
    tagline: "Custom frameworks and advanced reporting.",
    summary: "Higher limits, your own frameworks, advanced reporting, and SCIM.",
    ctaLabel: "Get started",
    ctaHref: "/signup",
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
