import type { Metadata } from "next";
import Link from "next/link";
import { Info } from "lucide-react";

import { PageHero } from "@/components/marketing/page-hero";
import { PricingPreview } from "@/components/marketing/pricing-preview";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Pricing — Agora Origin",
  description: "Simple plans that grow with you — from a free workspace to enterprise-scale governance.",
  alternates: { canonical: "/pricing" },
};

export default function PricingPage() {
  return (
    <div>
      <PageHero
        eyebrow="Pricing"
        title="Simple plans that"
        accent="grow with you"
        description="Every plan includes the full platform — plans differ by scale and by the governance features larger teams need. Start with a 14-day free trial."
      />

      <div className="mx-auto max-w-[var(--content-max-width)] px-4 pb-24 sm:px-6 lg:px-8">
        <PricingPreview />

        {/* Kept visible rather than set as fine print: these are the terms
            a reader needs before they can act on a price. */}
        <div className="mx-auto mt-12 max-w-3xl rounded-[var(--radius-lg)] border border-[var(--border-default)] bg-[var(--bg-surface)] p-6">
          <p className="flex items-center gap-2 text-sm font-semibold text-[var(--fg-default)]">
            <Info className="h-4 w-4 shrink-0 text-[var(--brand-primary)]" aria-hidden="true" />
            How pricing works
          </p>
          <p className="mt-2 text-sm leading-relaxed text-[var(--fg-muted)]">
            Listed prices are per organization, per month, excluding VAT. Every plan starts with a
            14-day free trial and no card is required to begin. Enterprise starts at €3,500 and is
            scoped per organization — talk to sales for a quote.
          </p>
          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <Button asChild>
              <Link href="/signup">Start free</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/contact">Talk to sales</Link>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
