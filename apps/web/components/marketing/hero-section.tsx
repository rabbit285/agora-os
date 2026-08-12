import Image from "next/image";
import Link from "next/link";
import { ShieldCheck, Sparkles } from "lucide-react";

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
      {/* Above 2xl the 88rem content cap leaves ~250px of gutter on each
          side, which the artwork can use. The text column is pinned to a
          fixed 38rem there rather than sharing the extra proportionally,
          so the headline keeps its four-line break and every additional
          pixel goes to the image.
          Below 2xl the original split is left exactly as it was: there is
          no gutter to spend there, so widening the image could only come
          out of the text column, and taking 60px off it pushed the
          headline from four lines to five at 1280. */}
      <div className="relative mx-auto grid max-w-[var(--content-max-width)] gap-14 px-4 py-20 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:py-28 lg:px-8 2xl:max-w-[96rem] 2xl:grid-cols-[38rem_1fr]">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-[var(--border-default)] bg-[var(--bg-surface)]/80 px-3 py-1 text-xs font-medium text-[var(--fg-muted)] shadow-[var(--shadow-sm)] backdrop-blur">
            <Sparkles className="h-3.5 w-3.5 text-[var(--brand-spark)]" aria-hidden="true" />
            Governed AI for SMEs
          </p>

          <h1 className="mt-6 text-[length:var(--text-display-2)] font-semibold leading-[1.06] tracking-tight text-[var(--fg-default)] sm:text-[length:var(--text-display-1)]">
            Run compliance, security, sales, and operations{" "}
            <span className="brand-gradient-text">from one secure AI platform</span>.
          </h1>

          <p className="mt-6 max-w-xl text-lg leading-relaxed text-[var(--fg-muted)]">
            Veyntra helps SMEs manage compliance, reduce security risk, find
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
            Designed for growing businesses that need practical AI with governance,
            visibility, and control.
          </p>
        </div>

        <div className="relative">
          {/* A soft echo of the mark behind the product shot, so the preview
              sits in the same light the headline does. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -inset-8 rounded-[2rem] bg-[radial-gradient(60%_60%_at_50%_40%,var(--aurora-blue),transparent_70%)] blur-2xl"
          />
          <div className="relative">
            <Image
              src="/images/hero-workspace.png"
              alt="Teams across compliance, security, sales, and customer support working from shared dashboards"
              width={1536}
              height={1024}
              // Largest element above the fold, so it is the likely LCP
              // candidate — eager rather than lazy.
              priority
              sizes="(max-width: 1024px) 100vw, 54vw"
              // No corner radius and no frame: roughly half the artwork is
              // transparent, so it blends into the hero on its own and a
              // rounded edge would have nothing to round.
              className="h-auto w-full"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
