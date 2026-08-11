import Link from "next/link";
import { ShieldCheck, Sparkles } from "lucide-react";

import { HeroVisual } from "@/components/marketing/hero-visual";
import { Button } from "@/components/ui/button";

/** The brand's own composition, used as the page's opening statement: two
 * arcs of ambient light (teal left, blue right) meeting around a warm
 * center, exactly the relationship the mark draws. Everything here is
 * decorative and sits behind the content — the headline stays real text
 * with real contrast, never baked into the gradient. */
export function HeroSection() {
  return (
    <section className="relative isolate overflow-hidden bg-[var(--bg-app)]">
      <div
        aria-hidden="true"
        className="brand-aurora pointer-events-none absolute inset-x-0 -top-24 h-[46rem]"
      />
      {/* A single hairline of the full brand sweep, closing the hero the way
          the mark's arcs close around the spark. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-[image:var(--gradient-brand)] opacity-60"
      />

      {/* The visual gets the larger share and a negative right margin so it
          runs to the viewport edge: its own left-hand fade is what joins it
          to the copy, and boxing it inside the content gutter would put a
          hard stop where that fade is meant to continue. */}
      <div className="relative mx-auto grid max-w-[var(--content-max-width)] items-center gap-10 px-4 py-20 sm:px-6 lg:grid-cols-[1fr_1.2fr] lg:gap-6 lg:py-28 lg:pl-8 lg:pr-0">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)]/80 px-3 py-1 text-xs font-medium text-[var(--fg-muted)] shadow-[var(--shadow-sm)] backdrop-blur">
            <Sparkles className="h-3.5 w-3.5 text-[var(--brand-spark)]" aria-hidden="true" />
            Governed AI for European SMEs
          </p>

          <h1 className="mt-6 text-[length:var(--text-display-2)] font-semibold leading-[1.06] tracking-tight text-[var(--fg-default)] sm:text-[length:var(--text-display-1)]">
            Run compliance, security, sales, and operations{" "}
            <span className="brand-gradient-text">from one secure AI platform</span>.
          </h1>

          <p className="mt-6 max-w-xl text-lg leading-relaxed text-[var(--fg-muted)]">
            Agora Origin helps European SMEs manage compliance, reduce security risk, find
            customers, support users, and automate daily operations from one intelligent
            workspace.
          </p>

          <div className="mt-9 flex flex-col gap-3 sm:flex-row">
            <Button asChild size="lg">
              <Link href="/signup">Start free</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="/contact">Request a demo</Link>
            </Button>
          </div>

          <p className="mt-7 flex items-start gap-2 text-sm text-[var(--fg-muted)]">
            <ShieldCheck
              className="mt-0.5 h-4 w-4 shrink-0 text-[var(--brand-teal)]"
              aria-hidden="true"
            />
            Designed for growing European businesses that need practical AI with governance,
            visibility, and control.
          </p>
        </div>

        <HeroVisual />
      </div>
    </section>
  );
}
