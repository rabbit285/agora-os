/** The one place display copy for pricing lives (docs/PUBLIC_SITE_DESIGN.md §5).
 * Plan names and entitlement values are never hardcoded here — both the
 * homepage's PricingPreview and the full /pricing page fetch the real,
 * public GET /api/v1/billing/plans for those. This file only supplies the
 * marketing framing (tagline, price label, which entitlements to headline)
 * for each of the four real plan keys, so there is exactly one place to
 * change if that framing ever needs to.
 *
 * No plan has a real euro figure anywhere in the system (see
 * docs/PUBLIC_SITE_AUDIT.md §3) — Starter is "Free" (org creation genuinely
 * has no payment step today, and it matches the hero's "Start free" CTA);
 * the rest are "Contact sales", the brief's own specified fallback for
 * unfinalized pricing. Nothing here is a number this effort invented. */

export type PricingPlanCopy = {
  key: "starter" | "growth" | "business" | "enterprise";
  priceLabel: string;
  tagline: string;
  ctaLabel: string;
  ctaHref: string;
  highlightEntitlements: string[];
  featured?: boolean;
};

export const PRICING_PLAN_COPY: PricingPlanCopy[] = [
  {
    key: "starter",
    priceLabel: "Free",
    tagline: "Get a governed workspace running in minutes.",
    ctaLabel: "Start free",
    ctaHref: "/signup",
    highlightEntitlements: ["max_users", "max_documents", "max_storage_gb", "max_frameworks"],
  },
  {
    key: "growth",
    priceLabel: "Contact sales",
    tagline: "For teams ready to connect SSO and their own tools.",
    ctaLabel: "Contact sales",
    ctaHref: "/contact",
    highlightEntitlements: ["max_users", "sso_enabled", "api_enabled", "max_integrations"],
    featured: true,
  },
  {
    key: "business",
    priceLabel: "Contact sales",
    tagline: "Custom frameworks, advanced reporting, and SCIM provisioning.",
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
    priceLabel: "Contact sales",
    tagline: "Unlimited scale with data residency and dedicated support.",
    ctaLabel: "Contact sales",
    ctaHref: "/contact",
    highlightEntitlements: ["data_residency_enabled", "trust_center_enabled", "sso_enabled", "scim_enabled"],
  },
];
