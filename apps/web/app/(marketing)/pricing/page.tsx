import type { Metadata } from "next";

import { PricingPreview } from "@/components/marketing/pricing-preview";
import { SectionHeader } from "@/components/marketing/section-header";

export const metadata: Metadata = {
  title: "Pricing — Agora Origin",
  description: "Simple plans that grow with you — from a free workspace to enterprise-scale governance.",
  alternates: { canonical: "/pricing" },
};

export default function PricingPage() {
  return (
    <div className="mx-auto max-w-[var(--content-max-width)] px-4 py-16 sm:px-6 lg:px-8">
      <SectionHeader
        eyebrow="Pricing"
        title="Simple plans that grow with you"
        description="Start free. Every plan includes the full platform — plans differ by scale and by the governance features larger teams need."
      />
      <div className="mt-14">
        <PricingPreview />
      </div>
      <p className="mx-auto mt-10 max-w-2xl text-center text-xs text-[var(--fg-subtle)]">
        Prices for Growth, Business, and Enterprise are set per organization based on scale and
        requirements — contact sales for a quote. No payment details are required to start on the
        Starter plan.
      </p>
    </div>
  );
}
