import Link from "next/link";

import { LogoMark } from "@/components/logo";
import { Button } from "@/components/ui/button";

/** The mark reads strongest on a dark ground — its arcs glow rather than
 * sit flat — so the closing panel is where the brand gets its fullest
 * statement: the mark itself, lit by the same two-lobe wash the hero uses. */
export function FinalCTA() {
  return (
    <section className="relative isolate overflow-hidden border-t border-[var(--border-default)] bg-[var(--gray-900)]">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(34rem_22rem_at_18%_0%,rgba(45,212,191,0.22),transparent_70%),radial-gradient(32rem_22rem_at_82%_10%,rgba(96,165,250,0.24),transparent_70%),radial-gradient(18rem_12rem_at_50%_-4%,rgba(251,191,36,0.14),transparent_72%)]"
      />

      <div className="relative mx-auto max-w-3xl px-4 py-24 text-center sm:px-6 lg:px-8">
        <LogoMark size={56} className="mx-auto" idSuffix="final-cta" />
        <h2 className="mt-8 text-[length:var(--text-3xl)] font-semibold tracking-tight text-white">
          Bring your compliance, security, sales, and operations into one intelligent workspace.
        </h2>
        <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
          <Button asChild size="lg">
            <Link href="/signup">Start free</Link>
          </Button>
          <Button
            asChild
            size="lg"
            variant="outline"
            className="border-[var(--gray-700)] bg-transparent text-white hover:bg-[var(--gray-800)]"
          >
            <Link href="/contact">Book a demo</Link>
          </Button>
        </div>
      </div>
    </section>
  );
}
