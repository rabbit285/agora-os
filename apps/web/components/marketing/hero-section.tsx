import Link from "next/link";

import { ProductPreview } from "@/components/marketing/product-preview";
import { Button } from "@/components/ui/button";

export function HeroSection() {
  return (
    <section className="relative overflow-hidden bg-[var(--bg-app)]">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[32rem] bg-[radial-gradient(ellipse_60%_50%_at_50%_-10%,var(--brand-primary-subtle),transparent)]"
      />
      <div className="relative mx-auto grid max-w-[var(--content-max-width)] gap-12 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:items-center lg:py-24 lg:px-8">
        <div>
          <h1 className="text-[var(--text-display-2)] font-semibold leading-[1.08] tracking-tight text-[var(--fg-default)] sm:text-[var(--text-display-1)]">
            Run compliance, security, sales, and operations from one secure AI platform.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-[var(--fg-muted)]">
            Agora Origin helps European SMEs manage compliance, reduce security risk, find
            customers, support users, and automate daily operations from one intelligent
            workspace.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button asChild size="lg">
              <Link href="/signup">Start free</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/contact">Request a demo</Link>
            </Button>
          </div>
          <p className="mt-6 text-sm text-[var(--fg-muted)]">
            Designed for growing European businesses that need practical AI with governance,
            visibility, and control.
          </p>
        </div>
        <ProductPreview />
      </div>
    </section>
  );
}
